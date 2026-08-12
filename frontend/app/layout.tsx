import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Copiloto de Crédito PF',
  description: 'Demo de assistente de crédito — MongoDB Solutions Architect',
};

// The brand bar + persona switch live inside `AppShell`'s left pane (each
// route composes it there), not here — the target design anchors that bar to
// the 44% customer/analyst pane, not the full page width.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className="m-0 h-screen w-screen overflow-hidden font-sans text-charcoal">{children}</body>
    </html>
  );
}
