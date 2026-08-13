'use client';
import { useEffect, useState } from 'react';
import { useAgentStream } from '../hooks/useAgentStream';
import { useReplay } from '../hooks/useReplay';
import { AppShell } from '../components/AppShell';
import { IOSDevice } from '../components/IOSDevice';
import { CustomerApp } from '../components/CustomerApp';
import { RightPane } from '../components/RightPane';
import type { FocusState } from '../components/ArchitecturePanel';
import { Drawer, type DrawerState } from '../components/Drawer';
import { laneCardId } from '../lib/archMeta';
import {
  contractApplication, createApplication, currentDecisionOf, fmtBRL, getApplication, getHistory,
  listApplications, previewFinanced, previewLtv,
} from '../lib/api';
import type { ChatMessage } from '../hooks/useAgentStream';
import type { Product } from '../lib/api';

// The seeded demo persona (data/profiles/profiles.json) — renda líquida
// R$ 11.200, dívida existente R$ 1.350, score interno 782 (SDD 16 §2).
const CUSTOMER_ID = 'CUST-0001';

// The bell is only for a new human decision. The v2 key intentionally leaves
// markers written by the previous implementation behind: that version also
// marked automatic assessments, which made an old simulation ring on load.
function decisionSeenKey(threadId: string) {
  return `credit-assistant:decision-seen:v2:${threadId}`;
}
function analystDecisionMarker(app: Awaited<ReturnType<typeof getApplication>>) {
  if (!app.final_decision || app.final_decision.outcome !== app.status) return null;
  return `${app.final_decision.outcome}@${app.updated_at ?? ''}`;
}

// Per-product defaults so switching the picker lands on sane numbers instead
// of e.g. a R$400k "veículo" — SDD 16 §2 only seeds a mortgage profile for
// CUST-0001, so auto is a real product (POL-002/003/005/009/019/021) simulated
// against the same seeded income/score, not a separate persona.
const PRODUCT_DEFAULTS: Record<
  Product,
  { assetValue: number; downPayment: number; termMonths: number; purpose: string; terms: number[]; purposes: string[] }
> = {
  mortgage: {
    assetValue: 400000, downPayment: 100000, termMonths: 360, purpose: 'Compra de imóvel residencial',
    terms: [180, 240, 300, 360, 420],
    purposes: ['Compra de imóvel residencial', 'Reforma do imóvel', 'Troca de imóvel'],
  },
  auto: {
    assetValue: 80000, downPayment: 16000, termMonths: 48, purpose: 'Compra de veículo novo',
    terms: [12, 24, 36, 48, 60],
    purposes: ['Compra de veículo novo', 'Compra de veículo usado', 'Troca de veículo'],
  },
};

