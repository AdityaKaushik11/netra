import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { api } from "../api/client";
import type { Camera, Page } from "../api/types";
import { PageHeader } from "../components/ui";
import { VideoPlayer } from "../components/VideoPlayer";

export function LiveWallPage() {
  const [cols, setCols] = useState(3);
  const [lowLatency, setLowLatency] = useState(false);
  const { data } = useQuery({ queryKey: ["cameras", "wall"], queryFn: () => api<Page<Camera>>("/cameras?enabled=true&limit=64") });
  return (
    <div>
      <PageHeader
        title="Live wall"
        subtitle="Every enabled source in one unified view · gateway LL-HLS, direct HLS and vendor snapshots"
        actions={
          <>
          <label className="flex items-center gap-2 text-xs text-ink-300">
            <input type="checkbox" checked={lowLatency} onChange={(e) => setLowLatency(e.target.checked)} />
            WebRTC low latency
          </label>
          <div className="flex overflow-hidden rounded-md border border-ink-600">
            {[2, 3, 4].map((n) => (
              <button key={n} className={clsx("px-3 py-1 text-xs", cols === n ? "bg-ink-700 text-accent" : "text-ink-300")} onClick={() => setCols(n)}>
                {n}×
              </button>
            ))}
          </div>
          </>
        }
      />
      <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
        {data?.items.map((c) => (
          <VideoPlayer key={`${c.id}-${lowLatency}`} camera={c} lowLatency={lowLatency} />
        ))}
      </div>
    </div>
  );
}
