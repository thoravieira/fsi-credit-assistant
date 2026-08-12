# Copiloto de Crédito PF — frontend

Next.js (App Router) + Tailwind, sem biblioteca de componentes. Uma aplicação,
duas rotas, componentes compartilhados — ver `docs/specs/12-frontend.md`.

## Rodando localmente

```
npm install
npm run dev
```

- `http://localhost:3000` — Mariana (cliente): simulação + chat + trace colapsada.
- `http://localhost:3000/console` — Carlos (analista): fila + caso + negociação + trace em destaque.

Requer o backend rodando em `http://localhost:8000` (`cd ../backend && make dev`,
ou `docker compose up` na raiz do repo). Para apontar para outra URL, defina
`NEXT_PUBLIC_API_URL` (o mesmo nome usado em `.env.example` na raiz do repo)
antes de `npm run build` — é inlinada no bundle do cliente em tempo de build,
não lida em runtime.

## Estrutura

```
app/
├── page.tsx             /          Mariana
├── console/page.tsx     /console   Carlos
└── layout.tsx                      seletor de persona
components/
├── AppShell.tsx          casco de duas colunas (44% persona / 56% arquitetura+trace)
├── RightPane.tsx          coluna direita compartilhada — arquitetura + trace, com
│                          divisor arrastável entre os dois (proporção salva em localStorage)
├── ArchitecturePanel.tsx "Fluxo em tempo real" — swimlanes por executor, ao vivo
├── TraceLog.tsx           "Trace ao vivo" — eventos SSE brutos
├── ChatThread.tsx
├── ScenarioTable.tsx     cenários acumulados da negociação
├── CaseQueue.tsx
├── DecisionCard.tsx      resultado + motivos/rationale + citações de política
├── CustomerApp.tsx        conteúdo de Mariana dentro do mockup de iPhone
├── IOSDevice.tsx           moldura de iPhone reutilizável
├── Drawer.tsx              painel de detalhe ao clicar num node/linha do trace
└── PersonaHeader.tsx     cabeçalho com alternância Cliente/Analista (navegação real, não toggle de estado)
hooks/useAgentStream.ts SSE — consumo real (fetch + ReadableStream)
lib/api.ts               cliente HTTP, tipos e diretório de políticas/clientes
```

## O contrato real, não um mock

Não há mock neste frontend — `lib/api.ts` fala diretamente com os endpoints de
`docs/specs/11-api-sse.md`. Os tipos em `lib/api.ts` (`CalcResult`, `Decision`,
`Scenario`, `PendingApproval`) usam os mesmos nomes de campo em snake_case que
`backend/app/graph/state.py` e `backend/app/domain/{calculator,rules}.py` —
sem camada de tradução, o que a aba de rede mostra é o que os tipos dizem.

`streamChat()` usa `fetch()` + `ReadableStream` com parsing manual de frames
SSE (buffer de frame parcial entre chunks). **Não usa `EventSource`** —
`/api/chat` é `POST`, e `EventSource` só faz `GET` (docs/specs/12-frontend.md §2).

`POLICY_TEXT` (em `lib/api.ts`) é o texto real de `data/policies/*.md` — não
uma paráfrase — porque não existe endpoint `GET /api/policies/{id}` no
contrato fixo da SDD 11 §1. É a única forma dos chips de `policy_refs`
expandirem para o texto realmente citado.

Não há persistência local do histórico de conversa: a tela de Mariana sempre
abre no formulário de simulação, e um ícone dedicado chama `getHistory()`
(`GET /api/history/{thread_id}`) para carregar a transcrição real a partir do
checkpoint do LangGraph, buscada do MongoDB a cada clique — nunca de cache.

## Pendências conhecidas

- Sem autenticação — fora do escopo da demo.
- A fila do console não atualiza sozinha entre abas abertas simultaneamente;
  ela recarrega ao entrar em `/console` e ao voltar da tela de um caso.
