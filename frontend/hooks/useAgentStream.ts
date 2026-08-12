import { useCallback, useEffect, useRef, useState } from 'react';
import {
  CalcResult, Decision, PendingApproval, Persona, Scenario, SendChatInput, TraceEvent,
  streamChat,
} from '../lib/api';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  streaming?: boolean;
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
  const assistantIdRef = useRef<string | null>(null);

  useEffect(() => {
    setTrace([]);
    setMessages([]);
    setCalc(null);
    setDecision(null);
    setPendingApproval(null);
    setScenarios([]);
    assistantIdRef.current = null;
  }, [threadId]);

  const send = useCallback(
    async (message: string) => {
      setIsStreaming(true);
      setMessages((prev) => [...prev, { id: 'u-' + Date.now(), role: 'user', text: message }]);
      const input: SendChatInput = { threadId, persona, message };
      try {
        for await (const evt of streamChat(input)) {
          switch (evt.type) {
            case 'trace':
              setTrace((prev) => [...prev.slice(-59), evt]);
              break;
            case 'token':
              setMessages((prev) => {
                if (!assistantIdRef.current) {
                  assistantIdRef.current = 'a-' + Date.now();
                  return [...prev, { id: assistantIdRef.current, role: 'assistant', text: evt.text, streaming: true }];
                }
                return prev.map((m) => (m.id === assistantIdRef.current ? { ...m, text: m.text + evt.text } : m));
              });
              break;
            case 'state':
              if (evt.calc) setCalc(evt.calc);
              if (evt.decision) setDecision(evt.decision);
              setPendingApproval(evt.pending_approval ?? null);
              if (evt.scenarios) setScenarios(evt.scenarios);
              break;
            case 'done':
              setMessages((prev) => prev.map((m) => (m.id === assistantIdRef.current ? { ...m, streaming: false } : m)));
              assistantIdRef.current = null;
              break;
          }
        }
      } finally {
        setIsStreaming(false);
      }
    },
    [threadId, persona]
  );

  return { trace, messages, calc, decision, pendingApproval, scenarios, isStreaming, send };
}
