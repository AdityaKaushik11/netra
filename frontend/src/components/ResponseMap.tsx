import L from "leaflet";
import { useEffect } from "react";
import { Circle, MapContainer, Marker, Polyline, Tooltip, useMap } from "react-leaflet";
import type { TraceStop } from "../api/types";
import type { MyLocation } from "../hooks/location";
import { fmtTime } from "../lib/format";
import { OsmTiles } from "./OsmTiles";

export interface Target {
  lat: number;
  lng: number;
  identifier: string;
  seenAt: string;
  place: string;
}

const targetIcon = L.divIcon({
  className: "",
  html: `<div class="target-marker"><span class="pulse"></span><span class="core"><svg viewBox="0 0 24 24" width="16" height="16"><path fill="#fff" d="M5 11l1.5-4.5A2 2 0 0 1 8.4 5h7.2a2 2 0 0 1 1.9 1.5L19 11v6a1 1 0 0 1-1 1h-1a1 1 0 0 1-1-1v-1H8v1a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1zm2.2-1h9.6l-1-3H8.2zM7.5 14a1.25 1.25 0 1 0 0-2.5 1.25 1.25 0 0 0 0 2.5m9 0a1.25 1.25 0 1 0 0-2.5 1.25 1.25 0 0 0 0 2.5"/></svg></span></div>`,
  iconSize: [34, 34],
  iconAnchor: [17, 17],
});

const meIcon = (fallback: boolean) =>
  L.divIcon({
    className: "",
    html: `<div class="me-marker ${fallback ? "hq" : ""}"><span></span></div>`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });

const sightingIcon = (n: number) =>
  L.divIcon({ className: "", html: `<div class="sighting-dot">${n}</div>`, iconSize: [18, 18], iconAnchor: [9, 9] });

function Fit({ points }: { points: [number, number][] }) {
  const map = useMap();
  const key = points.map((p) => p.map((x) => x.toFixed(4)).join(",")).join("|");
  useEffect(() => {
    if (points.length) map.fitBounds(L.latLngBounds(points), { padding: [50, 50], maxZoom: 15 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, map]);
  return null;
}

/** Map for responding to an alert: where the wanted entity is, where the operator is, and the gap. */
export function ResponseMap({ target, me, sightings }: { target: Target; me: MyLocation; sightings: TraceStop[] }) {
  const t: [number, number] = [target.lat, target.lng];
  const m: [number, number] = [me.lat, me.lng];
  const trail = sightings.map((s) => [s.latitude, s.longitude] as [number, number]);
  const earlier = sightings.slice(0, -1);
  return (
    <MapContainer center={t} zoom={13} className="h-full w-full" preferCanvas>
      <OsmTiles />
      {/* Frame the two things that matter: the operator and the wanted entity */}
      <Fit points={[t, m]} />
      {trail.length > 1 && (
        <Polyline positions={trail} pathOptions={{ color: "#f87171", weight: 2, opacity: 0.6, dashArray: "4 6" }} />
      )}
      {earlier.map((s, i) => (
        <Marker key={s.event_id} position={[s.latitude, s.longitude]} icon={sightingIcon(i + 1)}>
          <Tooltip direction="top" offset={[0, -8]}>
            Earlier sighting {i + 1} · {s.camera_id} · {fmtTime(s.detected_at)}
          </Tooltip>
        </Marker>
      ))}
      <Polyline positions={[m, t]} pathOptions={{ color: "#22d3ee", weight: 3, dashArray: "10 8" }} />
      {me.accuracy && me.accuracy < 3000 && (
        <Circle center={m} radius={me.accuracy} pathOptions={{ color: "#3b82f6", weight: 1, fillOpacity: 0.08 }} />
      )}
      <Marker position={m} icon={meIcon(me.source !== "device")} zIndexOffset={900}>
        <Tooltip direction="bottom" offset={[0, 10]} permanent className="map-label me">
          {me.label}
        </Tooltip>
      </Marker>
      <Marker position={t} icon={targetIcon} zIndexOffset={1000}>
        <Tooltip direction="top" offset={[0, -18]} permanent className="map-label target">
          Wanted {target.identifier} · {fmtTime(target.seenAt)} · {target.place}
        </Tooltip>
      </Marker>
    </MapContainer>
  );
}
