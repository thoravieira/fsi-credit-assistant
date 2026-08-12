'use client';
import { useEffect, useRef, useState } from 'react';
import type { TraceEvent } from '../lib/api';

type Role = 'det' | 'llm' | 'vec' | 'mem' | 'wait';
const ROLE: Record<string, Role> = {
  router: 'det', credit_calculator: 'det', decision: 'det', recalculate_scenario: 'det',
  check_open_finance_assets: 'det',
  intake: 'llm', analyst_brief: 'llm', customer_response: 'llm', negotiation: 'llm',
  policy_retrieval: 'vec', precedent_search: 'vec', policy_researcher: 'vec', precedent_analyst: 'vec',
  load_context: 'mem', persist_decision: 'mem', await_approval: 'wait',
};
const DOT: Record<Role, string> = { det: '#B7C6C1', llm: '#00684A', vec: '#00ED64', mem: '#6FA89E', wait: '#C9D6D1' };
const BRIGHT: Record<Role, string> = { det: '#DCE4E2', llm: '#4FBF93', vec: '#00ED64', mem: '#9CC9C0', wait: '#EDEBD8' };

const CUST_LANE = [
  { id: 'intake', label: 'intake', sub: 'LLM · extrai dados' },
  { id: 'load_context', label: 'load_context', sub: 'memória · perfil' },
  { id: 'policy_retrieval', label: 'policy_retrieval', sub: '$vectorSearch' },
  { id: 'credit_calculator', label: 'credit_calculator', sub: 'Python · 0 LLM' },
  { id: 'decision', label: 'decision', sub: 'regras determinísticas' },
  { id: 'customer_response', label: 'customer_response', sub: 'LLM · resposta' },
];
const ANA_LANE = [
  { id: 'precedent_search', label: 'precedent_search', sub: '$vectorSearch' },
  { id: 'analyst_brief', label: 'analyst_brief', sub: 'LLM · dossiê' },
  { id: 'negotiation', label: 'negotiation', sub: '[OPUS] deep agent' },
  { id: 'await_approval', label: 'await_approval', sub: 'interrupt() humano' },
  { id: 'persist_decision', label: 'persist_decision', sub: 'memória · grava' },
];

function chipStyle(id: string, active: boolean) {
  const role = ROLE[id] ?? 'det';
  if (!active) return { background: 'rgba(255,255,255,.04)', borderColor: 'rgba(255,255,255,.1)', color: 'rgba(255,255,255,.55)', boxShadow: 'none' };
  return { background: 'rgba(255,255,255,.1)', borderColor: DOT[role], color: BRIGHT[role], boxShadow: '0 0 0 1px ' + DOT[role] + ', 0 0 14px ' + DOT[role] + '55' };
}

/**
 * The architecture + trace half of the screen — identical on both routes.
 * Driven entirely by `trace`, the array `useAgentStream` accumulates directly
 * from real `/api/chat` SSE `trace` events (docs/specs/11-api-sse.md §2) —
 * no simulated timings, no hardcoded step lists (SDD 11 §4).
 */
