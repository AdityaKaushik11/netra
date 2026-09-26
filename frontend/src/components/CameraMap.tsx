import L from "leaflet";
import { useEffect, useMemo } from "react";
import { MapContainer, Marker, Polyline, Popup, Tooltip, useMap } from "react-leaflet";
import type { Camera, TraceStop, TrackPoint } from "../api/types";
import { fmtTime } from "../lib/format";
import { STATUS_COLOR, StatusBadge } from "./Badges";
import { OsmTiles } from "./OsmTiles";

const AHMEDABAD: [number, number] = [23.07, 72.57];

function cameraIcon(c: Camera, showLabel: boolean) {
  const color = c.is_enabled ? STATUS_COLOR[c.status] : "#475569";
  if (c.camera_type === "DASHCAM") {
    // Mobile camera: arrow pointing along the vehicle's heading, speed in the label
    const ring = c.open_alerts > 0 ? '<span class="ring"></span>' : "";
    const speed = c.speed_kmh != null ? ` · ${Math.round(c.speed_kmh)} km/h` : "";
    const label = showLabel ? `<span class="label">${c.id}${speed}</span>` : "";
    return L.divIcon({
      className: "",
      html: `<div class="cam-marker dashcam">${ring}<span class="arrow" style="transform:rotate(${c.heading_deg ?? 0}deg)"><svg viewBox="0 0 24 24" width="22" height="22"><path d="M12 2 20 21 12 16 4 21Z" fill="${color}" stroke="#0a0e13" stroke-width="1.5"/></svg></span>${label}</div>`,
      iconSize: [22, 22],
      iconAnchor: [11, 11],
    });
  }
  const ring = c.open_alerts > 0 ? '<span class="ring"></span>' : "";
  const label = showLabel ? `<span class="label">${c.id}</span>` : "";
  return L.divIcon({
    className: "",
    html: `<div class="cam-marker">${ring}<span class="dot" style="background:${color}"></span>${label}</div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

function stopIcon(n: number) {
  return L.divIcon({ className: "", html: `<div class="route-stop">${n}</div>`, iconSize: [24, 24], iconAnchor: [12, 12] });
}

function FitBounds({ points, padding = 40 }: { points: [number, number][]; padding?: number }) {
  const map = useMap();
  const key = points.map((p) => p.join(",")).join("|");
  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) map.setView(points[0], 14);
    else map.fitBounds(L.latLngBounds(points), { padding: [padding, padding], maxZoom: 14 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, map, padding]);
  return null;
}

interface Props {
  cameras: Camera[];
  route?: TraceStop[];
  /** GPS trails of mobile cameras, keyed by camera id */
  tracks?: Record<string, TrackPoint[]>;
  onSelect?: (c: Camera) => void;
  showLabels?: boolean;
  className?: string;
}

export function CameraMap({ cameras, route, tracks, onSelect, showLabels = true, className }: Props) {
  const routePoints = useMemo<[number, number][]>(
    () => (route ?? []).map((s) => [s.latitude, s.longitude]),
    [route],
  );
  const fitPoints = routePoints.length ? routePoints : cameras.map((c) => [c.latitude, c.longitude] as [number, number]);

  return (
    <MapContainer center={AHMEDABAD} zoom={11} className={className ?? "h-full w-full"} zoomControl preferCanvas>
      <OsmTiles />
      <FitBounds points={fitPoints} />
      {cameras.map((c) => (
        <Marker
          key={c.id}
          position={[c.latitude, c.longitude]}
          icon={cameraIcon(c, showLabels && !route?.length)}
          eventHandlers={{ click: () => onSelect?.(c) }}
        >
          {!onSelect && (
            <Popup>
              <div className="space-y-1 text-xs">
                <div className="font-semibold">
                  {c.id} · {c.name}
                </div>
                <StatusBadge status={c.status} enabled={c.is_enabled} />
                <div className="text-ink-300">{c.status_reason}</div>
              </div>
            </Popup>
          )}
          <Tooltip direction="top" offset={[0, -8]}>
            {c.id} · {c.name}
            {c.open_alerts > 0 ? ` · ${c.open_alerts} open alert(s)` : ""}
          </Tooltip>
        </Marker>
      ))}
      {Object.entries(tracks ?? {}).map(([id, pts]) =>
        pts.length > 1 ? (
          <Polyline
            key={`track-${id}`}
            positions={pts.map((p) => [p.latitude, p.longitude] as [number, number])}
            pathOptions={{ color: "#a78bfa", weight: 3, opacity: 0.75 }}
          />
        ) : null,
      )}
      {routePoints.length > 1 && (
        <>
          <Polyline positions={routePoints} pathOptions={{ color: "#22d3ee", weight: 8, opacity: 0.15 }} />
          <Polyline positions={routePoints} pathOptions={{ color: "#22d3ee", weight: 3, dashArray: "8 8" }} />
        </>
      )}
      {route?.map((s, i) => (
        <Marker key={s.event_id} position={[s.latitude, s.longitude]} icon={stopIcon(i + 1)} zIndexOffset={1000}>
          <Tooltip direction="right" offset={[14, 0]} permanent>
            <span className="font-mono">{fmtTime(s.detected_at)}</span> · {s.camera_id}
          </Tooltip>
        </Marker>
      ))}
    </MapContainer>
  );
}
