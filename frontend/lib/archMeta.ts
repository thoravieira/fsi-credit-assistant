// Reference/documentation copy for the architecture diagram and its drawer —
// NOT live data. What actually happened (node, status, ms, detail) always
// comes from real `TraceEvent`s via `useAgentStream` (docs/specs/11-api-sse.md).
// This file only supplies the static "what does this step do" explainer text,
// the step ordering per persona, and the visual classification (kind/chip)
// used to color a step once a real trace event confirms it ran.

export type Kind = 'io' | 'code' | 'llm' | 'rag' | 'data';

export const KIND: Record<Kind, { glyph: string; name: string; fill: string; ink: string; line: string }> = {
  io: { glyph: '⇄', name: 'stream', fill: '#ec3013', ink: '#fff', line: '#ec3013' },
  code: { glyph: 'ƒ', name: 'código', fill: '#fff', ink: '#201e1d', line: '#201e1d' },
  llm: { glyph: '◯', name: 'LLM', fill: '#001E2B', ink: '#fff', line: '#001E2B' },
  rag: { glyph: '⬡', name: 'RAG', fill: '#00684A', ink: '#fff', line: '#00684A' },
  data: { glyph: '▤', name: 'dados', fill: '#C3F3D7', ink: '#023430', line: '#00684A' },
};

export type ChipKey = 'mongo' | 'vector' | 'short' | 'long' | 'openai' | 'embed' | 'python' | 'graph' | 'chain' | 'deep' | 'human';

export const CHIP: Record<ChipKey, { label: string; bg: string; color: string }> = {
  mongo: { label: 'MongoDB', bg: 'rgba(0,237,100,.22)', color: '#00684A' },
  vector: { label: 'Vector', bg: 'rgba(0,237,100,.22)', color: '#00684A' },
  short: { label: 'Mem. curta', bg: 'rgba(2,52,48,.14)', color: '#023430' },
  long: { label: 'Mem. longa', bg: 'rgba(0,104,74,.16)', color: '#00684A' },
  openai: { label: 'OpenAI', bg: 'rgba(32,30,29,.1)', color: '#201e1d' },
  embed: { label: 'Embeddings', bg: 'rgba(0,104,74,.12)', color: '#00684A' },
  python: { label: 'Python', bg: 'rgba(141,151,148,.2)', color: '#4a5350' },
  graph: { label: 'LangGraph', bg: 'rgba(32,30,29,.07)', color: '#4a5350' },
  chain: { label: 'LangChain', bg: 'rgba(32,30,29,.07)', color: '#4a5350' },
  deep: { label: 'Deep Agents', bg: 'rgba(32,30,29,.07)', color: '#4a5350' },
  human: { label: 'Humano', bg: 'rgba(32,30,29,.07)', color: '#4a5350' },
};

// Item 9 — every card links back to the exact real source, not just a
// paraphrase: `main` branch (not a pinned SHA), so the link always opens
// whatever is actually deployed rather than drifting from a stale commit.
export const GITHUB_REPO = 'thoravieira/fsi-credit-assistant';
export const GITHUB_REF = 'main';
export function githubUrl(file: string, lines: [number, number]): string {
  return `https://github.com/${GITHUB_REPO}/blob/${GITHUB_REF}/${file}#L${lines[0]}-L${lines[1]}`;
}

export interface SourceRef {
  file: string;
  lines: [number, number];
}

export interface NodeInfo {
  label: string;
  sub: string;
  chips: ChipKey[];
  what: string;
  rows: [string, string][];
  sample: string;
  code: string;
  // The exact implementation this card describes — shown expanded — and
  // where it's wired into the graph — shown collapsed. Both are real
  // file:line ranges verified against the checked-out source, not the
  // `code` field's paraphrase above, so a GitHub link opens precisely what
  // the reader is looking at (item 9).
  source: SourceRef;
  usage: SourceRef;
}

