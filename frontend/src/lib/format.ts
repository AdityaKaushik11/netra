import { format, formatDistanceToNowStrict } from "date-fns";

export const fmtTime = (iso: string | null | undefined) => (iso ? format(new Date(iso), "HH:mm:ss") : "—");
export const fmtDateTime = (iso: string | null | undefined) =>
  iso ? format(new Date(iso), "dd MMM yyyy, HH:mm:ss") : "—";
export const fmtShort = (iso: string | null | undefined) => (iso ? format(new Date(iso), "dd MMM HH:mm") : "—");
export const ago = (iso: string | null | undefined) =>
  iso ? formatDistanceToNowStrict(new Date(iso), { addSuffix: true }) : "never";
export const pct = (v: number) => `${Math.round(v * 100)}%`;

export const titleCase = (s: string | null | undefined) =>
  (s ?? "")
    .toLowerCase()
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

export const EVENT_LABEL: Record<string, string> = {
  ANPR: "Number-plate read (ANPR)",
  VEHICLE_DETECTION: "Vehicle detection",
  PERSON_DETECTION: "Person detection",
  FACE_RECOGNITION: "Face recognition",
  OBJECT_DETECTION: "Object detection",
  OVERSPEED: "Overspeeding",
  HARSH_BRAKING: "Harsh braking",
  COLLISION_WARNING: "Forward collision warning",
  DRIVER_DROWSINESS: "Driver drowsiness",
};

/** Great-circle distance in km. */
export function distanceKm(a: [number, number], b: [number, number]) {
  const r = 6371;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b[0] - a[0]);
  const dLng = toRad(b[1] - a[1]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLng / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(h));
}

/** Readable label for a key, e.g. "packet_loss_pct" -> "Packet Loss %", "temperature_c" -> "Temperature (°C)". */
export const humanKey = (k: string) =>
  titleCase(
    k
      .replace(/_pct$/, "_%")
      .replace(/_kbps$/, "_(kbps)")
      .replace(/_kmh$/, "_(km/h)")
      .replace(/_ms$/, "_(ms)")
      .replace(/_s$/, "_(s)")
      .replace(/_c$/, "_(°C)"),
  );
