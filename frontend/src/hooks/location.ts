import { useCallback, useEffect, useState } from "react";

export interface MyLocation {
  lat: number;
  lng: number;
  accuracy: number | null;
  source: "device" | "control-room";
  label: string;
}

/** Fallback when the browser can't share a position: Ahmedabad Police Commissionerate control room. */
const CONTROL_ROOM: MyLocation = {
  lat: 23.05275,
  lng: 72.59083,
  accuracy: null,
  source: "control-room",
  label: "Control room (Shahibaug)",
};

/** Operator's position from the browser (GPS / Wi-Fi), falling back to the control room. */
export function useMyLocation() {
  const [location, setLocation] = useState<MyLocation>(CONTROL_ROOM);
  const [status, setStatus] = useState<"locating" | "ok" | "denied" | "unavailable">("locating");

  const locate = useCallback(() => {
    if (!("geolocation" in navigator)) {
      setStatus("unavailable");
      return;
    }
    setStatus("locating");
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setLocation({
          lat: p.coords.latitude,
          lng: p.coords.longitude,
          accuracy: p.coords.accuracy,
          source: "device",
          label: "Your location",
        });
        setStatus("ok");
      },
      (err) => setStatus(err.code === err.PERMISSION_DENIED ? "denied" : "unavailable"),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60_000 },
    );
  }, []);

  useEffect(() => {
    locate();
  }, [locate]);

  return { location, status, locate };
}
