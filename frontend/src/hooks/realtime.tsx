import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { getToken } from "../api/client";
import type { Alert, Camera, CameraLocation, DetectionEvent, Page, RealtimeMessage, TrackPoint } from "../api/types";
import { AlertToast } from "../components/AlertToast";
import { playAlertTone } from "../lib/sound";

interface RealtimeState {
  connected: boolean;
  detections: DetectionEvent[];
  recentAlertIds: Set<number>;
  muted: boolean;
  setMuted: (m: boolean) => void;
  messagesPerMin: number;
}

const RealtimeContext = createContext<RealtimeState | null>(null);

/** Same origin by default; a separate frontend host (e.g. Vercel, which cannot proxy
 * WebSockets) sets VITE_WS_URL to the backend's wss://…/api/v1/ws at build time. */
function wsEndpoint(): string {
  const configured = import.meta.env.VITE_WS_URL as string | undefined;
  if (configured) return configured;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/api/v1/ws`;
}
const MAX_DETECTIONS = 80;

/**
 * One WebSocket per tab. Server pushes domain events; we merge them into local state and
 * invalidate the relevant React Query caches (throttled) so every view stays in sync without
 * polling or page refreshes.
 */
export function RealtimeProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [detections, setDetections] = useState<DetectionEvent[]>([]);
  const [recentAlertIds, setRecentAlertIds] = useState<Set<number>>(new Set());
  const [muted, setMuted] = useState(false);
  const [messagesPerMin, setRate] = useState(0);
  const mutedRef = useRef(muted);
  const stamps = useRef<number[]>([]);

  useEffect(() => {
    mutedRef.current = muted;
  }, [muted]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry = 0;
    let closed = false;
    let wasConnected = false;
    let ping: number | undefined;
    const pending = new Set<string>();
    let flushTimer: number | undefined;

    const invalidate = (...keys: string[]) => {
      keys.forEach((k) => pending.add(k));
      if (flushTimer) return;
      flushTimer = window.setTimeout(() => {
        pending.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
        pending.clear();
        flushTimer = undefined;
      }, 1200);
    };

    const handle = (msg: RealtimeMessage) => {
      const now = Date.now();
      stamps.current = [...stamps.current.filter((t) => now - t < 60_000), now];
      switch (msg.type) {
        case "detection.created": {
          const ev = msg.data as DetectionEvent;
          setDetections((prev) => [ev, ...prev].slice(0, MAX_DETECTIONS));
          invalidate("overview", "events", "timeseries");
          break;
        }
        case "alert.created": {
          const a = msg.data as Alert;
          setRecentAlertIds((prev) => new Set(prev).add(a.id));
          toast.custom((id) => <AlertToast alert={a} toastId={id} />, {
            duration: a.severity === "CRITICAL" ? 20_000 : 10_000,
          });
          if (!mutedRef.current) playAlertTone(a.severity);
          invalidate("alerts", "overview", "cameras", "trace", "watchlist");
          break;
        }
        case "alert.updated":
          invalidate("alerts", "overview", "cameras");
          break;
        case "camera.status": {
          const c = msg.data as Camera;
          if (c.status === "OFFLINE") toast.error(`${c.id} ${c.name} went OFFLINE`, { description: c.status_reason ?? "" });
          else if (c.status === "DEGRADED") toast.warning(`${c.id} ${c.name} DEGRADED`, { description: c.status_reason ?? "" });
          else if (c.status === "ONLINE") toast.success(`${c.id} ${c.name} back ONLINE`);
          invalidate("cameras", "overview", "camera");
          break;
        }
        case "camera.created":
        case "camera.updated":
        case "camera.bulk_created":
          invalidate("cameras", "overview", "camera");
          break;
        case "camera.location": {
          // Dashcam GPS fix: move the marker in every cached camera list and extend its trail
          const loc = msg.data as CameraLocation;
          qc.setQueriesData<Page<Camera>>({ queryKey: ["cameras"] }, (old) =>
            old && Array.isArray(old.items)
              ? {
                  ...old,
                  items: old.items.map((c) =>
                    c.id === loc.id
                      ? { ...c, latitude: loc.latitude, longitude: loc.longitude, speed_kmh: loc.speed_kmh, heading_deg: loc.heading_deg, location_updated_at: loc.at }
                      : c,
                  ),
                }
              : old,
          );
          qc.setQueriesData<TrackPoint[]>({ queryKey: ["track", loc.id] }, (old) =>
            old
              ? [...old, { t: loc.at, latitude: loc.latitude, longitude: loc.longitude, speed_kmh: loc.speed_kmh, heading_deg: loc.heading_deg }].slice(-2000)
              : old,
          );
          break;
        }
        case "watchlist.changed":
          invalidate("watchlist");
          break;
      }
    };

    const connect = () => {
      const token = getToken();
      if (!token || closed) return;
      ws = new WebSocket(`${wsEndpoint()}?token=${encodeURIComponent(token)}`);
      ws.onopen = () => {
        retry = 0;
        setConnected(true);
        ping = window.setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send("ping"), 25_000);
        // After a reconnect, catch up on anything missed while disconnected
        if (wasConnected) qc.invalidateQueries();
        wasConnected = true;
      };
      ws.onmessage = (e) => {
        try {
          handle(JSON.parse(e.data));
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        setConnected(false);
        window.clearInterval(ping);
        if (closed) return;
        const delay = Math.min(15_000, 500 * 2 ** retry++) + Math.random() * 500;
        window.setTimeout(connect, delay);
      };
    };
    connect();
    const rateTimer = window.setInterval(() => {
      const now = Date.now();
      stamps.current = stamps.current.filter((t) => now - t < 60_000);
      setRate(stamps.current.length);
    }, 2000);
    return () => {
      closed = true;
      window.clearInterval(ping);
      window.clearInterval(rateTimer);
      window.clearTimeout(flushTimer);
      ws?.close();
    };
  }, [qc]);

  const value = useMemo(
    () => ({ connected, detections, recentAlertIds, muted, setMuted, messagesPerMin }),
    [connected, detections, recentAlertIds, muted, messagesPerMin],
  );
  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

export function useRealtime() {
  const ctx = useContext(RealtimeContext);
  if (!ctx) throw new Error("useRealtime outside RealtimeProvider");
  return ctx;
}
