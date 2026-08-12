'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

// Top bar of the left pane: brand mark + persona switch. Real Next.js
// navigation between the two routes (not a state toggle) — each route owns
// its own `useAgentStream` instance (docs/specs/12-frontend.md §1).
export function PersonaHeader() {
  const pathname = usePathname();
  const isCustomer = pathname === '/';
  const pill = (active: boolean) =>
    'border-none px-[13px] py-2 font-sans text-[11.5px] font-semibold ' + (active ? 'bg-charcoal text-paper' : 'bg-transparent text-charcoal/60');

  return (
    <div className="flex h-[58px] flex-none items-center justify-between border-b-2 border-charcoal/40 bg-white px-[18px]">
      <div className="flex items-center gap-[9px]">
        <span className="inline-block h-[9px] w-[9px] bg-spring" />
        <span className="text-[12.5px] font-extrabold uppercase tracking-[0.02em]">Copiloto de Crédito PF</span>
      </div>
      <div className="inline-flex border border-charcoal/40">
        <Link href="/" className={pill(isCustomer)}>Cliente</Link>
        <Link href="/console" className={'border-l border-charcoal/40 ' + pill(!isCustomer)}>Analista</Link>
      </div>
    </div>
  );
}
