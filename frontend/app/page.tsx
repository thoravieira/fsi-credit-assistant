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
  createApplication, currentDecisionOf, fmtBRL, getApplication, getHistory, listApplications, previewFinanced, previewLtv,
} from '../lib/api';
import type { ChatMessage } from '../hooks/useAgentStream';
import type { Product } from '../lib/api';

// The seeded demo persona (data/profiles/profiles.json) — renda líquida
// R$ 11.200, dívida existente R$ 1.350, score interno 782 (SDD 16 §2).
const CUSTOMER_ID = 'CUST-0001';

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

  const { trace, messages, decision, isStreaming, send, hydrate, markContracted } = useAgentStream(threadId ?? '', 'customer');
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
    if (!threadId || historyLoading) return;
    setHistoryLoading(true);
    try {
      const [pastMessages, app] = await Promise.all([getHistory(threadId), getApplication(threadId)]);
      const chatMessages: ChatMessage[] = pastMessages.map((m, i) => ({ id: 'h-' + i, role: m.role, text: m.text }));
      hydrate({ messages: chatMessages, decision: currentDecisionOf(app) });
      setFocus(null);
      setDrawer(null);
      setFormOpen(false);
    } finally {
      setHistoryLoading(false);
    }
  };

  // "Contratar" (item 6): a real chat turn, not a local-only flag — it goes
  // through the same `/api/chat` pipeline as any message, so it lands in the
  // LangGraph checkpoint and survives a history reload. `markContracted`
  // flips the button to its confirmed state immediately rather than waiting
  // for the round trip, since the outcome here is never in doubt.
  const onContract = (m: ChatMessage) => {
    markContracted(m.id);
    sendAndReset('Aceito contratar esta proposta e seguir com a formalização do financiamento.');
  };

  return (
    <AppShell
      leftBg="#eae9e9"
      left={
        <div className="flex flex-1 items-start justify-center overflow-auto p-5">
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
