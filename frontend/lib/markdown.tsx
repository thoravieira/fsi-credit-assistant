// Minimal hand-rolled renderer for the LLM's own prose (customer_response,
// analyst_brief, negotiation) — bold/italic/code/lists/headings only, no HTML
// parsing and no `dangerouslySetInnerHTML`: every node is a real React
// element, so there is no injection surface for whatever the model writes.
import type { ReactNode } from 'react';

const INLINE_RE = /(\*\*(.+?)\*\*|`([^`]+?)`|\*(.+?)\*|_(.+?)_)/g;

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let i = 0;
  INLINE_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = INLINE_RE.exec(text))) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[2] !== undefined) nodes.push(<b key={keyPrefix + i++}>{m[2]}</b>);
    else if (m[3] !== undefined)
      nodes.push(
        <code key={keyPrefix + i++} className="bg-charcoal/[0.08] px-1 py-[1px] font-mono text-[0.92em]">
          {m[3]}
        </code>
      );
    else nodes.push(<i key={keyPrefix + i++}>{m[4] ?? m[5]}</i>);
    last = INLINE_RE.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function isListLine(line: string): boolean {
  return /^\s*([-*]|\d+\.)\s+/.test(line);
}

export function Markdown({ text, className }: { text: string; className?: string }) {
  const blocks = text.split(/\n{2,}/).filter((b) => b.trim().length > 0);

  return (
    <div className={className}>
      {blocks.map((block, bi) => {
        const lines = block.split('\n').filter((l) => l.trim().length > 0);

        if (lines.length > 0 && lines.every(isListLine)) {
          const ordered = /^\s*\d+\./.test(lines[0]);
          const items = lines.map((l) => l.replace(/^\s*([-*]|\d+\.)\s+/, ''));
          const Tag = ordered ? 'ol' : 'ul';
          return (
            <Tag key={bi} className={'my-1 flex flex-col gap-1 pl-4 ' + (ordered ? 'list-decimal' : 'list-disc')}>
              {items.map((it, ii) => (
                <li key={ii}>{renderInline(it, bi + '-' + ii + '-')}</li>
              ))}
            </Tag>
          );
        }

        const heading = block.match(/^(#{1,4})\s+(.*)$/);
        if (heading) {
          const level = heading[1].length;
          return (
            <div key={bi} className={'mt-1.5 first:mt-0 ' + (level <= 2 ? 'text-[13px] font-extrabold' : 'text-[12.5px] font-bold')}>
              {renderInline(heading[2], bi + '-h-')}
            </div>
          );
        }

        const bodyLines = block.split('\n');
        return (
          <p key={bi} className="mt-2 first:mt-0">
            {bodyLines.map((line, li) => (
              <span key={li}>
                {renderInline(line, bi + '-' + li + '-')}
                {li < bodyLines.length - 1 && <br />}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}
