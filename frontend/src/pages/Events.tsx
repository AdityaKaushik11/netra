import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Download } from "lucide-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, getToken, qs } from "../api/client";
import type { Camera, DetectionEvent, Page } from "../api/types";
import { Confidence, Plate } from "../components/Badges";
import { Empty, PageHeader, Pager, Panel } from "../components/ui";
import { useAuth } from "../hooks/auth";
import { EVENT_LABEL, fmtDateTime, titleCase } from "../lib/format";

export function EventsPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { can } = useAuth();
  const [f, setF] = useState({
    camera_id: params.get("camera_id") ?? "",
    event_type: "",
    identifier: "",
    since: "",
    until: "",
    watchlist_hit: "",
  });
  const [offset, setOffset] = useState(0);
  const limit = 50;
  const query = {
    ...f,
    since: f.since ? new Date(f.since).toISOString() : "",
    until: f.until ? new Date(f.until).toISOString() : "",
  };
  const { data } = useQuery({
    queryKey: ["events", query, offset],
    queryFn: () => api<Page<DetectionEvent>>(`/events${qs({ ...query, limit, offset })}`),
  });
  const { data: cams } = useQuery({ queryKey: ["cameras", "all"], queryFn: () => api<Page<Camera>>("/cameras?limit=1000") });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => {
    setOffset(0);
    setF({ ...f, [k]: e.target.value });
  };

  const exportCsv = async () => {
    const res = await fetch(`/api/v1/events/export.csv${qs(query)}`, { headers: { Authorization: `Bearer ${getToken()}` } });
    if (!res.ok) return toast.error("Export failed");
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: "netra-events.csv" });
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <PageHeader
        title="Detection history"
        subtitle="Every validated analytics event, persisted and searchable · repeat reads folded by the dedup window"
        actions={
          can("ADMIN", "OPERATOR") && (
            <button className="btn" onClick={exportCsv}>
              <Download size={14} /> Export CSV
            </button>
          )
        }
      />
      <Panel
        title={`${data?.total ?? 0} events`}
        actions={
          <div className="flex flex-wrap gap-2">
            <input className="input w-36 py-1 font-mono uppercase" placeholder="Plate / ref" value={f.identifier} onChange={set("identifier")} />
            <select className="input w-auto py-1" value={f.camera_id} onChange={set("camera_id")}>
              <option value="">All cameras</option>
              {cams?.items.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.id} · {c.name}
                </option>
              ))}
            </select>
            <select className="input w-auto py-1" value={f.event_type} onChange={set("event_type")}>
              <option value="">All types</option>
              {[
                "ANPR",
                "VEHICLE_DETECTION",
                "PERSON_DETECTION",
                "FACE_RECOGNITION",
                "OBJECT_DETECTION",
                "OVERSPEED",
                "HARSH_BRAKING",
                "COLLISION_WARNING",
                "DRIVER_DROWSINESS",
              ].map((t) => (
                <option key={t} value={t}>
                  {titleCase(t)}
                </option>
              ))}
            </select>
            <select className="input w-auto py-1" value={f.watchlist_hit} onChange={set("watchlist_hit")}>
              <option value="">Any</option>
              <option value="true">Watchlist hits</option>
            </select>
            <input className="input w-auto py-1" type="datetime-local" value={f.since} onChange={set("since")} title="From" />
            <input className="input w-auto py-1" type="datetime-local" value={f.until} onChange={set("until")} title="To" />
          </div>
        }
        bodyClass="overflow-x-auto"
      >
        <table className="data">
          <thead>
            <tr>
              <th>Detected at</th>
              <th>Type</th>
              <th>Entity</th>
              <th>Vehicle</th>
              <th>Camera</th>
              <th>Confidence</th>
              <th>Reads</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((e) => (
              <tr key={e.id} className="cursor-pointer" onClick={() => e.identifier && navigate(`/trace/${e.identifier_normalized}`)}>
                <td className="font-mono text-xs whitespace-nowrap">{fmtDateTime(e.detected_at)}</td>
                <td className="text-xs">{EVENT_LABEL[e.event_type] ?? titleCase(e.event_type)}</td>
                <td>
                  <span className="flex items-center gap-1.5">
                    {e.identifier ? <Plate value={e.identifier} /> : <span className="text-xs">{e.object_label}</span>}
                    {e.watchlist_hit && <AlertTriangle size={13} className="text-offline" />}
                  </span>
                </td>
                <td className="text-xs text-ink-300">{[e.vehicle_color, e.vehicle_type].filter(Boolean).join(" ") || "—"}</td>
                <td className="text-xs">
                  <span className="font-mono">{e.camera_id}</span> <span className="text-ink-400">{e.camera_name}</span>
                </td>
                <td>
                  <Confidence value={e.confidence} />
                </td>
                <td className="font-mono text-xs">{e.repeat_count + 1}</td>
                <td className="max-w-40 truncate text-[11px] text-ink-400" title={e.model_name ?? ""}>
                  {e.source_client}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && !data.items.length && <Empty>No events match.</Empty>}
        {data && <Pager total={data.total} limit={limit} offset={offset} onChange={setOffset} />}
      </Panel>
    </div>
  );
}
