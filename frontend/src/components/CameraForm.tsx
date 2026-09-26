import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { api } from "../api/client";
import type { Camera, CameraType, Department, SourceProtocol } from "../api/types";
import { Field } from "./ui";

const PROTOCOL_HINT: Record<SourceProtocol, string> = {
  RTSP: "rtsp://host:554/path — pulled by the video gateway and relayed as LL-HLS",
  ONVIF: "http://host/onvif/device_service — stream URI resolved via ONVIF GetStreamUri",
  HLS: "https://…/index.m3u8 — existing HLS publisher, played directly",
  VENDOR_API: "https://nvr/api/channels/1 — vendor REST API (status + snapshot); password = API key",
};

export interface CameraDraft {
  id?: string;
  name?: string;
  latitude?: number;
  longitude?: number;
  source_protocol?: SourceProtocol;
  stream_endpoint?: string;
  stream_username?: string;
  vendor?: string;
  model?: string;
}

export function CameraForm({ camera, draft, onDone }: { camera?: Camera; draft?: CameraDraft; onDone: () => void }) {
  const qc = useQueryClient();
  const editing = !!camera;
  const { data: departments } = useQuery({ queryKey: ["departments"], queryFn: () => api<Department[]>("/departments") });
  const [f, setF] = useState({
    id: camera?.id ?? draft?.id ?? "",
    name: camera?.name ?? draft?.name ?? "",
    department_id: camera?.department_id?.toString() ?? "",
    zone: camera?.zone ?? "",
    address: camera?.address ?? "",
    latitude: (camera?.latitude ?? draft?.latitude ?? 23.03).toString(),
    longitude: (camera?.longitude ?? draft?.longitude ?? 72.58).toString(),
    camera_type: camera?.camera_type ?? ("ANPR" as CameraType),
    source_protocol: camera?.source_protocol ?? draft?.source_protocol ?? ("RTSP" as SourceProtocol),
    stream_endpoint: camera?.stream_endpoint ?? draft?.stream_endpoint ?? "",
    stream_username: camera?.stream_username ?? draft?.stream_username ?? "",
    stream_password: "",
    vendor: camera?.vendor ?? draft?.vendor ?? "",
    model: camera?.model ?? draft?.model ?? "",
    resolution: camera?.resolution ?? "1280x720",
    fps: camera?.fps?.toString() ?? "15",
    recording_enabled: camera?.recording_enabled ?? true,
    storage_tier: camera?.storage_tier ?? "HOT",
    storage_location: camera?.storage_location ?? "",
    retention_days: (camera?.retention_days ?? 30).toString(),
    health_mode: camera?.health_mode ?? "PROBE",
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        name: f.name,
        department_id: f.department_id ? Number(f.department_id) : null,
        zone: f.zone || null,
        address: f.address || null,
        latitude: Number(f.latitude),
        longitude: Number(f.longitude),
        camera_type: f.camera_type,
        stream_endpoint: f.stream_endpoint,
        stream_username: f.stream_username || null,
        vendor: f.vendor || null,
        model: f.model || null,
        resolution: f.resolution || null,
        fps: f.fps ? Number(f.fps) : null,
        recording_enabled: f.recording_enabled,
        storage_tier: f.storage_tier,
        storage_location: f.storage_location || null,
        retention_days: Number(f.retention_days),
        health_mode: f.health_mode,
      };
      if (f.stream_password) body.stream_password = f.stream_password;
      if (editing) return api<Camera>(`/cameras/${camera!.id}`, { method: "PATCH", json: body });
      return api<Camera>("/cameras", { method: "POST", json: { ...body, id: f.id.toUpperCase(), source_protocol: f.source_protocol } });
    },
    onSuccess: (c) => {
      toast.success(`${c.id} ${editing ? "updated" : "onboarded"}`, { description: "Health probe scheduled" });
      qc.invalidateQueries({ queryKey: ["cameras"] });
      qc.invalidateQueries({ queryKey: ["camera"] });
      onDone();
    },
    onError: (e: Error) => toast.error("Save failed", { description: e.message }),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Camera ID">
          <input className="input font-mono uppercase" required disabled={editing} value={f.id} onChange={set("id")} placeholder="C007" pattern="[A-Za-z0-9][A-Za-z0-9_\-]{1,31}" />
        </Field>
        <Field label="Name">
          <input className="input" required minLength={2} value={f.name} onChange={set("name")} placeholder="Nehru Bridge East" />
        </Field>
        <Field label="Department">
          <select className="input" value={f.department_id} onChange={set("department_id")}>
            <option value="">—</option>
            {departments?.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Zone">
          <input className="input" value={f.zone} onChange={set("zone")} placeholder="Ahmedabad East" />
        </Field>
        <Field label="Latitude">
          <input className="input font-mono" type="number" step="0.000001" min={-90} max={90} required value={f.latitude} onChange={set("latitude")} />
        </Field>
        <Field label="Longitude">
          <input className="input font-mono" type="number" step="0.000001" min={-180} max={180} required value={f.longitude} onChange={set("longitude")} />
        </Field>
        <Field label="Address">
          <input className="input" value={f.address} onChange={set("address")} />
        </Field>
        <Field label="Camera type">
          <select className="input" value={f.camera_type} onChange={set("camera_type")}>
            {["ANPR", "FIXED", "PTZ", "DOME", "BULLET", "THERMAL", "DASHCAM"].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </Field>
      </div>

      <fieldset className="space-y-3 rounded-lg border border-ink-700 p-3">
        <legend className="px-1 text-xs font-semibold text-ink-300">Video source</legend>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Source protocol">
            <select className="input" value={f.source_protocol} disabled={editing} onChange={set("source_protocol")}>
              {(["RTSP", "ONVIF", "HLS", "VENDOR_API"] as SourceProtocol[]).map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Health monitoring">
            <select className="input" value={f.health_mode} onChange={set("health_mode")}>
              <option value="PROBE">Active probe</option>
              <option value="HEARTBEAT">Edge heartbeat</option>
            </select>
          </Field>
        </div>
        <Field label="Stream endpoint" hint={PROTOCOL_HINT[f.source_protocol]}>
          <input className="input font-mono text-xs" required value={f.stream_endpoint} onChange={set("stream_endpoint")} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Username">
            <input className="input" autoComplete="off" value={f.stream_username} onChange={set("stream_username")} />
          </Field>
          <Field label={editing ? "Password / API key (leave blank to keep)" : "Password / API key"} hint="Encrypted at rest · never returned by the API">
            <input className="input" type="password" autoComplete="new-password" value={f.stream_password} onChange={set("stream_password")} />
          </Field>
        </div>
      </fieldset>

      <div className="grid grid-cols-3 gap-3">
        <Field label="Vendor">
          <input className="input" value={f.vendor} onChange={set("vendor")} />
        </Field>
        <Field label="Model">
          <input className="input" value={f.model} onChange={set("model")} />
        </Field>
        <Field label="Resolution">
          <input className="input font-mono" value={f.resolution} onChange={set("resolution")} pattern="\d{3,4}x\d{3,4}" />
        </Field>
        <Field label="FPS">
          <input className="input" type="number" min={1} max={120} value={f.fps} onChange={set("fps")} />
        </Field>
        <Field label="Storage tier">
          <select className="input" value={f.storage_tier} onChange={set("storage_tier")}>
            <option>HOT</option>
            <option>WARM</option>
            <option>COLD</option>
          </select>
        </Field>
        <Field label="Retention (days)">
          <input className="input" type="number" min={1} max={3650} value={f.retention_days} onChange={set("retention_days")} />
        </Field>
      </div>
      <div className="grid grid-cols-[1fr_auto] items-end gap-3">
        <Field label="Storage location">
          <input className="input font-mono text-xs" value={f.storage_location} onChange={set("storage_location")} placeholder="s3://bucket/zone/cam" />
        </Field>
        <label className="flex items-center gap-2 pb-2 text-xs text-ink-300">
          <input type="checkbox" checked={f.recording_enabled} onChange={(e) => setF({ ...f, recording_enabled: e.target.checked })} />
          Recording
        </label>
      </div>
      <div className="flex justify-end gap-2 border-t border-ink-700 pt-3">
        <button type="button" className="btn" onClick={onDone}>
          Cancel
        </button>
        <button className="btn btn-primary" disabled={save.isPending}>
          {save.isPending ? "Saving…" : editing ? "Save changes" : "Onboard camera"}
        </button>
      </div>
    </form>
  );
}
