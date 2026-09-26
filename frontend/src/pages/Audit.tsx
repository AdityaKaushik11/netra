import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, qs } from "../api/client";
import type { AuditEntry } from "../api/types";
import { DetailsView } from "../components/DetailsView";
import { PageHeader, Pager, Panel } from "../components/ui";
import { fmtDateTime } from "../lib/format";

export function AuditPage() {
  const [f, setF] = useState({ entity_type: "", action: "" });
  const [offset, setOffset] = useState(0);
  const limit = 100;
  const { data } = useQuery({
    queryKey: ["audit", f, offset],
    queryFn: () => api<{ total: number; items: AuditEntry[] }>(`/audit${qs({ ...f, limit, offset })}`),
    refetchInterval: 15_000,
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => {
    setOffset(0);
    setF({ ...f, [k]: e.target.value });
  };
  return (
    <div>
      <PageHeader title="Audit log" subtitle="Immutable record of logins, onboarding, configuration changes, stream access and alert handling" />
      <Panel
        title={`${data?.total ?? 0} entries`}
        actions={
          <div className="flex gap-2">
            <select className="input w-auto py-1" value={f.entity_type} onChange={set("entity_type")}>
              <option value="">All entities</option>
              {["camera", "alert", "watchlist", "user", "api_client"].map((e) => (
                <option key={e}>{e}</option>
              ))}
            </select>
            <select className="input w-auto py-1" value={f.action} onChange={set("action")}>
              <option value="">All actions</option>
              {[
                "LOGIN_SUCCESS",
                "LOGIN_FAILED",
                "CAMERA_ONBOARDED",
                "CAMERA_UPDATED",
                "CAMERA_DISABLED",
                "CAMERA_STATUS_CHANGED",
                "STREAM_ACCESSED",
                "ALERT_RAISED",
                "ALERT_ACKNOWLEDGED",
                "ALERT_RESOLVED",
                "WATCHLIST_ADDED",
                "WATCHLIST_DEACTIVATED",
                "API_CLIENT_CREATED",
              ].map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
          </div>
        }
        bodyClass="overflow-x-auto"
      >
        <table className="data">
          <thead>
            <tr>
              <th>Time</th>
              <th>Actor</th>
              <th>Action</th>
              <th>Entity</th>
              <th>Details</th>
              <th>IP</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((a) => (
              <tr key={a.id}>
                <td className="font-mono text-[11px] whitespace-nowrap">{fmtDateTime(a.created_at)}</td>
                <td className="text-xs">
                  {a.actor_name}
                  <div className="text-[10px] text-ink-400">{a.actor_type}</div>
                </td>
                <td className="text-xs font-semibold">{a.action}</td>
                <td className="font-mono text-xs">
                  {a.entity_type}:{a.entity_id ?? "—"}
                </td>
                <td className="max-w-md">
                  <DetailsView details={a.details} />
                </td>
                <td className="font-mono text-[11px] text-ink-400">{a.ip_address}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && <Pager total={data.total} limit={limit} offset={offset} onChange={setOffset} />}
      </Panel>
    </div>
  );
}
