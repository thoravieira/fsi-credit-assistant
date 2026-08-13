import { CUSTOMER_NAMES, CreditApplication, PRODUCT_LABELS, fmtBRL } from '../lib/api';

export interface PendingCase {
  id: string;
  name: string;
  product: string;
  amount: string;
  flag: string;
  activity: string;
}

function formatActivity(value?: string): string {
  if (!value) return 'Data não informada';
  // MongoDB returns UTC datetimes without a suffix with the default PyMongo
  // codec. Add it explicitly so browsers do not reinterpret UTC as local.
  const utcValue = /(Z|[+-]\d{2}:\d{2})$/.test(value) ? value : value + 'Z';
  const date = new Date(utcValue);
  if (Number.isNaN(date.getTime())) return 'Data não informada';
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
    timeZone: 'America/Sao_Paulo',
  }).format(date);
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
    activity: formatActivity(doc.updated_at ?? doc.created_at),
  };
}

export function CaseQueue({ cases, onSelect }: { cases: PendingCase[]; onSelect: (id: string) => void }) {
  if (!cases.length) return <p className="py-6 text-sm text-charcoal/50">Nenhum caso nesta fila.</p>;
  return (
    <div className="flex flex-col">
      {cases.map((c) => (
        <button key={c.id} onClick={() => onSelect(c.id)} className="flex items-center gap-3.5 border-none border-b border-charcoal/[0.18] bg-transparent py-3.5 text-left">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-[13.5px] font-bold">{c.name}</span>
            </div>
            <div className="mt-0.5 text-[11.5px] text-charcoal/50">{c.product} · {c.amount} · {c.id}</div>
            <div className="mt-0.5 text-[10.5px] font-medium text-charcoal/45">Atualizado em {c.activity}</div>
            <div className="mt-0.5 text-[11.5px] text-charcoal/75">{c.flag}</div>
          </div>
          <span className="flex-none text-charcoal/40">›</span>
        </button>
      ))}
    </div>
  );
}
