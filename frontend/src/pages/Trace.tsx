import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Route, Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Camera, Page, Trace } from "../api/types";
import { Confidence, Plate, SeverityBadge } from "../components/Badges";
import { CameraMap } from "../components/CameraMap";
import { Empty, PageHeader, Panel } from "../components/ui";
import { fmtDateTime, fmtShort, fmtTime, titleCase } from "../lib/format";

interface SearchResult {
  entities: { identifier_normalized: string; identifier: string; detections: number; last_seen: string; cameras: number }[];
  watchlist: { id: number; identifier: string; category: string; severity: string; is_active: boolean }[];
  cameras: { id: string; name: string; status: string; zone: string | null }[];
}

export function TracePage() {
  const { identifier } = useParams();
  const navigate = useNavigate();
  const [q, setQ] = useState(identifier ?? "");
  const [term, setTerm] = useState(identifier ?? "");

  const { data: trace, isFetching } = useQuery({
    queryKey: ["trace", identifier],
    queryFn: () => api<Trace>(`/trace/${encodeURIComponent(identifier!)}`),
    enabled: !!identifier,
  });
  const { data: results } = useQuery({
    queryKey: ["search", term],
    queryFn: () => api<SearchResult>(`/search?q=${encodeURIComponent(term)}`),
    enabled: term.length >= 2 && !identifier,
  });
  const { data: cams } = useQuery({ queryKey: ["cameras", "all"], queryFn: () => api<Page<Camera>>("/cameras?limit=1000") });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const v = q.trim().toUpperCase();
    if (!v) return;
    setTerm(v);
    navigate(`/trace/${v}`);
  };

  return (
    <div>
      <PageHeader title="Entity search & movement trace" subtitle="Reconstructs a vehicle's chronological route across cameras" />
      <form onSubmit={submit} className="mb-3 flex max-w-xl gap-2">
        <div className="relative flex-1">
          <Search size={14} className="absolute top-1/2 left-2.5 -translate-y-1/2 text-ink-400" />
          <input className="input pl-8 font-mono uppercase" value={q} onChange={(e) => setQ(e.target.value)} placeholder="GJ01XX0001" />
        </div>
        <button className="btn btn-primary">
          <Route size={14} /> Trace
        </button>
        {identifier && (
          <button
            type="button"
            className="btn"
            onClick={() => {
              setTerm(q);
              navigate("/trace");
            }}
          >
            Partial-match search
          </button>
        )}
      </form>

      {!identifier && (
        <Panel title="Search results" bodyClass="p-3">
          {!results ? (
            <Empty>Type a full or partial plate / person reference: Trace follows one exact identity, partial-match search lists everything that contains it.</Empty>
          ) : (
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <h4 className="panel-title mb-2">Detected entities</h4>
                {results.entities.map((e) => (
                  <Link key={e.identifier_normalized} to={`/trace/${e.identifier_normalized}`} className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-ink-800">
                    <Plate value={e.identifier} />
                    <span className="text-xs text-ink-400">
                      {e.detections} det. · {e.cameras} cams · {fmtShort(e.last_seen)}
                    </span>
                  </Link>
                ))}
                {!results.entities.length && <p className="text-xs text-ink-400">None</p>}
              </div>
              <div>
                <h4 className="panel-title mb-2">Watchlist</h4>
                {results.watchlist.map((w) => (
                  <Link key={w.id} to={`/trace/${w.identifier}`} className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-ink-800">
                    <Plate value={w.identifier} />
                    <span className="text-xs text-ink-400">{titleCase(w.category)}</span>
                  </Link>
                ))}
                {!results.watchlist.length && <p className="text-xs text-ink-400">None</p>}
              </div>
              <div>
                <h4 className="panel-title mb-2">Cameras</h4>
                {results.cameras.map((c) => (
                  <Link key={c.id} to={`/cameras?focus=${c.id}`} className="block rounded px-2 py-1.5 text-xs hover:bg-ink-800">
                    <span className="font-mono">{c.id}</span> {c.name}
                  </Link>
                ))}
                {!results.cameras.length && <p className="text-xs text-ink-400">None</p>}
              </div>
            </div>
          )}
        </Panel>
      )}

      {identifier && trace && (
        <div className="grid gap-3 xl:grid-cols-[420px_1fr]">
          <div className="space-y-3">
            <Panel bodyClass="p-3 space-y-3">
              <div className="flex items-center gap-3">
                <Plate value={trace.identifier} className="text-lg leading-7" />
                {trace.watchlist && <SeverityBadge severity={trace.watchlist.severity} />}
              </div>
              {trace.watchlist ? (
                <div className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs">
                  <div className="font-semibold text-red-300">
                    ON WATCHLIST · {titleCase(trace.watchlist.category)} {!trace.watchlist.is_active && "(inactive)"}
                  </div>
                  <div className="text-ink-200">{trace.watchlist.description}</div>
                  <div className="font-mono text-ink-400">{trace.watchlist.case_reference}</div>
                </div>
              ) : (
                <div className="text-xs text-ink-400">Not on the watchlist.</div>
              )}
              <div className="grid grid-cols-3 gap-2 text-center">
                <Stat label="Sightings" value={trace.total_detections} />
                <Stat label="Cameras" value={trace.distinct_cameras} />
                <Stat label="Distance" value={`${trace.total_distance_km} km`} />
              </div>
              <div className="text-xs text-ink-400">
                First {fmtDateTime(trace.first_seen)} · Last {fmtDateTime(trace.last_seen)}
              </div>
              {trace.anomalies.map((a) => (
                <div key={a} className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200">
                  <AlertTriangle size={14} className="shrink-0" /> {a}
                </div>
              ))}
            </Panel>
            <Panel title="Chronological history" bodyClass="p-3">
              {!trace.stops.length && <Empty>No detections for this entity.</Empty>}
              <ol className="relative space-y-4 border-l border-ink-600 pl-5">
                {trace.stops.map((s, i) => (
                  <li key={s.event_id} className="relative">
                    <span className="absolute top-0 -left-[31px] grid size-5 place-items-center rounded-full bg-accent font-mono text-[10px] font-bold text-ink-950">
                      {i + 1}
                    </span>
                    <div className="flex items-baseline gap-2">
                      <span className="font-mono text-sm font-semibold">{fmtTime(s.detected_at)}</span>
                      <span className="text-xs text-ink-400">{fmtShort(s.detected_at)}</span>
                    </div>
                    <div className="text-sm">
                      <span className="font-mono">{s.camera_id}</span> · {s.camera_name}
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-400">
                      {s.zone}
                      <Confidence value={s.confidence} />
                      {s.repeat_count > 0 && <span>{s.repeat_count + 1} reads</span>}
                    </div>
                    {s.minutes_since_previous !== null && (
                      <div className="mt-1 text-[11px] text-ink-300">
                        +{s.minutes_since_previous} min · {s.distance_km_from_previous} km
                        {s.implied_speed_kmh !== null && ` · ~${Math.round(s.implied_speed_kmh)} km/h`}
                      </div>
                    )}
                  </li>
                ))}
              </ol>
            </Panel>
          </div>
          <Panel title="Route reconstruction" className="h-[640px]">
            <CameraMap cameras={cams?.items ?? []} route={trace.stops} />
          </Panel>
        </div>
      )}
      {identifier && !trace && isFetching && <Empty>Loading trace…</Empty>}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md bg-ink-800 p-2">
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      <div className="text-[10px] tracking-wide text-ink-400 uppercase">{label}</div>
    </div>
  );
}