export const NODES: Record<string, NodeInfo> = {
  api: {
    label: 'FastAPI', sub: 'SSE · astream', chips: ['graph'],
    what: 'Hidrata o thread e roda graph.astream com três stream_modes, mapeando cada chunk para um dos quatro eventos SSE.',
    rows: [['Camada', 'API'], ['stream_mode', 'updates · messages · custom'], ['state', 'emitido uma vez, antes de done']],
    sample: 'event: trace\ndata: {"node":"policy_retrieval","status":"finished","ms":812}',
    code: 'async for mode, chunk in graph.astream(\n    payload, config={"configurable":{"thread_id": thread_id}},\n    stream_mode=["updates","messages","custom"]):\n    yield sse(map_chunk(mode, chunk))',
    source: { file: 'backend/app/main.py', lines: [288, 391] },
    usage: { file: 'backend/app/main.py', lines: [393, 396] },
  },
  router: {
    label: 'router', sub: 'decide o caminho', chips: ['python', 'graph'],
    what: 'Função pura: persona + stage decidem a rota. Sem I/O, sem LLM. ~90% dos pedidos nunca saem do caminho determinístico.',
    rows: [['Camada', 'LangGraph'], ['Modelo', 'nenhum'], ['Latência', '~10 ms']],
    sample: '{"persona":"customer","stage":"intake"} → "intake"',
    code: 'def route(state: AgentState) -> str:\n    if state["persona"] == "analyst":\n        return "precedent_search" if state["stage"]=="review" else "negotiation"\n    return "intake"',
    source: { file: 'backend/app/graph/routing.py', lines: [9, 12] },
    usage: { file: 'backend/app/graph/builder.py', lines: [44, 44] },
  },
  intake: {
    label: 'intake', sub: 'entende o pedido', chips: ['chain', 'openai', 'short'],
    what: 'LangChain com structured output transforma texto livre em CreditApplication tipada. Campo faltando não vira None no cálculo: o grafo desvia e pergunta.',
    rows: [['Camada', 'LangChain'], ['Modelo', 'OpenAI · structured output'], ['Memória', 'checkpoint (curta)'], ['Tokens', '312 in · 88 out']],
    sample: '{"product":"mortgage","asset_value":400000,\n "down_payment":100000,"term_months":360}',
    code: 'llm = get_chat_model().with_structured_output(CreditApplication)\napp = llm.invoke([SystemMessage(PROMPT), *state["messages"]])\nreturn {"application": {**(state.get("application") or {}), **app}}',
    source: { file: 'backend/app/graph/nodes/intake.py', lines: [55, 101] },
    usage: { file: 'backend/app/graph/builder.py', lines: [45, 45] },
  },
  load_context: {
    label: 'load_context', sub: 'perfil e memória', chips: ['mongo', 'long', 'short'],
    what: 'Lê customer_profiles (Collections) e o MongoDBStore (memória longa, 3 namespaces). O checkpoint da conversa (memória curta) já foi restaurado pelo LangGraph antes do nó rodar.',
    rows: [['Camada', 'LangGraph'], ['Mem. curta', 'checkpoints · TTL 24 h · MongoDBSaver'], ['Mem. longa', 'agent_memories · MongoDBStore'], ['Namespaces', '("customer",id,"preferences") · ("...","facts") · ("analyst",id,"decision_patterns")']],
    sample: '{"content":"Prioriza parcela menor sobre prazo curto",\n "observed_at":"2026-05-02T13:07:00Z"}',
    code: 'store = get_store()\nmems = store.search(("customer", cid, "preferences"), limit=5)\nprofile = db.customer_profiles.find_one({"_id": cid})',
    source: { file: 'backend/app/graph/nodes/load_context.py', lines: [13, 39] },
    usage: { file: 'backend/app/graph/builder.py', lines: [46, 46] },
  },
  policy_retrieval: {
    label: 'policy_retrieval', sub: 'busca a política (RAG)', chips: ['embed', 'vector'],
    what: 'É aqui que a pergunta vira vetor: o texto da consulta passa pelo modelo de embeddings (Voyage, 1024d) e o vetor entra num $vectorSearch em credit_policies, com pre_filter por produto, k=4.',
    rows: [['Camada', 'LangChain + MongoDB'], ['Embeddings', 'voyage-4-lite · 1024d'], ['Operação', '$vectorSearch · credit_policies · k=4 · cosine'], ['Latência', 'embed 120 ms + busca 520 ms']],
    sample: '[{"_id":"POL-020","score":0.92,"title":"Alçadas de aprovação"},\n {"_id":"POL-004","score":0.88,"title":"DTI máximo"}]',
    code: 'writer({"op":"$vectorSearch","collection":"credit_policies","k":4})\ndocs = vector_store.similarity_search(query, k=4,\n        pre_filter={"product": product})   # pre_filter, não filter',
    source: { file: 'backend/app/graph/nodes/policy_retrieval.py', lines: [16, 42] },
    usage: { file: 'backend/app/graph/builder.py', lines: [47, 47] },
  },
  credit_calculator: {
    label: 'credit_calculator', sub: 'calcula (Python puro)', chips: ['python'],
    what: 'PMT pela Tabela Price, CET por bisseção, LTV e DTI em Python puro — zero chamada de LLM. O modelo escolhe o cenário; este módulo avalia. É a resposta para "como você impede a alucinação de número".',
    rows: [['Camada', 'domain/calculator.py'], ['Modelo', 'nenhum — 0 LLM'], ['Taxa mensal', '(1+anual)^(1/12) − 1 (efetiva)'], ['Latência', '< 10 ms']],
    sample: '{"monthly_payment":2658.78,"ltv":0.75,"dti":0.358,\n "annual_rate":0.106,"cet_annual":0.1113}',
    code: 'def pmt(pv, i, n):\n    return pv * i / (1 - (1 + i) ** -n)\n\ni = (1 + annual) ** (1/12) - 1      # efetiva, nunca annual/12',
    source: { file: 'backend/app/graph/nodes/credit_calculator.py', lines: [14, 63] },
    usage: { file: 'backend/app/graph/builder.py', lines: [48, 48] },
  },
  decision: {
    label: 'decision', sub: 'aplica as regras', chips: ['python', 'mongo'],
    what: 'domain/rules.py aplica a matriz de limites por produto e devolve outcome, policy_refs e reasons em português. Grava o assessment em decisions_log e atualiza applications.',
    rows: [['Camada', 'domain/rules.py'], ['Saídas', 'auto_approved · manual_review · denied'], ['Escreve', 'decisions_log · applications.status']],
    sample: '{"outcome":"manual_review","policy_refs":["POL-020","POL-004"],\n "breached_rules":["ltv_auto_approval_limit","dti_auto_approval_limit"]}',
    code: 'if ltv > LIMITS[p]["ltv_abs"] or dti > LIMITS[p]["dti_abs"]:\n    return Decision(outcome="denied", policy_refs=["POL-001","POL-004"])\nif auto_ok: return Decision(outcome="auto_approved", ...)',
    source: { file: 'backend/app/graph/nodes/decision.py', lines: [16, 49] },
    usage: { file: 'backend/app/graph/builder.py', lines: [49, 49] },
  },
  customer_response: {
    label: 'customer_response', sub: 'responde à cliente', chips: ['chain', 'openai'],
    what: 'O LLM escreve a resposta em português ancorado em policies + calc que já estão no estado. Os tokens chegam por streaming. O modelo descreve números, nunca os calcula.',
    rows: [['Camada', 'LangChain'], ['Modelo', 'OpenAI · chat completions (stream)'], ['Tokens', '~420 in · 96 out']],
    sample: '"Com entrada de R$ 100.000, a parcela fica em R$ 2.658,78 — LTV de 75,0%…"',
    code: 'async for chunk in llm.astream(prompt.format(calc=state["calc"],\n        policies=state["policies"])):\n    writer({"token": chunk.content})',
    source: { file: 'backend/app/graph/nodes/customer_response.py', lines: [40, 63] },
    usage: { file: 'backend/app/graph/builder.py', lines: [50, 50] },
  },
  precedent_search: {
    label: 'precedent_search', sub: 'casos parecidos (RAG)', chips: ['embed', 'vector'],
    what: 'Mesmo caminho de RAG em outra coleção: embedding da consulta + $vectorSearch em historical_cases (k=3) para trazer casos similares e como foram decididos.',
    rows: [['Camada', 'LangChain + MongoDB'], ['Operação', '$vectorSearch · historical_cases · k=3'], ['Detalhe', 'text_key="summary" — a prosa do caso mora em summary']],
    sample: '[{"_id":"CASE-2025-0001","score":0.88,"decision":"approved_with_conditions"}]',
    code: 'store = MongoDBAtlasVectorSearch(coll, embeddings, text_key="summary")\ncases = store.similarity_search(q, k=3, pre_filter={"product": p})',
    source: { file: 'backend/app/graph/nodes/precedent_search.py', lines: [30, 41] },
    usage: { file: 'backend/app/graph/builder.py', lines: [51, 51] },
  },
  analyst_brief: {
    label: 'analyst_brief', sub: 'monta o dossiê', chips: ['chain', 'openai'],
    what: 'Produz a recomendação para o analista: motivo, política aplicável e precedentes citados, já em português.',
    rows: [['Camada', 'LangChain'], ['Modelo', 'OpenAI · chat completions'], ['Tokens', '~980 in · 210 out']],
    sample: '{"recommendation":"negociar entrada ou prazo",\n "policy_refs":["POL-020","POL-004"],"precedents":["CASE-2025-0001"]}',
    code: 'brief = llm.invoke(BRIEF_PROMPT.format(calc=calc, policies=pol,\n        precedents=prec))\nreturn {"decision": {**brief, "stage": "negotiation"}}',
    source: { file: 'backend/app/graph/nodes/analyst_brief.py', lines: [40, 66] },
    usage: { file: 'backend/app/graph/builder.py', lines: [52, 52] },
  },
  negotiation: {
    label: 'negotiation', sub: 'raciocínio (deep agent)', chips: ['deep', 'openai'],
    what: 'A etapa de raciocínio. create_deep_agent roda como subgrafo com planejamento, ferramentas e dois subagentes de contexto isolado. É o único ponto onde o problema é aberto.',
    rows: [['Camada', 'Deep Agents (deepagents 0.7.5)'], ['Ferramentas', 'recalculate_scenario → Python · check_open_finance_assets'], ['Subagentes', 'policy_researcher · precedent_analyst'], ['Checkpoints', 'aninhados no mesmo thread_id do pai']],
    sample: '{"scenario":{"down_payment":140000},"outcome":"manual_review",\n "resumo":"parcela R$ 2.164,54 · LTV 65,0% · DTI 31,4%"}',
    code: 'agent = create_deep_agent(model=get_chat_model(),\n    tools=[recalculate_scenario, check_open_finance_assets],\n    subagents=[POLICY_RESEARCHER, PRECEDENT_ANALYST], store=store)\n# sem checkpointer=: herda o do pai pelo config',
    source: { file: 'backend/app/agent/negotiation.py', lines: [78, 89] },
    usage: { file: 'backend/app/graph/builder.py', lines: [53, 53] },
  },
  policy_researcher: {
    label: 'policy_researcher', sub: 'subagente · política', chips: ['deep', 'vector'],
    what: 'Subagente com janela de contexto própria: busca a política aplicável e devolve conclusão curta e citada, em vez de despejar quatro trechos no loop principal. Isolamento de contexto é o ponto do padrão.',
    rows: [['Camada', 'Deep Agents · subagente'], ['Operação', '$vectorSearch · credit_policies'], ['Retorno', 'conclusão + POL-xxx']],
    sample: '"DTI de 31,4% permitido em análise manual com fator compensatório (POL-004, POL-016)."',
    code: 'POLICY_RESEARCHER: SubAgent = {"name":"policy_researcher",\n  "description":"Consulta a política de crédito…",\n  "system_prompt": load_prompt("subagent_policy"), "tools":[search_policy]}',
    source: { file: 'backend/app/agent/subagents.py', lines: [16, 24] },
    usage: { file: 'backend/app/agent/negotiation.py', lines: [71, 71] },
  },
  precedent_analyst: {
    label: 'precedent_analyst', sub: 'subagente · precedentes', chips: ['deep', 'vector'],
    what: 'Subagente para casos limítrofes: busca precedentes e resume como cada um foi decidido. Usado só quando o caso é borderline, por custo de latência.',
    rows: [['Camada', 'Deep Agents · subagente'], ['Operação', '$vectorSearch · historical_cases'], ['Quando', 'casos borderline']],
    sample: '"Dois precedentes aprovados com Open Finance como mitigante (CASE-2025-0016, CASE-2024-0003)."',
    code: 'PRECEDENT_ANALYST: SubAgent = {"name":"precedent_analyst", …,\n  "tools":[search_precedents]}',
    source: { file: 'backend/app/agent/subagents.py', lines: [26, 34] },
    usage: { file: 'backend/app/agent/negotiation.py', lines: [71, 71] },
  },
  await_approval: {
    label: 'await_approval', sub: 'aprovação humana', chips: ['graph', 'human', 'short'],
    what: 'Nó do grafo pai que chama interrupt(). O agente não consegue gravar decisão sem um humano retomar — é arquitetura, não política. O estado pausado vive no checkpoint.',
    rows: [['Camada', 'LangGraph'], ['Mecanismo', 'interrupt() → Command(resume=…)'], ['Mem. curta', 'estado pausado em checkpoints'], ['Retomada', 'POST /api/approve']],
    sample: '{"__interrupt__":[{"value":{"scenario":…,"policy_refs":["POL-016"]}}]}',
    code: 'def await_approval(state):\n    verdict = interrupt(state["pending_approval"])\n    return {"pending_approval": None,\n            "decision": {**state["pending_approval"], **verdict}}',
    source: { file: 'backend/app/graph/nodes/await_approval.py', lines: [24, 32] },
    usage: { file: 'backend/app/graph/builder.py', lines: [54, 54] },
  },
  persist_decision: {
    label: 'persist_decision', sub: 'grava e aprende', chips: ['mongo', 'long', 'embed'],
    what: 'Grava três coisas: evento em decisions_log, novo documento em historical_cases já com embedding (o caso decidido vira precedente pesquisável na hora) e memórias longas nos três namespaces.',
    rows: [['Camada', 'LangGraph'], ['Escreve', 'decisions_log · historical_cases · agent_memories'], ['Embeddings', 'voyage-4-lite no resumo do novo precedente'], ['Efeito', 'a próxima busca já encontra este caso']],
    sample: '{"_id":"CASE-2026-0051","summary":"Aprovado com Open Finance…",\n "embedding":[0.021,-0.118,…]}',
    code: 'db.decisions_log.insert_one(event)\ndb.historical_cases.insert_one({**case, "embedding": embed(summary)})\nstore.put(("analyst", aid, "decision_patterns"), key, {"content": …})',
    source: { file: 'backend/app/graph/nodes/persist_decision.py', lines: [49, 80] },
    usage: { file: 'backend/app/graph/builder.py', lines: [55, 55] },
  },
  // Synthetic lane cards: the negotiation deep agent's own tool calls arrive as
  // real `status:'step'` events nested under the `negotiation` node, not as
  // distinct top-level graph nodes — these two cards group them by lane for
  // the swimlane view (see SUBSTEP_TO_CARD) without inventing a fake node.
  scenario_tools: {
    label: 'ferramentas de cenário', sub: 'recalculate_scenario', chips: ['deep', 'python'],
    what: 'A negociação chama esta ferramenta para recalcular PMT/LTV/DTI com um novo down_payment ou term_months — o mesmo domain/calculator.py determinístico do credit_calculator, exposto como tool ao deep agent.',
    rows: [['Camada', 'Deep Agents · tool'], ['Chamada por', 'negotiation'], ['Código', 'domain/calculator.py — mesma função do credit_calculator']],
    sample: '{"down_payment":140000,"term_months":360} → {"ltv":0.65,"dti":0.314}',
    code: '@tool\ndef recalculate_scenario(down_payment: int, term_months: int) -> dict:\n    return calculate(product, asset_value, down_payment, term_months)',
    source: { file: 'backend/app/graph/tools/scenario.py', lines: [21, 122] },
    usage: { file: 'backend/app/agent/negotiation.py', lines: [69, 69] },
  },
  research_tools: {
    label: 'pesquisa (RAG)', sub: 'policy_researcher · precedent_analyst', chips: ['deep', 'vector'],
    what: 'Os subagentes de contexto isolado — política, precedentes e (quando pedido) Open Finance — chamados sob demanda pela negociação, cada um com seu próprio $vectorSearch ou consulta externa.',
    rows: [['Camada', 'Deep Agents · subagentes'], ['Coleções', 'credit_policies · historical_cases'], ['Isolamento', 'contexto próprio por subagente']],
    sample: '"DTI de 31,4% permitido em análise manual com fator compensatório (POL-004, POL-016)."',
    code: 'subagents=[POLICY_RESEARCHER, PRECEDENT_ANALYST]',
    source: { file: 'backend/app/graph/tools/scenario.py', lines: [125, 169] },
    usage: { file: 'backend/app/agent/negotiation.py', lines: [69, 71] },
  },
};

