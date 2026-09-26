import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Route, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, qs } from "../api/client";
import type { Page, Severity, WatchlistCategory, WatchlistEntry } from "../api/types";
import { Plate, SeverityBadge } from "../components/Badges";
import { Empty, Field, Modal, PageHeader, Pager, Panel } from "../components/ui";
import { useAuth } from "../hooks/auth";
import { ago, titleCase } from "../lib/format";

const CATEGORIES: WatchlistCategory[] = ["STOLEN_VEHICLE", "BLACKLISTED_VEHICLE", "WANTED_PERSON", "MISSING_PERSON", "SUSPICIOUS"];

export function WatchlistPage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [f, setF] = useState({ q: "", category: "", active: "true" });
  const [offset, setOffset] = useState(0);
  const [adding, setAdding] = useState(false);
  const limit = 50;
  const { data } = useQuery({
    queryKey: ["watchlist", f, offset],
    queryFn: () => api<Page<WatchlistEntry>>(`/watchlist${qs({ ...f, limit, offset })}`),
  });
  const deactivate = useMutation({
    mutationFn: (id: number) => api(`/watchlist/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Entry deactivated");
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => {
    setOffset(0);
    setF({ ...f, [k]: e.target.value });
  };

  return (
    <div>
      <PageHeader
        title="Watchlist"
        subtitle="Synthetic representative records · matched against every detection (exact + OCR-tolerant fuzzy)"
        actions={
          can("ADMIN", "OPERATOR") && (
            <button className="btn btn-primary" onClick={() => setAdding(true)}>
              <Plus size={14} /> Add entry
            </button>
          )
        }
      />
      <Panel
        title={`${data?.total ?? 0} entries`}
        actions={
          <div className="flex gap-2">
            <input className="input w-44 py-1" placeholder="Search…" value={f.q} onChange={set("q")} />
            <select className="input w-auto py-1" value={f.category} onChange={set("category")}>
              <option value="">All categories</option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {titleCase(c)}
                </option>
              ))}
            </select>
            <select className="input w-auto py-1" value={f.active} onChange={set("active")}>
              <option value="true">Active</option>
              <option value="false">Inactive</option>
              <option value="">All</option>
            </select>
          </div>
        }
        bodyClass="overflow-x-auto"
      >
        <table className="data">
          <thead>
            <tr>
              <th>Identifier</th>
              <th>Category</th>
              <th>Severity</th>
              <th>Description</th>
              <th>Case / agency</th>
              <th>Alerts</th>
              <th>Last seen</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data?.items.map((w) => (
              <tr key={w.id} className={w.is_active ? "" : "opacity-50"}>
                <td>
                  <Plate value={w.identifier} />
                  <div className="text-[10px] text-ink-400">{w.entity_type}</div>
                </td>
                <td className="text-xs">{titleCase(w.category)}</td>
                <td>
                  <SeverityBadge severity={w.severity} />
                </td>
                <td className="max-w-72 text-xs text-ink-300">{w.description}</td>
                <td className="text-xs">
                  <div className="font-mono">{w.case_reference}</div>
                  <div className="text-ink-400">{w.source_agency}</div>
                </td>
                <td className="font-mono text-xs">{w.hit_count}</td>
                <td className="text-xs whitespace-nowrap text-ink-300">{w.last_seen_at ? ago(w.last_seen_at) : "—"}</td>
                <td className="whitespace-nowrap">
                  <Link to={`/trace/${w.identifier}`} className="btn px-2 py-0.5" title="Trace">
                    <Route size={13} />
                  </Link>
                  {w.is_active && can("ADMIN", "OPERATOR") && (
                    <button className="btn btn-danger ml-1 px-2 py-0.5" title="Deactivate" onClick={() => deactivate.mutate(w.id)}>
                      <Trash2 size={13} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && !data.items.length && <Empty>No watchlist entries.</Empty>}
        {data && <Pager total={data.total} limit={limit} offset={offset} onChange={setOffset} />}
      </Panel>
      {adding && <AddEntry onClose={() => setAdding(false)} />}
    </div>
  );
}

function AddEntry({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({
    entity_type: "VEHICLE",
    identifier: "",
    category: "STOLEN_VEHICLE" as WatchlistCategory,
    severity: "HIGH" as Severity,
    description: "",
    case_reference: "",
    source_agency: "",
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const save = useMutation({
    mutationFn: () => api<WatchlistEntry>("/watchlist", { method: "POST", json: { ...f, case_reference: f.case_reference || null, source_agency: f.source_agency || null } }),
    onSuccess: (w) => {
      toast.success(`${w.identifier} added to watchlist`, { description: "Live matching is active immediately" });
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  return (
    <Modal title="Add watchlist entry" onClose={onClose}>
      <form onSubmit={submit} className="grid grid-cols-2 gap-3">
        <Field label="Entity type">
          <select className="input" value={f.entity_type} onChange={set("entity_type")}>
            <option value="VEHICLE">Vehicle (plate)</option>
            <option value="PERSON">Person (face-gallery ref)</option>
          </select>
        </Field>
        <Field label="Identifier">
          <input className="input font-mono uppercase" required minLength={3} value={f.identifier} onChange={set("identifier")} placeholder="GJ01XX0001" />
        </Field>
        <Field label="Category">
          <select className="input" value={f.category} onChange={set("category")}>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {titleCase(c)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Severity">
          <select className="input" value={f.severity} onChange={set("severity")}>
            {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </Field>
        <div className="col-span-2">
          <Field label="Description">
            <textarea className="input h-16" value={f.description} onChange={set("description")} />
          </Field>
        </div>
        <Field label="Case reference">
          <input className="input font-mono" value={f.case_reference} onChange={set("case_reference")} placeholder="FIR-…" />
        </Field>
        <Field label="Source agency">
          <input className="input" value={f.source_agency} onChange={set("source_agency")} />
        </Field>
        <div className="col-span-2 flex justify-end gap-2 border-t border-ink-700 pt-3">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={save.isPending}>
            Add to watchlist
          </button>
        </div>
      </form>
    </Modal>
  );
}
