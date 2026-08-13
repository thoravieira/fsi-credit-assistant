// Real API client for the credit copilot demo — fetch() + manual SSE parsing.
// NOT EventSource: /api/chat is a POST with a JSON body, and EventSource only
// issues GET (see docs/specs/12-frontend.md §2). Contract: docs/specs/11-api-sse.md.
//
// Field names below are the backend's own — snake_case, taken verbatim from
// `backend/app/graph/state.py`, `backend/app/domain/{calculator,rules}.py` and
// `backend/app/agent/proposal.py`. No translation layer: what the network tab
// shows is what these types say.

export type Persona = 'customer' | 'analyst';
export type Outcome = 'auto_approved' | 'manual_review' | 'denied' | 'approved' | 'approved_with_conditions';
export type Product = 'mortgage' | 'auto';

export interface CalcResult {
  monthly_payment: number;
  total_interest: number;
  annual_rate: number;
  cet_annual: number;
  ltv: number;
  dti: number;
  schedule_preview?: Array<{ installment: number; payment: number; interest: number; amortization: number; balance: number }>;
}

// `resumo` — pre-formatted pt-BR strings from `domain/formatting.py`, quoted
// verbatim by the negotiation agent (see backend/app/graph/tools/scenario.py).
// Rendered as-is: reformatting them client-side would risk disagreeing with
// what the agent's own prose says about the same scenario.
export interface ScenarioResumo {
  entrada: string;
  valor_financiado: string;
  prazo_meses: number;
  parcela: string;
  ltv: string;
  comprometimento_renda: string;
  taxa_anual: string;
  cet_anual: string;
  juros_totais: string;
}

export interface Scenario {
  inputs: { asset_value?: number; amount: number; down_payment: number; term_months: number; annual_rate: number };
  calc: CalcResult;
  resumo: ScenarioResumo;
  outcome: Outcome;
  policy_refs: string[];
  reasons: string[];
  feasible?: boolean;
  target_dti?: number;
  constraint?: string;
  infeasible_reason?: string | null;
}

// Two producers, one shape (SDD 04 §2): the customer path's `domain/rules.py`
// writes `reasons`/`breached_rules`; the analyst path's human gate writes
// `rationale`/`scenario`/`precedent_refs`/`conditions`. Both are optional here
// because a given `Decision` only ever carries one producer's fields.
export interface Decision {
  outcome: Outcome;
  policy_refs: string[];
  reasons?: string[];
  breached_rules?: string[];
  scenario?: Scenario | null;
  rationale?: string;
  precedent_refs?: string[];
  conditions?: string[];
  application_id?: string;
}

// What `await_approval` hands to the human — built by `agent/proposal.py`,
// carried on `pending_approval` until `/api/approve` resumes the interrupt.
export interface PendingApproval {
  outcome: Outcome;
  application_id: string;
  scenario: Scenario | null;
  rationale: string;
  policy_refs: string[];
  precedent_refs: string[];
}

export interface CreditApplication {
  application_id: string;
  customer_id: string;
  product: Product;
  asset_value: number;
  down_payment: number;
  requested_amount: number;
  term_months: number;
  purpose: string;
  status?: string;
  latest_assessment?: { calc: CalcResult; decision: Decision } | null;
  final_decision?: Decision | null;
  contract_status?: 'contracted';
  contracted_at?: string;
  created_at?: string;
  updated_at?: string;
}

export interface TraceEvent {
  type: 'trace';
  node: string;
  status: 'started' | 'finished' | 'step' | 'interrupted';
  ts: number;
  ms?: number;
  step?: string;
  detail?: Record<string, unknown>;
}
export interface TokenEvent { type: 'token'; text: string }
export interface StateEvent {
  type: 'state';
  stage: string | null;
  calc: CalcResult | null;
  decision: Decision | null;
  pending_approval: PendingApproval | null;
  scenarios: Scenario[] | null;
}
export interface DoneEvent { type: 'done'; thread_id: string }
export type ChatStreamEvent = TraceEvent | TokenEvent | StateEvent | DoneEvent;

export interface SendChatInput {
  threadId: string;
  persona: Persona;
  message: string;
}

// ---------------------------------------------------------------------------
// fetch() + manual SSE frame parsing (docs/specs/12-frontend.md §2).
// Split the decoded buffer on \n\n; keep the trailing partial frame across
// reads, since chunks do not align to frame boundaries.
// ---------------------------------------------------------------------------
const BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

