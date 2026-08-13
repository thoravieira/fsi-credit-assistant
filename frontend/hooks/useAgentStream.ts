import { useCallback, useEffect, useState } from 'react';
import {
  CalcResult, Decision, PendingApproval, Persona, Scenario, SendChatInput, TraceEvent,
  streamChat,
} from '../lib/api';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  streaming?: boolean;
  // The decision produced by *this* turn, if any — attached per message so
  // every proposal keeps its own outcome instead of one global `decision`
  // being overwritten by the next simulation (SDD 12 follow-up fix).
  decision?: Decision;
  contracted?: boolean;
}

export interface UseAgentStreamResult {
  trace: TraceEvent[];
  messages: ChatMessage[];
  calc: CalcResult | null;
  decision: Decision | null;
  pendingApproval: PendingApproval | null;
  scenarios: Scenario[];
  isStreaming: boolean;
  send: (message: string) => Promise<void>;
  hydrate: (data: { messages: ChatMessage[]; decision?: Decision | null }) => void;
  markContracted: (messageId: string, contracted?: boolean) => void;
}

/**
 * Single seam between the UI and the agent backend (docs/specs/12-frontend.md
 * §1). Every screen — Mariana's page and Carlos's console — consumes only
 * this hook, which drives the real `/api/chat` SSE stream via `streamChat()`.
 *
 * State resets whenever `threadId` changes, so switching between analyst
 * cases (or between a fresh page load and an existing thread) starts each
 * case with a clean trace/chat panel instead of carrying over the previous
 * case's events.
 */
export function useAgentStream(threadId: string, persona: Persona): UseAgentStreamResult {
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [calc, setCalc] = useState<CalcResult | null>(null);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  useEffect(() => {
    setTrace([]);
    setMessages([]);
    setCalc(null);
    setDecision(null);
    setPendingApproval(null);
    setScenarios([]);
  }, [threadId]);

  const send = useCallback(
    async (message: string) => {
      setIsStreaming(true);
      setMessages((prev) => [...prev, { id: 'u-' + Date.now(), role: 'user', text: message }]);
      const input: SendChatInput = { threadId, persona, message };
      // `decision` node runs (and its `state` event fires) before
      // `customer_response` starts streaming tokens (SDD 05 §1's node order),
      // so the assistant message this decision belongs to usually doesn't
      // exist yet when the event arrives — stash it here and attach it the
      // moment that message is actually created below.
      let pendingDecision: Decision | undefined;
      try {
        for await (const evt of streamChat(input)) {
          switch (evt.type) {
            case 'trace':
              setTrace((prev) => [...prev.slice(-59), evt]);
              // Fast Python nodes (router, credit_calculator, decision) can
              // finish in <10ms, so their 'started' + 'finished' pair often
              // arrives in the same buffered network chunk. Without a yield
              // here, React 18 batches every setState from this whole
              // synchronous frame loop into one commit — the browser paints
              // only the final state and the swimlane highlight never
              // visibly moves through intermediate steps. Yielding to the
              // next animation frame forces a real paint per trace event.
              await new Promise((resolve) => requestAnimationFrame(resolve));
              break;
            case 'token':
              // Pure updater — derives "is there an in-progress assistant
              // message" from `prev` itself rather than a ref mutated as a
              // side effect. React 18 Strict Mode double-invokes updaters in
              // dev; a ref written inside the updater gets set on the
              // discarded first call, so the committed second call never
              // finds a matching id and silently drops every token.
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                if (last && last.role === 'assistant' && last.streaming) {
                  return prev.map((m, i) => (i === prev.length - 1 ? { ...m, text: m.text + evt.text } : m));
                }
                return [...prev, { id: 'a-' + Date.now(), role: 'assistant', text: evt.text, streaming: true, decision: pendingDecision }];
              });
              break;
            case 'state':
              if (evt.calc) setCalc(evt.calc);
              if (evt.decision) {
                setDecision(evt.decision);
                pendingDecision = evt.decision;
                // Covers the reverse ordering too (analyst path can stream
                // tokens before its own `state` event) — if an assistant
                // message already exists for this turn, attach directly.
                setMessages((prev) => {
                  const last = prev[prev.length - 1];
                  if (!last || last.role !== 'assistant') return prev;
                  return prev.map((m, i) => (i === prev.length - 1 ? { ...m, decision: evt.decision ?? undefined } : m));
                });
              }
              setPendingApproval(evt.pending_approval ?? null);
              if (evt.scenarios) setScenarios(evt.scenarios);
              break;
            case 'done':
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                if (!last || last.role !== 'assistant') return prev;
                return prev.map((m, i) => (i === prev.length - 1 ? { ...m, streaming: false } : m));
              });
              break;
          }
        }
      } finally {
        setIsStreaming(false);
      }
    },
    [threadId, persona]
  );

  // Seeds this hook's own `messages`/`decision` from data fetched elsewhere —
  // real MongoDB history (`GET /api/history`), not a simulated turn. Nothing
  // else on the hook is touched: `trace` stays empty (there is no durable,
  // replayable trace for a past turn) and a `send()` afterwards appends to
  // `messages` exactly as it would after any other turn.
  const hydrate = useCallback((data: { messages: ChatMessage[]; decision?: Decision | null }) => {
    let msgs = data.messages;
    // `GET /api/history` returns plain transcript text, not a decision per
    // turn — there is no durable per-proposal decision history to restore
    // after a reload, only whichever one is current right now. Best-effort:
    // attach it to the last assistant message so the outcome still renders
    // somewhere sensible instead of nowhere.
    if (data.decision) {
      const lastAssistantIdx = msgs.reduce((acc, m, i) => (m.role === 'assistant' ? i : acc), -1);
      if (lastAssistantIdx >= 0) {
        msgs = msgs.map((m, i) => (i === lastAssistantIdx ? { ...m, decision: data.decision ?? undefined } : m));
      }
    }
    setMessages(msgs);
    if (data.decision !== undefined) setDecision(data.decision);
  }, []);

  const markContracted = useCallback((messageId: string, contracted = true) => {
    setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, contracted } : m)));
  }, []);

  return { trace, messages, calc, decision, pendingApproval, scenarios, isStreaming, send, hydrate, markContracted };
}
