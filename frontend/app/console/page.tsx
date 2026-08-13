'use client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAgentStream } from '../../hooks/useAgentStream';
import { useReplay } from '../../hooks/useReplay';
import { AppShell } from '../../components/AppShell';
import { RightPane } from '../../components/RightPane';
import type { FocusState } from '../../components/ArchitecturePanel';
import { Drawer, type DrawerState } from '../../components/Drawer';
import { laneCardId } from '../../lib/archMeta';
import { DecisionCard } from '../../components/DecisionCard';
import { ChatThread } from '../../components/ChatThread';
import { Markdown } from '../../lib/markdown';
import { ScenarioTable } from '../../components/ScenarioTable';
import { CaseQueue, toPendingCase } from '../../components/CaseQueue';
import {
  CUSTOMER_NAMES, CreditApplication, OUTCOME_LABELS, PRODUCT_LABELS,
  approve, currentDecisionOf, fmtBRL, getApplication, listApplications,
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

// Item 8: which 1-2 levers are actually plausible for *this* decision, not a
// static row of all three every turn. Read off the same `policy_refs`/
// `reasons` the decision itself cites (POL-001..003 = LTV, POL-004/005 = DTI)
// so the suggestion tracks whatever the real decision breached, not a guess.
function pickLevers(decision: ReturnType<typeof currentDecisionOf> | null): typeof LEVERS {
  if (!decision || decision.outcome === 'approved' || decision.outcome === 'approved_with_conditions') return [];
  const refs = decision.policy_refs.join(' ');
  const text = (decision.reasons ?? []).join(' ').toLowerCase() + ' ' + (decision.rationale ?? '').toLowerCase();
  const ltvIssue = /pol-00[123]\b/.test(refs) || text.includes('ltv');
  const dtiIssue = /pol-00[45]\b/.test(refs) || text.includes('comprometimento de renda');

  const picks: string[] = [];
  if (ltvIssue) picks.push('reduce_amount');
  if (dtiIssue) picks.push('extend_term', 'open_finance');
  if (!picks.length) picks.push('reduce_amount', 'open_finance'); // no clear signal yet — the two most broadly useful levers
  return LEVERS.filter((l) => picks.includes(l.key)).slice(0, 2);
}

const TAB_LABEL = { pending: 'Pendentes', approved: 'Aprovados', denied: 'Reprovações' } as const;

export default function ConsolePage() {
  const [tab, setTab] = useState<'pending' | 'approved' | 'denied'>('pending');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [applications, setApplications] = useState<CreditApplication[]>([]);
  const [selectedApp, setSelectedApp] = useState<CreditApplication | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [focus, setFocus] = useState<FocusState | null>(null);
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

  // Switching cases means switching trace history — the flow diagram should
  // stop pointing at whatever step was focused for the previous case.
  useEffect(() => {
    setFocus(null);
    setDrawer(null);
  }, [selectedId]);

  const { trace, messages, decision, pendingApproval, scenarios, send, isStreaming } = useAgentStream(selectedId ?? '', 'analyst');
  const { replay, start: startReplay } = useReplay();

  const sendAndReset = (message: string) => {
    setFocus(null);
    setDrawer(null);
    return send(message);
  };

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

  // `currentDecisionOf` picks whichever of `final_decision`/`latest_assessment`
  // actually matches the application's current `status` — a plain `??` fallback
  // would show a stale approved decision after the customer re-simulates on
  // the same thread and it comes back denied (found live, see memory).
  const shownDecision = decision ?? (selectedApp ? currentDecisionOf(selectedApp) : null);
  // Item 10 — a case already resolved (Aprovados/Reprovações tabs) can't be
  // decided again; the backend mirrors this (`negotiation.py` never sets
  // `pending_approval` once `application.status` leaves `manual_review`).
  const alreadyDecided = !!selectedApp?.status && selectedApp.status !== 'manual_review' && selectedApp.status !== 'auto_approved';

  const stateVerdict = (outcome: 'approved' | 'denied') => {
    sendAndReset(outcome === 'approved' ? 'Aprovar a proposta apresentada.' : 'Reprovar a proposta, não seguir com o crédito.');
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
    <AppShell
      left={
        <div className="flex-1 overflow-auto p-6">
          {!selectedApp ? (
            <div className="flex flex-col gap-4">
              <div>
                <div className="text-[21px] font-extrabold">Console do analista</div>
                <div className="mt-0.5 text-[12.5px] text-charcoal/55">Carlos · fila de crédito</div>
              </div>
              <div className="flex border border-charcoal/40">
                {(['pending', 'approved', 'denied'] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className={'flex-1 border-y-0 border-l-0 border-r border-charcoal/40 px-[11px] py-[13px] text-left last:border-r-0 ' + (tab === t ? 'bg-charcoal text-paper' : 'bg-white text-charcoal')}
                  >
                    <div className="text-[23px] font-extrabold leading-none">{counts[t]}</div>
                    <div className="mt-1 text-[10.5px] font-semibold uppercase tracking-[0.05em]">{TAB_LABEL[t]}</div>
                  </button>
                ))}
              </div>
              <CaseQueue cases={listForTab.map(toPendingCase)} onSelect={setSelectedId} />
            </div>
          ) : (
            <div className="flex flex-col gap-3.5">
              <button onClick={() => setSelectedId(null)} className="self-start border-none bg-transparent text-[11.5px] font-bold uppercase tracking-[0.05em] text-charcoal/55">← Fila de casos</button>
              <div className="flex items-start justify-between gap-3 border-2 border-charcoal/40 p-[15px]">
                <div>
                  <div className="text-[16px] font-extrabold">{CUSTOMER_NAMES[selectedApp.customer_id] ?? selectedApp.customer_id}</div>
                  <div className="mt-[3px] text-[12px] text-charcoal/55">
                    {PRODUCT_LABELS[selectedApp.product] ?? selectedApp.product} · {fmtBRL(selectedApp.asset_value)}
                  </div>
                </div>
                <div className="text-right font-mono text-[10px] leading-[1.5] text-charcoal/45">
                  thread_id<br /><b className="text-charcoal">{selectedApp.application_id}</b>
                </div>
              </div>

              {shownDecision && <DecisionCard decision={shownDecision} />}
              <ScenarioTable scenarios={scenarios} />
              {messages.length > 0 && (
                <ChatThread
                  messages={messages}
                  onSend={sendAndReset}
                  disabled={isStreaming}
                  placeholder="Pedir recomendação ou contraproposta…"
                  suggestions={!pendingApproval && !isStreaming ? pickLevers(shownDecision) : undefined}
                />
              )}

              <div className="flex flex-col gap-2.5 border border-charcoal/[0.25] bg-white p-3.5">
                {pendingApproval ? (
                  <>
                    <div className="text-[11.5px] font-bold text-charcoal/70">
                      Proposta do agente: <span className="text-forest">{OUTCOME_LABELS[pendingApproval.outcome] ?? pendingApproval.outcome}</span> — aguardando confirmação humana.
                    </div>
                    <Markdown text={pendingApproval.rationale} className="max-h-24 overflow-auto text-[12px] leading-relaxed text-charcoal/70" />
                    <button onClick={confirmApproval} disabled={confirming} className="border-none bg-spring py-3 text-[13px] font-extrabold text-ink disabled:opacity-50">
                      {confirming ? 'Confirmando…' : 'Confirmar ' + (OUTCOME_LABELS[pendingApproval.outcome] ?? pendingApproval.outcome)}
                    </button>
                  </>
                ) : (
                  <>
                    {alreadyDecided && (
                      <div className="text-[11.5px] font-bold text-charcoal/70">
                        Decisão já registrada: <span className="text-forest">{OUTCOME_LABELS[selectedApp.status ?? ''] ?? selectedApp.status}</span>. O chat acima pode ser usado para simular cenários e entender a decisão, mas não altera o resultado.
                      </div>
                    )}
                    <div className="flex gap-2.5">
                      <button onClick={() => stateVerdict('approved')} disabled={isStreaming || alreadyDecided} title={alreadyDecided ? 'Este caso já foi decidido' : undefined} className="flex-1 border-none bg-spring py-3 text-center text-[13px] font-extrabold text-ink disabled:opacity-50">Aprovar</button>
                      <button onClick={() => stateVerdict('denied')} disabled={isStreaming || alreadyDecided} title={alreadyDecided ? 'Este caso já foi decidido' : undefined} className="flex-1 border border-charcoal/40 bg-transparent py-3 text-center text-[13px] font-bold text-charcoal disabled:opacity-50">Reprovar</button>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      }
      right={
        <RightPane
          persona="analyst"
          trace={trace}
          isStreaming={isStreaming}
          replay={replay}
          focus={focus}
          onOpenNode={(id) => {
            setFocus({ nodeId: id });
            setDrawer({ kind: 'node', id });
          }}
          onOpenRow={(event, groupLabel) => {
            setFocus({ nodeId: laneCardId(event), event });
            setDrawer({ kind: 'row', event, groupLabel });
          }}
          onReplay={(label, rows, speed) => {
            setFocus(null);
            startReplay(label, rows, speed);
          }}
        />
      }
      drawer={<Drawer state={drawer} onClose={() => setDrawer(null)} />}
    />
  );
}