export async function* streamChat(input: SendChatInput): AsyncGenerator<ChatStreamEvent> {
  const res = await fetch(`${BASE_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thread_id: input.threadId, persona: input.persona, message: input.message }),
  });
  if (!res.ok || !res.body) throw new Error(`/api/chat failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? ''; // trailing partial frame — carried to the next read
    for (const frame of frames) {
      if (!frame.trim()) continue;
      const eventLine = frame.split('\n').find((l) => l.startsWith('event:'));
      const dataLine = frame.split('\n').find((l) => l.startsWith('data:'));
      if (!eventLine || !dataLine) continue;
      const type = eventLine.slice('event:'.length).trim();
      const data = JSON.parse(dataLine.slice('data:'.length).trim());
      yield { type, ...data } as ChatStreamEvent;
    }
  }
}

export interface CreateApplicationInput {
  customer_id: string;
  product: Product;
  asset_value: number;
  down_payment: number;
  term_months: number;
  purpose?: string;
}

export async function createApplication(input: CreateApplicationInput): Promise<string> {
  const res = await fetch(`${BASE_URL}/api/applications`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(`/api/applications failed: ${res.status}`);
  const body = await res.json();
  return body.application_id as string;
}

function normalizeApplication(doc: Record<string, any>): CreditApplication {
  return { ...doc, application_id: doc._id ?? doc.application_id } as CreditApplication;
}

export async function listApplications(filter?: { status?: string; customerId?: string }): Promise<CreditApplication[]> {
  const params = new URLSearchParams();
  if (filter?.status) params.set('status', filter.status);
  if (filter?.customerId) params.set('customer_id', filter.customerId);
  const qs = params.toString();
  const res = await fetch(`${BASE_URL}/api/applications${qs ? '?' + qs : ''}`);
  if (!res.ok) throw new Error(`/api/applications failed: ${res.status}`);
  const body = await res.json();
  // Server sorts by latest activity (`updated_at`) so customer and analyst
  // views both open the case that was actually touched most recently.
  return ((body.applications ?? []) as Record<string, any>[]).map(normalizeApplication);
}

export async function getApplication(applicationId: string): Promise<CreditApplication> {
  const res = await fetch(`${BASE_URL}/api/applications/${encodeURIComponent(applicationId)}`);
  if (!res.ok) throw new Error(`/api/applications/${applicationId} failed: ${res.status}`);
  return normalizeApplication(await res.json());
}

export interface HistoryMessage {
  role: 'user' | 'assistant';
  text: string;
}

// The real transcript for a thread, read back from the LangGraph checkpoint
// (`GET /api/history`) — not a local cache. `applications.latest_assessment`/
// `final_decision` only ever hold the *last* snapshot of each producer, so a
// case that has been both auto-assessed and analyst-approved, then
// re-simulated, needs its own current-vs-stale check — see `currentDecisionOf`.
export async function getHistory(threadId: string, persona?: Persona): Promise<HistoryMessage[]> {
  const params = new URLSearchParams();
  if (persona) params.set('persona', persona);
  const qs = params.toString();
  const res = await fetch(`${BASE_URL}/api/history/${encodeURIComponent(threadId)}${qs ? '?' + qs : ''}`);
  if (!res.ok) throw new Error(`/api/history/${threadId} failed: ${res.status}`);
  const body = await res.json();
  return (body.messages ?? []) as HistoryMessage[];
}

export async function contractApplication(threadId: string): Promise<{
  thread_id: string;
  contract_status: 'contracted';
  contracted_at: string;
}> {
  const res = await fetch(`${BASE_URL}/api/contract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thread_id: threadId }),
  });
  if (!res.ok) throw new Error(`/api/contract failed: ${res.status}`);
  return res.json();
}

// `applications.status` is the one field both producers (the automatic
// `decision` node and the analyst's `persist_decision`) always update
// together with their own decision object, so whichever object's `outcome`
// currently matches `status` is the live one — the other is a stale snapshot
// left over from before the most recent write. A customer re-simulating on an
// already-approved thread is exactly the case this resolves (SDD 04 §2 has no
// single "current decision" field — this is the client-side rule for it).
export function currentDecisionOf(app: CreditApplication): Decision | null {
  if (!app.status) return null;
  if (app.final_decision?.outcome === app.status) return app.final_decision;
  if (app.latest_assessment?.decision?.outcome === app.status) return app.latest_assessment.decision;
  return app.final_decision ?? app.latest_assessment?.decision ?? null;
}

export async function approve(
  threadId: string,
  resume: Record<string, unknown>
): Promise<{ stage: string; decision: Decision }> {
  const res = await fetch(`${BASE_URL}/api/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thread_id: threadId, resume }),
  });
  if (!res.ok) throw new Error(`/api/approve failed: ${res.status}`);
  return res.json();
}

