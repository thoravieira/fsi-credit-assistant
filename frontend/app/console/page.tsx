'use client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAgentStream } from '../../hooks/useAgentStream';
import { DecisionCard } from '../../components/DecisionCard';
import { ChatThread } from '../../components/ChatThread';
import { ScenarioTable } from '../../components/ScenarioTable';
import { CaseQueue, toPendingCase } from '../../components/CaseQueue';
import { TracePanel } from '../../components/TracePanel';
import {
  CUSTOMER_NAMES, CreditApplication, OUTCOME_LABELS, PRODUCT_LABELS,
  approve, fmtBRL, getApplication, listApplications,
} from '../../lib/api';

// Instruction text sent to the deep agent, not fabricated numbers — the
// negotiation node's own tools (`recalculate_scenario`,
// `check_open_finance_assets`, docs/specs/06-negotiation-agent.md §3) do the
// actual work and the accumulated result comes back on the `state` event's
// `scenarios` array.
const LEVERS = [
  { key: 'reduce_amount', label: 'Reduzir valor financiado', prompt: 'Reduza o valor financiado o quanto for necessário para a proposta entrar na faixa de aprovação automática, mantendo os demais parâmetros, e recalcule.' },
  { key: 'extend_term', label: 'Estender prazo (420 meses)', prompt: 'Estenda o prazo do financiamento para 420 meses, mantendo os demais parâmetros, e recalcule.' },
  { key: 'open_finance', label: 'Solicitar Open Finance', prompt: 'Consulte os ativos elegíveis via Open Finance da cliente e avalie se servem como fator compensatório para a proposta atual.' },
];

