"""SDD 06 — the negotiation deep agent and its wrapper node.

Everything here runs the *real* `create_deep_agent` with a scripted chat model,
so the assertions cover the actual wiring — tool schemas, runtime-context
injection, subagent registration, and what does and does not cross back into
`AgentState`. Only the model is fake.
"""

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from deepagents import create_deep_agent

from app.agent import negotiation as negotiation_module
from app.agent.negotiation import negotiation
from app.agent.subagents import POLICY_RESEARCHER, PRECEDENT_ANALYST
from app.graph.prompts import load_prompt
from app.graph.tools.case import NegotiationCase
from app.graph.tools.research import search_policy, search_precedents
from app.graph.tools.scenario import (
    check_open_finance_assets,
    recalculate_scenario,
    solve_for_target_dti,
    solve_term_for_target_dti,
)
from tests.fakes import ScriptedChatModel, tool_call

APPLICATION = {
    "application_id": "APP-TEST-NEG",
    "customer_id": "CUST-0001",
    "product": "mortgage",
    "asset_value": 400_000.0,
    "down_payment": 100_000.0,
    "requested_amount": 300_000.0,
    "term_months": 360,
    "purpose": "Aquisição de imóvel residencial próprio",
}

PROFILE = {
    "name": "Mariana Duarte",
    "birth_date": "1990-04-17",
    "employment": {"type": "clt"},
    "income": {"net_monthly": 11_200.0, "verified": True, "verification_method": "holerite"},
    "credit": {"internal_score": 782, "existing_monthly_debt": 1_350.0},
    "open_finance": {
        "consent_granted": False,
        "shareable_assets": [
            {"institution": "Corretora Meridiano", "type": "cdb", "balance": 96_000.0,
             "liquidity": "d_plus_1"},
            {"institution": "Corretora Meridiano", "type": "fundo_multimercado",
             "balance": 42_000.0, "liquidity": "d_plus_30"},
        ],
    },
}


def _state(analyst_message: str) -> dict:
    return {
        "persona": "analyst",
        "stage": "negotiation",
        "application": APPLICATION,
        "profile": PROFILE,
        "calc": {"monthly_payment": 2_800.0, "ltv": 0.75, "dti": 0.37, "annual_rate": 0.113},
        "decision": {"outcome": "manual_review", "reasons": ["LTV de 75% acima de 70%."],
                     "policy_refs": ["POL-020"], "breached_rules": ["ltv_auto_approval_limit"]},
        "precedents": [{"_id": "CASE-2025-0417", "summary": "..."}],
        "scenarios": [],
        "messages": [HumanMessage(analyst_message)],
    }


def _agent(script: list[AIMessage]):
    """The real deep agent, with the real tools, on a scripted model."""
    return create_deep_agent(
        model=ScriptedChatModel(script),
        tools=[
            recalculate_scenario,
            solve_for_target_dti,
            solve_term_for_target_dti,
            check_open_finance_assets,
        ],
        system_prompt=load_prompt("negotiation"),
        subagents=[POLICY_RESEARCHER, PRECEDENT_ANALYST],
        context_schema=NegotiationCase,
        name="negotiation",
    )


def _run(state: dict, script: list[AIMessage]) -> tuple[dict, list[dict], list]:
    """Drive the wrapper node directly, capturing the trace events it emits.

    `get_stream_writer()` is patched because it is only valid inside a running
    graph; `tests/test_analyst_path.py` covers the real streaming path.
    """
    events: list[dict] = []
    with (
        patch.object(negotiation_module, "get_negotiation_agent", return_value=_agent(script)),
        patch.object(negotiation_module, "get_stream_writer", return_value=events.append),
        patch.object(negotiation_module, "append_event") as logged,
    ):
        update = negotiation(state, config={"configurable": {"thread_id": "APP-TEST-NEG"}})
    return update, events, logged.call_args_list


# --- composition -----------------------------------------------------------


def test_the_main_agent_holds_exactly_the_four_domain_tools():
    """SDD 06 acceptance. The filesystem and `task` tools `deepagents` adds are
    the harness; these four are the domain, and research is delegated.
    """
    with patch.object(negotiation_module, "create_deep_agent") as factory:
        negotiation_module.get_negotiation_agent.cache_clear()
        negotiation_module.get_negotiation_agent()
    kwargs = factory.call_args.kwargs

    assert [tool.name for tool in kwargs["tools"]] == [
        "recalculate_scenario",
        "solve_for_target_dti",
        "solve_term_for_target_dti",
        "check_open_finance_assets",
    ]
    assert kwargs["subagents"] == [POLICY_RESEARCHER, PRECEDENT_ANALYST]
    assert kwargs["context_schema"] is NegotiationCase
    # No `checkpointer=`: it is inherited from the parent through `config`,
    # which is what puts the nested checkpoints on the parent thread.
    assert "checkpointer" not in kwargs
    negotiation_module.get_negotiation_agent.cache_clear()


