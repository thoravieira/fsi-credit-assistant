'use client';
import type { Persona, TraceEvent } from '../lib/api';
import {
  BRANCH_CHIPS_ANA, BRANCH_CHIPS_CUST, CHECKPOINT_NOTE, LANE, LANE_INFO, LANE_SEQ_ANA, LANE_SEQ_CUST,
  NODES, TRACK_META, fmtMs, laneCardId, summarizeDetail,
} from '../lib/archMeta';
import type { Lane } from '../lib/archMeta';

const LANES: Lane[] = ['agent', 'data', 'python'];
const ROW_H = 68;

export interface FocusState {
  nodeId: string;
  event?: TraceEvent;
}

// `finished` covers ordinary nodes; negotiation sub-steps (recalculate_scenario,
// policy_researcher, precedent_analyst, check_open_finance_assets) arrive as a
// single `status:'step'` event carrying their own `detail` directly — there is
// no separate `finished` event for those, so both statuses count as "real,
// completed data" for the lê/escreve footer.
function findRealEvent(trace: TraceEvent[], cid: string): TraceEvent | null {
  for (let i = trace.length - 1; i >= 0; i--) {
    const r = trace[i];
    if (laneCardId(r) === cid && (r.status === 'finished' || r.status === 'step')) return r;
  }
  return null;
}

/**
 * "Fluxo em tempo real" — the same real nodes as before, now grouped into
 * swimlanes by who executes them (LangGraph/FM vs. MongoDB Atlas vs. plain
 * Python) instead of a single technical-kind row. Highlight state and the
 * lê/escreve footer are driven by one shared `cid` computation — replay,
 * clicking a trace row (`focus`), or live execution all feed the same seam,
 * so the diagram and the real input/output are always showing the same step.
 */
