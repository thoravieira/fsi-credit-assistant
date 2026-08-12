import type { Metadata } from 'next';
import { PersonaNav } from '../components/PersonaNav';
import './globals.css';

export const metadata: Metadata = {
  title: 'Copiloto de Crédito PF',
  description: 'Demo de assistente de crédito — MongoDB Solutions Architect',
};

// Persona switcher lives here because it triggers real navigation between the
// two routes (not just a state toggle) — see docs/specs/12-frontend.md §1.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className="m-0 font-sans text-ink">
        <header className="flex h-[52px] items-center justify-between border-b-2 border-ink/10 bg-white px-5">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-spring" />
            <span className="text-[13px] font-extrabold">Copiloto de Crédito PF</span>
          </div>
          <PersonaNav />
        </header>
        <main className="h-[calc(100vh-52px)]">{children}</main>
      </body>
    </html>
  );
}
