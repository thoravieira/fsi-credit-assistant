'use client';
import type { Persona, TraceEvent } from '../lib/api';
import { ArchitecturePanel, type FocusState } from './ArchitecturePanel';
import { TraceLog } from './TraceLog';

// The right 56% pane, identical in composition on both routes — each route
// just feeds it its own `useAgentStream` trace (docs/specs/12-frontend.md §1).
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
  return (
    <>
      <ArchitecturePanel persona={persona} trace={trace} isStreaming={isStreaming} onOpenNode={onOpenNode} replay={replay} focus={focus} />
      <TraceLog trace={trace} onOpenRow={onOpenRow} onReplay={onReplay} replayingLabel={replay?.label ?? null} />
    </>
  );
}
