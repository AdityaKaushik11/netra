import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { CheckCheck, Eye } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, qs } from "../api/client";
import type { Alert, AlertStatus, Page } from "../api/types";
import { AlertDetail } from "../components/AlertDetail";
import { AlertStatusBadge, Confidence, Plate, SEVERITY_COLOR, SeverityBadge } from "../components/Badges";
import { Empty, PageHeader, Pager, Panel } from "../components/ui";
import { useAuth } from "../hooks/auth";
import { useRealtime } from "../hooks/realtime";
import { ago, fmtDateTime, titleCase } from "../lib/format";

const TABS: { label: string; status: AlertStatus[] }[] = [
  { label: "Open", status: ["NEW", "ACKNOWLEDGED"] },
  { label: "New", status: ["NEW"] },
  { label: "Acknowledged", status: ["ACKNOWLEDGED"] },
  { label: "Closed", status: ["RESOLVED", "FALSE_POSITIVE"] },
  { label: "All", status: [] },
];

export function AlertsPage() {
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState(0);
  const [severity, setSeverity] = useState("");
  const [offset, setOffset] = useState(0);
  const { recentAlertIds } = useRealtime();
  const { can } = useAuth();
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkNote, setBulkNote] = useState("");
  const focus = params.get("focus");
  const limit = 50;
  const { data } = useQuery({
    queryKey: ["alerts", tab, severity, offset],
    queryFn: () => api<Page<Alert>>(`/alerts${qs({ status: TABS[tab].status, severity, limit, offset })}`),
  });

  const openIds = (data?.items ?? []).filter((a) => a.status === "NEW" || a.status === "ACKNOWLEDGED").map((a) => a.id);
  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const bulk = useMutation({
    mutationFn: (action: "acknowledge" | "resolve") =>
      api<{ updated: number }>("/alerts/bulk", { method: "POST", json: { action, ids: [...selected], note: bulkNote || null } }),
    onSuccess: (r, action) => {
      toast.success(`${r.updated} alert(s) ${action === "resolve" ? "resolved" : "acknowledged"}`);
      setSelected(new Set());
      setBulkNote("");
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div>
      <PageHeader title="Alerts" subtitle="Watchlist correlation results · acknowledge and resolve with an auditable note" />
      {selected.size > 0 && can("ADMIN", "OPERATOR") && (
        <div className="panel mb-3 flex flex-wrap items-center gap-2 p-2 text-xs">
          <span className="font-semibold">{selected.size} selected</span>
          <input
            className="input w-72 py-1"
            placeholder="Note (required to resolve)"
            value={bulkNote}
            onChange={(e) => setBulkNote(e.target.value)}
          />
          <button className="btn py-1 text-xs" disabled={bulk.isPending} onClick={() => bulk.mutate("acknowledge")}>
            <Eye size={13} /> Acknowledge
          </button>
          <button
            className="btn btn-primary py-1 text-xs"
            disabled={bulk.isPending || bulkNote.trim().length < 3}
            onClick={() => bulk.mutate("resolve")}
          >
            <CheckCheck size={13} /> Resolve
          </button>
          <button className="ml-auto text-ink-400 hover:text-ink-100" onClick={() => setSelected(new Set())}>
            Clear
          </button>
        </div>
      )}
      <Panel
        title={
          <div className="flex gap-1 normal-case">
            {TABS.map((t, i) => (
              <button
                key={t.label}
                onClick={() => {
                  setTab(i);
                  setOffset(0);
                }}
                className={clsx("rounded px-2 py-1 text-xs tracking-normal", tab === i ? "bg-ink-700 text-accent" : "text-ink-300 hover:text-ink-100")}
              >
                {t.label}
              </button>
            ))}
          </div>
        }
        actions={
          <select className="input w-auto py-1" value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="">All severities</option>
            {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        }
        bodyClass="overflow-x-auto"
      >
        <table className="data">
          <thead>
            <tr>
              <th className="w-8">
                <input
                  type="checkbox"
                  aria-label="Select all open alerts on this page"
                  checked={openIds.length > 0 && openIds.every((id) => selected.has(id))}
                  onChange={(e) => setSelected(e.target.checked ? new Set(openIds) : new Set())}
                />
              </th>
              <th>Severity</th>
              <th>Entity</th>
              <th>Match</th>
              <th>Camera</th>
              <th>Triggered</th>
              <th>Hits</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data?.items.map((a) => (
              <tr
                key={a.id}
                className={clsx("cursor-pointer", recentAlertIds.has(a.id) && a.status === "NEW" && "alert-in")}
                style={{ boxShadow: `inset 3px 0 0 ${SEVERITY_COLOR[a.severity]}` }}
                onClick={() => setParams({ focus: String(a.id) })}
              >
                <td onClick={(e) => e.stopPropagation()}>
                  {(a.status === "NEW" || a.status === "ACKNOWLEDGED") && (
                    <input type="checkbox" checked={selected.has(a.id)} onChange={() => toggle(a.id)} aria-label={`Select alert ${a.id}`} />
                  )}
                </td>
                <td>
                  <SeverityBadge severity={a.severity} />
                </td>
                <td>
                  <Plate value={a.identifier} />
                  <div className="text-[10px] text-ink-400">{titleCase(a.category)}</div>
                </td>
                <td className="text-xs">
                  {a.match_type}
                  <div>
                    <Confidence value={a.confidence} />
                  </div>
                </td>
                <td className="text-xs">
                  <span className="font-mono">{a.camera_id}</span> {a.camera_name}
                  <div className="text-[10px] text-ink-400">{a.camera_zone}</div>
                </td>
                <td className="font-mono text-xs whitespace-nowrap">
                  {fmtDateTime(a.triggered_at)}
                  <div className="font-sans text-[10px] text-ink-400">{ago(a.triggered_at)}</div>
                </td>
                <td className="font-mono text-xs">{a.hit_count}</td>
                <td>
                  <AlertStatusBadge status={a.status} />
                </td>
                <td>
                  <Eye size={14} className="text-ink-400" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && !data.items.length && <Empty>No alerts in this view.</Empty>}
        {data && <Pager total={data.total} limit={limit} offset={offset} onChange={setOffset} />}
      </Panel>
      {focus && <AlertDetail id={Number(focus)} onClose={() => setParams({})} />}
    </div>
  );
}