export default function CustomerPage() {
  const [product, setProduct] = useState<Product>('mortgage');
  const [assetValue, setAssetValue] = useState(400000);
  const [downPayment, setDownPayment] = useState(100000);
  const [termMonths, setTermMonths] = useState(360);
  const [purpose, setPurpose] = useState('Compra de imóvel residencial');

  // Switching product resets the form to that product's own sane range —
  // POL-024's 20% entrada mínima for mortgage and POL-025's 10%/20% for auto
  // are worlds apart, so carrying over a mortgage-scale down payment onto a
  // vehicle would just misrepresent the simulation, not merely look odd.
  const switchProduct = (p: Product) => {
    setProduct(p);
    const d = PRODUCT_DEFAULTS[p];
    setAssetValue(d.assetValue);
    setDownPayment(d.downPayment);
    setTermMonths(d.termMonths);
    setPurpose(d.purpose);
  };
  const [threadId, setThreadId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(true);
  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [focus, setFocus] = useState<FocusState | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [hasUnreadDecision, setHasUnreadDecision] = useState(false);
  const [highlightMessageId, setHighlightMessageId] = useState<string | null>(null);

  // `thread_id == application_id` (SDD 04 §1). No localStorage: the screen
  // always opens on the simulation form (below), and the only thing this
  // needs from a previous visit — which thread to keep patching via chat
  // instead of starting a parallel duplicate — is looked up fresh from
  // MongoDB every time. `listApplications` sorts by `created_at` desc, so the
  // customer's most recent case is index 0; a customer with no case yet gets
  // one created lazily, same as before.
  useEffect(() => {
    let cancelled = false;

    async function init() {
      const existing = await listApplications({ customerId: CUSTOMER_ID });
      if (cancelled) return;
      if (existing.length > 0) {
        setThreadId(existing[0].application_id);
        return;
      }

      const id = await createApplication({
        customer_id: CUSTOMER_ID,
        product,
        asset_value: assetValue,
        down_payment: downPayment,
        term_months: termMonths,
        purpose,
      });
      if (cancelled) return;
      setThreadId(id);
    }

    init();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once on mount; a reused thread keeps its own history, these are only the fallback for creating a brand new one
  }, []);

  const {
    trace, messages, decision, isStreaming, send, appendTrace, hydrate, markContracted,
  } = useAgentStream(threadId ?? '', 'customer');

  // Establish the current state as a silent baseline, then poll for an analyst
  // decision made while this customer session is open. The baseline is also
  // persisted so leaving for the analyst console and returning detects the
  // newly recorded result without animating for historical decisions.
  useEffect(() => {
    if (!threadId) return;
    let cancelled = false;
    const key = decisionSeenKey(threadId);

    async function checkDecision() {
      const app = await getApplication(threadId!);
      if (cancelled) return;
      const marker = analystDecisionMarker(app) ?? 'none';
      const seen = localStorage.getItem(key);
      if (seen === null) {
        localStorage.setItem(key, marker);
        setHasUnreadDecision(false);
      } else {
        setHasUnreadDecision(marker !== 'none' && marker !== seen);
      }
    }

    checkDecision().catch(() => undefined);
    const timer = window.setInterval(() => checkDecision().catch(() => undefined), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [threadId]);
  const { replay, start: startReplay } = useReplay();
  const financed = previewFinanced(assetValue, downPayment);
  const ltv = previewLtv(assetValue, downPayment);

  // A new turn should resume "follow the live execution" in the flow diagram
  // rather than staying stuck on whatever step the user last clicked to
  // inspect — so every entry point into `send` clears focus/drawer first.
  const sendAndReset = (message: string) => {
    setFocus(null);
    setDrawer(null);
    return send(message);
  };

  const simulate = () => {
    if (!threadId) return;
    setFormOpen(false);
    const noun = product === 'auto' ? 'veículo' : 'imóvel';
    const label = product === 'auto' ? 'financiamento de veículo' : 'financiamento imobiliário';
    sendAndReset(
      `Simular ${label}: ${noun} de ${fmtBRL(assetValue)}, entrada de ${fmtBRL(downPayment)}, ` +
        `prazo de ${termMonths} meses. Finalidade: ${purpose}.`
    );
  };

  // "Abrir histórico": the real transcript for this thread, read back from
  // the LangGraph checkpoint (`GET /api/history`), plus whichever of
  // `final_decision`/`latest_assessment` is actually current right now
  // (`currentDecisionOf` — the two can disagree once a customer re-simulates
  // on an already-approved thread). Always fetched fresh from MongoDB, never
  // cached: this is the one place stale state used to leak back in.
  const openHistory = async () => {
    if (!threadId || historyLoading) return null;
    setHistoryLoading(true);
    try {
      const [pastMessages, app] = await Promise.all([
        getHistory(threadId, 'customer'),
        getApplication(threadId),
      ]);
      const chatMessages: ChatMessage[] = pastMessages.map((m, i) => ({ id: 'h-' + i, role: m.role, text: m.text }));
      const decision = currentDecisionOf(app);
      // Same best-effort attachment `hydrate()` uses internally (SDD 12
      // follow-up): a past decision has no id of its own, so "the message
      // carrying it" is the last assistant turn, once one exists.
      const lastAssistantIdx = chatMessages.reduce((acc, m, i) => (m.role === 'assistant' ? i : acc), -1);
      if (app.contract_status === 'contracted' && lastAssistantIdx >= 0) {
        chatMessages[lastAssistantIdx] = { ...chatMessages[lastAssistantIdx], contracted: true };
      }
      hydrate({ messages: chatMessages, decision });
      setFocus(null);
      setDrawer(null);
      setFormOpen(false);
      return { app, decisionMessageId: decision && lastAssistantIdx >= 0 ? chatMessages[lastAssistantIdx].id : null };
    } finally {
      setHistoryLoading(false);
    }
  };

  // Item 4 — clicking the bell: stop the animation, remember this decision as
  // seen (so it doesn't ring again on the next reopen), and jump to the exact
  // message that carries the approval/rejection.
  const handleBellClick = async () => {
    if (!threadId) return;
    setHasUnreadDecision(false);
    const result = await openHistory();
    if (!result) return;
    localStorage.setItem(decisionSeenKey(threadId), analystDecisionMarker(result.app) ?? 'none');
    if (result.decisionMessageId) {
      setHighlightMessageId(result.decisionMessageId);
      setTimeout(() => setHighlightMessageId(null), 2500);
    }
  };

  // Contract acceptance is a business transition, not another simulation.
  // The dedicated endpoint records it in MongoDB and appends a deterministic
  // customer-visible confirmation to the checkpoint without re-running the
  // credit graph (which would replace the analyst's verdict).
  const onContract = async (m: ChatMessage) => {
    if (!threadId) return;
    markContracted(m.id);
    try {
      const result = await contractApplication(threadId);
      appendTrace(result.trace);
      startReplay('Contratação', result.trace, 0.5);
      await openHistory();
    } catch {
      markContracted(m.id, false);
    }
  };

  return (
    <AppShell
      leftBg="#eae9e9"
      left={
        // Item 9 — `overflow-x` deliberately dropped: a horizontally
        // scrollable flex-centered container is a well-known scroll trap
        // (once the window was ever narrow enough to overflow, the browser
        // does not reliably re-center scroll position as it widens again,
        // so the phone would look pinned in place instead of tracking the
        // window). The 390px phone comfortably fits 44% of any realistic
        // demo window width, so there's nothing to trade off by removing it.
        <div className="flex-1 overflow-y-auto overflow-x-hidden">
          <div className="flex min-h-full items-center justify-center p-5">
            <IOSDevice dark width={390} height={800}>
              <CustomerApp
              product={product}
              setProduct={switchProduct}
              termOptions={PRODUCT_DEFAULTS[product].terms}
              purposeOptions={PRODUCT_DEFAULTS[product].purposes}
              assetValue={assetValue}
              setAssetValue={setAssetValue}
              downPayment={downPayment}
              setDownPayment={setDownPayment}
              termMonths={termMonths}
              setTermMonths={setTermMonths}
              purpose={purpose}
              setPurpose={setPurpose}
              financed={financed}
              ltv={ltv}
              onSimulate={simulate}
              isStreaming={isStreaming}
              threadId={threadId}
              formOpen={formOpen}
              onOpenForm={() => setFormOpen(true)}
              onOpenHistory={openHistory}
              historyLoading={historyLoading}
              messages={messages}
              onSend={sendAndReset}
              decision={decision}
              onContract={onContract}
              hasUnreadDecision={hasUnreadDecision}
              onBellClick={handleBellClick}
              highlightMessageId={highlightMessageId}
              />
            </IOSDevice>
          </div>
        </div>
      }
      right={
        <RightPane
          persona="customer"
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
