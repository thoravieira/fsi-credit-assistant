'use client';
import { useState } from 'react';
import { Decision, OUTCOME_LABELS, POLICY_TEXT } from '../lib/api';
import { Markdown } from '../lib/markdown';

// Shared by both routes: Mariana sees it standalone after a simulation,
// Carlos sees it inside the case detail panel. Two producers write `Decision`
// (SDD 04 §2): `domain/rules.py` on the customer path gives `reasons`, the
// negotiation human gate gives `rationale` — never both, so both render paths
// are handled here rather than assuming one shape.
export function DecisionCard({ decision }: { decision: Decision }) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const ok = decision.outcome === 'auto_approved' || decision.outcome.startsWith('approved');

  return (
    <div className="flex flex-col gap-3 border border-[rgba(0,30,43,0.16)] bg-white p-4">
      <div className="flex items-center gap-[9px]">
        <span className="flex h-[26px] w-[26px] flex-none items-center justify-center" style={{ background: ok ? '#00ED64' : 'rgba(32,30,29,.1)' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={ok ? '#001E2B' : '#201e1d'} strokeWidth="2.4" strokeLinecap="round">
            {ok ? <path d="M20 6 9 17l-5-5" /> : <path d="M6 6l12 12M18 6 6 18" />}
          </svg>
        </span>
        <div>
          <div className="text-[14px] font-bold text-ink">{OUTCOME_LABELS[decision.outcome] ?? decision.outcome}</div>
          <div className="text-[11px] text-ink/50">Resultado</div>
        </div>
      </div>

      <div className="flex flex-col gap-[7px]">
        {decision.reasons?.map((r, i) => (
          <p key={i} className="flex gap-2 text-[12.5px] leading-relaxed text-ink/72">
            <span className="text-forest">•</span>{r}
          </p>
        ))}
        {decision.rationale && !decision.reasons?.length && (
          <Markdown text={decision.rationale} className="text-[12.5px] leading-relaxed text-ink/72" />
        )}
        {decision.conditions?.map((c, i) => (
          <p key={'c' + i} className="flex gap-2 text-[12.5px] leading-relaxed text-ink/72">
            <span className="text-forest">•</span>Condição: {c}
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
                className={'border border-forest px-[11px] py-[5px] text-[10.5px] font-bold ' + (isOpen ? 'bg-forest text-white' : 'bg-[rgba(0,104,74,0.1)] text-forest')}
              >
                {id}
              </button>
              {isOpen && pol && (
                <div className="mt-[7px] bg-[#F1F2F1] p-3 text-[11.5px] leading-[1.55] text-ink/72">
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
