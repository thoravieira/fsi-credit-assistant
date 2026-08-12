'use client';
import { useState } from 'react';
import type { ChatMessage } from '../hooks/useAgentStream';
import { Markdown } from '../lib/markdown';

// Split from the combined thread so a pinned-input layout (customer journey,
// SDD 12 follow-up) can scroll `ChatMessages` on its own while `ChatInputBar`
// stays fixed at the screen's bottom — see `CustomerApp.tsx`.
export function ChatMessages({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className="flex flex-col gap-2.5">
      {messages.map((m) => (
        <div key={m.id} className={'flex ' + (m.role === 'user' ? 'justify-end' : 'justify-start')}>
          <div className={'max-w-[86%] px-3.5 py-2.5 text-[13px] leading-relaxed ' + (m.role === 'user' ? 'bg-ink text-white' : 'bg-white text-ink')}>
            {m.role === 'assistant' ? <Markdown text={m.text} /> : m.text}
            {m.streaming && <span className="animate-caret">▊</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

export function ChatInputBar({
  onSend, disabled, placeholder = 'Escreva uma mensagem…',
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  const [text, setText] = useState('');
  const submit = () => {
    if (!text.trim() || disabled) return;
    onSend(text.trim());
    setText('');
  };

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
      <button onClick={submit} disabled={disabled} className="border-none bg-ink px-4 text-[12.5px] font-bold text-white disabled:opacity-40">
        Enviar
      </button>
    </div>
  );
}

export function ChatThread({
  messages, onSend, disabled, placeholder,
}: {
  messages: ChatMessage[];
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  return (
    <div className="flex flex-col gap-2.5">
      <ChatMessages messages={messages} />
      <ChatInputBar onSend={onSend} disabled={disabled} placeholder={placeholder} />
    </div>
  );
}
