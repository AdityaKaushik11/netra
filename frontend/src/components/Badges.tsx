import clsx from "clsx";
import type { AlertStatus, CameraStatus, Severity, SourceProtocol } from "../api/types";

export const STATUS_COLOR: Record<CameraStatus, string> = {
  ONLINE: "var(--color-online)",
  DEGRADED: "var(--color-degraded)",
  OFFLINE: "var(--color-offline)",
  UNKNOWN: "var(--color-unknown)",
};

export const SEVERITY_COLOR: Record<Severity, string> = {
  CRITICAL: "var(--color-sev-critical)",
  HIGH: "var(--color-sev-high)",
  MEDIUM: "var(--color-sev-medium)",
  LOW: "var(--color-sev-low)",
};

export function StatusDot({ status, className }: { status: CameraStatus; className?: string }) {
  return (
    <span
      className={clsx("inline-block size-2 shrink-0 rounded-full", className)}
      style={{ background: STATUS_COLOR[status], boxShadow: `0 0 6px ${STATUS_COLOR[status]}` }}
    />
  );
}

export function StatusBadge({ status, enabled = true }: { status: CameraStatus; enabled?: boolean }) {
  if (!enabled)
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md border border-ink-600 px-1.5 py-0.5 text-[11px] font-semibold text-ink-400">
        DISABLED
      </span>
    );
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-[11px] font-semibold"
      style={{ color: STATUS_COLOR[status], background: `color-mix(in srgb, ${STATUS_COLOR[status]} 14%, transparent)` }}
    >
      <StatusDot status={status} />
      {status}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className="inline-block rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wider"
      style={{
        color: SEVERITY_COLOR[severity],
        background: `color-mix(in srgb, ${SEVERITY_COLOR[severity]} 16%, transparent)`,
        border: `1px solid color-mix(in srgb, ${SEVERITY_COLOR[severity]} 40%, transparent)`,
      }}
    >
      {severity}
    </span>
  );
}

const ALERT_STATUS_STYLE: Record<AlertStatus, string> = {
  NEW: "bg-red-500/15 text-red-300 border-red-500/40",
  ACKNOWLEDGED: "bg-amber-500/10 text-amber-300 border-amber-500/40",
  RESOLVED: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  FALSE_POSITIVE: "bg-slate-500/10 text-slate-300 border-slate-500/30",
};

export function AlertStatusBadge({ status }: { status: AlertStatus }) {
  return (
    <span className={clsx("inline-block rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wide", ALERT_STATUS_STYLE[status])}>
      {status.replace("_", " ")}
    </span>
  );
}

export function ProtocolBadge({ protocol }: { protocol: SourceProtocol }) {
  return (
    <span className="rounded border border-ink-600 bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] text-ink-200">
      {protocol.replace("_", " ")}
    </span>
  );
}

export function Plate({ value, className }: { value: string | null | undefined; className?: string }) {
  if (!value) return <span className="text-ink-400">—</span>;
  const isPerson = value.startsWith("FR-");
  if (isPerson)
    return <span className={clsx("rounded bg-violet-500/15 px-1.5 font-mono text-xs text-violet-200", className)}>{value}</span>;
  return <span className={clsx("plate", className)}>{value}</span>;
}

export function Confidence({ value }: { value: number }) {
  const color = value >= 0.9 ? "var(--color-online)" : value >= 0.75 ? "var(--color-degraded)" : "var(--color-offline)";
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-xs">
      <span className="h-1.5 w-10 overflow-hidden rounded-full bg-ink-700">
        <span className="block h-full rounded-full" style={{ width: `${value * 100}%`, background: color }} />
      </span>
      {Math.round(value * 100)}%
    </span>
  );
}
