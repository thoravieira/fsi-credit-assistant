'use client';
import { useEffect, useRef } from 'react';
import { ChatInputBar, ChatMessages } from './ChatThread';
import type { ChatMessage } from '../hooks/useAgentStream';
import type { Decision, Product } from '../lib/api';
import { fmtBRL0, fmtPct } from '../lib/api';

// Down-payment slider range differs by product (POL-024 mortgage vs. POL-025
// auto): a 60k-220k mortgage range would leave a R$16.000 default vehicle
// entrada unreachable by the slider entirely.
const DOWN_PAYMENT_RANGE: Record<Product, { min: number; max: number; step: number }> = {
  mortgage: { min: 60000, max: 220000, step: 5000 },
  auto: { min: 4000, max: 40000, step: 1000 },
};
const PRODUCT_TABS: { key: Product; label: string; header: string; assetLabel: string }[] = [
  { key: 'mortgage', label: 'Imóvel', header: 'Crédito imobiliário', assetLabel: 'Valor do imóvel' },
  { key: 'auto', label: 'Veículo', header: 'Crédito de veículo', assetLabel: 'Valor do veículo' },
];

// Content rendered inside the iPhone bezel for Mariana's route (`/`). Toggles
// between the simulation form and the chat/result view — matches the target
// design's `formOpen`/`chatVisible` split — but every number, message and
// decision comes from the real `useAgentStream` state passed in by
// `app/page.tsx`; nothing here is computed or simulated locally.
export function CustomerApp({
  product,
  setProduct,
  termOptions,
  purposeOptions,
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
  onOpenHistory,
  historyLoading,
  messages,
  onSend,
  decision,
  onContract,
}: {
  product: Product;
  setProduct: (p: Product) => void;
  termOptions: number[];
  purposeOptions: string[];
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
  onOpenHistory: () => void;
  historyLoading: boolean;
  messages: ChatMessage[];
  onSend: (text: string) => void;
  decision: Decision | null;
  onContract: (m: ChatMessage) => void;
}) {
  const activeTab = PRODUCT_TABS.find((t) => t.key === product) ?? PRODUCT_TABS[0];
  const downRange = DOWN_PAYMENT_RANGE[product];
  // Explicitly loaded via the history icon (real `GET /api/history` +
  // `GET /api/applications`, app/page.tsx's `openHistory`) — this screen
  // never auto-restores anything on its own.
  const chatVisible = !formOpen && (messages.length > 0 || !!decision);

  // Opening the history (or any new turn) should land the customer at the
  // bottom of the transcript, not wherever the scroll happened to be — the
  // scroll container is the `overflow-auto` div directly below, not the
  // window, so a plain anchor/`scrollIntoView` on mount isn't enough once
  // `chatVisible` flips true from a fresh `hydrate()`.
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (chatVisible && scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [chatVisible, messages.length, decision]);

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
          <div className="text-[10.5px] uppercase tracking-[0.08em] text-white/45">{activeTab.header}</div>
          <div className="mt-0.5 text-[21px] font-bold text-white">{formOpen ? 'Simular crédito' : 'Sua simulação'}</div>
        </div>
      </div>

      {/* Always visible, on the form and on the chat — the only two ways in
          or out of a case: reopen the simulation form, or pull the real
          conversation for this thread from MongoDB (never a local cache). */}
      <div className="flex flex-none items-center justify-between border-b border-[#E7E9E8] bg-white px-3.5 py-2">
        <span className="text-[11px] font-bold uppercase tracking-[0.04em] text-ink/55">Nova simulação</span>
        <div className="flex items-center gap-1.5">
          <button
            onClick={onOpenHistory}
            disabled={!threadId || historyLoading}
            title="Abrir histórico"
            className="flex h-7 w-7 items-center justify-center border border-[rgba(0,30,43,0.2)] bg-white disabled:opacity-40"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#00684A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </button>
          <button
            onClick={onOpenForm}
            title="Nova simulação"
            className="flex h-7 w-7 items-center justify-center border border-[rgba(0,30,43,0.2)] bg-white"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#00684A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" />
              <line x1="12" y1="18" x2="12" y2="12" /><line x1="9" y1="15" x2="15" y2="15" />
            </svg>
          </button>
        </div>
      </div>

      {formOpen && (
        <div className="flex flex-1 flex-col overflow-auto p-3.5">
          <div className="flex flex-col gap-3.5 border border-[rgba(0,30,43,0.16)] bg-white p-4">
            <div className="flex gap-1.5">
              {PRODUCT_TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setProduct(t.key)}
                  className={
                    'flex-1 border px-1 py-[9px] text-center text-[11.5px] font-bold ' +
                    (t.key === product ? 'border-ink bg-ink text-white' : 'border-[rgba(0,30,43,0.16)] bg-white text-ink/60')
                  }
                >
                  {t.label}
                </button>
              ))}
            </div>

            <label className="flex flex-col gap-1.5 text-[11px] font-semibold text-[rgba(0,30,43,0.5)]">
              {activeTab.assetLabel}
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
                type="range" min={downRange.min} max={downRange.max} step={downRange.step} value={downPayment}
                onChange={(e) => setDownPayment(Number(e.target.value))}
                className="w-full accent-forest"
              />
            </div>

            <div className="flex gap-2.5">
              <label className="flex flex-1 flex-col gap-1.5 text-[11px] font-semibold text-[rgba(0,30,43,0.5)]">
                Prazo
                <select value={termMonths} onChange={(e) => setTermMonths(Number(e.target.value))} className="border border-[rgba(0,30,43,0.16)] bg-[#FAFBFA] p-2.5 text-[13px] font-semibold text-ink">
                  {termOptions.map((m) => <option key={m} value={m}>{m} meses</option>)}
                </select>
              </label>
              <label className="flex flex-1 flex-col gap-1.5 text-[11px] font-semibold text-[rgba(0,30,43,0.5)]">
                Finalidade
                <select value={purpose} onChange={(e) => setPurpose(e.target.value)} className="border border-[rgba(0,30,43,0.16)] bg-[#FAFBFA] p-2.5 text-[13px] font-semibold text-ink">
                  {purposeOptions.map((p) => <option key={p}>{p}</option>)}
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
          {/* Scrollable transcript: messages, and each proposal's outcome
              (auto_approved/manual_review/denied/approved) directly under the
              AI message that produced it — `ChatMessages` renders a
              `DecisionCard` per message that carries a `decision`, so a
              customer who re-simulates several times keeps every proposal's
              result in place instead of one card overwritten by the latest. */}
          <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto p-3.5">
            <ChatMessages messages={messages} onContract={onContract} />
          </div>

          {/* Pinned footer: the composer is always the last thing on screen —
              reopening the form is the icon in the utility bar above now. */}
          <div className="flex flex-none border-t border-[#E7E9E8] bg-[#F4F5F6] px-3.5 pb-2.5 pt-2">
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
