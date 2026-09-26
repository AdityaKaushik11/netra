import clsx from "clsx";
import { X } from "lucide-react";
import { useEffect, type ReactNode } from "react";

export function Modal({
  title,
  onClose,
  children,
  wide,
  size,
}: {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
  size?: "xl";
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-[1000] flex items-start justify-center overflow-y-auto bg-black/60 p-4 backdrop-blur-sm sm:p-10" onMouseDown={onClose}>
      <div
        className={clsx("panel w-full shadow-2xl", size === "xl" ? "max-w-6xl" : wide ? "max-w-4xl" : "max-w-xl")}
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal
      >
        <div className="flex items-center justify-between border-b border-ink-700 px-4 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button className="text-ink-400 hover:text-ink-100" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-ink-300">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-ink-400">{hint}</span>}
    </label>
  );
}

export function Panel({
  title,
  actions,
  children,
  className,
  bodyClass,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClass?: string;
}) {
  return (
    <section className={clsx("panel flex min-h-0 flex-col", className)}>
      {(title || actions) && (
        <header className="flex items-center gap-2 border-b border-ink-700 px-3 py-2">
          <h3 className="panel-title">{title}</h3>
          <div className="ml-auto flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className={clsx("min-h-0 flex-1", bodyClass)}>{children}</div>
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="flex h-full min-h-24 items-center justify-center p-6 text-center text-xs text-ink-400">{children}</div>;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end gap-3 pb-4">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="text-xs text-ink-400">{subtitle}</p>}
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-2">{actions}</div>
    </div>
  );
}

export function Pager({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  if (total <= limit) return <div className="px-3 py-2 text-xs text-ink-400">{total} result(s)</div>;
  return (
    <div className="flex items-center gap-2 px-3 py-2 text-xs text-ink-400">
      {offset + 1}–{Math.min(offset + limit, total)} of {total}
      <button className="btn ml-auto py-0.5" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
        Prev
      </button>
      <button className="btn py-0.5" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
        Next
      </button>
    </div>
  );
}
