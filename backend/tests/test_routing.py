"""SDD 05 §3 — routing functions. Pure, no I/O, no graph compilation needed."""

from app.graph.routing import has_complete_application, needs_approval, route


def _base_state(**overrides):
    state = {
        "messages": [],
        "persona": "customer",
        "stage": "intake",
        "application": None,
        "profile": None,
        "memories": [],
        "policies": [],
        "precedents": [],
        "calc": None,
        "decision": None,
        "scenarios": [],
        "pending_approval": None,
    }
    state.update(overrides)
    return state


def test_route_customer_always_goes_to_intake():
    assert route(_base_state(persona="customer", stage="negotiation")) == "intake"
    assert route(_base_state(persona="customer", stage="review")) == "intake"


def test_route_analyst_at_review_goes_to_precedent_search():
    assert route(_base_state(persona="analyst", stage="review")) == "precedent_search"


def test_route_analyst_elsewhere_goes_to_negotiation():
    assert route(_base_state(persona="analyst", stage="negotiation")) == "negotiation"


def test_route_analyst_with_no_checkpoint_yet_goes_to_precedent_search():
    """A thread the graph has never run on before — e.g. an application
    seeded straight into `applications` (Part B of the demo data) rather
    than created live through the customer path — has no `stage` in its
    checkpoint at all. This must not crash, and should present the dossier
    like any other case Carlos is opening for the first time.
    """
    state = _base_state(persona="analyst")
    del state["stage"]
    assert route(state) == "precedent_search"


def test_has_complete_application_missing_fields():
    state = _base_state(application={"product": "mortgage", "asset_value": None})
    assert has_complete_application(state) == "incomplete"


def test_has_complete_application_none():
    assert has_complete_application(_base_state(application=None)) == "incomplete"


def test_has_complete_application_all_required_present():
    app = {
        "product": "mortgage",
        "asset_value": 400_000.0,
        "down_payment": 100_000.0,
        "term_months": 360,
        "purpose": "Compra de imóvel residencial",
    }
    assert has_complete_application(_base_state(application=app)) == "complete"


def test_needs_approval_present():
    assert needs_approval(_base_state(pending_approval={"scenario": "x"})) == "await_approval"


def test_needs_approval_absent():
    assert needs_approval(_base_state(pending_approval=None)) == "end"
