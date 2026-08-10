"""SDD 09 — retrieval evaluation. Day 1 gate: recall@3 >= 0.8.

A golden set of 10 queries against `credit_policies`, each mapped to the
policy IDs that should be retrieved. Covers every policy family in
docs/specs/02-data-model.md §3 at least once; at least 2 queries are phrased
the way a customer would speak, not the way the policy is written.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.db import get_client
from app.embeddings import get_embeddings

REPO_ROOT = Path(__file__).resolve().parents[2]

GOLDEN_SET = [
    {  # ltv_limit — policy language
        "query": "Qual o limite de LTV para financiamento imobiliário residencial?",
        "product": "mortgage",
        "expected": ["POL-001"],
    },
    {  # max_dti — customer language
        "query": "Quanto da minha renda posso comprometer com a parcela do financiamento da casa?",
        "product": "mortgage",
        "expected": ["POL-004"],
    },
    {  # age_term_limit — policy language
        "query": "Qual a idade máxima somada ao prazo para financiar um imóvel?",
        "product": "mortgage",
        "expected": ["POL-006"],
    },
    {  # score_bands (+ alternative_collateral overlap) — customer language
        "query": "Meu score está baixo, ainda consigo financiar um carro?",
        "product": "auto",
        "expected": ["POL-009"],
    },
    {  # fgts_usage — policy language
        "query": "Posso usar o FGTS para dar entrada no imóvel?",
        "product": "mortgage",
        "expected": ["POL-010"],
    },
    {  # income_verification_self_employed — customer language
        "query": "Sou autônomo e não tenho holerite, como comprovo renda para financiar a casa?",
        "product": "mortgage",
        "expected": ["POL-012"],
    },
    {  # alternative_collateral — policy language
        "query": "Que garantia adicional posso oferecer se o LTV solicitado for maior que o limite?",
        "product": "mortgage",
        "expected": ["POL-014"],
    },
    {  # open_finance_mitigant — policy language
        "query": "Como o compartilhamento de dados via Open Finance pode ajudar a aprovar um "
        "financiamento com DTI acima do limite?",
        "product": "mortgage",
        "expected": ["POL-016"],
    },
    {  # rate_spread_table + approval_authority — policy language
        "query": "Qual a alçada de aprovação e a taxa de juros para um financiamento imobiliário "
        "de alto valor?",
        "product": "mortgage",
        "expected": ["POL-018", "POL-020"],
    },
    {  # probate_restriction — customer language
        "query": "O imóvel que eu quero comprar ainda está em inventário, dá pra financiar mesmo assim?",
        "product": "mortgage",
        "expected": ["POL-022"],
    },
]


def evaluate(store) -> list[dict]:
    rows = []
    for item in GOLDEN_SET:
        hits = store.similarity_search_with_score(
            item["query"], k=5, pre_filter={"product": item["product"]}
        )
        retrieved = [doc.metadata.get("_id") for doc, _ in hits]
        top1_score = hits[0][1] if hits else 0.0
        rows.append(
            {
                "query": item["query"],
                "product": item["product"],
                "expected": item["expected"],
                "retrieved": retrieved,
                "hit3": any(rid in item["expected"] for rid in retrieved[:3]),
                "hit5": any(rid in item["expected"] for rid in retrieved[:5]),
                "top1_score": top1_score,
            }
        )
    return rows


def write_report(rows, recall_at_3, recall_at_5, mean_top1, worst) -> None:
    out = REPO_ROOT / "docs" / "retrieval-eval.md"
    lines = [
        "# Retrieval evaluation",
        "",
        "Committed output of `backend/scripts/03_eval_retrieval.py`.",
        "",
        "| Metric | Value | Healthy |",
        "|---|---|---|",
        f"| recall@3 | {recall_at_3:.2f} | >= 0.8 |",
        f"| recall@5 | {recall_at_5:.2f} | >= 0.9 |",
        f"| mean top-1 score | {mean_top1:.4f} | report, no threshold |",
        f"| worst query | {worst['query']} (top-1 score {worst['top1_score']:.4f}) | inspect manually |",
        "",
        "## Golden set results",
        "",
        "| # | Query | Product | Expected | Retrieved (top 5) | Hit@3 |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, start=1):
        lines.append(
            f"| {i} | {r['query']} | {r['product']} | {', '.join(r['expected'])} | "
            f"{', '.join(r['retrieved'])} | {'yes' if r['hit3'] else 'no'} |"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report written to {out.relative_to(REPO_ROOT)}")


def main() -> None:
    from langchain_mongodb import MongoDBAtlasVectorSearch

    settings = get_settings()
    client = get_client()
    db = client[settings.mongodb_db]
    embeddings = get_embeddings()

    store = MongoDBAtlasVectorSearch(
        collection=db["credit_policies"], embedding=embeddings, index_name="vector_index"
    )

    rows = evaluate(store)
    recall_at_3 = sum(r["hit3"] for r in rows) / len(rows)
    recall_at_5 = sum(r["hit5"] for r in rows) / len(rows)
    mean_top1 = sum(r["top1_score"] for r in rows) / len(rows)
    worst = min(rows, key=lambda r: r["top1_score"])

    print(f"recall@3 = {recall_at_3:.2f}  (healthy >= 0.8)")
    print(f"recall@5 = {recall_at_5:.2f}  (healthy >= 0.9)")
    print(f"mean top-1 score = {mean_top1:.4f}")
    print(f"worst query: {worst['query']!r} (top-1 score {worst['top1_score']:.4f})")
    print()
    for r in rows:
        mark = "OK  " if r["hit3"] else "MISS"
        print(f"[{mark}] {r['query'][:65]:65s} expected={r['expected']} got={r['retrieved']}")

    write_report(rows, recall_at_3, recall_at_5, mean_top1, worst)

    print()
    if recall_at_3 < 0.8:
        print("FAIL: recall@3 below 0.8 — fix chunking per SDD 09 §3 before building further.")
        sys.exit(1)
    print("PASS: recall@3 meets the Day 1 gate.")


if __name__ == "__main__":
    main()
