import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Bell,
  BellOff,
  Camera,
  FileClock,
  KeyRound,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Radar,
  Route,
  ScanLine,
  Search,
  ShieldAlert,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Overview } from "../api/types";
import { useAuth } from "../hooks/auth";
import { useRealtime } from "../hooks/realtime";

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(t);
  }, []);
  return (
    <span className="font-mono text-xs text-ink-300">
      {now.toLocaleDateString("en-IN", { day: "2-digit", month: "short" })} {now.toLocaleTimeString("en-IN", { hour12: false })} IST
    </span>
  );
}

export function Layout() {
  const { user, logout, can } = useAuth();
  const { connected, muted, setMuted, messagesPerMin } = useRealtime();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const { data: overview } = useQuery({
    queryKey: ["overview"],
    queryFn: () => api<Overview>("/stats/overview"),
    refetchInterval: 30_000,
  });

  const nav = [
    { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
    { to: "/wall", label: "Live Wall", icon: ScanLine },
    { to: "/cameras", label: "Cameras", icon: Camera },
    { to: "/alerts", label: "Alerts", icon: ShieldAlert, badge: overview?.alerts.new },
    { to: "/events", label: "Detections", icon: Radar },
    { to: "/trace", label: "Trace", icon: Route },
    { to: "/watchlist", label: "Watchlist", icon: ListChecks },
    ...(can("ADMIN")
      ? [
          { to: "/audit", label: "Audit Log", icon: FileClock },
          { to: "/api-clients", label: "API Clients", icon: KeyRound },
        ]
      : []),
  ];

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const v = q.trim().toUpperCase().replace(/[^A-Z0-9-]/g, "");
    if (v.length >= 3) navigate(`/trace/${v}`);
  };

  return (
    <div className="flex h-full">
      <aside className="flex w-16 shrink-0 flex-col border-r border-ink-700 bg-ink-950 lg:w-56">
        <div className="flex items-center gap-2.5 px-4 py-4">
          <svg viewBox="0 0 32 32" className="size-8 shrink-0">
            <path d="M4 16c3.5-6 7.5-9 12-9s8.5 3 12 9c-3.5 6-7.5 9-12 9S7.5 22 4 16z" fill="none" stroke="#22d3ee" strokeWidth="2.2" />
            <circle cx="16" cy="16" r="4.2" fill="#22d3ee" />
          </svg>
          <div className="hidden lg:block">
            <div className="text-sm font-bold tracking-wide">NETRA</div>
            <div className="text-[10px] text-ink-400">CCTV Intelligence Console</div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 px-2">
          {nav.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive ? "bg-ink-800 text-accent" : "text-ink-300 hover:bg-ink-850 hover:text-ink-100",
                )
              }
            >
              <n.icon size={17} className="shrink-0" />
              <span className="hidden lg:inline">{n.label}</span>
              {!!n.badge && (
                <span className="ml-auto hidden rounded-full bg-red-600 px-1.5 text-[10px] font-bold text-white lg:inline">{n.badge}</span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-ink-700 p-3 text-xs">
          <div className="hidden lg:block">
            <div className="font-medium">{user?.full_name}</div>
            <div className="text-ink-400">
              {user?.username} · {user?.role}
            </div>
          </div>
          <button className="mt-2 flex items-center gap-2 text-ink-400 hover:text-ink-100" onClick={logout}>
            <LogOut size={14} /> <span className="hidden lg:inline">Sign out</span>
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-ink-700 bg-ink-950/60 px-4">
          <form onSubmit={submit} className="relative w-full max-w-sm">
            <Search size={14} className="absolute top-1/2 left-2.5 -translate-y-1/2 text-ink-400" />
            <input
              className="input pl-8 font-mono uppercase placeholder:font-sans placeholder:normal-case"
              placeholder="Search vehicle / entity (e.g. GJ01XX0001) and trace…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </form>
          <div className="ml-auto flex items-center gap-4">
            <span
              className={clsx("flex items-center gap-1.5 text-xs", connected ? "text-emerald-400" : "text-red-400")}
              title="Real-time WebSocket channel"
            >
              <span className={clsx("size-2 rounded-full", connected ? "animate-pulse bg-emerald-400" : "bg-red-500")} />
              {connected ? `LIVE · ${messagesPerMin} msg/min` : "RECONNECTING"}
            </span>
            <button
              className="text-ink-400 hover:text-ink-100"
              onClick={() => setMuted(!muted)}
              title={muted ? "Unmute alert sound" : "Mute alert sound"}
            >
              {muted ? <BellOff size={16} /> : <Bell size={16} />}
            </button>
            <Clock />
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-auto p-4">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