export function ArchitecturePanel({
  persona,
  trace,
  isStreaming,
  onOpenNode,
  replay,
  focus,
  heightPercent = 62,
}: {
  persona: Persona;
  trace: TraceEvent[];
  isStreaming: boolean;
  onOpenNode: (id: string) => void;
  replay?: { label: string; nodeId: string } | null;
  focus?: FocusState | null;
  heightPercent?: number;
}) {
  const seq = persona === 'customer' ? LANE_SEQ_CUST : LANE_SEQ_ANA;
  const branchChips = persona === 'customer' ? BRANCH_CHIPS_CUST : BRANCH_CHIPS_ANA;
  const last = trace[trace.length - 1];
  const waiting = !replay && !focus && last?.status === 'interrupted';
  const liveActiveId = last && last.status !== 'finished' ? laneCardId(last) : null;
  const effectiveId = replay?.nodeId ?? focus?.nodeId ?? liveActiveId;

  const seen = (id: string) => trace.some((r) => laneCardId(r) === id);
  let doneIdx = -1;
  seq.forEach((id, i) => {
    if (seen(id)) doneIdx = i;
  });
  const activeIdx = effectiveId ? seq.indexOf(effectiveId) : -1;
  const curIdx = activeIdx >= 0 ? activeIdx : Math.max(doneIdx, 0);
  const cid = seq[curIdx] ?? seq[0];

  const info = NODES[cid];
  const meta = TRACK_META[cid];
  const laneOfCur = LANE_INFO[LANE[cid]];
  const realEvent = focus?.event && laneCardId(focus.event) === cid ? focus.event : findRealEvent(trace, cid);
  const ms = realEvent?.ms != null
    ? fmtMs(realEvent.ms)
    : realEvent && (realEvent.status === 'started' || realEvent.status === 'interrupted')
      ? 'em andamento'
      : info.rows.find((r) => r[0] === 'Latência')?.[1] ?? '—';
  const saida = (realEvent?.detail && summarizeDetail(realEvent.detail)) || (info.sample || '').split('\n')[0].slice(0, 110) || '—';

  const statusLine = replay
    ? 'replay · ' + replay.nodeId
    : waiting
      ? 'aguardando aprovação humana'
      : liveActiveId
        ? 'executando ' + liveActiveId
        : trace.length
          ? 'ocioso'
          : 'aguardando entrada';
  const statusActive = !!liveActiveId || waiting;

  return (
    <div className="flex flex-none flex-col overflow-hidden border-b-2 border-charcoal/40 px-[18px] pb-2.5 pt-3.5" style={{ height: heightPercent + '%' }}>
      <div className="mb-2.5 flex flex-none items-center justify-between gap-3">
        <span className="whitespace-nowrap text-[12px] font-extrabold uppercase tracking-[0.05em]">Fluxo em tempo real</span>
        <span
          className="flex items-center gap-2 whitespace-nowrap px-2.5 py-1 text-[11px] font-bold"
          style={{ color: '#001E2B', background: statusActive ? 'rgba(0,237,100,.22)' : 'rgba(32,30,29,.08)' }}
        >
          <span
            className={'inline-block h-[7px] w-[7px] ' + (statusActive ? 'animate-soft-blink' : '')}
            style={{ background: statusActive ? '#00ED64' : waiting ? '#023430' : '#8d9794' }}
          />
          {statusLine}
        </span>
      </div>

      <div className="mb-2.5 grid flex-none grid-cols-3 gap-2">
        {LANES.map((lane) => {
          const l = LANE_INFO[lane];
          return (
            <div key={lane} className="flex items-center gap-2 border border-charcoal/15 bg-white px-2 py-1.5" style={{ borderRadius: 8 }}>
              <span
                className="flex h-6 w-6 flex-none items-center justify-center border text-[10px] font-extrabold"
                style={{ borderRadius: 999, borderColor: l.accent, color: l.accent }}
              >
                {l.badge}
              </span>
              <div className="min-w-0">
                <div className="text-[9.5px] font-extrabold uppercase tracking-[0.05em]">{l.badgeLabel}</div>
                <div className="truncate text-[9px] text-charcoal/55">{l.desc}</div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mb-1.5 flex flex-none items-baseline justify-between">
        <span className="text-[10px] font-bold uppercase tracking-[0.04em] text-charcoal/50">Swimlanes por executor</span>
        <span className="text-[10px] text-charcoal/45">{persona === 'customer' ? 'Jornada da cliente' : 'Jornada do analista'} · selecione um passo</span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="grid grid-cols-3 gap-2" style={{ minHeight: seq.length * ROW_H }}>
          {LANES.map((lane) => {
            const l = LANE_INFO[lane];
            const rows = seq.map((id, i) => ({ id, i })).filter((r) => LANE[r.id] === lane);
            const firstRow = rows[0]?.i ?? 0;
            const lastRow = rows[rows.length - 1]?.i ?? 0;
            return (
              <div key={lane} className="relative" style={{ background: l.tint, borderRadius: 8, minHeight: seq.length * ROW_H }}>
                {rows.length > 1 && (
                  <div
                    className="absolute left-1/2"
                    style={{
                      top: firstRow * ROW_H + ROW_H / 2,
                      height: (lastRow - firstRow) * ROW_H,
                      borderLeft: `2px dashed ${l.accent}55`,
                    }}
                  />
                )}
                {rows.map(({ id, i }) => {
                  const on = i === activeIdx;
                  const lit = i <= doneIdx;
                  const m = TRACK_META[id];
                  return (
                    <button
                      key={id}
                      onClick={() => onOpenNode(id)}
                      className="absolute left-1.5 right-1.5 flex flex-col items-start gap-0.5 border bg-white px-2 py-1.5 text-left font-sans"
                      style={{
                        top: i * ROW_H + 3,
                        height: ROW_H - 6,
                        borderRadius: 7,
                        borderWidth: on ? 2 : 1,
                        borderColor: on || lit ? l.accent : 'rgba(32,30,29,.18)',
                        boxShadow: on ? `0 0 0 3px ${l.accent}30` : 'none',
                        opacity: lit || on ? 1 : 0.6,
                      }}
                    >
                      <span className="flex w-full items-center justify-between gap-1">
                        <span className="truncate font-mono text-[9px] font-semibold text-charcoal/40">{String(i + 1).padStart(2, '0')}</span>
                        {on && <span className="h-1.5 w-1.5 flex-none animate-soft-blink" style={{ background: l.accent, borderRadius: 999 }} />}
                      </span>
                      <span className="line-clamp-2 whitespace-normal break-words text-[10.5px] font-bold leading-[1.15] text-charcoal">{NODES[id].label}</span>
                      <span className="truncate text-[9px] text-charcoal/55">{m.tech}</span>
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>

      <div className="my-2 flex flex-none flex-wrap gap-1.5">
        {branchChips.map((c) => (
          <span key={c} className="whitespace-nowrap border border-charcoal/20 bg-white px-2 py-1 text-[9.5px] text-charcoal/65" style={{ borderRadius: 999 }}>
            {c}
          </span>
        ))}
      </div>

      <div className="mb-2 flex-none border-l-[3px] px-2.5 py-1.5 text-[10px] leading-snug text-charcoal/70" style={{ borderColor: LANE_INFO.data.accent, background: LANE_INFO.data.tint }}>
        {CHECKPOINT_NOTE}
      </div>

      <div className="grid flex-none grid-cols-3 gap-2 border-t-2 border-charcoal/40 pt-2">
        <div>
          <div className="text-[9px] font-extrabold uppercase tracking-[0.05em] text-charcoal/45">Passo ativo · {laneOfCur.badgeLabel}</div>
          <div className="mt-0.5 truncate text-[12.5px] font-bold">{info.label}</div>
          <div className="mt-0.5 line-clamp-2 text-[10px] leading-snug text-charcoal/60">{info.what}</div>
          <div className="mt-1 font-mono text-[9.5px] text-charcoal/45">{ms}</div>
        </div>
        <div>
          <div className="text-[9px] font-extrabold uppercase tracking-[0.05em] text-charcoal/45">Input</div>
          <div className="mt-0.5 font-mono text-[10px] leading-snug text-charcoal">{meta.in}</div>
        </div>
        <div>
          <div className="text-[9px] font-extrabold uppercase tracking-[0.05em] text-charcoal/45">Output</div>
          <div className="mt-0.5 font-mono text-[10px] leading-snug text-forest">{saida}</div>
        </div>
      </div>
    </div>
  );
}
