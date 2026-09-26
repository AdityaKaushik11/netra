import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { CheckCheck, Crosshair, Eye, Navigation, Route } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api } from "../api/client";
import type { Alert, Camera, DetectionEvent, Trace } from "../api/types";
import { useAuth } from "../hooks/auth";
import { useMyLocation } from "../hooks/location";
import { ago, distanceKm, EVENT_LABEL, fmtDateTime, humanKey, pct, titleCase } from "../lib/format";
import { AlertStatusBadge, Confidence, Plate, SEVERITY_COLOR, SeverityBadge } from "./Badges";
import { ResponseMap } from "./ResponseMap";
import { Field, Modal } from "./ui";
import { ClipPlayer, VideoPlayer } from "./VideoPlayer";

const URBAN_SPEED_KMH = 30;

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="contents">
      <dt className="text-ink-400">{label}</dt>
      <dd className="text-ink-100">{children}</dd>
    </div>
  );
}

function Card({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  return (
    <section className={clsx("rounded-lg border border-ink-700 bg-ink-900/60 p-3", className)}>
      <h3 className="panel-title mb-2">{title}</h3>
      {children}
    </section>
  );
}

/** Where in the camera frame the AI found the plate / face / object. */
function FrameRegion({ box, label }: { box: { x: number; y: number; w: number; h: number }; label: string }) {
  // Boxes may be in pixels (1280x720 frame) or normalised (0..1)
  const norm = box.x <= 1 && box.y <= 1 && box.w <= 1 && box.h <= 1;
  const W = 1280;
  const H = 720;
  const b = norm ? { x: box.x * W, y: box.y * H, w: box.w * W, h: box.h * H } : box;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-28 w-auto rounded border border-ink-700 bg-ink-950" role="img" aria-label="Detection region in frame">
      <rect x="0" y={H * 0.45} width={W} height={H * 0.55} fill="#1a2531" />
      <line x1="0" y1={H * 0.72} x2={W} y2={H * 0.72} stroke="#3a4b5e" strokeWidth="6" strokeDasharray="40 30" />
      <rect x={b.x} y={b.y} width={b.w} height={b.h} fill="rgba(34,211,238,0.18)" stroke="#22d3ee" strokeWidth="6" rx="6" />
      <text x={b.x} y={Math.max(40, b.y - 16)} fill="#22d3ee" fontSize="40" fontFamily="JetBrains Mono, monospace" fontWeight="700">
        {label}
      </text>
    </svg>
  );
}

