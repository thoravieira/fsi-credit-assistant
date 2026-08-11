"""SDD 05 §1 — persist_decision node. Everything a decision leaves behind.

Three writes, and the second one is the architecture:

1. a `final_decision` event in `decisions_log`, plus the application's new status;
2. **a new document in `historical_cases`, with a freshly generated embedding**;
3. long-term memories across the three `MongoDBStore` namespaces (SDD 07 §2).

Write 2 is the precedent loop (SDD 08 §4). The case just decided becomes
retrievable by the next `precedent_search` immediately — the system improves
from operation without retraining anything, and it is demonstrable live:
decide a case, run a similar simulation, watch it appear in the trace panel.

Everything here is composed from data that already exists. No LLM call runs in
this node: the narrative it writes into `historical_cases.summary` is the
agent's own rationale, framed by figures the calculator produced.
"""

from datetime import datetime, timezone

from app.audit import append_event
from app.config import DEMO_ANALYST_ID
from app.db import get_db
from app.domain.formatting import brl, percent
from app.embeddings import get_embeddings
from app.graph.state import AgentState
from app.memory.store import (
    analyst_decision_patterns_namespace,
    customer_facts_namespace,
    customer_preferences_namespace,
    get_store,
)

PRODUCT_LABELS = {"mortgage": "financiamento imobiliário", "auto": "financiamento de veículo"}
OUTCOME_LABELS = {
    "approved": "aprovado",
    "approved_with_conditions": "aprovado com condições",
    "denied": "negado",
}


def _ltv_band(ltv: float) -> str:
    """SDD 02 §4 — a filter field on the vector index, derived not stored twice."""
    if ltv <= 0.60:
        return "low"
    return "mid" if ltv <= 0.75 else "high"


def persist_decision(state: AgentState) -> dict:
    decision = state.get("decision") or {}
    application = state.get("application") or {}
    profile = state.get("profile") or {}
    application_id = application.get("application_id")
    scenario = decision.get("scenario") or {}
    calc = scenario.get("calc") or state.get("calc") or {}
    outcome = decision.get("outcome", "denied")
    now = datetime.now(timezone.utc)

    append_event(
        application_id,
        "final_decision",
        {"type": "analyst", "id": DEMO_ANALYST_ID},
        inputs=scenario.get("inputs"),
        calc=calc,
        outcome=outcome,
        policy_refs=decision.get("policy_refs", []),
        precedent_refs=decision.get("precedent_refs", []),
        conditions=decision.get("conditions", []),
        rationale=decision.get("rationale", ""),
    )

    get_db()["applications"].update_one(
        {"_id": application_id},
        {"$set": {"status": outcome, "updated_at": now, "final_decision": decision}},
    )

    _write_precedent(application, profile, calc, decision, now)
    _write_memories(application, profile, calc, decision, now)

    return {"stage": "closed"}


def _write_precedent(
    application: dict, profile: dict, calc: dict, decision: dict, now: datetime
) -> None:
    """SDD 08 §2/§4 — `summary` is prose and prose only.

    Cosine similarity over a serialised `{"ltv": 0.80}` is noise; a narrative
    paragraph is what carries signal. So the numbers are spoken rather than
    dumped, and the agent's rationale — already prose, already about this case
    — is the body of it.
    """
    application_id = application["application_id"]
    employment = (profile.get("employment") or {}).get("type", "não informado")
    product = application.get("product", "mortgage")
    ltv = calc.get("ltv", 0.0)

    summary = (
        f"{PRODUCT_LABELS.get(product, product).capitalize()} de "
        f"{brl(application.get('requested_amount', 0.0))} em "
        f"{application.get('term_months')} meses para cliente {employment}, com LTV de "
        f"{percent(ltv)} e comprometimento de renda de {percent(calc.get('dti', 0.0))}. "
        f"Caso {OUTCOME_LABELS.get(decision.get('outcome'), decision.get('outcome'))} "
        f"pelo analista. {decision.get('rationale', '')}"
    ).strip()

    document = {
        "product": product,
        "summary": summary,
        "structured": {
            "requested_amount": application.get("requested_amount"),
            "asset_value": application.get("asset_value"),
            "term_months": application.get("term_months"),
            "ltv": ltv,
            "dti": calc.get("dti"),
            "internal_score": (profile.get("credit") or {}).get("internal_score"),
            "employment_type": employment,
        },
        "decision": decision.get("outcome"),
        "final_rate_annual": calc.get("annual_rate"),
        "conditions": decision.get("conditions", []),
        "rationale": decision.get("rationale", ""),
        "decided_by": DEMO_ANALYST_ID,
        "decided_at": now,
        "ltv_band": _ltv_band(ltv),
        "embedding": get_embeddings().embed_query(summary),
        "source_application_id": application_id,
    }

    # Deterministic `_id`, so re-resuming an already-approved thread updates the
    # precedent instead of growing a second near-duplicate in the corpus the
    # demo retrieves from.
    get_db()["historical_cases"].replace_one(
        {"_id": f"CASE-{application_id.removeprefix('APP-')}"},
        document | {"_id": f"CASE-{application_id.removeprefix('APP-')}"},
        upsert=True,
    )


def _write_memories(
    application: dict, profile: dict, calc: dict, decision: dict, now: datetime
) -> None:
    """SDD 07 §2 — all three namespaces, every one of them derived.

    Nothing here is a model's summary of the conversation. Each memory is
    composed from what actually happened, which is why it can be shown next to
    the decision that produced it. Keys are stable slugs, not hashes: the demo
    needs to *update* a customer's memory across runs, not accumulate near
    duplicates.
    """
    customer_id = application.get("customer_id")
    if not customer_id:
        return

    store = get_store()
    application_id = application["application_id"]
    product = PRODUCT_LABELS.get(application.get("product"), application.get("product"))
    observed = now.isoformat()

    def remember(namespace: tuple[str, ...], key: str, content: str) -> None:
        store.put(
            namespace,
            key,
            {
                "content": content,
                "evidence_application_ids": [application_id],
                "observed_at": observed,
            },
        )

    remember(
        customer_preferences_namespace(customer_id),
        "estrutura-aceita",
        f"Aceitou {product} com entrada de {brl(application.get('down_payment', 0.0))} e "
        f"prazo de {application.get('term_months')} meses, com parcela de "
        f"{brl(calc.get('monthly_payment', 0.0))}.",
    )

    employment = profile.get("employment") or {}
    income = profile.get("income") or {}
    remember(
        customer_facts_namespace(customer_id),
        "renda-e-vinculo",
        f"Vínculo {employment.get('type', 'não informado')}, renda líquida de "
        f"{brl(income.get('net_monthly', 0.0))} "
        f"{'comprovada por ' + str(income.get('verification_method')) if income.get('verified') else 'não comprovada'}"
        f"; score interno {(profile.get('credit') or {}).get('internal_score')}.",
    )

    # The analyst pattern is the calibration memory: it is what lets a later
    # case be read against how this analyst actually decides, rather than
    # against the policy alone.
    mitigant = (
        " com ativos compartilhados via Open Finance"
        if "open finance" in decision.get("rationale", "").lower()
        else ""
    )
    dti = calc.get("dti", 0.0)
    remember(
        analyst_decision_patterns_namespace(DEMO_ANALYST_ID),
        f"{application.get('product')}-dti-ate-{round(dti * 100)}",
        f"{OUTCOME_LABELS.get(decision.get('outcome'), 'decidiu')} {product} com "
        f"comprometimento de renda de {percent(dti)} e LTV de {percent(calc.get('ltv', 0.0))}"
        f"{mitigant}.",
    )
