import { useCallback, useEffect, useRef, useState } from 'react';
import type { TraceEvent } from '../lib/api';

// Replays a past turn's real trace rows across the architecture diagram —
// re-highlighting the steps in the order they actually ran, at a fixed pace
// for legibility. Not a re-execution: the rows themselves are the same real
// `TraceEvent`s already in `trace`, just re-walked visually.
export function useReplay() {
  const [replay, setReplay] = useState<{ label: string; nodeId: string } | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clear = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  }, []);

  useEffect(() => clear, [clear]);

  const start = useCallback(
    (label: string, rows: TraceEvent[]) => {
      clear();
      let t = 0;
      rows.forEach((row) => {
        t += 480;
        const nodeId = row.step ?? row.node;
        timers.current.push(setTimeout(() => setReplay({ label, nodeId }), t));
      });
      timers.current.push(setTimeout(() => setReplay(null), t + 500));
    },
    [clear]
  );

  return { replay, start };
}
