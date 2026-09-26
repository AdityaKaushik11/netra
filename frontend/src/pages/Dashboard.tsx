import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, Camera as CameraIcon, CopyMinus, Gauge, ListChecks, Radar } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { api } from "../api/client";
import { ADAS_EVENTS, type Alert, type Camera, type DetectionEvent, type Overview, type Page, type TimePoint, type TrackPoint } from "../api/types";
import { AlertStatusBadge, Confidence, Plate, SEVERITY_COLOR, SeverityBadge, StatusBadge, StatusDot } from "../components/Badges";
import { CameraMap } from "../components/CameraMap";
import { Empty, Panel } from "../components/ui";
import { VideoPlayer } from "../components/VideoPlayer";
import { useAuth } from "../hooks/auth";
import { useRealtime } from "../hooks/realtime";
import { ago, fmtTime, titleCase } from "../lib/format";

function Kpi({ icon, label, value, sub, tone }: { icon: ReactNode; label: string; value: ReactNode; sub?: ReactNode; tone?: string }) {
  return (
    <div className="panel flex items-start gap-3 p-3">
      <div className="rounded-md bg-ink-800 p-2 text-ink-300" style={tone ? { color: tone } : undefined}>
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-[11px] font-medium tracking-wide text-ink-400 uppercase">{label}</div>
        <div className="text-2xl leading-tight font-semibold tabular-nums">{value}</div>
        {sub && <div className="text-[11px] text-ink-400">{sub}</div>}
      </div>
    </div>
  );
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { detections: live } = useRealtime();
  const { can } = useAuth();
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [camQuery, setCamQuery] = useState("");

  const { data: ov } = useQuery({ queryKey: ["overview"], queryFn: () => api<Overview>("/stats/overview"), refetchInterval: 30_000 });
  const { data: cams } = useQuery({ queryKey: ["cameras", "all"], queryFn: () => api<Page<Camera>>("/cameras?limit=1000") });
  const { data: alerts } = useQuery({
    queryKey: ["alerts", "open"],
    queryFn: () => api<Page<Alert>>("/alerts?status=NEW&status=ACKNOWLEDGED&limit=30"),
  });
  const { data: recent } = useQuery({ queryKey: ["events", "recent"], queryFn: () => api<Page<DetectionEvent>>("/events?limit=40") });
  const { data: series } = useQuery({
    queryKey: ["timeseries", 24],
    queryFn: () => api<TimePoint[]>("/stats/timeseries?hours=24"),
    refetchInterval: 60_000,
  });

  const ack = useMutation({
    mutationFn: (id: number) => api<Alert>(`/alerts/${id}/acknowledge`, { method: "POST", json: {} }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      toast.success("Alert acknowledged");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const allCameras = useMemo(() => cams?.items ?? [], [cams]);
  // Camera search/filter applies to the map, the live grid and the health table
  const cameras = useMemo(() => {
    const q = camQuery.trim().toLowerCase();
    if (!q) return allCameras;
    return allCameras.filter((c) =>
      [c.id, c.name, c.zone, c.status, c.source_protocol, c.camera_type].some((v) => v?.toLowerCase().includes(q)),
    );
  }, [allCameras, camQuery]);
  const selected = useMemo(() => allCameras.find((c) => c.id === selectedId) ?? null, [allCameras, selectedId]);
  const setSelected = (c: Camera | null) => setSelectedId(c?.id ?? null);
  const gridCams = useMemo(() => {
    const enabled = cameras.filter((c) => c.is_enabled);
    // Always show a mix: fixed cameras first, then the dashcam, when not filtering
    const dash = enabled.filter((c) => c.camera_type === "DASHCAM");
    const fixed = enabled.filter((c) => c.camera_type !== "DASHCAM");
    return camQuery ? enabled.slice(0, 4) : [...fixed.slice(0, 4 - Math.min(1, dash.length)), ...dash.slice(0, 1)];
  }, [cameras, camQuery]);
  const dashcams = useMemo(() => allCameras.filter((c) => c.camera_type === "DASHCAM" && c.is_enabled), [allCameras]);
  const trackQueries = useQueries({
    queries: dashcams.map((c) => ({
      queryKey: ["track", c.id],
      queryFn: () => api<TrackPoint[]>(`/cameras/${c.id}/track?minutes=20`),
      refetchInterval: 120_000,
    })),
  });
  const tracks = Object.fromEntries(dashcams.map((c, i) => [c.id, trackQueries[i]?.data ?? []]));
  const detections = useMemo(() => {
    const seen = new Set<number>();
    return [...live, ...(recent?.items ?? [])].filter((d) => !seen.has(d.id) && seen.add(d.id)).slice(0, 40);
  }, [live, recent]);
  const liveIds = useMemo(() => new Set(live.map((d) => d.id)), [live]);
  const chartData = (series ?? []).map((p) => ({ ...p, label: fmtTime(p.hour).slice(0, 5) }));

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi
          icon={<CameraIcon size={18} />}
          label="Cameras online"
          value={
            <>
              {ov?.cameras.online ?? "–"}
              <span className="text-sm text-ink-400"> / {ov ? ov.cameras.total - ov.cameras.disabled : "–"}</span>
            </>
          }
          sub={
            <span className="flex gap-2">
              <span className="text-degraded">{ov?.cameras.degraded ?? 0} degraded</span>
              <span className="text-offline">{ov?.cameras.offline ?? 0} offline</span>
            </span>
          }
          tone="var(--color-online)"
        />
        <Kpi
          icon={<AlertTriangle size={18} />}
          label="Open alerts"
          value={ov?.alerts.open ?? "–"}
          sub={
            <span className="flex gap-2">
              {([["CRITICAL", "crit"], ["HIGH", "high"], ["MEDIUM", "med"]] as const).map(([s, label]) => (
                <span key={s} style={{ color: SEVERITY_COLOR[s] }}>
                  {ov?.alerts.by_severity[s] ?? 0} {label}
                </span>
              ))}
            </span>
          }
          tone={ov?.alerts.new ? "var(--color-offline)" : undefined}
        />
        <Kpi
          icon={<Radar size={18} />}
          label="Detections (1h)"
          value={ov?.events.last_hour ?? "–"}
          sub={`${ov?.events.last_24h ?? 0} in 24h`}
        />
        <Kpi icon={<Gauge size={18} />} label="Ingest rate" value={ov?.events.per_minute ?? "–"} sub="events / min (5-min avg)" />
        <Kpi
          icon={<ListChecks size={18} />}
          label="Watchlist"
          value={ov?.watchlist.active ?? "–"}
          sub={`${ov?.alerts.last_24h ?? 0} alerts in 24h`}
        />
        <Kpi
          icon={<CopyMinus size={18} />}
          label="Duplicates suppressed"
          value={ov?.events.duplicates_suppressed_24h ?? "–"}
          sub="repeat ANPR reads folded (24h)"
        />
      </div>

      <div className="grid gap-3 xl:grid-cols-12">
        <Panel
          title="Camera map"
          className="h-[460px] xl:col-span-7"
          actions={
            <span className="flex items-center gap-3 text-[11px] text-ink-400">
              {(["ONLINE", "DEGRADED", "OFFLINE"] as const).map((s) => (
                <span key={s} className="flex items-center gap-1">
                  <StatusDot status={s} /> {titleCase(s)}
                </span>
              ))}
              <span className="flex items-center gap-1">
                <span className="size-2.5 rounded-full border-2 border-offline" /> Open alert
              </span>
              <span className="flex items-center gap-1">
                <span className="h-0.5 w-3 bg-violet-400" /> Dashcam track
              </span>
            </span>
          }
        >
          <div className="relative h-full">
            <CameraMap cameras={cameras} tracks={tracks} onSelect={setSelected} />
            <input
              className="input absolute top-3 right-3 z-[500] w-56 py-1 text-xs shadow-lg"
              placeholder="Filter cameras (id, name, zone, status)…"
              value={camQuery}
              onChange={(e) => setCamQuery(e.target.value)}
            />
            {selected && (
              <div className="absolute right-3 bottom-3 z-[500] w-80 rounded-lg border border-ink-600 bg-ink-900/95 p-2 shadow-2xl">
                <div className="mb-2 flex items-center gap-2 text-xs">
                  <StatusBadge status={selected.status} enabled={selected.is_enabled} />
                  <span className="truncate text-ink-300">{selected.status_reason}</span>
                  <button className="ml-auto text-ink-400 hover:text-ink-100" onClick={() => setSelected(null)}>
                    ✕
                  </button>
                </div>
                <VideoPlayer camera={selected} />
                {selected.camera_type === "DASHCAM" && (
                  <div className="mt-1 font-mono text-[11px] text-violet-200">
                    GPS {selected.latitude.toFixed(5)}, {selected.longitude.toFixed(5)} · {Math.round(selected.speed_kmh ?? 0)} km/h ·{" "}
                    {Math.round(selected.heading_deg ?? 0)}° · fix {ago(selected.location_updated_at)}
                  </div>
                )}
                <div className="mt-2 flex gap-2">
                  <Link to={`/cameras?focus=${selected.id}`} className="btn py-1 text-xs">
                    Details
                  </Link>
                  <Link to={`/events?camera_id=${selected.id}`} className="btn py-1 text-xs">
                    Detections
                  </Link>
                </div>
              </div>
            )}
          </div>
        </Panel>

        <Panel
          title={`Active alerts (${alerts?.total ?? 0})`}
          className="h-[460px] xl:col-span-5"
          bodyClass="overflow-y-auto"
          actions={
            <Link to="/alerts" className="text-xs text-accent hover:underline">
              All alerts →
            </Link>
          }
        >
          {!alerts?.items.length ? (
            <Empty>No open alerts. Watchlist matches appear here instantly.</Empty>
          ) : (
            <ul className="divide-y divide-ink-800">
              {alerts.items.map((a) => (
                <li
                  key={a.id}
                  className={clsx("flex gap-3 px-3 py-2.5", a.status === "NEW" && "alert-in")}
                  style={{ boxShadow: `inset 3px 0 0 ${SEVERITY_COLOR[a.severity]}` }}
                >
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <SeverityBadge severity={a.severity} />
                      <Plate value={a.identifier} />
                      <span className="text-xs text-ink-300">{titleCase(a.category)}</span>
                      {a.match_type === "FUZZY" && <span className="text-[10px] text-amber-300">FUZZY</span>}
                    </div>
                    <div className="truncate text-xs text-ink-300">
                      {a.camera_id} · {a.camera_name} · <span className="font-mono">{fmtTime(a.last_hit_at)}</span>
                      {a.hit_count > 1 && <span className="text-ink-400"> · {a.hit_count} hits</span>}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <AlertStatusBadge status={a.status} />
                    <div className="flex gap-1">
                      {a.status === "NEW" && can("ADMIN", "OPERATOR") && (
                        <button className="btn px-2 py-0.5 text-[11px]" onClick={() => ack.mutate(a.id)}>
                          Ack
                        </button>
                      )}
                      <button className="btn px-2 py-0.5 text-[11px]" onClick={() => navigate(`/trace/${a.identifier}`)}>
                        Trace
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="grid gap-3 xl:grid-cols-12">
        <Panel
          title="Live camera grid"
          className="xl:col-span-7"
          bodyClass="p-2"
          actions={
            <Link to="/wall" className="text-xs text-accent hover:underline">
              Open live wall →
            </Link>
          }
        >
          <div className="grid grid-cols-2 gap-2">
            {gridCams.map((c) => (
              <VideoPlayer key={c.id} camera={c} />
            ))}
          </div>
        </Panel>

        <Panel
          title="Recent detections"
          className="h-[520px] xl:col-span-5"
          bodyClass="overflow-y-auto"
          actions={<span className="text-[11px] text-ink-400">streaming</span>}
        >
          <table className="data">
            <thead>
              <tr>
                <th>Time</th>
                <th>Entity</th>
                <th>Camera</th>
                <th>Conf.</th>
              </tr>
            </thead>
            <tbody>
              {detections.map((d) => (
                <tr
                  key={d.id}
                  className={clsx(liveIds.has(d.id) && "flash-in", "cursor-pointer")}
                  onClick={() => d.identifier && navigate(`/trace/${d.identifier_normalized}`)}
                >
                  <td className="font-mono text-xs text-ink-300">{fmtTime(d.detected_at)}</td>
                  <td>
                    <div className="flex items-center gap-1.5">
                      {d.identifier ? (
                        <Plate value={d.identifier} />
                      ) : ADAS_EVENTS.includes(d.event_type) ? (
                        <span className="rounded bg-violet-500/15 px-1.5 text-xs text-violet-200">{d.object_label}</span>
                      ) : (
                        <span className="text-xs text-ink-300">{d.object_label}</span>
                      )}
                      {d.watchlist_hit && <AlertTriangle size={13} className="text-offline" />}
                      {d.repeat_count > 0 && <span className="text-[10px] text-ink-400">×{d.repeat_count + 1}</span>}
                    </div>
                    <div className="text-[10px] text-ink-400">
                      {titleCase(d.event_type)}
                      {d.vehicle_type && ` · ${d.vehicle_type}`}
                    </div>
                  </td>
                  <td className="text-xs">
                    <span className="font-mono">{d.camera_id}</span>
                    <div className="max-w-32 truncate text-[10px] text-ink-400">{d.camera_name}</div>
                  </td>
                  <td>
                    <Confidence value={d.confidence} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>

      <div className="grid gap-3 xl:grid-cols-12">
        <Panel title="Detections per hour · last 24h" className="h-64 xl:col-span-7" bodyClass="p-2">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
              <CartesianGrid vertical={false} stroke="#1a2531" />
              <XAxis dataKey="label" tick={{ fill: "#6b7f95", fontSize: 10 }} axisLine={false} tickLine={false} interval={2} />
              <YAxis tick={{ fill: "#6b7f95", fontSize: 10 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                cursor={{ fill: "rgba(34,211,238,0.08)" }}
                contentStyle={{ background: "#121a23", border: "1px solid #243242", borderRadius: 6, fontSize: 12 }}
                labelStyle={{ color: "#c3cfdc" }}
                formatter={(v: number, _n, p) => [`${v} detections · ${p.payload.watchlist_hits} watchlist hits`, ""]}
              />
              <Bar dataKey="detections" fill="#22d3ee" radius={[3, 3, 0, 0]} maxBarSize={22} />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Camera & system health" className="h-64 xl:col-span-5" bodyClass="overflow-y-auto">
          <div className="flex flex-wrap gap-1.5 border-b border-ink-800 px-3 py-2">
            {Object.entries(ov?.system ?? {}).map(([k, v]) => {
              const bad = typeof v === "string" && v !== "ok";
              return (
                <span
                  key={k}
                  className={clsx(
                    "rounded border px-1.5 py-0.5 font-mono text-[10px]",
                    bad ? "border-red-500/40 text-red-300" : "border-ink-600 text-ink-300",
                  )}
                >
                  {k.replace(/_/g, " ")}: <span className={bad ? "" : "text-emerald-400"}>{String(v)}</span>
                </span>
              );
            })}
          </div>
          <table className="data">
            <tbody>
              {cameras.map((c) => (
                <tr key={c.id}>
                  <td className="font-mono text-xs">{c.id}</td>
                  <td className="max-w-40 truncate text-xs">{c.name}</td>
                  <td>
                    <StatusBadge status={c.status} enabled={c.is_enabled} />
                  </td>
                  <td className="max-w-44 truncate text-[11px] text-ink-400" title={c.status_reason ?? ""}>
                    {c.status_reason}
                  </td>
                  <td className="text-[11px] whitespace-nowrap text-ink-400">{ago(c.last_heartbeat_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
}
