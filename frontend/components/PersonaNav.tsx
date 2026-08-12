'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

// A client component so `usePathname()` can highlight the active route — kept
// separate from `app/layout.tsx` so the layout itself stays a server
// component and can export `metadata` the idiomatic way.
export function PersonaNav() {
  const pathname = usePathname();
  const linkClass = (active: boolean) =>
    'rounded-full px-4 py-1.5 text-[12px] font-bold ' + (active ? 'bg-white text-ink shadow-sm' : 'text-ink/70 hover:text-ink');
  return (
    <nav className="inline-flex gap-0.5 rounded-full bg-[#EEF2EF] p-1">
      <Link href="/" className={linkClass(pathname === '/')}>Jornada da Cliente</Link>
      <Link href="/console" className={linkClass(pathname === '/console')}>Jornada do Analista</Link>
    </nav>
  );
}