export function AlertDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const [falsePositive, setFalsePositive] = useState(false);
  const { location: me, status: locStatus, locate } = useMyLocation();

  const { data: alert } = useQuery({ queryKey: ["alerts", "detail", id], queryFn: () => api<Alert>(`/alerts/${id}`) });
  const { data: camera } = useQuery({
    queryKey: ["camera", alert?.camera_id],
    queryFn: () => api<Camera>(`/cameras/${alert!.camera_id}`),
    enabled: !!alert,
  });
  const { data: event } = useQuery({
    queryKey: ["events", "detail", alert?.event_id],
    queryFn: () => api<DetectionEvent>(`/events/${alert!.event_id}`),
    enabled: !!alert,
  });
  const { data: trace } = useQuery({
    queryKey: ["trace", alert?.identifier],
    queryFn: () => api<Trace>(`/trace/${encodeURIComponent(alert!.identifier)}`),
    enabled: !!alert,
  });

  const done = (msg: string) => () => {
    toast.success(msg);
    qc.invalidateQueries({ queryKey: ["alerts"] });
    qc.invalidateQueries({ queryKey: ["overview"] });
  };
  const ack = useMutation({
    mutationFn: () => api<Alert>(`/alerts/${id}/acknowledge`, { method: "POST", json: { note: note || null } }),
    onSuccess: done("Alert acknowledged"),
    onError: (e: Error) => toast.error(e.message),
  });
  const resolve = useMutation({
    mutationFn: () => api<Alert>(`/alerts/${id}/resolve`, { method: "POST", json: { note, false_positive: falsePositive } }),
    onSuccess: () => {
      done("Alert closed")();
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!alert) return null;
  const open = alert.status === "NEW" || alert.status === "ACKNOWLEDGED";
  const recorded = camera?.recording_enabled && (camera.source_protocol === "RTSP" || camera.source_protocol === "ONVIF");

  // The wanted entity's best known position: the latest sighting (may be newer than this alert)
  const last = trace?.stops.at(-1);
  const newer = last && new Date(last.detected_at) > new Date(alert.triggered_at);
  const target = newer
    ? { lat: last.latitude, lng: last.longitude, identifier: alert.identifier, seenAt: last.detected_at, place: `${last.camera_id} ${last.camera_name}` }
    : { lat: alert.latitude, lng: alert.longitude, identifier: alert.identifier, seenAt: event?.detected_at ?? alert.triggered_at, place: `${alert.camera_id} ${alert.camera_name ?? ""}` };
  const recentSightings = (trace?.stops ?? [])
    .filter((st) => new Date(target.seenAt).getTime() - new Date(st.detected_at).getTime() < 2 * 3600_000)
    .slice(-6);
  const km = distanceKm([me.lat, me.lng], [target.lat, target.lng]);
  const etaMin = Math.max(1, Math.round((km / URBAN_SPEED_KMH) * 60));
  const directions = `https://www.google.com/maps/dir/?api=1&origin=${me.lat},${me.lng}&destination=${target.lat},${target.lng}&travelmode=driving`;
  const vehicle = [alert.vehicle_color, alert.vehicle_type].filter(Boolean).join(" ");
  const attrs = Object.entries(alert.watchlist_attributes ?? {});
  const speed = event?.attributes?.speed_kmh as number | undefined;
  const listedColor = String(alert.watchlist_attributes?.color ?? "").toLowerCase();
  const colorMismatch = !!listedColor && !!alert.vehicle_color && listedColor !== alert.vehicle_color.toLowerCase();

  return (
    <Modal
      size="xl"
      onClose={onClose}
      title={
        <span className="flex items-center gap-2">
          <SeverityBadge severity={alert.severity} /> Alert #{alert.id} <AlertStatusBadge status={alert.status} />
        </span>
      }
    >
      {/* Summary strip */}
      <div
        className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border p-3"
        style={{ borderColor: SEVERITY_COLOR[alert.severity], background: `color-mix(in srgb, ${SEVERITY_COLOR[alert.severity]} 8%, transparent)` }}
      >
        <Plate value={alert.identifier} className="text-xl leading-8" />
        <div>
          <div className="text-base font-semibold">{titleCase(alert.category)}</div>
          <div className="text-xs text-ink-300">
            Seen {ago(target.seenAt)} at <b>{target.place}</b>
          </div>
        </div>
        <div className="ml-auto flex flex-wrap gap-4 text-center text-xs">
          <div>
            <div className="text-lg font-semibold tabular-nums">{pct(alert.confidence)}</div>
            <div className="text-ink-400">Confidence</div>
          </div>
          <div>
            <div className="text-lg font-semibold tabular-nums">{alert.hit_count}</div>
            <div className="text-ink-400">Hits</div>
          </div>
          <div>
            <div className="text-lg font-semibold tabular-nums">{km.toFixed(1)} km</div>
            <div className="text-ink-400">From {me.source === "device" ? "you" : "control room"}</div>
          </div>
          <div>
            <div className="text-lg font-semibold tabular-nums">~{etaMin} min</div>
            <div className="text-ink-400">Drive time</div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          <Card title="Watchlist record">
            <p className="mb-2 text-sm text-ink-100">{alert.watchlist_description ?? "—"}</p>
            <dl className="grid grid-cols-[130px_1fr] gap-x-3 gap-y-1.5 text-xs">
              <Row label="Listed as">
                <Plate value={alert.watchlist_identifier ?? alert.identifier} /> · {titleCase(alert.category)}
              </Row>
              {attrs.map(([k, v]) => (
                <Row key={k} label={humanKey(k)}>
                  {String(v)}
                </Row>
              ))}
              <Row label="Case reference">
                <span className="font-mono">{alert.case_reference ?? "—"}</span>
              </Row>
              <Row label="Reported by">{alert.source_agency ?? "—"}</Row>
            </dl>
          </Card>

          <Card title="What the camera detected">
            <dl className="grid grid-cols-[130px_1fr] gap-x-3 gap-y-1.5 text-xs">
              <Row label="Detection">{event ? EVENT_LABEL[event.event_type] ?? titleCase(event.event_type) : "—"}</Row>
              <Row label="Read as">
                <Plate value={alert.identifier} />
                {alert.match_type === "EXACT" ? (
                  <span className="ml-2 text-emerald-300">exact match with watchlist</span>
                ) : (
                  <span className="ml-2 text-amber-300">
                    possible match — differs by one character from {alert.watchlist_identifier} (verify visually)
                  </span>
                )}
                {event?.attributes?.plate_format_valid === false && (
                  <div className="mt-0.5 text-amber-300">Not a standard Indian registration format — possible fake or misread plate.</div>
                )}
              </Row>
              <Row label="AI confidence">
                <Confidence value={alert.confidence} />
              </Row>
              <Row label="Time">
                {event ? fmtDateTime(event.detected_at) : fmtDateTime(alert.triggered_at)}
                <span className="text-ink-400"> ({ago(event?.detected_at ?? alert.triggered_at)})</span>
              </Row>
              <Row label="Camera">
                {alert.camera_id} · {alert.camera_name}
                {alert.camera_zone && <span className="text-ink-400"> · {alert.camera_zone}</span>}
              </Row>
              <Row label="Location">
                {camera?.address ?? "—"}{" "}
                <span className="font-mono text-ink-400">
                  ({alert.latitude.toFixed(5)}, {alert.longitude.toFixed(5)})
                </span>
              </Row>
              {vehicle && (
                <Row label="Vehicle seen">
                  {titleCase(vehicle.replace(/ /g, "_"))}
                  {colorMismatch && (
                    <div className="mt-0.5 text-amber-300">
                      Watchlist lists a {listedColor} vehicle — colour differs, possible false plate or misread. Verify on the feed.
                    </div>
                  )}
                </Row>
              )}
              {speed !== undefined && <Row label="Camera speed">{Math.round(speed)} km/h (mobile dashcam)</Row>}
              {event && (
                <Row label="Reads">
                  {event.repeat_count + 1} read{event.repeat_count ? "s" : ""} of this vehicle as it passed
                </Row>
              )}
              {event?.model_name && <Row label="Analysed by">{event.model_name}</Row>}
            </dl>
            {event?.bounding_box && (
              <div className="mt-3">
                <div className="mb-1 text-[11px] text-ink-400">Where the plate was found in the frame</div>
                <FrameRegion box={event.bounding_box} label={alert.identifier} />
              </div>
            )}
          </Card>

          <Card title="Timeline">
            <ol className="space-y-1.5 text-xs">
              <li>
                <span className="text-ink-400">Raised</span> · {fmtDateTime(alert.triggered_at)}
              </li>
              {alert.hit_count > 1 && (
                <li>
                  <span className="text-ink-400">Seen again</span> · {fmtDateTime(alert.last_hit_at)} ({alert.hit_count} hits)
                </li>
              )}
              <li>
                <span className="text-ink-400">Acknowledged</span> · {alert.acknowledged_at ? fmtDateTime(alert.acknowledged_at) : "pending"}
              </li>
              <li>
                <span className="text-ink-400">Closed</span> · {alert.resolved_at ? fmtDateTime(alert.resolved_at) : "open"}
                {alert.resolution_note && <span className="text-ink-300"> — “{alert.resolution_note}”</span>}
              </li>
            </ol>
          </Card>
        </div>

        <div className="space-y-4">
          {camera && (
            <Card title="Live feed">
              <VideoPlayer camera={camera} />
            </Card>
          )}
          {camera && recorded && (
            <Card title="Evidence clip · recorded around the alert">
              <ClipPlayer cameraId={camera.id} start={new Date(new Date(alert.triggered_at).getTime() - 20_000).toISOString()} duration={40} />
            </Card>
          )}
        </div>
      </div>

      <section className="mt-4 overflow-hidden rounded-lg border border-ink-700">
        <header className="flex flex-wrap items-center gap-3 border-b border-ink-700 bg-ink-900 px-3 py-2 text-xs">
          <h3 className="panel-title">Response map</h3>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-full border-2 border-white bg-offline" /> Wanted {alert.identifier}
            {newer && <span className="text-amber-300">(latest sighting, newer than this alert)</span>}
          </span>
          <span className="flex items-center gap-1.5">
            <span className={clsx("size-2.5 border-2 border-white", me.source === "device" ? "rounded-full bg-blue-500" : "rounded-sm bg-accent")} />
            {me.source === "device" ? "You" : "Control room"}
          </span>
          {recentSightings.length > 1 && (
            <span className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-full border-2 border-red-400 bg-ink-700" /> Earlier sightings
            </span>
          )}
          <span className="font-mono text-accent">
            {km.toFixed(2)} km · ~{etaMin} min
          </span>
          <div className="ml-auto flex gap-2">
            <button className="btn py-1 text-xs" onClick={locate} title="Use this device's location">
              <Crosshair size={13} />
              {locStatus === "locating" ? "Locating…" : me.source === "device" ? "Update my location" : "Use my location"}
            </button>
            <a className="btn py-1 text-xs" href={directions} target="_blank" rel="noreferrer">
              <Navigation size={13} /> Directions
            </a>
            <Link to={`/trace/${alert.identifier}`} className="btn py-1 text-xs">
              <Route size={13} /> Full movement history
            </Link>
          </div>
        </header>
        {me.source !== "device" && (
          <div className="border-b border-ink-700 bg-amber-500/10 px-3 py-1.5 text-[11px] text-amber-200">
            {locStatus === "denied"
              ? "Location permission was denied, so distances are measured from the control room. Allow location for this site and press “Use my location”."
              : locStatus === "locating"
                ? "Getting your location…"
                : "Your device location is unavailable, so distances are measured from the control room."}
          </div>
        )}
        <div className="h-[360px]">
          <ResponseMap target={target} me={me} sightings={recentSightings} />
        </div>
      </section>

      {open && can("ADMIN", "OPERATOR") && (
        <div className="mt-4 space-y-2 border-t border-ink-700 pt-4">
          <Field label="Operator note">
            <textarea className="input h-16" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. PCR van 12 dispatched to Paldi junction" />
          </Field>
          <div className="flex flex-wrap items-center gap-2">
            {alert.status === "NEW" && (
              <button className="btn" onClick={() => ack.mutate()} disabled={ack.isPending}>
                <Eye size={14} /> Acknowledge
              </button>
            )}
            <label className="ml-auto flex items-center gap-2 text-xs text-ink-300">
              <input type="checkbox" checked={falsePositive} onChange={(e) => setFalsePositive(e.target.checked)} /> False positive
            </label>
            <button className="btn btn-primary" onClick={() => resolve.mutate()} disabled={note.trim().length < 3 || resolve.isPending}>
              <CheckCheck size={14} /> Resolve
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
