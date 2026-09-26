import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import Hls from "hls.js";
import { VideoOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Camera, PlaybackInfo } from "../api/types";
import { StatusDot } from "./Badges";

function withToken(url: string, token: string | null) {
  if (!token || !url.startsWith("/")) return url; // never leak tokens to third-party origins
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
}

/** Unified live view: gateway WebRTC or LL-HLS (RTSP/ONVIF), direct HLS, or vendor snapshot polling. */
export function VideoPlayer({
  camera,
  className,
  showMeta = true,
  lowLatency = false,
}: {
  camera: Camera;
  className?: string;
  showMeta?: boolean;
  /** Prefer WebRTC (sub-second) for gateway streams; falls back to LL-HLS automatically */
  lowLatency?: boolean;
}) {
  const [webrtcFailed, setWebrtcFailed] = useState(false);
  const [transport, setTransport] = useState<string | null>(null);
  const { data: info, error } = useQuery({
    queryKey: ["playback", camera.id],
    queryFn: () => api<PlaybackInfo>(`/cameras/${camera.id}/playback`),
    enabled: camera.is_enabled,
    staleTime: 200_000,
    refetchInterval: 200_000, // stream tokens are short-lived; refresh before expiry
  });
  return (
    <div className={clsx("relative overflow-hidden rounded-lg bg-black", className)}>
      {!camera.is_enabled ? (
        <Placeholder text="Camera disabled" />
      ) : error ? (
        <Placeholder text="Playback unavailable" />
      ) : !info ? (
        <Placeholder text="Connecting…" pulse />
      ) : info.kind === "hls" && info.url && lowLatency && info.webrtc_url && !webrtcFailed ? (
        <WhepView
          url={info.webrtc_url}
          token={info.token}
          onConnected={() => setTransport("WebRTC")}
          onFail={() => {
            setWebrtcFailed(true);
            setTransport("LL-HLS (WebRTC unavailable)");
          }}
        />
      ) : info.kind === "hls" && info.url ? (
        <HlsView url={info.url} token={info.token} />
      ) : info.kind === "snapshot" && info.url ? (
        <SnapshotView url={info.url} token={info.token} />
      ) : (
        <Placeholder text={info.note ?? "No live view"} />
      )}
      {showMeta && (
        <>
          <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center gap-2 bg-gradient-to-b from-black/80 to-transparent px-2.5 py-1.5 text-[11px]">
            <StatusDot status={camera.status} />
            <span className="font-mono font-bold">{camera.id}</span>
            <span className="truncate text-ink-200">{camera.name}</span>
            {camera.open_alerts > 0 && (
              <span className="ml-auto rounded bg-red-600 px-1.5 font-bold text-white">{camera.open_alerts} ALERT</span>
            )}
          </div>
          <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center gap-2 bg-gradient-to-t from-black/80 to-transparent px-2.5 py-1 text-[10px] text-ink-300">
            <span className="font-mono">{camera.source_protocol}</span>
            {transport && <span className="rounded bg-accent/20 px-1 font-mono text-accent">{transport}</span>}
            {camera.camera_type === "DASHCAM" && camera.speed_kmh != null && (
              <span className="rounded bg-violet-500/25 px-1 font-mono text-violet-200">{Math.round(camera.speed_kmh)} km/h</span>
            )}
            <span className="truncate">{info?.note}</span>
          </div>
        </>
      )}
    </div>
  );
}

function Placeholder({ text, pulse }: { text: string; pulse?: boolean }) {
  return (
    <div className={clsx("flex aspect-video h-full w-full flex-col items-center justify-center gap-2 text-xs text-ink-400", pulse && "animate-pulse")}>
      <VideoOff size={22} />
      {text}
    </div>
  );
}

function HlsView({ url, token }: { url: string; token: string | null }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const tokenRef = useRef(token);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    setFailed(false);
    let retryTimer: number | undefined;
    if (Hls.isSupported()) {
      const hls = new Hls({
        lowLatencyMode: true,
        liveSyncDurationCount: 2,
        backBufferLength: 10,
        xhrSetup: (xhr, reqUrl) => {
          const same = reqUrl.startsWith(location.origin) || reqUrl.startsWith("/");
          xhr.open("GET", same ? withToken(reqUrl.replace(location.origin, ""), tokenRef.current) : reqUrl, true);
        },
      });
      hls.loadSource(url);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}));
      hls.on(Hls.Events.ERROR, (_e, data) => {
        if (!data.fatal) return;
        setFailed(true);
        hls.destroy();
        retryTimer = window.setTimeout(() => setAttempt((a) => a + 1), 5000);
      });
      return () => {
        window.clearTimeout(retryTimer);
        hls.destroy();
      };
    }
    video.src = withToken(url, tokenRef.current);
    video.play().catch(() => {});
    return () => {
      video.removeAttribute("src");
      video.load();
    };
  }, [url, attempt]);

  return (
    <>
      <video ref={videoRef} className="aspect-video h-full w-full object-cover" muted playsInline autoPlay />
      {failed && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/70 text-xs text-ink-300">
          <span className="animate-pulse">Stream unavailable · retrying…</span>
        </div>
      )}
    </>
  );
}