interface TrackMeta {
  short: string;
  kind: Kind;
  tech: string;
  in: string;
}

export const TRACK_META: Record<string, TrackMeta> = {
  api: { short: 'SSE', kind: 'io', tech: 'stream', in: 'POST /api/chat · {persona, message}' },
  scenario_tools: { short: 'scenario tools', kind: 'code', tech: 'Python', in: 'down_payment · term_months' },
  research_tools: { short: 'research tools', kind: 'rag', tech: 'Deep Agents', in: 'pergunta isolada · contexto próprio' },
  router: { short: 'router', kind: 'code', tech: 'Python', in: '{persona, stage}' },
  intake: { short: 'intake', kind: 'llm', tech: 'OpenAI', in: 'texto livre da cliente' },
  load_context: { short: 'context', kind: 'data', tech: 'MongoDB', in: 'thread_id · customer_id' },
  policy_retrieval: { short: 'policy RAG', kind: 'rag', tech: 'Voyage · Atlas', in: 'embed(consulta) · 1024d' },
  credit_calculator: { short: 'calculator', kind: 'code', tech: 'Python', in: 'valor · entrada · prazo' },
  decision: { short: 'decision', kind: 'code', tech: 'Python · Mongo', in: 'calc + políticas' },
  customer_response: { short: 'response', kind: 'llm', tech: 'OpenAI', in: 'calc + políticas + memórias' },
  precedent_search: { short: 'cases RAG', kind: 'rag', tech: 'Voyage · Atlas', in: 'embed(resumo do caso)' },
  analyst_brief: { short: 'brief', kind: 'llm', tech: 'OpenAI', in: 'calc + políticas + precedentes' },
  negotiation: { short: 'negotiation', kind: 'llm', tech: 'Deep Agents', in: 'pedido do analista + estado' },
  policy_researcher: { short: 'policy sub', kind: 'rag', tech: 'subagente', in: 'pergunta isolada · contexto próprio' },
  precedent_analyst: { short: 'cases sub', kind: 'rag', tech: 'subagente', in: 'pergunta isolada · contexto próprio' },
  await_approval: { short: 'approval', kind: 'io', tech: 'humano', in: 'decisão do analista' },
  persist_decision: { short: 'persist', kind: 'data', tech: 'MongoDB', in: 'assessment + trace' },
};

