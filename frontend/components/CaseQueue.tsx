import { CUSTOMER_NAMES, CreditApplication, PRODUCT_LABELS, fmtBRL } from '../lib/api';

export interface PendingCase {
  id: string;
  name: string;
  product: string;
  amount: string;
  flag: string;
}

// Real `applications` documents (SDD 11 §1 `GET /api/applications`) mapped to
// what the queue row needs. There is no name-join endpoint over
// `customer_id`, so the name falls back to the raw id for customers outside
// the seeded directory (lib/api.ts `CUSTOMER_NAMES`) instead of guessing one.
export function toPendingCase(doc: CreditApplication): PendingCase {
  const reason = doc.latest_assessment?.decision?.reasons?.[0];
  return {
    id: doc.application_id,
    name: CUSTOMER_NAMES[doc.customer_id] ?? doc.customer_id,
    product: PRODUCT_LABELS[doc.product] ?? doc.product,
    amount: fmtBRL(doc.asset_value),
    flag: reason ?? 'Fora da faixa de aprovação automática.',
  };
}

export function CaseQueue({ cases, onSelect }: { cases: PendingCase[]; onSelect: (id: string) => void }) {
  if (!cases.length) return <p className="py-6 text-sm text-ink/50">Nenhum caso nesta fila.</p>;
  return (
    <div className="flex flex-col">
      {cases.map((c) => (
        <button key={c.id} onClick={() => onSelect(c.id)} className="flex items-center gap-3.5 border-b border-ink/10 py-3.5 text-left">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-[13.5px] font-bold">{c.name}</span>
            </div>
            <div className="mt-0.5 text-[11.5px] text-ink/55">{c.product} · {c.amount} · {c.id}</div>
            <div className="mt-0.5 text-[11.5px] text-ink/70">{c.flag}</div>
          </div>
          <span className="flex-none text-ink/30">›</span>
        </button>
      ))}
    </div>
  );
}