function SnapshotView({ url, token }: { url: string; token: string | null }) {
  const [tick, setTick] = useState(0);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const t = window.setInterval(() => setTick((x) => x + 1), 1000);
    return () => window.clearInterval(t);
  }, []);
  const base = withToken(url, token);
  const src = `${base}${base.includes("?") ? "&" : "?"}t=${tick}`;
  return (
    <>
      <img
        src={src}
        alt="Live snapshot"
        className="aspect-video h-full w-full object-cover"
        onLoad={() => setFailed(false)}
        onError={() => setFailed(true)}
      />
      {failed && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/80 text-xs text-ink-300">Video loss</div>
      )}
    </>
  );
}

/** WebRTC playback via WHEP (MediaMTX). Sub-second latency; the stream token authorises the session. */
function WhepView({
  url,
  token,
  onConnected,
  onFail,
}: {
  url: string;
  token: string | null;
  onConnected: () => void;
  onFail: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const cb = useRef({ onConnected, onFail });
  useEffect(() => {
    cb.current = { onConnected, onFail };
  }, [onConnected, onFail]);

  useEffect(() => {
    let pc: RTCPeerConnection | null = null;
    let session: string | null = null;
    let done = false;
    const fail = () => {
      if (done) return;
      done = true;
      cb.current.onFail();
    };
    const timer = window.setTimeout(fail, 8000);
    (async () => {
      try {
        pc = new RTCPeerConnection();
        pc.addTransceiver("video", { direction: "recvonly" });
        pc.ontrack = (e) => {
          if (videoRef.current) videoRef.current.srcObject = e.streams[0];
        };
        pc.onconnectionstatechange = () => {
          if (pc?.connectionState === "connected" && !done) {
            done = true;
            window.clearTimeout(timer);
            cb.current.onConnected();
          } else if (pc?.connectionState === "failed") fail();
        };
        await pc.setLocalDescription(await pc.createOffer());
        // Wait briefly for ICE candidates so the offer is complete (no trickle needed)
        await new Promise<void>((resolve) => {
          if (pc!.iceGatheringState === "complete") return resolve();
          const t = window.setTimeout(resolve, 1500);
          pc!.onicegatheringstatechange = () => {
            if (pc!.iceGatheringState === "complete") {
              window.clearTimeout(t);
              resolve();
            }
          };
        });
        const res = await fetch(withToken(url, token), {
          method: "POST",
          headers: { "Content-Type": "application/sdp" },
          body: pc.localDescription!.sdp,
        });
        if (res.status !== 201) throw new Error(`WHEP ${res.status}`);
        session = res.headers.get("Location");
        await pc.setRemoteDescription({ type: "answer", sdp: await res.text() });
      } catch {
        fail();
      }
    })();
    return () => {
      done = true;
      window.clearTimeout(timer);
      pc?.close();
      if (session) fetch(withToken(session, token), { method: "DELETE" }).catch(() => {});
    };
  }, [url, token]);

  return <video ref={videoRef} className="aspect-video h-full w-full object-cover" muted playsInline autoPlay />;
}

/** Recorded footage (evidence clip) served as MP4 by the gateway playback server. */
export function ClipPlayer({ cameraId, start, duration, className }: { cameraId: string; start: string; duration: number; className?: string }) {
  const { data, error } = useQuery({
    queryKey: ["clip", cameraId, start, duration],
    queryFn: () => api<PlaybackInfo>(`/cameras/${cameraId}/clip?start=${encodeURIComponent(start)}&duration=${duration}`),
    staleTime: 200_000,
    retry: false,
  });
  const [failed, setFailed] = useState(false);
  return (
    <div className={clsx("relative overflow-hidden rounded-lg bg-black", className)}>
      {error ? (
        <Placeholder text={(error as Error).message} />
      ) : !data?.url ? (
        <Placeholder text="Loading recording…" pulse />
      ) : failed ? (
        <Placeholder text="No recording for this time window yet" />
      ) : (
        <video
          key={data.url}
          src={withToken(data.url, data.token)}
          className="aspect-video h-full w-full object-cover"
          controls
          muted
          autoPlay
          playsInline
          onError={() => setFailed(true)}
        />
      )}
      {data?.note && (
        <div className="pointer-events-none absolute top-0 left-0 rounded-br bg-black/70 px-2 py-0.5 font-mono text-[10px] text-ink-200">
          REC · {data.note}
        </div>
      )}
    </div>
  );
}
