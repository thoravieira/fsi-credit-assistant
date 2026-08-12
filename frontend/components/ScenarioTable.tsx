import type { Scenario } from '../lib/api';
import { OUTCOME_LABELS } from '../lib/api';

// Accumulates across a negotiation without a page reload — `AgentState.scenarios`
// uses `operator.add` (docs/specs/04-graph-state.md §2) and the backend now
// returns the full accumulated list in the `state` event (docs/specs/11-api-sse.md
// §2). Every column below is the agent's own pre-formatted `resumo` string
// (backend/app/graph/tools/scenario.py) — never recomputed client-side.
export function ScenarioTable({ scenarios }: { scenarios: Scenario[] }) {
  if (!scenarios.length) return null;
  const ok = (s: Scenario) => s.outcome === 'auto_approved' || s.outcome.startsWith('approved');
  return (
    <div className="overflow-hidden border border-ink/[0.14]">
      <div className="border-b border-ink/[0.14] px-3.5 py-2.5 text-[13px] font-extrabold">Cenários negociados</div>
      <table className="w-full border-collapse text-[12px]">
        <thead>
          <tr className="text-[9.5px] uppercase tracking-wide text-ink/50">
            <th className="border-b border-ink/[0.14] px-2.5 py-2 text-left">#</th>
            <th className="border-b border-ink/[0.14] px-2.5 py-2 text-left">Entrada · prazo</th>
            <th className="border-b border-ink/[0.14] px-2.5 py-2 text-right">Parcela</th>
            <th className="border-b border-ink/[0.14] px-2.5 py-2 text-right">LTV</th>
            <th className="border-b border-ink/[0.14] px-2.5 py-2 text-right">DTI</th>
            <th className="border-b border-ink/[0.14] px-2.5 py-2 text-left">Parecer</th>
          </tr>
        </thead>
        <tbody>
          {scenarios.map((s, i) => (
            <tr key={i}>
              <td className="border-b border-ink/[0.08] px-2.5 py-2 text-ink/50">{i + 1}</td>
              <td className="border-b border-ink/[0.08] px-2.5 py-2 font-semibold">
                {s.resumo.entrada} · {s.resumo.prazo_meses} meses
              </td>
              <td className="border-b border-ink/[0.08] px-2.5 py-2 text-right font-mono">{s.resumo.parcela}</td>
              <td className="border-b border-ink/[0.08] px-2.5 py-2 text-right font-mono">{s.resumo.ltv}</td>
              <td className="border-b border-ink/[0.08] px-2.5 py-2 text-right font-mono">{s.resumo.comprometimento_renda}</td>
              <td className="border-b border-ink/[0.08] px-2.5 py-2">
                <span className={'px-2 py-0.5 text-[10px] font-bold ' + (ok(s) ? 'bg-spring/20 text-forest' : 'bg-ink/[0.08] text-ink')}>
                  {OUTCOME_LABELS[s.outcome] ?? s.outcome}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
