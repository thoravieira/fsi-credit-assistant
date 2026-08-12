'use client';
import { useState } from 'react';
import type { ChatMessage } from '../hooks/useAgentStream';

export function ChatThread({
  messages, onSend, disabled, placeholder = 'Escreva uma mensagem…',
}: {
  messages: ChatMessage[];
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
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-col gap-2">
        {messages.map((m) => (
          <div key={m.id} className={'flex ' + (m.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div className={'max-w-[84%] rounded-2xl px-3.5 py-2.5 text-[13.5px] leading-relaxed ' + (m.role === 'user' ? 'bg-ink text-white' : 'bg-[#EFF1F0] text-ink')}>
              {m.text}
              {m.streaming && <span className="animate-pulse">▊</span>}
            </div>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          disabled={disabled}
          placeholder={placeholder}
          className="flex-1 rounded-full border border-black/10 bg-white px-4 py-2.5 text-[13px] outline-none focus:border-forest disabled:opacity-60"
        />
        <button onClick={submit} disabled={disabled} className="rounded-full bg-ink px-4 text-[12.5px] font-bold text-white disabled:opacity-40">
          Enviar
        </button>
      </div>
    </div>
  );
}
