import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Pencil, Plus, Power, Radar, RefreshCw, Wifi } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, qs } from "../api/client";
import type { AuditEntry, Camera, Department, Page, TrackPoint } from "../api/types";
import { DetailsView } from "../components/DetailsView";
import { ProtocolBadge, StatusBadge } from "../components/Badges";
import { CameraForm, type CameraDraft } from "../components/CameraForm";
import { CameraMap } from "../components/CameraMap";
import { Empty, Modal, PageHeader, Pager, Panel } from "../components/ui";
import { ClipPlayer, VideoPlayer } from "../components/VideoPlayer";
import { useAuth } from "../hooks/auth";
import { ago, fmtDateTime, titleCase } from "../lib/format";

interface OnvifDevice {
  device_service_url: string;
  manufacturer: string | null;
  model: string | null;
  firmware: string | null;
  serial: string | null;
  stream_uri: string | null;
  already_registered: boolean;
}

export function CamerasPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [filters, setFilters] = useState({ q: "", status: "", protocol: "", department_id: "", zone: "" });
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState<CameraDraft | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const focus = params.get("focus");
  const limit = 50;

  const { data } = useQuery({
    queryKey: ["cameras", filters, offset],
    queryFn: () => api<Page<Camera>>(`/cameras${qs({ ...filters, limit, offset })}`),
  });
  const { data: departments } = useQuery({ queryKey: ["departments"], queryFn: () => api<Department[]>("/departments") });
  const { data: zones } = useQuery({ queryKey: ["cameras", "zones"], queryFn: () => api<string[]>("/cameras/zones") });
  const set = (k: keyof typeof filters) => (e: { target: { value: string } }) => {
    setOffset(0);
    setFilters({ ...filters, [k]: e.target.value });
  };

  return (
    <div>
      <PageHeader
        title="Camera registry"
        subtitle="Heterogeneous sources (RTSP, ONVIF, HLS, vendor API) onboarded into one registry"
        actions={
          can("ADMIN") && (
            <>
              <button className="btn" onClick={() => setDiscovering(true)}>
                <Wifi size={14} /> ONVIF discovery
              </button>
              <button className="btn btn-primary" onClick={() => setCreating({})}>
                <Plus size={14} /> Add camera
              </button>
            </>
          )
        }
      />
      <div className="grid gap-3 xl:grid-cols-[1fr_380px]">
        <Panel
          title={`${data?.total ?? 0} cameras`}
          actions={
            <div className="flex flex-wrap gap-2">
              <input className="input w-48 py-1" placeholder="Search id, name, zone…" value={filters.q} onChange={set("q")} />
              <select className="input w-auto py-1" value={filters.status} onChange={set("status")}>
                <option value="">All status</option>
                {["ONLINE", "DEGRADED", "OFFLINE", "UNKNOWN"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
              <select className="input w-auto py-1" value={filters.protocol} onChange={set("protocol")}>
                <option value="">All protocols</option>
                {["RTSP", "ONVIF", "HLS", "VENDOR_API"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
              <select className="input w-auto py-1" value={filters.department_id} onChange={set("department_id")}>
                <option value="">All departments</option>
                {departments?.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.code}
                  </option>
                ))}
              </select>
              <select className="input w-auto py-1" value={filters.zone} onChange={set("zone")}>
                <option value="">All zones</option>
                {zones?.map((z) => (
                  <option key={z}>{z}</option>
                ))}
              </select>
            </div>
          }
          bodyClass="overflow-x-auto"
        >
          <table className="data">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name / location</th>
                <th>Dept · zone</th>
                <th>Source</th>
                <th>Status</th>
                <th>Last seen</th>
                <th>Storage</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((c) => (
                <tr key={c.id} className="cursor-pointer" onClick={() => setParams({ focus: c.id })}>
                  <td className="font-mono font-semibold">{c.id}</td>
                  <td>
                    <div className="font-medium">{c.name}</div>
                    <div className="font-mono text-[10px] text-ink-400">
                      {c.latitude.toFixed(4)}, {c.longitude.toFixed(4)} · {titleCase(c.camera_type)}
                    </div>
                  </td>
                  <td className="text-xs">
                    <div>{c.department?.code ?? "—"}</div>
                    <div className="text-ink-400">{c.zone}</div>
                  </td>
                  <td>
                    <ProtocolBadge protocol={c.source_protocol} />
                    <div className="mt-0.5 text-[10px] text-ink-400">
                      {c.health_mode === "HEARTBEAT" ? "edge heartbeat" : "active probe"} · {c.onboarding_source.toLowerCase()}
                    </div>
                  </td>
                  <td>
                    <StatusBadge status={c.status} enabled={c.is_enabled} />
                    {c.open_alerts > 0 && <span className="ml-1 rounded bg-red-600 px-1 text-[10px] font-bold">{c.open_alerts}</span>}
                    <div className="max-w-48 truncate text-[10px] text-ink-400" title={c.status_reason ?? ""}>
                      {c.status_reason}
                    </div>
                  </td>
                  <td className="text-xs whitespace-nowrap text-ink-300">{ago(c.last_heartbeat_at)}</td>
                  <td className="text-xs">
                    {c.storage_tier} · {c.retention_days}d
                    <div className="text-[10px] text-ink-400">{c.recording_enabled ? "recording" : "live only"}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data && !data.items.length && <Empty>No cameras match these filters.</Empty>}
          {data && <Pager total={data.total} limit={limit} offset={offset} onChange={setOffset} />}
        </Panel>
        <Panel title="Locations" className="h-[520px]">
          <CameraMap cameras={data?.items ?? []} onSelect={(c) => setParams({ focus: c.id })} />
        </Panel>
      </div>

      {focus && <CameraDetail id={focus} onClose={() => setParams({})} />}
      {creating && (
        <Modal title="Onboard camera" onClose={() => setCreating(null)} wide>
          <CameraForm draft={creating} onDone={() => setCreating(null)} />
        </Modal>
      )}
      {discovering && (
        <OnvifDiscovery
          onClose={() => setDiscovering(false)}
          onPick={(d) => {
            setDiscovering(false);
            setCreating(d);
          }}
        />
      )}
    </div>
  );
}

function CameraDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [lowLatency, setLowLatency] = useState(false);
  const [replay, setReplay] = useState<{ start: string; duration: number } | null>(null);
  const { data: camera } = useQuery({ queryKey: ["camera", id], queryFn: () => api<Camera>(`/cameras/${id}`) });
  const { data: track } = useQuery({
    queryKey: ["track", id],
    queryFn: () => api<TrackPoint[]>(`/cameras/${id}/track?minutes=30`),
    enabled: camera?.camera_type === "DASHCAM",
  });
  const recordable = !!camera && camera.recording_enabled && (camera.source_protocol === "RTSP" || camera.source_protocol === "ONVIF");
  const startReplay = (minutesAgo: number, duration: number) =>
    setReplay({ start: new Date(Date.now() - minutesAgo * 60_000).toISOString(), duration });
  const { data: audit } = useQuery({
    queryKey: ["camera", id, "audit"],
    queryFn: () => api<AuditEntry[]>(`/cameras/${id}/audit?limit=50`),
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["camera"] });
    qc.invalidateQueries({ queryKey: ["cameras"] });
  };
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => api<Camera>(`/cameras/${id}`, { method: "PATCH", json: { is_enabled: enabled } }),
    onSuccess: (c) => {
      toast.success(`${c.id} ${c.is_enabled ? "enabled" : "disabled"}`);
      refresh();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const probe = useMutation({
    mutationFn: () => api<Camera>(`/cameras/${id}/probe`, { method: "POST" }),
    onSuccess: (c) => {
      toast.info(`${c.id}: ${c.status}`, { description: c.status_reason ?? "" });
      refresh();
    },
  });

  if (!camera) return null;
  if (editing)
    return (
      <Modal title={`Edit ${camera.id}`} onClose={() => setEditing(false)} wide>
        <CameraForm camera={camera} onDone={() => setEditing(false)} />
      </Modal>
    );
  const rows: [string, React.ReactNode][] = [
    ["Department", camera.department?.name ?? "—"],
    ["Zone / address", `${camera.zone ?? "—"} · ${camera.address ?? ""}`],
    ["Coordinates", `${camera.latitude}, ${camera.longitude}`],
    ["Type / protocol", `${camera.camera_type} · ${camera.source_protocol}`],
    ["Stream endpoint", <span className="font-mono text-[11px] break-all">{camera.stream_endpoint}</span>],
    ["Credentials", camera.has_credentials ? `${camera.stream_username ?? "api-key"} · ●●●●● (encrypted)` : "none"],
    ["Gateway path", camera.gateway_path ?? "—"],
    ["Vendor / model", `${camera.vendor ?? "—"} ${camera.model ?? ""}`],
    ["Resolution / FPS", `${camera.resolution ?? "—"} @ ${camera.fps ?? "—"}`],
    ["Storage", `${camera.storage_tier} · ${camera.retention_days} days · ${camera.storage_location ?? "—"}`],
    ["Health mode", camera.health_mode],
    ["Last heartbeat", fmtDateTime(camera.last_heartbeat_at)],
    ["Onboarded", `${fmtDateTime(camera.created_at)} (${camera.onboarding_source})`],
  ];
  return (
    <Modal
      wide
      onClose={onClose}
      title={
        <span className="flex items-center gap-2">
          <span className="font-mono">{camera.id}</span> {camera.name} <StatusBadge status={camera.status} enabled={camera.is_enabled} />
        </span>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-3">
          <VideoPlayer key={`${camera.id}-${lowLatency}`} camera={camera} lowLatency={lowLatency} />
          {camera.gateway_path && (
            <label className="flex items-center gap-2 text-xs text-ink-300">
              <input type="checkbox" checked={lowLatency} onChange={(e) => setLowLatency(e.target.checked)} />
              Low-latency live view (WebRTC, falls back to LL-HLS)
            </label>
          )}
          {recordable && (
            <div className="space-y-2 rounded-md border border-ink-700 bg-ink-900 p-2 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-ink-300">Recorded footage</span>
                <button className="btn px-2 py-0.5 text-[11px]" onClick={() => startReplay(1, 45)}>
                  Last 1 min
                </button>
                <button className="btn px-2 py-0.5 text-[11px]" onClick={() => startReplay(5, 120)}>
                  5 min ago
                </button>
                <button className="btn px-2 py-0.5 text-[11px]" onClick={() => startReplay(15, 180)}>
                  15 min ago
                </button>
                {replay && (
                  <button className="ml-auto text-ink-400 hover:text-ink-100" onClick={() => setReplay(null)}>
                    close
                  </button>
                )}
              </div>
              {replay && <ClipPlayer cameraId={camera.id} start={replay.start} duration={replay.duration} />}
            </div>
          )}
          {camera.camera_type === "DASHCAM" && (
            <div className="space-y-2 rounded-md border border-violet-500/30 bg-violet-500/5 p-2 text-xs">
              <div className="font-semibold text-violet-200">Dashcam telemetry</div>
              <div className="grid grid-cols-3 gap-2 font-mono">
                <span>{Math.round(camera.speed_kmh ?? 0)} km/h</span>
                <span>heading {Math.round(camera.heading_deg ?? 0)}°</span>
                <span>fix {ago(camera.location_updated_at)}</span>
              </div>
              <div className="h-44 overflow-hidden rounded border border-ink-700">
                <CameraMap cameras={[camera]} tracks={{ [camera.id]: track ?? [] }} />
              </div>
              <div className="text-[11px] text-ink-400">GPS track, last 30 min ({track?.length ?? 0} fixes)</div>
            </div>
          )}
          <div className="rounded-md border border-ink-700 bg-ink-900 p-2 text-xs">
            <div className="mb-1 flex items-center gap-1.5 font-semibold text-ink-300">
              <Activity size={13} /> Health
            </div>
            <div className="text-ink-200">{camera.status_reason ?? "—"}</div>
            {camera.health_metrics && (
              <div className="mt-1">
                <DetailsView details={camera.health_metrics} />
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Link className="btn" to={`/events?camera_id=${camera.id}`}>
              <Radar size={14} /> Detections
            </Link>
            {can("ADMIN", "OPERATOR") && (
              <button className="btn" onClick={() => probe.mutate()} disabled={probe.isPending}>
                <RefreshCw size={14} /> Probe now
              </button>
            )}
            {can("ADMIN") && (
              <>
                <button className="btn" onClick={() => setEditing(true)}>
                  <Pencil size={14} /> Edit
                </button>
                <button className={camera.is_enabled ? "btn btn-danger" : "btn"} onClick={() => toggle.mutate(!camera.is_enabled)}>
                  <Power size={14} /> {camera.is_enabled ? "Disable" : "Enable"}
                </button>
              </>
            )}
          </div>
        </div>
        <dl className="grid grid-cols-[120px_1fr] gap-x-3 gap-y-1.5 self-start text-xs">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-ink-400">{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </div>
      <h4 className="panel-title mt-5 mb-2">Audit history</h4>
      <div className="max-h-60 overflow-y-auto rounded-md border border-ink-700">
        <table className="data">
          <tbody>
            {audit?.map((a) => (
              <tr key={a.id}>
                <td className="font-mono text-[11px] whitespace-nowrap text-ink-400">{fmtDateTime(a.created_at)}</td>
                <td className="text-xs font-semibold">{a.action}</td>
                <td className="text-xs">{a.actor_name}</td>
                <td>
                  <DetailsView details={a.details} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}

function OnvifDiscovery({ onClose, onPick }: { onClose: () => void; onPick: (d: CameraDraft) => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const scan = useMutation({
    mutationFn: () => api<OnvifDevice[]>("/onvif/discover", { method: "POST", json: { username, password } }),
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Modal title="ONVIF discovery" onClose={onClose}>
      <p className="mb-3 text-xs text-ink-400">
        Probes the configured discovery targets with WS-Security digest auth, reads device information and resolves the RTSP
        stream URI (GetProfiles → GetStreamUri).
      </p>
      <div className="mb-3 grid grid-cols-[1fr_1fr_auto] items-end gap-2">
        <input className="input" placeholder="ONVIF username" value={username} onChange={(e) => setUsername(e.target.value)} />
        <input className="input" type="password" placeholder="ONVIF password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <button className="btn btn-primary" onClick={() => scan.mutate()} disabled={scan.isPending}>
          {scan.isPending ? "Scanning…" : "Scan"}
        </button>
      </div>
      {scan.data && !scan.data.length && <Empty>No devices responded (check credentials).</Empty>}
      <ul className="space-y-2">
        {scan.data?.map((d) => (
          <li key={d.device_service_url} className="rounded-md border border-ink-700 p-3 text-xs">
            <div className="font-semibold">
              {d.manufacturer} {d.model}
            </div>
            <div className="text-ink-400">
              FW {d.firmware} · SN {d.serial}
            </div>
            <div className="mt-1 font-mono text-[11px] break-all">{d.device_service_url}</div>
            <div className="font-mono text-[11px] break-all text-accent">→ {d.stream_uri}</div>
            <button
              className="btn btn-primary mt-2 py-1 text-xs"
              disabled={d.already_registered}
              onClick={() =>
                onPick({
                  name: `${d.model ?? "ONVIF camera"}`,
                  source_protocol: "ONVIF",
                  stream_endpoint: d.device_service_url,
                  stream_username: username,
                  vendor: d.manufacturer ?? undefined,
                  model: d.model ?? undefined,
                })
              }
            >
              {d.already_registered ? "Already registered" : "Onboard this device"}
            </button>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
