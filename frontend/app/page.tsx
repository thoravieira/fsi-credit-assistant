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
import { createApplication, fmtBRL, getApplication, previewFinanced, previewLtv, type CreditApplication } from '../lib/api';

// The seeded demo persona (data/profiles/profiles.json) — renda líquida
// R$ 11.200, dívida existente R$ 1.350, score interno 782 (SDD 16 §2).
const CUSTOMER_ID = 'CUST-0001';

// Survives a route change (this page fully unmounts navigating to `/console`
// and back — Next's App Router has no shared state between sibling routes)
// and a reload, so Mariana's case — and its decision, once she has one — is
// still there when she comes back, instead of a brand new draft silently
// replacing it (which also used to be why testing left a pile of duplicate
// draft applications behind, see memory).
const THREAD_STORAGE_KEY = 'fsi-customer-thread-id';

export default function CustomerPage() {
  const [assetValue, setAssetValue] = useState(400000);
  const [downPayment, setDownPayment] = useState(100000);
  const [termMonths, setTermMonths] = useState(360);
  const [purpose, setPurpose] = useState('Compra de imóvel residencial');
  const [threadId, setThreadId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(true);
  const [traceExpanded, setTraceExpanded] = useState(false);
  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [focus, setFocus] = useState<FocusState | null>(null);
  // Fallback for the outcome of a *previous* visit: the live `decision` from
  // `useAgentStream` only exists after this mount's own stream runs, so a
  // restored thread needs its last known status from the database instead —
  // same two-producer pattern as `console/page.tsx`'s `shownDecision`.
  const [restoredApp, setRestoredApp] = useState<CreditApplication | null>(null);

  // `thread_id == application_id` (SDD 04 §1). On mount, reuse the thread
  // stored from a previous visit — hydrating the sliders and, if it already
  // has an outcome, the result — rather than always creating a fresh draft.
  // Only when there is no usable stored thread does this fall back to
  // creating one, exactly as before.
  useEffect(() => {
    let cancelled = false;

    async function init() {
      const storedId = typeof window !== 'undefined' ? localStorage.getItem(THREAD_STORAGE_KEY) : null;
      if (storedId) {
        try {
          const app = await getApplication(storedId);
          if (cancelled) return;
          setAssetValue(app.asset_value);
          setDownPayment(app.down_payment);
          setTermMonths(app.term_months);
          if (app.purpose) setPurpose(app.purpose);
          if (app.status && app.status !== 'draft') {
            setRestoredApp(app);
            setFormOpen(false);
          }
          setThreadId(app.application_id);
          return;
        } catch {
          // Stored thread no longer exists (e.g. demo data was reset) — fall
          // through and create a new one below.
        }
      }

      const id = await createApplication({
        customer_id: CUSTOMER_ID,
        product: 'mortgage',
        asset_value: assetValue,
        down_payment: downPayment,
        term_months: termMonths,
        purpose,
      });
      if (cancelled) return;
      localStorage.setItem(THREAD_STORAGE_KEY, id);
      setThreadId(id);
    }

    init();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once on mount; a restored thread's own stored parameters win over these initial slider defaults
  }, []);

  const { trace, messages, decision, isStreaming, send } = useAgentStream(threadId ?? '', 'customer');
  const { replay, start: startReplay } = useReplay();
  const financed = previewFinanced(assetValue, downPayment);
  const ltv = previewLtv(assetValue, downPayment);
  const shownDecision = decision ?? restoredApp?.final_decision ?? restoredApp?.latest_assessment?.decision ?? null;

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
    sendAndReset(
      `Simular financiamento imobiliário: imóvel de ${fmtBRL(assetValue)}, entrada de ${fmtBRL(downPayment)}, ` +
        `prazo de ${termMonths} meses. Finalidade: ${purpose}.`
    );
  };

  return (
    <AppShell
      leftBg="#eae9e9"
      left={
        <div className="flex flex-1 items-start justify-center overflow-auto p-5">
          <IOSDevice dark width={390} height={800}>
            <CustomerApp
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
              messages={messages}
              onSend={sendAndReset}
              decision={shownDecision}
              traceExpanded={traceExpanded}
              onToggleTrace={() => setTraceExpanded((o) => !o)}
            />
          </IOSDevice>
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
          onReplay={(label, rows) => {
            setFocus(null);
            startReplay(label, rows);
          }}
        />
      }
      drawer={<Drawer state={drawer} onClose={() => setDrawer(null)} />}
    />
  );
}
