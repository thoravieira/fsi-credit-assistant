"""Day 1, hour 1 probe — docs/specs/03-atlas-indexes.md §3.

Nothing else gets built until this passes. Reports, against the real cluster:
  1. Connectivity and server version.
  2. Whether 3 vector search indexes can coexist (throwaway scratch collections).
  3. Whether MongoDBSaver(ttl=...) creates a native TTL index or client-side expiry.
  4. Measured p50/p95 latency of a real $vectorSearch.

All scratch collections created here are dropped before exit.
"""

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.mongodb import MongoDBSaver

from app.config import get_settings
from app.db import get_client
from app.embeddings import get_embeddings

PROBE_COLLECTIONS = [f"_atlas_probe_{i}" for i in range(1, 4)]
CORPUS_COLLECTION = PROBE_COLLECTIONS[0]  # also carries the latency-measurement data
DIMENSIONS = 1024

# Small, domain-flavored scratch corpus — not the real dataset (that's Session 2).
# Only exists to exercise a real $vectorSearch query against a non-trivial candidate set.
SCRATCH_CORPUS = [
    "Cliente solicita financiamento de veículo com renda comprovada.",
    "Análise de crédito para imóvel residencial dentro do SFH.",
    "Comprometimento de renda acima de 30% reprova a proposta.",
    "Histórico de inadimplência nos últimos 12 meses.",
    "Proposta de refinanciamento com LTV acima de 80%.",
    "Cliente autônomo sem comprovação formal de renda.",
    "Score de crédito elevado e relacionamento bancário longo.",
    "Solicitação de aumento de limite para cartão de crédito.",
    "Financiamento de veículo usado com entrada de 20%.",
    "Renegociação de dívida em atraso há mais de 90 dias.",
] * 6  # 60 short docs — enough to give $vectorSearch a real candidate pool


def report_connectivity(client) -> None:
    print("## 1. Connectivity and server version")
    info = client.server_info()
    print(f"Connected. MongoDB server version: {info['version']}")
    print()


def report_index_coexistence_and_latency(db, embeddings) -> None:
    from langchain_mongodb import MongoDBAtlasVectorSearch

    print("## 2. Three vector search indexes coexisting (throwaway scratch collections)")

    stores = []
    for i, name in enumerate(PROBE_COLLECTIONS, start=1):
        coll = db[name]
        if name == CORPUS_COLLECTION:
            vectors = embeddings.embed_documents(SCRATCH_CORPUS)
            coll.insert_many(
                [{"text": t, "embedding": v} for t, v in zip(SCRATCH_CORPUS, vectors)]
            )
        else:
            coll.insert_one({"text": "scratch", "embedding": [0.0] * DIMENSIONS})

        store = MongoDBAtlasVectorSearch(
            collection=coll,
            embedding=embeddings,
            index_name="vector_index",
        )
        t0 = time.perf_counter()
        store.create_vector_search_index(dimensions=DIMENSIONS, wait_until_complete=120)
        elapsed = time.perf_counter() - t0
        print(f"  [{i}/3] {name}: index queryable after {elapsed:.1f}s")
        stores.append((name, coll, store))

    still_present = [
        n for n, c, _ in stores if any(c.list_search_indexes())
    ]
    if len(still_present) == 3:
        print("PASS: all 3 vector search indexes coexist and are queryable on this cluster.")
    else:
        print(f"FAIL: only {len(still_present)}/3 indexes present at end of probe: {still_present}")
    print()

    print("## 4. Measured $vectorSearch latency (real query, real cluster)")
    corpus_coll = dict((n, c) for n, c, _ in stores)[CORPUS_COLLECTION]
    query_vector = embeddings.embed_query(
        "Cliente com renda comprovada solicita crédito para financiamento de veículo"
    )
    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": 100,
                "limit": 5,
            }
        },
        {"$project": {"_id": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]

    latencies = []
    for _ in range(20):
        t0 = time.perf_counter()
        list(corpus_coll.aggregate(pipeline))
        latencies.append(time.perf_counter() - t0)

    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95) - 1]
    print(f"  n={len(latencies)} queries, corpus={len(SCRATCH_CORPUS)} scratch docs")
    print(f"  p50 = {p50 * 1000:.1f} ms")
    print(f"  p95 = {p95 * 1000:.1f} ms")
    if p95 > 1.5:
        print("  FAIL: p95 > 1.5s — act on risk 2 in docs/specs/15-risks-and-open-items.md before building further.")
    else:
        print("  PASS: p95 within the 1.5s budget.")
    print()

    print("Cleaning up scratch collections...")
    for name, coll, _ in stores:
        coll.drop()
        print(f"  dropped {name}")
    print()


def report_checkpoint_ttl_behaviour(client, db_name) -> None:
    print("## 3. Checkpoint TTL behaviour — native index vs client-side expiry")

    saver = MongoDBSaver(client, db_name=db_name, ttl=60)
    config = {"configurable": {"thread_id": "_atlas_probe_checkpoint", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    metadata = {"source": "input", "step": -1, "parents": {}}
    saver.put(config, checkpoint, metadata, {})

    db = client[db_name]
    index_info = db["checkpoints"].index_information()
    print("  db.checkpoints.index_information():")
    for name, spec in index_info.items():
        print(f"    {name}: {spec}")

    ttl_indexes = {
        name: spec for name, spec in index_info.items() if "expireAfterSeconds" in spec
    }
    if ttl_indexes:
        print(f"  PASS: native MongoDB TTL index found: {list(ttl_indexes.keys())}")
    else:
        print("  NOTE: no expireAfterSeconds index found — MongoDBSaver(ttl=...) is applying "
              "client-side expiry, not a native TTL index. Do not claim TTL on stage without this.")
    print()

    db["checkpoints"].delete_many({"thread_id": "_atlas_probe_checkpoint"})
    db["checkpoint_writes"].delete_many({"thread_id": "_atlas_probe_checkpoint"})


def main() -> None:
    settings = get_settings()
    client = get_client()

    report_connectivity(client)

    db = client[settings.mongodb_db]
    embeddings = get_embeddings()
    report_index_coexistence_and_latency(db, embeddings)

    report_checkpoint_ttl_behaviour(client, settings.mongodb_db)

    print("Probe complete.")


if __name__ == "__main__":
    main()
