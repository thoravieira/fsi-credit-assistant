import { useCallback, useEffect, useRef, useState } from 'react';
import type { TraceEvent } from '../lib/api';
import { laneCardId } from '../lib/archMeta';

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
    (label: string, rows: TraceEvent[], speed = 1) => {
      clear();
      let t = 0;
      const step = 480 / speed; // speed 0.5x → 960ms/step, 1x → 480ms/step
      rows.forEach((row) => {
        t += step;
        const nodeId = laneCardId(row);
        timers.current.push(setTimeout(() => setReplay({ label, nodeId }), t));
      });
      timers.current.push(setTimeout(() => setReplay(null), t + 500 / speed));
    },
    [clear]
  );

  return { replay, start };
}
