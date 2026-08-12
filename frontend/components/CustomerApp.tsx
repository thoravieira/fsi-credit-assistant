'use client';
import { ChatInputBar, ChatMessages } from './ChatThread';
import { DecisionCard } from './DecisionCard';
import type { ChatMessage } from '../hooks/useAgentStream';
import type { Decision } from '../lib/api';
import { OUTCOME_LABELS, POLICY_TEXT, fmtBRL, fmtBRL0, fmtPct } from '../lib/api';

// Content rendered inside the iPhone bezel for Mariana's route (`/`). Toggles
// between the simulation form and the chat/result view — matches the target
// design's `formOpen`/`chatVisible` split — but every number, message and
// decision comes from the real `useAgentStream` state passed in by
// `app/page.tsx`; nothing here is computed or simulated locally.
export function CustomerApp({
  assetValue,
  setAssetValue,
  downPayment,
  setDownPayment,
  termMonths,
  setTermMonths,
  purpose,
  setPurpose,
  financed,
  ltv,
  onSimulate,
  isStreaming,
  threadId,
  formOpen,
  onOpenForm,
  messages,
  onSend,
  decision,
  traceExpanded,
  onToggleTrace,
}: {
  assetValue: number;
  setAssetValue: (v: number) => void;
  downPayment: number;
  setDownPayment: (v: number) => void;
  termMonths: number;
  setTermMonths: (v: number) => void;
  purpose: string;
  setPurpose: (v: string) => void;
  financed: number;
  ltv: number;
  onSimulate: () => void;
  isStreaming: boolean;
  threadId: string | null;
  formOpen: boolean;
  onOpenForm: () => void;
  messages: ChatMessage[];
  onSend: (text: string) => void;
  decision: Decision | null;
  traceExpanded: boolean;
  onToggleTrace: () => void;
}) {
  // A restored session (app/page.tsx rehydrating from a stored thread) can
  // have a decision with no live chat messages — the transcript itself isn't
  // recoverable, but the result and its explanation still need to show.
  const chatVisible = !formOpen && (messages.length > 0 || !!decision);
  const reasons = decision ? decision.reasons ?? (decision.rationale ? [decision.rationale] : []) : [];

  return (
    <div className="flex h-full flex-col bg-[#F4F5F6]">
      <div className="flex flex-none flex-col gap-[13px] bg-ink px-[18px] pb-4 pt-[54px]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-[34px] w-[34px] flex-none items-center justify-center bg-white/[0.12] text-[12.5px] font-bold text-white">MD</div>
            <div>
              <div className="text-[14px] font-semibold leading-[1.25] text-white">Mariana Duarte</div>
              <div className="text-[11px] text-white/45">Cliente desde 2016</div>
            </div>
          </div>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,.5)" strokeWidth="1.8" strokeLinecap="round">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
            <path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
        </div>
        <div>
          <div className="text-[10.5px] uppercase tracking-[0.08em] text-white/45">Crédito imobiliário</div>
          <div className="mt-0.5 text-[21px] font-bold text-white">{formOpen ? 'Simular crédito' : 'Sua simulação'}</div>
        </div>
      </div>

      {formOpen && (
        <div className="flex flex-1 flex-col overflow-auto p-3.5">
          <div className="flex flex-col gap-3.5 border border-[rgba(0,30,43,0.16)] bg-white p-4">
            <div className="flex gap-1.5">
              <div className="flex-1 border border-ink bg-ink px-1 py-[9px] text-center text-[11.5px] font-bold text-white">Imóvel</div>
            </div>

            <label className="flex flex-col gap-1.5 text-[11px] font-semibold text-[rgba(0,30,43,0.5)]">
              Valor do imóvel
              <div className="flex items-baseline gap-1.5 border-b-2 border-[rgba(0,30,43,0.25)] py-2">
                <span className="text-[20px] font-bold text-ink">R$</span>
                <input
                  type="number" value={assetValue} step={5000} min={0}
                  onChange={(e) => setAssetValue(Number(e.target.value) || 0)}
                  className="w-full border-none bg-transparent text-[20px] font-bold text-ink outline-none"
                />
              </div>
            </label>

            <div className="flex flex-col gap-[7px]">
              <div className="flex items-baseline justify-between">
                <label className="text-[11px] font-semibold text-[rgba(0,30,43,0.5)]">Entrada</label>
                <span className="text-[15px] font-bold text-ink">{fmtBRL0(downPayment)}</span>
              </div>
              <input
                type="range" min={60000} max={220000} step={5000} value={downPayment}
                onChange={(e) => setDownPayment(Number(e.target.value))}
                className="w-full accent-forest"
              />
            </div>

            <div className="flex gap-2.5">
              <label className="flex flex-1 flex-col gap-1.5 text-[11px] font-semibold text-[rgba(0,30,43,0.5)]">
                Prazo
                <select value={termMonths} onChange={(e) => setTermMonths(Number(e.target.value))} className="border border-[rgba(0,30,43,0.16)] bg-[#FAFBFA] p-2.5 text-[13px] font-semibold text-ink">
                  {[180, 240, 300, 360, 420].map((m) => <option key={m} value={m}>{m} meses</option>)}
                </select>
              </label>
              <label className="flex flex-1 flex-col gap-1.5 text-[11px] font-semibold text-[rgba(0,30,43,0.5)]">
                Finalidade
                <select value={purpose} onChange={(e) => setPurpose(e.target.value)} className="border border-[rgba(0,30,43,0.16)] bg-[#FAFBFA] p-2.5 text-[13px] font-semibold text-ink">
                  <option>Compra de imóvel residencial</option>
                  <option>Reforma do imóvel</option>
                  <option>Troca de imóvel</option>
                </select>
              </label>
            </div>

            <div className="flex justify-between border border-[rgba(0,30,43,0.12)] bg-[#F1F2F1] px-3 py-[11px] text-[11.5px] text-[rgba(0,30,43,0.6)]">
              <span>Financiado <b className="font-mono text-ink">{fmtBRL0(financed)}</b></span>
              <span>LTV <b className="font-mono text-ink">{fmtPct(ltv)}</b></span>
            </div>

            <button
              onClick={onSimulate}
              disabled={isStreaming || !threadId}
              className="flex items-center justify-between gap-2 border-none bg-spring px-4 py-3.5 text-[15px] font-bold text-ink disabled:opacity-55"
            >
              <span>{!threadId ? 'Preparando…' : isStreaming ? 'Simulando…' : 'Simular'}</span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#001E2B" strokeWidth="2.2" strokeLinecap="round">
                <path d="M5 12h14" /><path d="m12 5 7 7-7 7" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {chatVisible && (
        <div className="flex min-h-0 flex-1 flex-col">
          {/* Scrollable transcript: messages, then the result and its business
              explanation as if they were the assistant's own follow-up
              "messages" — only the composer and the simulation summary below
              are pinned outside this scroll region. */}
          <div className="min-h-0 flex-1 overflow-auto p-3.5">
            <ChatMessages messages={messages} />

            {decision && (
              <div className="mt-[11px]">
                <DecisionCard decision={decision} />
              </div>
            )}

            <div className="mt-[11px] overflow-hidden border border-[rgba(0,30,43,0.16)] bg-white">
              <button onClick={onToggleTrace} className="flex w-full items-center justify-between border-none bg-transparent px-4 py-3.5 text-left">
                <span className="flex items-center gap-2.5">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#00684A" strokeWidth="2" strokeLinecap="round">
                    <circle cx="12" cy="12" r="9" /><path d="M12 8v4l3 2" />
                  </svg>
                  <span className="text-[12.5px] font-bold text-ink">Como decidimos</span>
                </span>
                <span className="text-[10px] text-[rgba(0,30,43,0.4)]">{traceExpanded ? '▲' : '▼'}</span>
              </button>
              {traceExpanded && (
                <div className="flex flex-col gap-3 px-4 pb-4">
                  {!decision && <div className="text-[11.5px] text-ink/45">Aguardando o resultado desta simulação…</div>}
                  {decision && (
                    <>
                      <div className="text-[12.5px] font-bold text-ink">{OUTCOME_LABELS[decision.outcome] ?? decision.outcome}</div>
                      <div className="flex flex-col gap-1.5">
                        {reasons.map((r, i) => (
                          <p key={i} className="flex gap-2 text-[12.5px] leading-relaxed text-ink/72">
                            <span className="text-forest">•</span>{r}
                          </p>
                        ))}
                      </div>
                      {decision.policy_refs.length > 0 && (
                        <div className="flex flex-col gap-2.5 border-t border-[rgba(0,30,43,0.12)] pt-3">
                          {decision.policy_refs.map((id) => {
                            const pol = POLICY_TEXT[id];
                            if (!pol) return null;
                            return (
                              <div key={id} className="text-[11.5px] leading-[1.55] text-ink/70">
                                <b className="text-ink">{id} · {pol.title}</b>
                                <p className="mt-1">{pol.body}</p>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Pinned footer: the simulation summary is always the last "message",
              directly above the composer — neither ever needs scrolling to reach. */}
          <div className="flex flex-none flex-col gap-2 border-t border-[#E7E9E8] bg-[#F4F5F6] px-3.5 pb-2.5 pt-2">
            <button onClick={onOpenForm} className="flex w-full items-center justify-between border border-[rgba(0,30,43,0.2)] bg-white px-3.5 py-3">
              <span className="flex min-w-0 items-center gap-2.5">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#00684A" strokeWidth="2" strokeLinecap="round">
                  <path d="M21 12a9 9 0 1 1-3-6.7" /><path d="M21 3v6h-6" />
                </svg>
                <span className="text-left text-[12px] font-semibold text-ink">
                  {fmtBRL0(assetValue)} · entrada {fmtBRL0(downPayment)} · {termMonths} meses
                </span>
              </span>
              <span className="flex-none text-[11px] font-bold text-forest">Nova simulação</span>
            </button>
            <ChatInputBar onSend={onSend} disabled={isStreaming} placeholder="Escreva para o assistente…" />
          </div>
        </div>
      )}

      <div className="flex flex-none items-center justify-around border-t border-[#E7E9E8] bg-white pb-1.5">
        {[
          { label: 'Início', color: '#001E2B', d: 'm3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z' },
          { label: 'Crédito', color: '#00684A', rect: true },
          { label: 'Ajuda', color: '#9AA3A0', d: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z' },
          { label: 'Menu', color: '#9AA3A0', lines: true },
        ].map((t) => (
          <div key={t.label} className="flex flex-col items-center gap-1">
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke={t.color} strokeWidth="2" strokeLinecap="round">
              {t.rect && <><rect x="2" y="5" width="20" height="14" rx="2" /><path d="M2 10h20" /></>}
              {t.lines && <><line x1="4" y1="7" x2="20" y2="7" /><line x1="4" y1="12" x2="20" y2="12" /><line x1="4" y1="17" x2="20" y2="17" /></>}
              {t.d && <path d={t.d} />}
            </svg>
            <span className="text-[10px] font-bold" style={{ color: t.color }}>{t.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