def test_each_subagent_has_one_retrieval_tool():
    assert POLICY_RESEARCHER["tools"] == [search_policy]
    assert PRECEDENT_ANALYST["tools"] == [search_precedents]


@pytest.mark.parametrize(
    "tool, expected",
    [
        (recalculate_scenario, {"down_payment", "term_months", "amount", "annual_rate"}),
        (solve_for_target_dti, {"dti_target", "term_months", "keep_down_payment"}),
        (solve_term_for_target_dti, {"dti_target"}),
        (check_open_finance_assets, set()),
        (search_policy, {"query"}),
        (search_precedents, {"query"}),
    ],
)
def test_runtime_context_never_appears_in_the_model_facing_schema(tool, expected):
    """The customer's income, score and product reach the tools through
    `ToolRuntime`, which the framework strips from the JSON schema. If
    `runtime` ever showed up here, the model could supply it.
    """
    assert set(tool.args) == expected


# --- the wrapper -----------------------------------------------------------


def test_scenarios_come_back_as_state_and_as_audit_entries():
    """SDD 06 acceptance — three consecutive scenarios accumulate, and each one
    writes a `scenario_simulated` entry, the rejected ones included.
    """
    script = [
        tool_call("recalculate_scenario", "c1", down_payment=140_000.0),
        tool_call("recalculate_scenario", "c2", down_payment=168_000.0),
        tool_call("recalculate_scenario", "c3", down_payment=168_000.0, term_months=420),
        AIMessage("Com entrada de R$ 168.000,00 o LTV cai para 58% (POL-020)."),
    ]
    update, events, logged = _run(_state("e se a entrada subisse?"), script)

    assert [s["inputs"]["down_payment"] for s in update["scenarios"]] == [
        140_000.0,
        168_000.0,
        168_000.0,
    ]
    assert [call.args[1] for call in logged] == ["scenario_simulated"] * 3
    # Every figure in a scenario came from `domain/`, never from the model.
    assert update["scenarios"][1]["calc"]["ltv"] == pytest.approx(0.58)
    assert update["scenarios"][1]["outcome"] == "auto_approved"
    assert "POL-020" in update["scenarios"][1]["policy_refs"]


def test_solve_for_target_dti_hits_the_target_exactly():
    """Regression test for the negotiation-lever bug: asking for a target
    comprometimento de renda must resolve a `financed` that actually clears
    that target, not a guessed `down_payment` that only lands close (the
    reported bug: a guess-and-check via `recalculate_scenario` landed at
    32,5% when the analyst asked for exactly 32%).
    """
    script = [
        tool_call("solve_for_target_dti", "c1", dti_target=0.32),
        AIMessage("Com o comprometimento em 32%, o financiamento cai (POL-004)."),
    ]
    update, _events, _logged = _run(
        _state("reduzindo o comprometimento de renda para 32%, quanto fica o financiamento?"),
        script,
    )

    scenario = update["scenarios"][0]
    assert scenario["calc"]["dti"] == pytest.approx(0.32, abs=1e-3)
    # asset_value never moves: entrada is reported as the complement of the
    # solved financed amount, not as a lever the model chose to pull.
    assert scenario["inputs"]["amount"] + scenario["inputs"]["down_payment"] == pytest.approx(
        APPLICATION["asset_value"]
    )


def test_solve_for_target_dti_normalizes_30_as_thirty_percent_and_keeps_entry():
    script = [
        tool_call("solve_for_target_dti", "c1", dti_target=30, keep_down_payment=True),
        AIMessage("Mantendo a entrada, o financiamento foi recalculado para 30%."),
    ]
    update, _events, _logged = _run(
        _state("mantenha a entrada e o prazo e reduza o financiamento para DTI de 30%"),
        script,
    )

    scenario = update["scenarios"][0]
    assert scenario["target_dti"] == pytest.approx(0.30)
    assert scenario["calc"]["dti"] == pytest.approx(0.30, abs=1e-3)
    assert scenario["inputs"]["down_payment"] == pytest.approx(APPLICATION["down_payment"])
    assert scenario["inputs"]["asset_value"] == pytest.approx(
        scenario["inputs"]["amount"] + APPLICATION["down_payment"]
    )
    assert scenario["constraint"] == "keep_down_payment"


