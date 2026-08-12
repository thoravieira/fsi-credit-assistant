'use client';
import { useEffect, useState } from 'react';
import { useAgentStream } from '../hooks/useAgentStream';
import { DecisionCard } from '../components/DecisionCard';
import { ChatThread } from '../components/ChatThread';
import { TracePanel } from '../components/TracePanel';
import { createApplication, fmtBRL, fmtPct, previewFinanced, previewLtv } from '../lib/api';

// The seeded demo persona (data/profiles/profiles.json) — renda líquida
// R$ 11.200, dívida existente R$ 1.350, score interno 782 (SDD 16 §2).
const CUSTOMER_ID = 'CUST-0001';

export default function CustomerPage() {
  const [assetValue, setAssetValue] = useState(400000);
  const [downPayment, setDownPayment] = useState(180000);
  const [termMonths, setTermMonths] = useState(360);
  const [purpose, setPurpose] = useState('Compra de imóvel residencial');
  const [traceOpen, setTraceOpen] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);

  // `thread_id == application_id` (SDD 04 §1) — the draft application is
  // created once, on mount, with the sliders' initial values. Editing a
  // slider afterwards never creates a second application: it travels as a
  // free-text message on the same thread, which is what lets `intake` patch
  // `down_payment` in place and re-run the assessment (SDD 05 §3, SDD 16 §2
  // beat 3→4 — "same thread ID").
  useEffect(() => {
    let cancelled = false;
    createApplication({
      customer_id: CUSTOMER_ID,
      product: 'mortgage',
      asset_value: assetValue,
      down_payment: downPayment,
      term_months: termMonths,
      purpose,
    }).then((id) => {
      if (!cancelled) setThreadId(id);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- draft created once with the initial slider values; later edits are chat messages on this same thread, not a new draft
  }, []);

  const { trace, messages, decision, isStreaming, send } = useAgentStream(threadId ?? '', 'customer');
  const financed = previewFinanced(assetValue, downPayment);
  const ltv = previewLtv(assetValue, downPayment);

  const simulate = () => {
    if (!threadId) return;
    send(
      `Simular financiamento imobiliário: imóvel de ${fmtBRL(assetValue)}, entrada de ${fmtBRL(downPayment)}, ` +
        `prazo de ${termMonths} meses. Finalidade: ${purpose}.`
    );
  };

  return (
    <div className="flex h-full">
      <div className="flex w-1/2 items-start justify-center overflow-auto bg-[#E7ECE9] p-6">
        <div className="flex w-[380px] flex-col gap-3.5">
          <div className="rounded-2xl bg-ink p-4 text-white">
            <div className="text-[19px] font-extrabold">Simular crédito</div>
            <div className="text-[11px] text-white/55">Mariana Duarte · score interno 782</div>
          </div>

          <div className="flex flex-col gap-3.5 rounded-2xl bg-white p-4 shadow-[0_10px_26px_rgba(0,30,43,0.09)]">
            <div className="text-[14px] font-extrabold">Financiamento imobiliário</div>
            <label className="flex flex-col gap-1 text-[11px] font-semibold text-ink/55">
              Valor do imóvel
              <input
                type="number" value={assetValue} step={5000}
                onChange={(e) => setAssetValue(Number(e.target.value) || 0)}
                className="rounded-xl border border-black/10 bg-[#FAFBFA] px-3 py-2.5 text-[14px] font-semibold text-ink"
              />
            </label>
            <label className="flex flex-col gap-1 text-[11px] font-semibold text-ink/55">
              <span className="flex justify-between">Entrada <span className="text-[12.5px] font-extrabold text-forest">{fmtBRL(downPayment)}</span></span>
              <input
                type="range" min={60000} max={220000} step={5000} value={downPayment}
                onChange={(e) => setDownPayment(Number(e.target.value))}
                className="accent-spring"
              />
            </label>
            <div className="flex gap-2.5">
              <label className="flex flex-1 flex-col gap-1 text-[11px] font-semibold text-ink/55">
                Prazo
                <select value={termMonths} onChange={(e) => setTermMonths(Number(e.target.value))} className="rounded-xl border border-black/10 bg-[#FAFBFA] px-2.5 py-2.5 text-[13.5px] font-semibold">
                  {[180, 240, 300, 360, 420].map((m) => <option key={m} value={m}>{m} meses</option>)}
                </select>
              </label>
              <label className="flex flex-1 flex-col gap-1 text-[11px] font-semibold text-ink/55">
                Finalidade
                <select value={purpose} onChange={(e) => setPurpose(e.target.value)} className="rounded-xl border border-black/10 bg-[#FAFBFA] px-2.5 py-2.5 text-[13.5px] font-semibold">
                  <option>Compra de imóvel residencial</option>
                  <option>Reforma do imóvel</option>
                  <option>Troca de imóvel</option>
                </select>
              </label>
            </div>
            <div className="flex justify-between rounded-xl bg-[#F1F2F4] px-3 py-2.5 text-[11.5px] text-ink/65">
              <span>Financiado <b className="text-ink">{fmtBRL(financed)}</b></span>
              <span>LTV <b className="text-ink">{fmtPct(ltv)}</b></span>
            </div>
            <button onClick={simulate} disabled={isStreaming || !threadId} className="rounded-2xl bg-spring py-3.5 text-[14.5px] font-extrabold text-ink disabled:opacity-50">
              {!threadId ? 'Preparando…' : isStreaming ? 'Simulando…' : 'Simular'}
            </button>
          </div>

          {messages.length > 0 && <ChatThread messages={messages} onSend={send} disabled={isStreaming} placeholder="Ex.: e se eu desse mais entrada?" />}
          {decision && <DecisionCard decision={decision} />}

          <div className="rounded-xl bg-white shadow-sm">
            <button onClick={() => setTraceOpen((o) => !o)} className="flex w-full items-center justify-between px-3.5 py-3 text-[11.5px] font-bold text-ink/60">
              <span>{trace.length ? trace.length + ' eventos de trace' : 'Trace (nenhum evento ainda)'}</span>
              <span>{traceOpen ? '▲' : '▼'}</span>
            </button>
            {traceOpen && (
              <div className="flex flex-col gap-1 px-3.5 pb-3 font-mono text-[10.5px] text-ink/70">
                {trace.slice(-6).map((r, i) => <div key={i}>{r.node}{r.ms != null ? ' — ' + r.ms + 'ms' : ''}</div>)}
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="w-1/2"><TracePanel trace={trace} /></div>
    </div>
  );
}
