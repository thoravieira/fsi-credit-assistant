"""SDD 06 §3 — the two research subagents.

`SubAgent` is a plain `TypedDict`, not a class: `deepagents` 0.7.5 exports no
`SubAgent(...)` constructor (SDD 13 §6b). These are dicts, deliberately.

`description` is the field the main agent routes on — it is the only thing the
main model sees when deciding whether to delegate — so it is written as an
instruction to a caller, not as a summary for a reader.
"""

from deepagents import SubAgent

from app.graph.prompts import load_prompt
from app.graph.tools.research import search_policy, search_precedents

POLICY_RESEARCHER: SubAgent = {
    "name": "policy_researcher",
    "description": (
        "Consulta a política de crédito. Use quando precisar saber se um cenário é "
        "permitido e sob que condições. Devolve a conclusão já citada com os ids POL-xxx."
    ),
    "system_prompt": load_prompt("subagent_policy"),
    "tools": [search_policy],
}

PRECEDENT_ANALYST: SubAgent = {
    "name": "precedent_analyst",
    "description": (
        "Consulta casos semelhantes já decididos. Use quando o caso for limítrofe e o "
        "histórico puder sustentar a recomendação. Devolve id, decisão e motivo de cada caso."
    ),
    "system_prompt": load_prompt("subagent_precedent"),
    "tools": [search_precedents],
}
