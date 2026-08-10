"""SDD 04 §2 — graph state schema.

`AgentState` has exactly two reducer fields: `messages` (`add_messages`) and
`scenarios` (`operator.add`). Every other field uses default overwrite
semantics. A reducer on a field that should be replaced produces state that
silently grows — see SDD 04 §2 for why this is a common LangGraph mistake.
"""

import operator
from typing import Annotated, Literal, TypedDict

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
    outcome: Literal["auto_approved", "manual_review", "denied"]
    reasons: list[str]
    policy_refs: list[str]
    breached_rules: list[str]


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