export function TracePanel({ trace }: { trace: TraceEvent[] }) {
  const listRef = useRef<HTMLDivElement>(null);
  const [openRows, setOpenRows] = useState<Record<number, boolean>>({});
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [trace.length]);

  const last = trace[trace.length - 1];
  const activeNode = last && last.status !== 'finished' ? last.step ?? last.node : null;
  const activeLane = activeNode && CUST_LANE.some((n) => n.id === activeNode) ? 'cust' : activeNode && ANA_LANE.some((n) => n.id === activeNode) ? 'ana' : null;
  const vectorActive = activeNode === 'policy_retrieval' || activeNode === 'precedent_search' || activeNode === 'policy_researcher' || activeNode === 'precedent_analyst';
  const memActive = activeNode === 'load_context' || activeNode === 'persist_decision';

  return (
    <div className="flex h-full flex-col bg-ink">
      <div className="flex flex-col gap-1.5 border-b-2 border-white/[0.08] p-5" style={{ flex: '0 0 55%' }}>
        <div className="mb-1 flex items-center justify-between">
          <span className="text-[13px] font-extrabold text-white">Arquitetura em tempo real</span>
          <span className="flex items-center gap-1.5 font-mono text-[10.5px] text-white/50">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-spring" />Atlas conectado
          </span>
        </div>
        <div className="mb-1 flex gap-1.5">
          <div className="border border-white/15 px-2.5 py-1 text-[9.5px] font-bold text-white/70">Next.js</div>
          <span className="self-center text-white/25">→</span>
          <div className="border border-white/15 px-2.5 py-1 text-[9.5px] font-bold text-white/70">FastAPI + SSE</div>
        </div>
        <div className="flex flex-1 flex-col gap-1.5 overflow-auto border border-white/10 p-2.5">
          <div className="flex justify-center">
            <span className="rounded-full border px-3 py-1 text-[9.5px] font-bold" style={chipStyle('router', activeNode === 'router')}>router</span>
          </div>
          {[{ key: 'cust', label: 'Jornada cliente', nodes: CUST_LANE }, { key: 'ana', label: 'Jornada analista', nodes: ANA_LANE }].map((lane) => (
            <div key={lane.key} className="flex flex-col gap-1" style={{ opacity: activeLane && activeLane !== lane.key ? 0.35 : 1 }}>
              <div className="text-[8px] font-bold uppercase tracking-wide text-white/35">{lane.label}</div>
              <div className="flex flex-wrap items-center gap-1">
                {lane.nodes.map((n, i) => (
                  <span key={n.id} className="flex items-center gap-1">
                    {i > 0 && <span className="text-[10px] text-white/20">›</span>}
                    <span className="flex flex-col rounded-md border px-1.5 py-1" style={chipStyle(n.id, activeNode === n.id)}>
                      <span className="whitespace-nowrap font-mono text-[9.5px] font-bold">{n.label}</span>
                      <span className="whitespace-nowrap text-[7px] text-white/35">{n.sub}</span>
                    </span>
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-1.5 flex items-center gap-2.5 border border-white/15 px-3 py-1.5">
          <span className="flex-none text-[11px] font-extrabold text-white">MongoDB Atlas</span>
          <span className="rounded-full border px-2.5 py-1 text-[9.5px] font-bold" style={chipStyle('policy_retrieval', vectorActive)}>Vector Search</span>
          <span className="rounded-full border px-2.5 py-1 text-[9.5px] font-bold" style={{ background: 'rgba(255,255,255,.06)', color: 'rgba(255,255,255,.7)', borderColor: 'rgba(255,255,255,.15)' }}>Collections · Checkpoints</span>
          <span className="rounded-full border px-2.5 py-1 text-[9.5px] font-bold" style={chipStyle('load_context', memActive)}>Memory Store</span>
        </div>
      </div>

      <div className="flex flex-col bg-[#01171F]" style={{ flex: '0 0 45%' }}>
        <div className="flex items-center justify-between px-5 pt-3.5 pb-2.5">
          <span className="text-[13px] font-extrabold text-white">Trace ao vivo</span>
          <span className="flex gap-2.5 text-[9.5px] text-white/45">
            <span><span style={{ color: DOT.det }}>●</span> determinístico</span>
            <span><span style={{ color: DOT.llm }}>●</span> LLM</span>
            <span><span style={{ color: DOT.vec }}>●</span> vector search</span>
            <span><span style={{ color: DOT.mem }}>●</span> memória</span>
          </span>
        </div>
        <div ref={listRef} className="flex-1 overflow-auto px-5 pb-4 font-mono">
          {trace.length === 0 && <p className="py-5 text-[12px] text-white/30">Envie uma simulação ou abra um caso para ver o trace ao vivo…</p>}
          {trace.map((row, i) => {
            const role = ROLE[row.step ?? row.node] ?? 'det';
            const label = row.status === 'step' ? row.node + ' · ' + row.step : row.node;
            return (
              <div key={i} className="border-b border-white/[0.06] py-1.5">
                <button onClick={() => setOpenRows((s) => ({ ...s, [i]: !s[i] }))} className="flex w-full items-baseline gap-2 text-left">
                  <span style={{ color: DOT[role] }}>●</span>
                  <span className="flex-none text-[12.5px] font-semibold" style={{ color: BRIGHT[role] }}>{label}</span>
                  <span className="flex-1 truncate text-[11.5px] text-white/40">{row.status}</span>
                  <span className="flex-none text-[11px] text-white/35">{row.ms != null ? row.ms + 'ms' : ''}</span>
                </button>
                {openRows[i] && row.detail && (
                  <div className="ml-5 mt-1.5 rounded bg-white/[0.04] p-2 text-[11px] leading-relaxed text-white/60">{JSON.stringify(row.detail)}</div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