export const TRACK_CUST = ['api', 'router', 'intake', 'load_context', 'policy_retrieval', 'credit_calculator', 'decision', 'customer_response'];
export const TRACK_ANA = ['api', 'router', 'precedent_search', 'analyst_brief', 'negotiation', 'policy_researcher', 'precedent_analyst', 'await_approval', 'persist_decision'];

// The single most relevant chip per node for the (space-constrained) trace
// row badge — the drawer shows the full `NODES[id].chips` list instead.
const PRIMARY: Record<string, ChipKey> = {
  router: 'python', intake: 'openai', load_context: 'long', policy_retrieval: 'vector',
  credit_calculator: 'python', decision: 'python', customer_response: 'openai',
  precedent_search: 'vector', analyst_brief: 'openai', negotiation: 'deep',
  policy_researcher: 'vector', precedent_analyst: 'vector', await_approval: 'human',
  persist_decision: 'mongo', api: 'graph',
};

export function summarizeDetail(detail?: Record<string, unknown>): string | null {
  if (!detail) return null;
  const entries = Object.entries(detail);
  if (!entries.length) return null;
  return entries
    .slice(0, 3)
    .map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join(' · ')
    .slice(0, 140);
}

export function chipOf(nodeOrStep: string): { label: string; bg: string; color: string } {
  const key = PRIMARY[nodeOrStep];
  return key ? CHIP[key] : CHIP.graph;
}

