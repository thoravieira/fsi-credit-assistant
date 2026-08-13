'use client';
import { useEffect, useRef, useState } from 'react';
import type { ChatMessage } from '../hooks/useAgentStream';
import { Markdown } from '../lib/markdown';
import { DecisionCard } from './DecisionCard';

export interface Suggestion {
  label: string;
  prompt: string;
}

const POSITIVE_OUTCOMES = new Set(['auto_approved', 'approved', 'approved_with_conditions']);

// Split from the combined thread so a pinned-input layout (customer journey,
// SDD 12 follow-up) can scroll `ChatMessages` on its own while `ChatInputBar`
// stays fixed at the screen's bottom — see `CustomerApp.tsx`.
//
// Each proposal's outcome renders directly under the assistant message that
// produced it (one `DecisionCard` per turn that carries a `decision`,
// `ChatMessage.decision` — see `useAgentStream.ts`), instead of a single
// card overwritten by whichever simulation ran last. `onContract` — customer
// journey only — turns an approved proposal's card into a real "Contratar"
// action; `suggestions` — analyst console only — offers the 1-2 negotiation
// levers most likely to resolve the *current* decision, attached to the last
// message rather than a static always-on row.
export function ChatMessages({
  messages,
  onContract,
  suggestions,
  onSuggestion,
  highlightMessageId,
}: {
  messages: ChatMessage[];
  onContract?: (m: ChatMessage) => void;
  suggestions?: Suggestion[];
  onSuggestion?: (prompt: string) => void;
  // Customer journey only (item 4): the analyst/decision notification bell
  // scrolls to and briefly pulses the message carrying the approval/rejection,
  // reusing `.animate-card-pulse` rather than a bespoke highlight style.
  highlightMessageId?: string | null;
}) {
  const lastId = messages[messages.length - 1]?.id;
  const lastStreaming = messages[messages.length - 1]?.streaming;
  const highlightRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (highlightMessageId) highlightRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [highlightMessageId]);

  return (
    <div className="flex flex-col gap-2.5">
      {messages.map((m) => {
        const positive = m.decision && POSITIVE_OUTCOMES.has(m.decision.outcome);
        const highlighted = m.id === highlightMessageId;
        return (
          <div
            key={m.id}
            ref={highlighted ? highlightRef : undefined}
            className={'flex flex-col gap-1.5' + (highlighted ? ' animate-card-pulse' : '')}
          >
            <div className={'flex ' + (m.role === 'user' ? 'justify-end' : 'justify-start')}>
              <div className={'max-w-[86%] px-3.5 py-2.5 text-[13px] leading-relaxed ' + (m.role === 'user' ? 'bg-ink text-white' : 'bg-white text-ink')}>
                {m.role === 'assistant' ? <Markdown text={m.text} /> : m.text}
                {m.streaming && <span className="animate-caret">▊</span>}
              </div>
            </div>
            {m.decision && (
              <div>
                <DecisionCard decision={m.decision} />
                {positive && onContract && (
                  <button
                    onClick={() => !m.contracted && onContract(m)}
                    disabled={m.contracted}
                    className={
                      'mt-1.5 w-full border-none px-4 py-3 text-[13px] font-bold ' +
                      (m.contracted ? 'bg-[rgba(0,104,74,0.12)] text-forest' : 'bg-spring text-ink')
                    }
                  >
                    {m.contracted ? '✓ Proposta contratada' : 'Contratar'}
                  </button>
                )}
              </div>
            )}
            {m.id === lastId && !lastStreaming && suggestions && suggestions.length > 0 && onSuggestion && (
              <div className="flex flex-wrap gap-1.5">
                {suggestions.map((s) => (
                  <button
                    key={s.label}
                    onClick={() => onSuggestion(s.prompt)}
                    className="border border-forest bg-[rgba(0,104,74,0.08)] px-2.5 py-1.5 text-[11px] font-semibold text-forest"
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function ChatInputBar({
  onSend, disabled, placeholder = 'Escreva uma mensagem…', prefill, large,
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
  // Clicking a suggestion chip (item 8) should look like the customer/analyst
  // typed it — fill the visible box first, then send — not a silent direct
  // call to `onSend`. `nonce` forces the effect even when the same suggestion
  // is clicked twice in a row.
  prefill?: { text: string; nonce: number } | null;
  // Item 11 — customer journey only: a taller, multi-line composer with
  // Enviar anchored bottom-right, instead of the analyst console's compact
  // single-line input.
  large?: boolean;
}) {
  const [text, setText] = useState('');
  const submit = (value?: string) => {
    const v = (value ?? text).trim();
    if (!v || disabled) return;
    onSend(v);
    setText('');
  };

  useEffect(() => {
    if (!prefill?.text) return;
    setText(prefill.text);
    const t = setTimeout(() => submit(prefill.text), 260);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires only on a new prefill, not on every `disabled`/`text` change
  }, [prefill?.nonce]);

  if (large) {
    return (
      <div className="flex w-full items-end gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          disabled={disabled}
          placeholder={placeholder}
          rows={3}
          className="min-h-[72px] min-w-0 flex-1 resize-none border border-[rgba(0,30,43,0.2)] bg-white px-4 py-3 text-[13px] outline-none focus:border-forest disabled:opacity-60"
        />
        <button onClick={() => submit()} disabled={disabled} className="flex-none self-end border-none bg-ink px-4 py-3 text-[12.5px] font-bold text-white disabled:opacity-40">
          Enviar
        </button>
      </div>
    );
  }

  return (
    <div className="flex gap-2">
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && submit()}
        disabled={disabled}
        placeholder={placeholder}
        className="flex-1 border border-[rgba(0,30,43,0.2)] bg-white px-4 py-3 text-[13px] outline-none focus:border-forest disabled:opacity-60"
      />
      <button onClick={() => submit()} disabled={disabled} className="border-none bg-ink px-4 text-[12.5px] font-bold text-white disabled:opacity-40">
        Enviar
      </button>
    </div>
  );
}

export function ChatThread({
  messages, onSend, disabled, placeholder, onContract, suggestions,
}: {
  messages: ChatMessage[];
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
  onContract?: (m: ChatMessage) => void;
  suggestions?: Suggestion[];
}) {
  const [prefill, setPrefill] = useState<{ text: string; nonce: number } | null>(null);
  return (
    <div className="flex flex-col gap-2.5">
      <ChatMessages
        messages={messages}
        onContract={onContract}
        suggestions={suggestions}
        onSuggestion={(prompt) => setPrefill({ text: prompt, nonce: Date.now() })}
      />
      <ChatInputBar onSend={onSend} disabled={disabled} placeholder={placeholder} prefill={prefill} />
    </div>
  );
}
