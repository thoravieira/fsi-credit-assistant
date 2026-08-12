'use client';
import { useEffect, useRef } from 'react';
import type { TraceEvent } from '../lib/api';
import { chipOf, dotOf, fmtMs, summarizeDetail } from '../lib/archMeta';

// `step` (negotiation tool/subagent announcements) is a completed, one-shot
// event, not a pending one — only `started`/`interrupted` are actually still
// running (same distinction as Drawer.tsx's `latencyLabel`).
function statusFallback(status: TraceEvent['status']): string {
  switch (status) {
    case 'started':
      return 'iniciado';
    case 'interrupted':
      return 'pausado';
    default:
      return 'concluído';
  }
}

interface Group {
  label: string;
  rows: TraceEvent[];
}

// Splits the flat `trace` array into turns: every real turn starts with a
// `router` node (both TRACK_CUST and TRACK_ANA in `archMeta` begin there),
// so a `router`/`started` event is the boundary — no separate "turn id"
// exists on `TraceEvent` itself, so this is derived, not stored.
function groupByTurn(trace: TraceEvent[]): Group[] {
  const groups: Group[] = [];
  trace.forEach((r) => {
    const startsNewTurn = r.node === 'router' && r.status === 'started';
    if (startsNewTurn || groups.length === 0) {
      groups.push({ label: 'Turno ' + (groups.length + 1), rows: [r] });
    } else {
      groups[groups.length - 1].rows.push(r);
    }
  });
  return groups;
}

/**
 * Bottom-right panel: the live trace log, grouped by turn. Driven entirely by
 * `trace` — no simulated timings, no hardcoded step lists (SDD 11 §4,
 * SDD 12 §3 acceptance criteria).
 */
export function TraceLog({
  trace,
  onOpenRow,
  onReplay,
  replayingLabel,
}: {
  trace: TraceEvent[];
  onOpenRow: (event: TraceEvent, groupLabel: string) => void;
  onReplay: (label: string, rows: TraceEvent[]) => void;
  replayingLabel?: string | null;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [trace.length]);

  const groups = groupByTurn(trace).slice(-5);

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-surface">
      <div className="flex flex-none items-baseline justify-between px-[18px] pb-[7px] pt-[11px]">
        <span className="text-[12px] font-extrabold uppercase tracking-[0.05em]">Trace ao vivo</span>
        <span className="text-[10px] text-charcoal/50">
          {trace.length ? trace.length + ' eventos · clique num passo para abrir os dados' : ''}
        </span>
      </div>
      <div ref={listRef} className="flex-1 overflow-auto px-[18px] pb-3.5">
        {trace.length === 0 && (
          <div className="py-3.5 font-mono text-[12px] text-charcoal/45">Envie uma simulação ou abra um caso para ver o trace ao vivo…</div>
        )}
        {groups.map((g, gi) => {
          const total = g.rows.reduce((a, r) => a + (r.ms ?? 0), 0);
          const replaying = replayingLabel === g.label;
          return (
            <div key={gi} className="mb-3">
              <div className="mb-[3px] flex items-center gap-2 border-b-2 border-charcoal/40 py-[5px]">
                <button
                  onClick={() => onReplay(g.label, g.rows)}
                  title="Replay no diagrama"
                  className="flex flex-none items-center gap-[5px] border border-forest px-2 py-[3px] text-[10px] font-bold"
                  style={{ background: replaying ? '#00684A' : '#fff', color: replaying ? '#fff' : '#00684A' }}
                >
                  <span className="text-[9px]">▶</span>Replay
                </button>
                <span className="text-[10.5px] font-extrabold uppercase tracking-[0.05em]">{g.label}</span>
                <span className="font-mono text-[9.5px] text-charcoal/50">{g.rows.length} passos · {fmtMs(total)}</span>
              </div>
              {g.rows.map((row, ri) => {
                const key = row.step ?? row.node;
                const chip = chipOf(key);
                const label = row.status === 'step' ? row.node + ' · ' + row.step : row.node;
                const detail = summarizeDetail(row.detail) ?? statusFallback(row.status);
                return (
                  <button
                    key={ri}
                    onClick={() => onOpenRow(row, g.label)}
                    className="flex w-full animate-row-in items-center gap-2 border-none border-b border-charcoal/[0.14] bg-transparent px-1 py-1.5 text-left font-sans"
                  >
                    <span className="flex-none text-[10px]" style={{ color: dotOf(key) }}>■</span>
                    <span className="flex-none text-[11.5px] font-semibold">{label}</span>
                    <span className="flex-none px-1.5 py-0.5 text-[10px] font-bold" style={{ background: chip.bg, color: chip.color }}>{chip.label}</span>
                    <span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-[10.5px] text-charcoal/60">{detail}</span>
                    <span className="flex-none font-mono text-[10px] text-charcoal/45">{fmtMs(row.ms)}</span>
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