export function dotOf(nodeOrStep: string): string {
  const kind = TRACK_META[nodeOrStep]?.kind ?? 'code';
  return KIND[kind].line;
}

export function fmtMs(ms?: number): string {
  if (ms == null) return '';
  return ms < 1000 ? Math.round(ms) + 'ms' : (ms / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 's';
}

// ---------------------------------------------------------------------------
// Swimlanes — "Fluxo em tempo real" groups the same real nodes above by who
// executes them (LangGraph/Foundation Model vs. MongoDB Atlas vs. plain
// Python), instead of by technical kind. Purely a different arrangement of
// the same real trace-driven data — no new facts, no simulated steps.
// ---------------------------------------------------------------------------

export type Lane = 'agent' | 'data' | 'python';

export const LANE_INFO: Record<Lane, { title: string; badge: string; badgeLabel: string; desc: string; tint: string; accent: string }> = {
  agent: { title: 'LANGGRAPH / FM', badge: 'A', badgeLabel: 'AGENT', desc: 'LangGraph · Foundation Model · Deep Agent', tint: '#EEF6F0', accent: '#00684A' },
  data: { title: 'DATA / MEMORY / VECTOR', badge: 'M', badgeLabel: 'MONGODB ATLAS', desc: 'Dados · memória · checkpoints · Vector Search', tint: '#F1EEFA', accent: '#6A4FC2' },
  python: { title: 'CÓDIGO DETERMINÍSTICO', badge: 'Py', badgeLabel: 'PYTHON', desc: 'Cálculo · regras · validação · persistência', tint: '#FBF3E7', accent: '#B5651D' },
};

export const LANE: Record<string, Lane> = {
  router: 'agent', intake: 'agent', customer_response: 'agent',
  analyst_brief: 'agent', negotiation: 'agent', await_approval: 'agent',
  load_context: 'data', policy_retrieval: 'data', precedent_search: 'data',
  persist_decision: 'data', research_tools: 'data',
  credit_calculator: 'python', decision: 'python', scenario_tools: 'python',
};

// Real sub-step names (arriving as `status:'step'` nested under `negotiation`)
// mapped to the synthetic lane card that represents them — see NODES above.
const SUBSTEP_TO_CARD: Record<string, string> = {
  recalculate_scenario: 'scenario_tools',
  check_open_finance_assets: 'research_tools',
  policy_researcher: 'research_tools',
  precedent_analyst: 'research_tools',
};

// Which lane card a real `TraceEvent` should light up — collapses negotiation
// sub-steps onto their synthetic card, otherwise the event's own node.
export function laneCardId(event: { node: string; step?: string }): string {
  if (event.step && SUBSTEP_TO_CARD[event.step]) return SUBSTEP_TO_CARD[event.step];
  return event.step ?? event.node;
}

export const LANE_SEQ_CUST = ['router', 'intake', 'load_context', 'policy_retrieval', 'credit_calculator', 'decision', 'customer_response'];
export const LANE_SEQ_ANA = ['router', 'precedent_search', 'analyst_brief', 'negotiation', 'scenario_tools', 'research_tools', 'await_approval', 'persist_decision'];

export const BRANCH_CHIPS_CUST = [
  'intake incompleto → pedir dados',
  'auto_approved → resposta',
  'manual_review → fila do analista',
  'denied → resposta',
];
export const BRANCH_CHIPS_ANA = [
  'primeira abertura → dossiê',
  'novo cenário → volta à negociação',
  'decisão declarada → interrupt',
  'humano rejeita → não persiste',
];

export const CHECKPOINT_NOTE =
  'MongoDB Atlas · o LangGraph salva um checkpoint após cada superstep; a pausa humana também sobrevive no Atlas.';