def test_solve_term_for_target_dti_reports_when_age_ceiling_makes_it_impossible():
    script = [
        tool_call("solve_term_for_target_dti", "c1", dti_target=30),
        AIMessage("Só o prazo não é suficiente para chegar a 30%."),
    ]
    update, _events, _logged = _run(
        _state("sem mexer na entrada nem no valor, ajuste só o prazo para DTI de 30%"),
        script,
    )

    scenario = update["scenarios"][0]
    assert scenario["target_dti"] == pytest.approx(0.30)
    assert scenario["feasible"] is False
    assert scenario["calc"]["dti"] > 0.30
    assert scenario["inputs"]["amount"] == pytest.approx(APPLICATION["requested_amount"])
    assert scenario["inputs"]["down_payment"] == pytest.approx(APPLICATION["down_payment"])


def test_deep_agent_state_does_not_leak_into_agent_state():
    """SDD 06 acceptance — no `files`, no `todos`, no tool-call messages. Only
    the final answer, the computed scenarios and (when asked for) the proposal.
    """
    script = [AIMessage("O caso segue acima do limite automático (POL-020).")]
    update, _events, _logged = _run(_state("qual a situação?"), script)

    assert set(update) == {"messages", "scenarios"}
    assert [m.content for m in update["messages"]] == [
        "O caso segue acima do limite automático (POL-020)."
    ]


def test_tool_steps_and_tokens_are_forwarded_to_the_parent_stream():
    """SDD 06 §6 — the whole negotiation is one graph node running a nested
    graph, so neither the tool steps nor the agent's own tokens reach the
    parent's stream by themselves. Without both, the analyst watches a blank
    screen and then receives everything at once.
    """
    script = [
        tool_call("check_open_finance_assets", "c1"),
        AIMessage("O consentimento não foi concedido; nenhum saldo pode ser usado."),
    ]
    _update, events, _logged = _run(_state("o que ela pode compartilhar?"), script)

    steps = [e for e in events if "step" in e]
    assert [s["step"] for s in steps] == ["check_open_finance_assets"]
    assert steps[0]["node"] == "negotiation"
    assert steps[0]["detail"]["consent_granted"] is False
    assert "asset_count" not in steps[0]["detail"]
    assert "liquid_balance" not in steps[0]["detail"]

    streamed = "".join(e["token"] for e in events if "token" in e)
    assert streamed == "O consentimento não foi concedido; nenhum saldo pode ser usado."


def test_saying_aprovar_produces_a_proposal_for_the_human_gate():
    """SDD 06 acceptance — "aprovar" sets `pending_approval`. Nothing is
    recorded here; `await_approval` and `/api/approve` do that.
    """
    script = [
        tool_call("recalculate_scenario", "c1", down_payment=168_000.0),
        AIMessage("Recomendo aprovar: LTV de 58% dentro de POL-020, renda comprovada POL-012."),
    ]
    update, _events, _logged = _run(_state("pode aprovar"), script)

    proposal = update["pending_approval"]
    assert proposal["outcome"] == "approved"
    assert proposal["policy_refs"] == ["POL-020", "POL-012"]
    assert proposal["precedent_refs"] == ["CASE-2025-0417"]
    assert proposal["scenario"]["inputs"]["down_payment"] == 168_000.0
    assert "decision" not in update


def test_an_ordinary_turn_proposes_nothing():
    script = [AIMessage("Podemos tentar alongar o prazo.")]
    update, _events, _logged = _run(_state("e se o prazo aumentasse?"), script)

    assert "pending_approval" not in update


# --- item 10 — reopening an already-decided case ----------------------------


def test_case_briefing_flags_an_already_decided_case():
    from app.agent.negotiation import _case_briefing

    state = _state("existem casos parecidos?")
    state["application"] = {**APPLICATION, "status": "approved_with_conditions"}

    briefing = _case_briefing(state)

    assert "JÁ FOI DECIDIDO" in briefing
    assert "approved_with_conditions" in briefing


def test_case_briefing_says_nothing_extra_for_a_still_open_case():
    from app.agent.negotiation import _case_briefing

    state = _state("existem casos parecidos?")
    state["application"] = {**APPLICATION, "status": "manual_review"}

    assert "JÁ FOI DECIDIDO" not in _case_briefing(state)


def test_no_proposal_on_an_already_decided_case_even_if_asked_to_approve():
    """Belt and suspenders with the frontend disabling the buttons: even if
    the analyst's exploratory message contains a verdict keyword, a resolved
    case must never produce a fresh `pending_approval`.
    """
    script = [AIMessage("Esse caso já foi aprovado com condições — posso simular outro cenário.")]
    state = _state("pode aprovar de novo?")
    state["application"] = {**APPLICATION, "status": "approved_with_conditions"}

    update, _events, _logged = _run(state, script)

    assert "pending_approval" not in update
