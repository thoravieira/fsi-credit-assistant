import type { ReactNode } from 'react';
import { PersonaHeader } from './PersonaHeader';

// The two-pane shell shared by both routes: left 44% is persona content
// (Mariana's phone or Carlos's console), right 56% is the live architecture
// diagram + trace log for that route's own `useAgentStream` instance. Each
// route composes this the same way — see docs/specs/12-frontend.md §1.
export function AppShell({
  left,
  right,
  leftBg = '#f3f2f2',
  drawer,
}: {
  left: ReactNode;
  right: ReactNode;
  leftBg?: string;
  drawer?: ReactNode;
}) {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-paper font-sans text-charcoal">
      <div className="flex w-[44%] flex-none flex-col overflow-hidden border-r-2 border-charcoal/40" style={{ background: leftBg }}>
        <PersonaHeader />
        <div className="flex flex-1 flex-col overflow-hidden">{left}</div>
      </div>
      <div className="flex w-[56%] flex-none flex-col overflow-hidden bg-paper">{right}</div>
      {drawer}
    </div>
  );
}
