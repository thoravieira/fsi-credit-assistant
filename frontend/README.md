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
├── page.tsx            /          Mariana
├── console/page.tsx    /console   Carlos
└── layout.tsx                     seletor de persona
components/
├── TracePanel.tsx      arquitetura + trace — compartilhado, ao vivo
├── ChatThread.tsx
├── ScenarioTable.tsx   cenários acumulados da negociação
├── CaseQueue.tsx
├── DecisionCard.tsx    resultado + motivos/rationale + citações de política
└── PersonaNav.tsx       destaque da rota ativa no cabeçalho
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

## Pendências conhecidas

- Sem autenticação — fora do escopo da demo.
- `GET /api/trace/{thread_id}` (histórico de `decisions_log`) não está
  plugado na UI — não é um critério de aceite da SDD 12, e o trace ao vivo já
  cobre o que a demo precisa mostrar.
- A fila do console não atualiza sozinha entre abas abertas simultaneamente;
  ela recarrega ao entrar em `/console` e ao voltar da tela de um caso.
