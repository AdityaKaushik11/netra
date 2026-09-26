import { humanKey } from "../lib/format";

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (Array.isArray(v)) return v.map(fmt).join(", ");
  if (typeof v === "object") {
    return Object.entries(v as Record<string, unknown>)
      .map(([k, x]) => `${humanKey(k)} ${fmt(x)}`)
      .join(", ");
  }
  return String(v);
}

/** Human-readable rendering of audit / metric detail objects (no raw JSON on screen). */
export function DetailsView({ details }: { details: Record<string, unknown> | null | undefined }) {
  if (!details || Object.keys(details).length === 0) return <span className="text-ink-500">—</span>;
  // Status-style records {from, to, ...}: show the transition first, in reading order
  const { from, to, ...rest } = details;
  const transition = "from" in details && "to" in details;
  const entries = Object.entries(transition ? rest : details);
  return (
    <span className="flex flex-wrap gap-1">
      {transition && (
        <span className="rounded bg-ink-800 px-1.5 py-0.5 text-[11px] font-medium text-ink-100">
          {fmt(from)} <span className="text-accent">→</span> {fmt(to)}
        </span>
      )}
      {entries.map(([k, v]) => {
        const change = v && typeof v === "object" && !Array.isArray(v) && "from" in v && "to" in v;
        return (
          <span key={k} className="rounded bg-ink-800 px-1.5 py-0.5 text-[11px] text-ink-200">
            <span className="text-ink-400">{humanKey(k)}: </span>
            {change ? (
              <>
                {fmt((v as { from: unknown }).from)} <span className="text-accent">→</span> {fmt((v as { to: unknown }).to)}
              </>
            ) : (
              fmt(v)
            )}
          </span>
        );
      })}
    </span>
  );
}
