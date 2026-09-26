import { ShieldAlert, X } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import type { Alert } from "../api/types";
import { fmtTime, pct, titleCase } from "../lib/format";
import { Plate, SEVERITY_COLOR } from "./Badges";

export function AlertToast({ alert, toastId }: { alert: Alert; toastId: string | number }) {
  const color = SEVERITY_COLOR[alert.severity];
  return (
    <div
      className="w-[380px] overflow-hidden rounded-lg border bg-ink-850 text-ink-100 shadow-2xl"
      style={{ borderColor: color, boxShadow: `0 0 0 1px ${color}, 0 12px 40px rgba(0,0,0,.6)` }}
    >
      <div className="flex items-center gap-2 px-3 py-2 text-xs font-bold tracking-wider" style={{ background: color, color: "#0a0e13" }}>
        <ShieldAlert size={15} />
        {alert.severity} · WATCHLIST {alert.match_type === "FUZZY" ? "POSSIBLE " : ""}MATCH
        <button className="ml-auto opacity-70 hover:opacity-100" onClick={() => toast.dismiss(toastId)} aria-label="Dismiss">
          <X size={14} />
        </button>
      </div>
      <div className="space-y-2 p-3 text-sm">
        <div className="flex items-center gap-2">
          <Plate value={alert.identifier} className="text-sm" />
          <span className="text-ink-300">{titleCase(alert.category)}</span>
        </div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
          <span className="text-ink-400">Camera</span>
          <span>
            {alert.camera_id} · {alert.camera_name}
          </span>
          <span className="text-ink-400">Time</span>
          <span className="font-mono">{fmtTime(alert.triggered_at)}</span>
          <span className="text-ink-400">Confidence</span>
          <span className="font-mono">{pct(alert.confidence)}</span>
          {alert.case_reference && (
            <>
              <span className="text-ink-400">Case</span>
              <span className="font-mono">{alert.case_reference}</span>
            </>
          )}
        </div>
        <div className="flex gap-2 pt-1">
          <Link to={`/alerts?focus=${alert.id}`} className="btn btn-primary py-1 text-xs" onClick={() => toast.dismiss(toastId)}>
            Open alert
          </Link>
          <Link to={`/trace/${alert.identifier}`} className="btn py-1 text-xs" onClick={() => toast.dismiss(toastId)}>
            Trace movement
          </Link>
        </div>
      </div>
    </div>
  );
}
