'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Persona, TraceEvent } from '../lib/api';
import { ArchitecturePanel, type FocusState } from './ArchitecturePanel';
import { TraceLog } from './TraceLog';

const SPLIT_STORAGE_KEY = 'fsi-right-pane-split';
const SPLIT_MIN = 25;
const SPLIT_MAX = 80;
const SPLIT_DEFAULT = 62;

// The right 56% pane, identical in composition on both routes — each route
// just feeds it its own `useAgentStream` trace (docs/specs/12-frontend.md §1).
// The split between "Fluxo em tempo real" and "Trace ao vivo" is user-draggable;
// the ratio is remembered across reloads so it doesn't reset every session.
export function RightPane({
  persona,
  trace,
  isStreaming,
  replay,
  focus,
  onOpenNode,
  onOpenRow,
  onReplay,
}: {
  persona: Persona;
  trace: TraceEvent[];
  isStreaming: boolean;
  replay: { label: string; nodeId: string } | null;
  focus: FocusState | null;
  onOpenNode: (id: string) => void;
  onOpenRow: (event: TraceEvent, groupLabel: string) => void;
  onReplay: (label: string, rows: TraceEvent[]) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [splitPercent, setSplitPercent] = useState(SPLIT_DEFAULT);

  useEffect(() => {
    const saved = Number(localStorage.getItem(SPLIT_STORAGE_KEY));
    if (saved >= SPLIT_MIN && saved <= SPLIT_MAX) setSplitPercent(saved);
  }, []);

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const container = containerRef.current;
    if (!container) return;
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';

    const onMove = (ev: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      const pct = ((ev.clientY - rect.top) / rect.height) * 100;
      setSplitPercent(Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, pct)));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      setSplitPercent((pct) => {
        localStorage.setItem(SPLIT_STORAGE_KEY, String(pct));
        return pct;
      });
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, []);

  return (
    <div ref={containerRef} className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
      <ArchitecturePanel
        persona={persona}
        trace={trace}
        isStreaming={isStreaming}
        onOpenNode={onOpenNode}
        replay={replay}
        focus={focus}
        heightPercent={splitPercent}
      />
      <div
        onMouseDown={handleDragStart}
        className="group flex h-2 flex-none cursor-row-resize items-center justify-center bg-paper"
      >
        <div className="h-[3px] w-10 rounded-full bg-charcoal/15 group-hover:bg-charcoal/40" />
      </div>
      <TraceLog trace={trace} onOpenRow={onOpenRow} onReplay={onReplay} replayingLabel={replay?.label ?? null} />
    </div>
  );
}
