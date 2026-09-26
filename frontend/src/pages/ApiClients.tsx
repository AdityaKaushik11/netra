import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { api } from "../api/client";
import { Field, Modal, PageHeader, Panel } from "../components/ui";
import { ago, fmtDateTime } from "../lib/format";

interface ApiClient {
  id: number;
  name: string;
  key_prefix: string;
  scopes: string[];
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
}

const SCOPES = ["events:write", "cameras:heartbeat", "cameras:write"];

export function ApiClientsPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["events:write", "cameras:heartbeat"]);
  const [issued, setIssued] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["api-clients"], queryFn: () => api<ApiClient[]>("/api-clients") });
  const create = useMutation({
    mutationFn: () => api<ApiClient & { api_key: string }>("/api-clients", { method: "POST", json: { name, scopes } }),
    onSuccess: (c) => {
      setIssued(c.api_key);
      setName("");
      qc.invalidateQueries({ queryKey: ["api-clients"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const revoke = useMutation({
    mutationFn: (id: number) => api(`/api-clients/${id}/revoke`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-clients"] }),
  });
  return (
    <div>
      <PageHeader title="API clients" subtitle="Machine identities for AI inference engines, edge gateways and partner VMS (X-API-Key)" />
      <div className="grid gap-3 lg:grid-cols-[1fr_340px]">
        <Panel title="Issued keys" bodyClass="overflow-x-auto">
          <table className="data">
            <thead>
              <tr>
                <th>Name</th>
                <th>Key prefix</th>
                <th>Scopes</th>
                <th>Created</th>
                <th>Last used</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data?.map((c) => (
                <tr key={c.id} className={c.is_active ? "" : "opacity-50"}>
                  <td className="font-medium">{c.name}</td>
                  <td className="font-mono text-xs">{c.key_prefix}…</td>
                  <td className="font-mono text-[11px]">{c.scopes.join(", ")}</td>
                  <td className="text-xs">{fmtDateTime(c.created_at)}</td>
                  <td className="text-xs">{ago(c.last_used_at)}</td>
                  <td>
                    {c.is_active ? (
                      <button className="btn btn-danger py-0.5 text-xs" onClick={() => revoke.mutate(c.id)}>
                        Revoke
                      </button>
                    ) : (
                      <span className="text-xs text-ink-400">revoked</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title="Issue new key" bodyClass="p-3 space-y-3">
          <Field label="Client name">
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="edge-gateway-ahm-west" />
          </Field>
          <div className="space-y-1">
            <span className="text-xs text-ink-300">Scopes</span>
            {SCOPES.map((s) => (
              <label key={s} className="flex items-center gap-2 font-mono text-xs">
                <input
                  type="checkbox"
                  checked={scopes.includes(s)}
                  onChange={(e) => setScopes(e.target.checked ? [...scopes, s] : scopes.filter((x) => x !== s))}
                />
                {s}
              </label>
            ))}
          </div>
          <button className="btn btn-primary" disabled={name.length < 3 || create.isPending} onClick={() => create.mutate()}>
            <KeyRound size={14} /> Issue key
          </button>
        </Panel>
      </div>
      {issued && (
        <Modal title="API key issued" onClose={() => setIssued(null)}>
          <p className="mb-2 text-xs text-amber-300">Copy it now — only a keyed hash is stored, it cannot be shown again.</p>
          <div className="flex gap-2">
            <code className="input font-mono text-xs break-all">{issued}</code>
            <button
              className="btn"
              onClick={() => {
                navigator.clipboard.writeText(issued).then(() => toast.success("Copied"));
              }}
            >
              <Copy size={14} />
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
