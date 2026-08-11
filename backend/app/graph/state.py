"""SDD 04 §2 — graph state schema.

`AgentState` has exactly two reducer fields: `messages` (`add_messages`) and
`scenarios` (`operator.add`). Every other field uses default overwrite
semantics. A reducer on a field that should be replaced produces state that
silently grows — see SDD 04 §2 for why this is a common LangGraph mistake.
"""

import operator
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class CreditApplication(TypedDict):
    application_id: str
    customer_id: str
    product: Literal["mortgage", "auto"]
    asset_value: float
    down_payment: float
    requested_amount: float
    term_months: int
    purpose: str


class CalcResult(TypedDict):
    monthly_payment: float
    total_interest: float
    annual_rate: float
    cet_annual: float
    ltv: float
    dti: float
    schedule_preview: list[dict]


class Decision(TypedDict):
    """Two producers, one field.

    On the customer path `domain/rules.py` writes one of the three automatic
    outcomes. On the analyst path the human gate writes one of the three
    human outcomes (SDD 06 §5), merging the agent's proposal with the verdict
    that arrived through `/api/approve` — which is why the fields only one of
    them carries are `NotRequired`.
    """

    outcome: Literal[
        "auto_approved",
        "manual_review",
        "denied",
        "approved",
        "approved_with_conditions",
    ]
    policy_refs: list[str]
    reasons: NotRequired[list[str]]
    breached_rules: NotRequired[list[str]]
    scenario: NotRequired[dict]
    rationale: NotRequired[str]
    precedent_refs: NotRequired[list[str]]
    conditions: NotRequired[list[str]]


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    persona: Literal["customer", "analyst"]
    stage: Literal["intake", "assessment", "review", "negotiation", "closed"]
    application: CreditApplication | None
    profile: dict | None
    memories: list[dict]
    policies: list[dict]
    precedents: list[dict]
    calc: CalcResult | None
    decision: Decision | None
    scenarios: Annotated[list[dict], operator.add]
    pending_approval: dict | None
