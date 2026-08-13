'use client';
import { useState } from 'react';
import type { TraceEvent } from '../lib/api';
import { CHIP, NODES, TESTS, chipOf, fmtMs, githubUrl, laneCardId, type SourceRef } from '../lib/archMeta';

export type DrawerState =
  | { kind: 'node'; id: string }
  | { kind: 'row'; event: TraceEvent; groupLabel: string }
  | null;

// `status:'step'` events (negotiation tool/subagent announcements, SDD 06 §6)
// never carry `ms` — they are a one-shot announcement with its own `detail`,
// not a node boundary the backend timed. Only `started`/`interrupted` are
// genuinely still running; a `step` with no `ms` is already complete.
function latencyLabel(ms: number | undefined, status: TraceEvent['status']): string {
  if (ms != null) return fmtMs(ms);
  return status === 'started' || status === 'interrupted' ? 'em andamento' : 'concluído';
}

function stringifyDetailValue(v: unknown): string {
  if (typeof v === 'string') return v;
  return JSON.stringify(v);
}

// Slide-in detail panel, opened either from an architecture-diagram step
// (static reference copy from `archMeta`) or from a live trace-log row (the
// real `TraceEvent.detail` from that exact event, falling back to reference
// copy only when the event hasn't reported detail yet — e.g. `started` rows).
export function Drawer({ state, onClose }: { state: DrawerState; onClose: () => void }) {
  const [usageOpen, setUsageOpen] = useState(false);
  if (!state) return null;

  let kicker: string, title: string, subtitle: string, what: string;
  let chips: { label: string; bg: string; color: string }[];
  let rows: [string, string][];
  let sampleLabel: string, sample: string | undefined;
  let code: string | undefined;
  let source: SourceRef | undefined;
  let usage: SourceRef | undefined;
  let test: SourceRef | undefined;
  const isRealEvent = state.kind === 'row';

  if (state.kind === 'node') {
    const info = NODES[state.id];
    if (!info) return null;
    kicker = 'Componente da arquitetura';
    title = info.label;
    subtitle = info.sub;
    what = info.what;
    chips = info.chips.map((k) => CHIP[k]);
    rows = info.rows;
    sampleLabel = 'Exemplo típico deste passo';
    sample = info.sample;
    code = info.code;
    source = info.source;
    usage = info.usage;
    test = TESTS[state.id];
  } else {
    const { event, groupLabel } = state;
    const key = event.step ?? event.node;
    const infoId = laneCardId(event);
    const info = NODES[infoId];
    kicker = 'Passo do trace · ' + groupLabel;
    title = event.step ? event.node + ' · ' + event.step : event.node;
    subtitle = (info?.sub ?? '') + ' · status ' + event.status + (event.ms != null ? ' · ' + fmtMs(event.ms) : '');
    const detailEntries = event.detail ? Object.entries(event.detail) : [];
    what = detailEntries.length ? '' : info?.what ?? event.detail ? '' : 'Este passo ainda não retornou detalhe — aguardando conclusão.';
    chips = [chipOf(infoId)];
    rows = detailEntries.length
      ? [...detailEntries.map(([k, v]) => [k, stringifyDetailValue(v)] as [string, string]), ['latência', latencyLabel(event.ms, event.status)], ['grupo', groupLabel]]
      : info?.rows ?? [['latência', latencyLabel(event.ms, event.status)], ['grupo', groupLabel]];
    if (detailEntries.length) {
      sampleLabel = 'Dado real deste evento';
      sample = JSON.stringify(event.detail, null, 2);
    } else {
      sampleLabel = 'Exemplo típico deste passo';
      sample = info?.sample;
    }
    code = info?.code;
    source = info?.source;
    usage = info?.usage;
    test = TESTS[infoId];
  }

  return (
    <div
      className="fixed bottom-0 right-0 top-0 z-[60] flex flex-col border-l-2 border-charcoal/50 bg-paper"
      style={{ width: 'min(460px, 46vw)', boxShadow: '-14px 0 34px rgba(45,43,43,.18)' }}
    >
      <div className="flex flex-none items-start justify-between gap-3.5 border-b-2 border-charcoal/40 px-[18px] py-4">
        <div className="min-w-0">
          <div className="text-[9.5px] font-extrabold uppercase tracking-[0.08em] text-charcoal/50">{kicker}</div>
          <div className="mt-[3px] font-mono text-[17px] font-semibold">{title}</div>
          <div className="mt-[3px] text-[11.5px] text-charcoal/55">{subtitle}</div>
        </div>
        <button onClick={onClose} className="flex h-[30px] w-[30px] flex-none items-center justify-center border border-charcoal/40 bg-white text-sm">
          ×
        </button>
      </div>
      <div className="flex flex-1 flex-col gap-3.5 overflow-auto px-[18px] py-4">
        <div className="flex flex-wrap gap-[5px]">
          <span className={'px-[9px] py-1 text-[10px] font-extrabold uppercase tracking-[0.04em] ' + (isRealEvent ? 'bg-[#D7F4E3] text-forest' : 'bg-[#F6EEDC] text-[#8A520F]')}>
            {isRealEvent ? 'dado real desta execução' : 'explicação estática'}
          </span>
          {chips.map((c, i) => (
            <span key={i} className="px-[9px] py-1 text-[10px] font-bold uppercase tracking-[0.04em]" style={{ background: c.bg, color: c.color }}>
              {c.label}
            </span>
          ))}
        </div>
        {what && <p className="text-[13px] leading-[1.6] text-charcoal/85">{what}</p>}

        {rows.map(([k, v], i) => (
          <div key={i} className="flex gap-3 border-t border-charcoal/[0.18] pt-[9px]">
            <span className="w-[104px] flex-none text-[9.5px] font-extrabold uppercase tracking-[0.05em] text-charcoal/50">{k}</span>
            <span className="min-w-0 flex-1 text-[12px] leading-[1.55]" style={{ overflowWrap: 'anywhere' }}>{v}</span>
          </div>
        ))}

        {sample && (
          <div>
            <div className="mb-1.5 flex items-center gap-2 text-[9.5px] font-extrabold uppercase tracking-[0.06em] text-charcoal/50">
              {sampleLabel}
              {sampleLabel.startsWith('Exemplo') && <span className="bg-[#F6EEDC] px-1.5 py-0.5 text-[8px] text-[#8A520F]">ilustrativo</span>}
            </div>
            <pre className="overflow-auto whitespace-pre-wrap bg-ink p-3 font-mono text-[10.5px] leading-[1.6] text-[#C9D6D1]">{sample}</pre>
          </div>
        )}

        {code && (
          <div>
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <span className="text-[9.5px] font-extrabold uppercase tracking-[0.06em] text-charcoal/50">
                Pseudocódigo explicativo{source && <span className="ml-1.5 font-mono normal-case text-charcoal/40">· fonte real: {source.file}:{source.lines[0]}-{source.lines[1]}</span>}
              </span>
              {source && (
                <a
                  href={githubUrl(source.file, source.lines)}
                  target="_blank"
                  rel="noreferrer"
                  className="flex-none border border-forest px-2 py-[3px] text-[9.5px] font-bold text-forest hover:bg-forest hover:text-white"
                >
                  Abrir no GitHub ↗
                </a>
              )}
            </div>
            <pre className="overflow-auto whitespace-pre-wrap border border-charcoal/25 bg-white p-3 font-mono text-[10.5px] leading-[1.6] text-charcoal">{code}</pre>
          </div>
        )}

        {usage && (
          <div className="border-t border-charcoal/[0.18] pt-3">
            {/* Collapsed by default — where this is wired into the graph,
                not the implementation itself (item 9). */}
            <button
              onClick={() => setUsageOpen((o) => !o)}
              className="flex w-full items-center justify-between border-none bg-transparent p-0 text-left"
            >
              <span className="text-[9.5px] font-extrabold uppercase tracking-[0.06em] text-charcoal/50">
                Onde é usado <span className="font-mono normal-case text-charcoal/40">· {usage.file}:{usage.lines[0]}{usage.lines[1] !== usage.lines[0] ? '-' + usage.lines[1] : ''}</span>
              </span>
              <span className="text-[10px] text-charcoal/40">{usageOpen ? '▲' : '▼'}</span>
            </button>
            {usageOpen && (
              <a
                href={githubUrl(usage.file, usage.lines)}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-block border border-forest px-2 py-[3px] text-[9.5px] font-bold text-forest hover:bg-forest hover:text-white"
              >
                Abrir no GitHub ↗
              </a>
            )}
          </div>
        )}

        {test && (
          <div className="border-t border-charcoal/[0.18] pt-3">
            <div className="mb-2 text-[9.5px] font-extrabold uppercase tracking-[0.06em] text-charcoal/50">
              Como é testado <span className="font-mono normal-case text-charcoal/40">· {test.file}:{test.lines[0]}-{test.lines[1]}</span>
            </div>
            <a
              href={githubUrl(test.file, test.lines)}
              target="_blank"
              rel="noreferrer"
              className="inline-block border border-forest px-2 py-[3px] text-[9.5px] font-bold text-forest hover:bg-forest hover:text-white"
            >
              Abrir teste no GitHub ↗
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