export interface HealthResponse {
  connected: boolean;
  indexes: Record<string, { exists: boolean; queryable: boolean; error?: string }>;
}

export async function health(): Promise<HealthResponse> {
  const res = await fetch(`${BASE_URL}/api/health`);
  if (!res.ok) throw new Error(`/api/health failed: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Display-only helpers. No decision math lives here — `domain/calculator.py`
// and `domain/rules.py` are the only places that compute a number (CLAUDE.md).
// `previewFinanced`/`previewLtv` are the two derived figures shown under
// Mariana's sliders *before* she submits — pure arithmetic, not a decision.
// ---------------------------------------------------------------------------
export function previewFinanced(assetValue: number, downPayment: number): number {
  return Math.max(assetValue - downPayment, 0);
}
export function previewLtv(assetValue: number, downPayment: number): number {
  return assetValue > 0 ? previewFinanced(assetValue, downPayment) / assetValue : 0;
}
export function fmtBRL(v: number): string {
  return 'R$ ' + v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
// Whole-reais display for form fields (sliders, headline amounts) — the
// design's `fmtBRL0`; `fmtBRL` (with cents) stays for money the customer
// actually sees quoted back in prose.
export function fmtBRL0(v: number): string {
  return 'R$ ' + v.toLocaleString('pt-BR', { maximumFractionDigits: 0 });
}
export function fmtPct(v: number): string {
  return (v * 100).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + '%';
}

// Seeded customer directory (data/profiles/profiles.json) — display-only name
// lookup. There is no join endpoint over `applications.customer_id`, and
// adding one is out of scope for SDD 11 §1's fixed endpoint list.
export const CUSTOMER_NAMES: Record<string, string> = {
  'CUST-0001': 'Mariana Duarte',
  'CUST-0002': 'Rafael Nascimento Souza',
  'CUST-0003': 'Eliane Cristina Ferreira',
  'CUST-0004': 'Bruno Carvalho Lima',
  'CUST-0005': 'Camila Ribeiro Alves',
  'CUST-0006': 'Diego Fernandes Costa',
  'CUST-0007': 'Patrícia Gomes Martins',
  'CUST-0008': 'Thiago Almeida Rocha',
  'CUST-0009': 'Juliana Barbosa Pinto',
  'CUST-0010': 'Marcos Vinícius Teixeira',
  'CUST-0011': 'Fernanda Cardoso Dias',
  'CUST-0012': 'Rodrigo Santos Pereira',
  'CUST-0013': 'Aline Cristina Souza',
  'CUST-0014': 'Gustavo Henrique Moreira',
  'CUST-0015': 'Larissa Mendes Azevedo',
  'CUST-0016': 'Felipe Augusto Nogueira',
  'CUST-0017': 'Beatriz Correia Lopes',
  'CUST-0018': 'Leonardo Batista Cunha',
  'CUST-0019': 'Renata Oliveira Castro',
  'CUST-0020': 'Eduardo Ferreira Nunes',
  'CUST-0021': 'Vanessa Lima Rezende',
  'CUST-0022': 'Alexandre Pires Monteiro',
  'CUST-0023': 'Débora Santana Ramos',
  'CUST-0024': 'Paulo Roberto Andrade',
  'CUST-0025': 'Isabela Rocha Guimarães',
  'CUST-0026': 'Vinícius Martins Cavalcanti',
  'CUST-0027': 'Tatiane Aparecida Silveira',
  'CUST-0028': 'Ricardo Nunes Barreto',
  'CUST-0029': 'Simone Cristina Vasconcelos',
  'CUST-0030': 'André Luiz Ferreira Cordeiro',
};

export const PRODUCT_LABELS: Record<string, string> = {
  mortgage: 'Financiamento imobiliário',
  auto: 'Financiamento de veículo',
};

export const OUTCOME_LABELS: Record<string, string> = {
  auto_approved: 'Aprovado automaticamente',
  approved: 'Aprovado',
  approved_with_conditions: 'Aprovado com condições',
  manual_review: 'Em análise manual',
  denied: 'Reprovado',
};

// Real policy corpus (data/policies/*.md), title + first paragraph — not a
// paraphrase. There is no `/api/policies/{id}` endpoint (SDD 11 §1 is the
// fixed contract), so this is the only way `policy_refs` chips can expand to
// the actual cited text rather than to an ID with nothing behind it.
export const POLICY_TEXT: Record<string, { title: string; body: string }> = {
  'POL-001': { title: 'Limite de LTV para financiamento imobiliário residencial', body: 'O valor financiado em operações de financiamento imobiliário residencial não poderá exceder 80% (oitenta por cento) do valor de avaliação do imóvel, conforme laudo de avaliação aceito pelo banco, na modalidade dentro do Sistema Financeiro de Habitação (SFH). Isso implica uma entrada mínima de 20% do valor de avaliação, seja em recursos próprios, seja em saldo de FGTS elegível. Propostas de financiamento imobiliário com LTV solicitado acima de 80% devem ser recusadas automaticamente pelo sistema, sem passar por análise manual, salvo quando houver garantia adicional aprovada conforme a política de garantia complementar (POL-014). O limite de 80% se aplica ao valor total financiado, incluindo eventuais custos de registro e ITBI quando embutidos na operação.' },
  'POL-002': { title: 'Limite de LTV para financiamento de veículo novo', body: 'Para financiamento de veículos novos (zero quilômetro), o valor financiado não poderá exceder 90% (noventa por cento) do valor da nota fiscal do veículo. A entrada mínima exigida é, portanto, de 10% do valor do bem. Esse limite de LTV mais alto em relação ao financiamento imobiliário reflete o prazo mais curto das operações de veículo e a maior liquidez do bem como garantia em caso de retomada. Propostas de financiamento de veículo novo com LTV solicitado acima de 90% são recusadas automaticamente pelo sistema. Clientes com score interno abaixo de 600 têm o LTV máximo reduzido para 80%, independentemente do veículo ser novo, conforme a política de faixas de score (POL-009).' },
  'POL-003': { title: 'Limite de LTV para financiamento de veículo usado', body: 'Para financiamento de veículos usados, o valor financiado não poderá exceder 80% (oitenta por cento) do valor de referência da tabela FIPE na data da proposta. A entrada mínima exigida é de 20% do valor do veículo. Esse limite mais conservador em relação ao veículo novo reflete a depreciação mais rápida e a maior variabilidade de estado de conservação de veículos usados como garantia. Veículos usados com mais de 10 anos de fabricação têm o LTV máximo adicionalmente reduzido para 70%, e veículos com mais de 15 anos não são aceitos como garantia de financiamento de veículo sob esta política. Propostas fora desses limites são recusadas automaticamente pelo sistema.' },
  'POL-004': { title: 'Comprometimento de renda máximo para financiamento imobiliário', body: 'O comprometimento de renda (DTI — relação entre a parcela mensal do financiamento somada às dívidas existentes e a renda líquida mensal comprovada) não pode exceder 30% para aprovação automática de financiamento imobiliário residencial. Propostas com DTI entre 30% e 40% podem ser aprovadas mediante análise manual do analista de crédito, desde que existam fatores compensatórios como relacionamento bancário de longa data, score interno elevado ou compartilhamento de ativos via Open Finance (ver POL-016). Propostas com DTI acima de 40% são reprovadas automaticamente pelo sistema, independentemente de outros fatores, por representarem risco de superendividamento incompatível com a política de crédito responsável do banco.' },
  'POL-005': { title: 'Comprometimento de renda máximo para financiamento de veículo', body: 'Para financiamento de veículo, o comprometimento de renda (DTI) não pode exceder 35% para aprovação automática, limite mais permissivo do que o aplicado ao financiamento imobiliário (POL-004) em razão do prazo tipicamente mais curto das operações de veículo. Propostas com DTI entre 35% e 45% podem ser aprovadas em análise manual, condicionadas a fatores compensatórios como avalista (POL-015) ou score interno elevado. Propostas com DTI acima de 45% são reprovadas automaticamente. O cálculo do DTI para financiamento de veículo considera a parcela do novo financiamento somada a todas as dívidas mensais recorrentes já existentes do cliente, dividida pela renda líquida mensal comprovada.' },
  'POL-006': { title: 'Limite de idade somada ao prazo para financiamento imobiliário', body: 'A idade do cliente titular, somada ao prazo do financiamento imobiliário em anos, não pode ultrapassar 80 anos ao final do contrato. Por exemplo, um cliente com 55 anos de idade só pode contratar um financiamento imobiliário com prazo máximo de 300 meses (25 anos). Esse limite existe para manter a exigibilidade do seguro MIP (Morte e Invalidez Permanente) durante toda a vigência do contrato, já que seguradoras parceiras não emitem apólice para segurados acima dessa idade. Propostas que excedam o limite de idade mais prazo devem ser ajustadas — reduzindo o prazo solicitado ou incluindo um coobrigado mais jovem — antes de seguir para análise de crédito.' },
  'POL-007': { title: 'Limite de idade somada ao prazo para financiamento de veículo', body: 'A idade do cliente titular, somada ao prazo do financiamento de veículo em anos, não pode ultrapassar 80 anos ao final do contrato — a mesma regra aplicada ao financiamento imobiliário (POL-006), pelos mesmos motivos ligados à exigibilidade do seguro do veículo financiado. Como os prazos de financiamento de veículo são tipicamente mais curtos (até 60 meses, ou 5 anos), essa restrição raramente é o fator limitante nesse produto, mas ainda assim deve ser verificada automaticamente pelo sistema no momento da simulação. Propostas que excedam o limite devem ter o prazo reduzido antes de prosseguir, sem necessidade de análise manual adicional apenas por esse motivo.' },
  'POL-008': { title: 'Faixas de score interno para financiamento imobiliário', body: 'Para financiamento imobiliário, clientes com score interno igual ou superior a 750 têm acesso à faixa de taxa base, sem exigências adicionais de garantia. Clientes com score entre 650 e 749 são enquadrados na faixa padrão, com acréscimo de spread conforme a tabela de taxas por LTV e score (POL-018). Clientes com score interno abaixo de 650 só podem ter a proposta aprovada mediante análise manual e exigência de garantia adicional (POL-014) ou fatores compensatórios relevantes, como relacionamento bancário superior a 5 anos com portabilidade de salário ativa. O score interno combina o score de bureau externo com o histórico de relacionamento do cliente com o banco.' },
  'POL-009': { title: 'Faixas de score interno para financiamento de veículo', body: 'Para financiamento de veículo, clientes com score interno igual ou superior a 700 têm acesso à faixa de taxa base. Clientes com score entre 600 e 699 são enquadrados na faixa padrão, com acréscimo de spread conforme a tabela de taxas por LTV e score (POL-019). Clientes com score interno abaixo de 600 só podem ter a proposta aprovada mediante inclusão de avalista com renda comprovada e score interno igual ou superior a 750 (POL-015), e ainda assim com o LTV máximo reduzido para 80% mesmo em veículos novos (POL-002). As faixas de score para veículo são mais baixas que as de financiamento imobiliário porque o ticket médio e o prazo da operação são menores, reduzindo a exposição de risco do banco.' },
  'POL-010': { title: 'Uso do FGTS para composição da entrada', body: 'O saldo do FGTS (Fundo de Garantia do Tempo de Serviço) pode ser utilizado para composição da entrada em financiamento imobiliário residencial dentro do Sistema Financeiro de Habitação (SFH), desde que o imóvel tenha valor de avaliação de até R$ 1.500.000,00. São condições adicionais: o cliente não pode ter outro financiamento ativo pelo SFH em qualquer instituição, o imóvel deve ser destinado à moradia própria, e o cliente deve ter no mínimo 3 anos de trabalho sob o regime do FGTS, consecutivos ou não. O valor do FGTS utilizado na entrada é somado aos recursos próprios do cliente para fins de cálculo do LTV efetivo da operação (POL-001).' },
  'POL-011': { title: 'Uso do FGTS para amortização extraordinária', body: 'Além do uso na entrada (POL-010), o saldo do FGTS pode ser utilizado para amortização extraordinária do saldo devedor de financiamento imobiliário já contratado, reduzindo o valor da parcela ou o prazo restante, a critério do cliente. Essa modalidade de uso está limitada a uma solicitação a cada 24 meses, e o cliente deve comprovar que o imóvel financiado é o único imóvel residencial em seu nome. O valor mínimo de amortização extraordinária via FGTS é de R$ 5.000,00 por solicitação. Diferentemente do uso na entrada, a amortização extraordinária não exige que o financiamento esteja dentro do SFH, podendo ser aplicada também a financiamentos fora desse sistema, desde que o imóvel seja residencial.' },
  'POL-012': { title: 'Comprovação de renda para autônomos em financiamento imobiliário', body: 'Clientes autônomos sem holerite, que solicitam financiamento imobiliário, devem comprovar renda por meio de DECORE (Declaração Comprobatória de Percepção de Rendimentos) emitida e assinada por contador registrado no CRC, referente aos últimos 12 meses, acompanhada dos extratos bancários da conta PJ ou PF utilizada para recebimento nos últimos 6 meses. Alternativamente, aceita-se a declaração de Imposto de Renda Pessoa Física completa do último exercício, desde que compatível com os extratos apresentados. A renda considerada para cálculo do DTI (POL-004) é a média dos últimos 12 meses, e não o valor do mês mais recente, para suavizar sazonalidades típicas de rendimento autônomo.' },
  'POL-013': { title: 'Comprovação de renda para autônomos em financiamento de veículo', body: 'Para financiamento de veículo, clientes autônomos podem comprovar renda com documentação simplificada em relação ao financiamento imobiliário (POL-012), dado o ticket médio menor da operação: extratos bancários dos últimos 3 meses da conta de recebimento principal, somados a uma declaração simples de rendimentos assinada pelo próprio cliente, sem necessidade de DECORE assinada por contador para propostas de até R$ 60.000,00. Acima desse valor, aplica-se a mesma exigência de DECORE do financiamento imobiliário. A renda considerada para cálculo do DTI (POL-005) é a média dos últimos 3 meses de extratos apresentados.' },
  'POL-014': { title: 'Garantia adicional para financiamento imobiliário fora dos limites automáticos', body: 'Quando o LTV solicitado excede o limite automático de 80% (POL-001) ou o score interno do cliente está abaixo de 650 (POL-008), o analista de crédito pode aceitar a alienação fiduciária de um imóvel adicional já quitado, em nome do próprio cliente ou de coobrigado, como garantia complementar da operação. O imóvel adicional deve ter valor de avaliação suficiente para que a soma das garantias cubra ao menos 90% do valor total financiado. Essa garantia complementar não elimina a necessidade de análise manual, mas é um fator compensatório relevante que pode viabilizar a aprovação de propostas que seriam recusadas automaticamente pelo sistema.' },
  'POL-015': { title: 'Avalista como garantia adicional para financiamento de veículo', body: 'Quando o score interno do cliente está abaixo de 600 (POL-009) ou o DTI calculado excede o limite automático de 35% (POL-005), o analista de crédito pode aceitar a inclusão de um avalista como condição para aprovação do financiamento de veículo. O avalista deve ter renda própria comprovada, score interno igual ou superior a 750, e não pode ter nenhuma restrição de crédito ativa nos últimos 24 meses. A inclusão de avalista qualificado é considerada fator compensatório suficiente para aprovar em análise manual propostas que seriam recusadas automaticamente pelo sistema apenas por score ou DTI, desde que os demais critérios (LTV, idade mais prazo) estejam dentro dos limites normais.' },
  'POL-016': { title: 'Compartilhamento de dados via Open Finance como mitigador de risco', body: 'Clientes de financiamento imobiliário que autorizam o compartilhamento de dados financeiros via Open Finance, evidenciando ativos líquidos (investimentos em CDB, tesouro direto, fundos de liquidez diária ou D+30) em valor igual ou superior a 20% do valor solicitado no financiamento, podem ter propostas com DTI entre 30% e 40% (POL-004) aprovadas em análise manual mesmo sem outros fatores compensatórios adicionais. Os ativos compartilhados funcionam como colchão de liquidez que reduz o risco de inadimplência em caso de oscilação temporária de renda, e são um argumento explícito que o analista deve registrar na justificativa da decisão quando utilizados como mitigador.' },
  'POL-017': { title: 'Compartilhamento de dados via Open Finance para financiamento de veículo', body: 'Para financiamento de veículo, o mesmo princípio do mitigador de Open Finance aplicado ao financiamento imobiliário (POL-016) vale com um limiar menor: ativos líquidos compartilhados em valor igual ou superior a 15% do valor solicitado já são suficientes para viabilizar análise manual de propostas com DTI entre 35% e 45% (POL-005), dado o ticket médio menor da operação. O consentimento de Open Finance é sempre uma ação explícita do cliente, nunca presumida, e pode ser solicitado pelo analista durante a negociação como alternativa à exigência de avalista (POL-015) quando o cliente possui reserva financeira mas prefere não incluir um terceiro na operação.' },
  'POL-018': { title: 'Tabela de taxas por LTV e score para financiamento imobiliário', body: 'A taxa anual de financiamento imobiliário é composta pela taxa base de 9,8% ao ano, acrescida de spread conforme a combinação de LTV e score interno do cliente. Para LTV até 60% e score igual ou superior a 750, aplica-se apenas a taxa base. Para LTV entre 60% e 80% com score entre 650 e 749, aplica-se um spread adicional de 1,5 ponto percentual. Para LTV entre 60% e 80% com score igual ou superior a 750, o spread adicional é reduzido para 0,8 ponto percentual. Propostas fora dessas combinações (LTV acima de 80% ou score abaixo de 650) não têm taxa tabelada automática e dependem de aprovação manual com taxa definida caso a caso pelo comitê de crédito.' },
  'POL-019': { title: 'Tabela de taxas por LTV e score para financiamento de veículo', body: 'A taxa anual de financiamento de veículo é composta pela taxa base de 14,5% ao ano — mais alta que a do financiamento imobiliário (POL-018) por não haver garantia real de mesma liquidez — acrescida de spread conforme LTV e score. Para LTV até 70% e score igual ou superior a 700, aplica-se apenas a taxa base. Para LTV entre 70% e 90% com score entre 600 e 699, aplica-se spread adicional de 2,5 pontos percentuais. Para LTV entre 70% e 90% com score igual ou superior a 700, o spread adicional é de 1,2 ponto percentual. Veículos usados com mais de 5 anos de fabricação têm spread adicional de 0,5 ponto percentual sobre qualquer combinação de LTV e score.' },
  'POL-020': { title: 'Alçadas de aprovação para financiamento imobiliário', body: 'Propostas de financiamento imobiliário com valor solicitado até R$ 300.000,00, LTV igual ou inferior a 70% e DTI igual ou inferior a 30% são aprovadas automaticamente pelo sistema, sem intervenção humana. Propostas acima desse valor, ou fora desses limites de LTV e DTI mas ainda dentro dos limites máximos absolutos (POL-001, POL-004), exigem análise manual do analista de crédito, com alçada de aprovação de até R$ 800.000,00. Propostas acima de R$ 800.000,00, ou que envolvam qualquer exceção de política (garantia adicional, LTV no limite máximo, DTI no limite máximo), exigem aprovação do comitê de crédito, não podendo ser decididas unicamente pelo analista.' },
  'POL-021': { title: 'Alçadas de aprovação para financiamento de veículo', body: 'Propostas de financiamento de veículo com valor solicitado até R$ 80.000,00, LTV igual ou inferior a 80% e DTI igual ou inferior a 35% são aprovadas automaticamente pelo sistema. Propostas acima desse valor, ou fora desses limites de LTV e DTI mas ainda dentro dos limites máximos absolutos (POL-002, POL-003, POL-005), exigem análise manual do analista de crédito, com alçada de aprovação de até R$ 200.000,00. Propostas acima de R$ 200.000,00, ou que envolvam qualquer exceção de política, exigem aprovação do comitê de crédito. Essas alçadas são revisadas semestralmente pelo comitê de crédito com base no volume e na inadimplência da carteira de veículos.' },
  'POL-022': { title: 'Restrição a imóveis em processo de inventário', body: 'Imóveis que estejam em processo de inventário (sucessão hereditária ainda não concluída) não podem ser aceitos como garantia em operações de financiamento imobiliário, seja como imóvel objeto do financiamento, seja como garantia adicional (POL-014). A restrição existe porque a titularidade do imóvel permanece indefinida até a conclusão do inventário e a emissão do formal de partilha devidamente registrado em cartório de registro de imóveis. Propostas envolvendo imóveis nessa situação devem ser recusadas automaticamente pelo sistema no momento da análise documental, independentemente de qualquer outro fator de crédito do cliente estar dentro dos limites normais. Esta é uma restrição documental, não uma restrição de crédito.' },
  'POL-023': { title: 'Exceção à restrição de inventário mediante alvará judicial', body: 'A restrição a imóveis em inventário (POL-022) admite uma única exceção: quando existe alvará judicial expresso autorizando a venda ou oneração do imóvel antes da conclusão do processo de inventário, emitido pelo juízo responsável. Nesse caso, a proposta pode ser reencaminhada para análise jurídica específica do comitê de crédito, que avaliará a validade e o alcance do alvará junto ao departamento jurídico do banco antes de qualquer decisão de crédito. Essa exceção nunca é aprovada automaticamente pelo sistema nem pelo analista isoladamente — exige sempre parecer jurídico documentado e aprovação do comitê de crédito, dado o risco residual de contestação da partilha por outros herdeiros.' },
  'POL-024': { title: 'Entrada mínima para financiamento imobiliário', body: 'A entrada mínima exigida para financiamento imobiliário residencial é de 20% do valor de avaliação do imóvel, decorrência direta do limite máximo de LTV de 80% (POL-001). A entrada pode ser composta por recursos próprios do cliente, saldo de FGTS elegível (POL-010), ou uma combinação de ambos. Não é permitido financiar a entrada por meio de outro produto de crédito do próprio banco, como empréstimo pessoal ou cartão de crédito, sob pena de descaracterizar o cálculo real de LTV da operação e violar as normas do Conselho Monetário Nacional aplicáveis ao Sistema Financeiro de Habitação. O comprovante de origem dos recursos da entrada é exigido na formalização do contrato.' },
  'POL-025': { title: 'Entrada mínima para financiamento de veículo', body: 'A entrada mínima para financiamento de veículo novo é de 10% do valor da nota fiscal, e para veículo usado é de 20% do valor de referência da tabela FIPE, decorrência direta dos limites máximos de LTV por tipo de veículo (POL-002, POL-003). A entrada pode ser composta por recursos próprios do cliente ou pelo valor de um veículo usado dado como parte do pagamento (troca), desde que o veículo entregue seja avaliado por um avaliador credenciado do banco e o valor de avaliação seja utilizado, não o valor pretendido pelo cliente. Não é permitido compor a entrada com outro produto de crédito do banco.' },
  'POL-026': { title: 'Seguro obrigatório MIP e DFI para financiamento imobiliário', body: 'Todo financiamento imobiliário residencial exige a contratação obrigatória de dois seguros durante toda a vigência do contrato: o seguro MIP (Morte e Invalidez Permanente do Segurado), que garante a quitação do saldo devedor em caso de morte ou invalidez permanente do titular, e o seguro DFI (Danos Físicos ao Imóvel), que cobre danos estruturais ao imóvel dado em garantia. Ambos os seguros são cobrados junto com a parcela mensal do financiamento e seu valor é considerado no cálculo do CET (Custo Efetivo Total) da operação, mas não entra no cálculo de DTI (POL-004), que considera apenas principal e juros. A ausência de pagamento do seguro por dois meses consecutivos caracteriza inadimplência contratual.' },
  'POL-027': { title: 'Seguro obrigatório para veículo financiado', body: 'Todo veículo financiado com alienação fiduciária ao banco deve manter seguro com cobertura compreensiva (colisão, roubo, furto e incêndio) durante toda a vigência do contrato, com o banco constando como beneficiário em caso de perda total. O cliente pode contratar a apólice com a seguradora de sua preferência, não sendo obrigatória a contratação com a seguradora parceira do banco, desde que a cobertura mínima exigida seja comprovada anualmente. A ausência de comprovação de seguro vigente autoriza o banco a contratar apólice em nome do cliente e cobrar o prêmio na parcela seguinte, conforme previsto em contrato. Veículos com mais de 10 anos podem ter dificuldade de contratação e devem ser avaliados caso a caso pelo analista.' },
  'POL-028': { title: 'Refinanciamento com garantia imobiliária (home equity)', body: 'Clientes que possuem imóvel residencial já quitado, ou com saldo devedor reduzido de financiamento anterior, podem solicitar refinanciamento com garantia imobiliária (home equity), oferecendo o próprio imóvel como garantia para obter crédito com finalidade livre. O LTV máximo para essa modalidade é de 60% sobre o valor de avaliação atual do imóvel, mais conservador que o limite do financiamento de aquisição (POL-001) por se tratar de operação com finalidade não vinculada à compra do bem. A análise de DTI segue os mesmos limites do financiamento imobiliário tradicional (POL-004). O prazo máximo é de 240 meses, e a idade somada ao prazo segue o mesmo limite de 80 anos (POL-006).' },
  'POL-029': { title: 'Troca de veículo financiado com saldo devedor', body: 'Clientes que desejam trocar um veículo ainda financiado antes da quitação total devem solicitar a portabilidade do saldo devedor para o veículo substituto, o que exige nova avaliação de LTV considerando o valor do saldo devedor remanescente somado ao complemento necessário para adquirir o novo veículo, sobre o valor de avaliação do veículo substituto. Se o LTV resultante ultrapassar os limites normais de financiamento de veículo (POL-002, POL-003), a operação exige análise manual mesmo que a proposta original tivesse sido aprovada automaticamente. O veículo entregue como parte do pagamento deve estar livre de outras restrições além do próprio financiamento sendo quitado.' },
  'POL-030': { title: 'Comprovação de renda variável e comissionados', body: 'Clientes com renda variável ou majoritariamente composta por comissões, mesmo quando formalmente registrados em regime CLT, devem comprovar renda por meio dos últimos 12 contracheques ou informe de rendimentos, com a renda considerada para cálculo de DTI (POL-004) sendo a média dos últimos 12 meses, aplicando-se um desconto de 20% sobre essa média para absorver a volatilidade típica de rendimentos variáveis. Esse desconto de 20% é adicional a qualquer verificação normal de renda e não se aplica a clientes CLT com salário fixo. O objetivo é evitar superestimar a capacidade de pagamento de clientes cuja renda pode oscilar significativamente entre meses de alta e baixa performance comercial.' },
};