export default function ConsolePage() {
  const [tab, setTab] = useState<'pending' | 'approved' | 'denied'>('pending');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [applications, setApplications] = useState<CreditApplication[]>([]);
  const [selectedApp, setSelectedApp] = useState<CreditApplication | null>(null);
  const [confirming, setConfirming] = useState(false);
  const openedRef = useRef<Set<string>>(new Set());

  const refreshQueue = useCallback(() => {
    listApplications().then(setApplications).catch(() => setApplications([]));
  }, []);

  useEffect(refreshQueue, [refreshQueue]);

  useEffect(() => {
    if (!selectedId) {
      setSelectedApp(null);
      return;
    }
    getApplication(selectedId).then(setSelectedApp);
  }, [selectedId]);

  const { trace, messages, decision, pendingApproval, scenarios, send, isStreaming } = useAgentStream(selectedId ?? '', 'analyst');

  // Carlos's first look at a fresh case: SDD 05 §1 routes an analyst turn on
  // a case still in `review` to `precedent_search` → `analyst_brief`, which
  // is the dossier (recommendation + citations + precedents, SDD 16 §2 beat
  // 5). Fired once per case per session — a case already in `negotiation`
  // just gets an ordinary opening turn instead of a second dossier.
  useEffect(() => {
    if (!selectedId || openedRef.current.has(selectedId)) return;
    openedRef.current.add(selectedId);
    send('Abrir o caso e apresentar o parecer.');
  }, [selectedId, send]);

  const pending = useMemo(() => applications.filter((a) => a.status === 'manual_review'), [applications]);
  const approvedList = useMemo(
    () => applications.filter((a) => a.status === 'approved' || a.status === 'approved_with_conditions'),
    [applications]
  );
  const deniedList = useMemo(() => applications.filter((a) => a.status === 'denied'), [applications]);
  const counts = { pending: pending.length, approved: approvedList.length, denied: deniedList.length };
  const listForTab = tab === 'pending' ? pending : tab === 'approved' ? approvedList : deniedList;

  const shownDecision = decision ?? selectedApp?.final_decision ?? selectedApp?.latest_assessment?.decision ?? null;

  const runLever = (key: string) => {
    const lever = LEVERS.find((l) => l.key === key);
    if (lever) send(lever.prompt);
  };

  const stateVerdict = (outcome: 'approved' | 'denied') => {
    send(outcome === 'approved' ? 'Aprovar a proposta apresentada.' : 'Reprovar a proposta, não seguir com o crédito.');
  };

  const confirmApproval = async () => {
    if (!selectedId || !pendingApproval) return;
    setConfirming(true);
    try {
      await approve(selectedId, { outcome: pendingApproval.outcome });
      openedRef.current.delete(selectedId);
      setSelectedId(null);
      refreshQueue();
    } finally {
      setConfirming(false);
    }
  };

  return (
    <div className="flex h-full">
      <div className="w-1/2 overflow-auto bg-[#F7F8F7] p-7">
        {!selectedApp ? (
          <div className="flex flex-col gap-4">
            <div>
              <div className="text-[20px] font-extrabold">Console do analista</div>
              <div className="text-[12.5px] text-ink/55">Carlos · fila de crédito</div>
            </div>
            <div className="flex border border-ink/[0.14]">
              {(['pending', 'approved', 'denied'] as const).map((t) => (
                <button key={t} onClick={() => setTab(t)} className={'flex-1 border-r border-ink/[0.14] px-2.5 py-3.5 text-left last:border-r-0 ' + (tab === t ? 'bg-ink text-white' : 'bg-white text-ink')}>
                  <div className="text-[22px] font-extrabold leading-none">{counts[t]}</div>
                  <div className="mt-1 text-[11.5px] font-semibold">{t === 'pending' ? 'Pendentes' : t === 'approved' ? 'Aprovados' : 'Reprovações'}</div>
                </button>
              ))}
            </div>
            <CaseQueue cases={listForTab.map(toPendingCase)} onSelect={setSelectedId} />
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <button onClick={() => setSelectedId(null)} className="self-start text-[12.5px] font-bold text-ink/55">← Fila de casos</button>
            <div className="border border-ink/[0.14] p-4">
              <div className="text-[16px] font-extrabold">{CUSTOMER_NAMES[selectedApp.customer_id] ?? selectedApp.customer_id}</div>
              <div className="text-[12px] text-ink/55">
                {PRODUCT_LABELS[selectedApp.product] ?? selectedApp.product} · {fmtBRL(selectedApp.asset_value)} · {selectedApp.application_id}
              </div>
            </div>

            {shownDecision && <DecisionCard decision={shownDecision} />}
            <ScenarioTable scenarios={scenarios} />
            {messages.length > 0 && <ChatThread messages={messages} onSend={send} disabled={isStreaming} placeholder="Pedir recomendação ou contraproposta…" />}

            <div className="flex flex-col gap-2.5 border border-ink/[0.14] p-3.5">
              {pendingApproval ? (
                <>
                  <div className="text-[11.5px] font-bold text-ink/70">
                    Proposta do agente: <span className="text-forest">{OUTCOME_LABELS[pendingApproval.outcome] ?? pendingApproval.outcome}</span> — aguardando confirmação humana.
                  </div>
                  <p className="max-h-24 overflow-auto text-[12px] leading-relaxed text-ink/70">{pendingApproval.rationale}</p>
                  <button onClick={confirmApproval} disabled={confirming} className="bg-spring py-3 text-[13px] font-extrabold text-ink disabled:opacity-50">
                    {confirming ? 'Confirmando…' : 'Confirmar ' + (OUTCOME_LABELS[pendingApproval.outcome] ?? pendingApproval.outcome)}
                  </button>
                </>
              ) : (
                <>
                  <div className="flex flex-wrap gap-1.5">
                    {LEVERS.map((l) => (
                      <button key={l.key} disabled={isStreaming} onClick={() => runLever(l.key)} className="border border-ink/20 px-3 py-1.5 text-[11.5px] font-semibold disabled:opacity-40">
                        {l.label}
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-2.5 border-t border-ink/10 pt-2.5">
                    <button onClick={() => stateVerdict('approved')} disabled={isStreaming} className="flex-1 bg-spring py-3 text-[13px] font-extrabold text-ink disabled:opacity-50">Aprovar</button>
                    <button onClick={() => stateVerdict('denied')} disabled={isStreaming} className="flex-1 border border-ink/30 py-3 text-[13px] font-bold disabled:opacity-50">Reprovar</button>
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>
      <div className="w-1/2"><TracePanel trace={trace} /></div>
    </div>
  );
}
