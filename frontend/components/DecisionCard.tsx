'use client';
import { useState } from 'react';
import { Decision, OUTCOME_LABELS, POLICY_TEXT } from '../lib/api';

// Shared by both routes: Mariana sees it standalone after a simulation,
// Carlos sees it inside the case detail panel. Two producers write `Decision`
// (SDD 04 §2): `domain/rules.py` on the customer path gives `reasons`, the
// negotiation human gate gives `rationale` — never both, so both render paths
// are handled here rather than assuming one shape.
export function DecisionCard({ decision }: { decision: Decision }) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const ok = decision.outcome === 'auto_approved' || decision.outcome.startsWith('approved');

  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-white p-4 shadow-[0_10px_26px_rgba(0,30,43,0.09)]">
      <div className="flex items-center justify-between">
        <span className="text-sm font-extrabold text-ink">Resultado</span>
        <span className={'rounded-full px-3 py-1 text-[11px] font-extrabold ' + (ok ? 'bg-spring/[0.15] text-forest' : 'bg-ink/[0.08] text-ink')}>
          {OUTCOME_LABELS[decision.outcome] ?? decision.outcome}
        </span>
      </div>

      <div className="flex flex-col gap-1.5">
        {decision.reasons?.map((r, i) => (
          <p key={i} className="flex gap-1.5 text-[12.5px] leading-relaxed text-ink/75">
            <span className="text-forest">—</span>{r}
          </p>
        ))}
        {decision.rationale && !decision.reasons?.length && (
          <p className="text-[12.5px] leading-relaxed text-ink/75">{decision.rationale}</p>
        )}
        {decision.conditions?.map((c, i) => (
          <p key={'c' + i} className="flex gap-1.5 text-[12.5px] leading-relaxed text-ink/75">
            <span className="text-forest">—</span>Condição: {c}
          </p>
        ))}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {decision.policy_refs.map((id) => {
          const pol = POLICY_TEXT[id];
          const isOpen = !!expanded[id];
          return (
            <div key={id}>
              <button
                onClick={() => setExpanded((s) => ({ ...s, [id]: !s[id] }))}
                className={'rounded-full border border-forest px-2.5 py-1 text-[10.5px] font-bold ' + (isOpen ? 'bg-forest text-white' : 'bg-forest/10 text-forest')}
              >
                {id}
              </button>
              {isOpen && pol && (
                <div className="mt-1.5 rounded-lg bg-[#F1F2F4] p-2.5 text-[11.5px] leading-relaxed text-ink/75">
                  <b className="text-ink">{pol.title}</b>
                  <br />
                  {pol.body}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {decision.precedent_refs && decision.precedent_refs.length > 0 && (
        <div className="border-t border-ink/10 pt-2 text-[11px] text-ink/55">
          Precedentes: {decision.precedent_refs.join(' · ')}
        </div>
      )}
    </div>
  );
}
