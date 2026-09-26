import clsx from "clsx";
import { AlertCircle, Eye, EyeOff, Loader2, Lock, MapPinned, ShieldAlert, User, Video } from "lucide-react";
import { useState, type FormEvent, type KeyboardEvent } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/auth";

const REMEMBER_KEY = "netra.username";

function readRemembered(): string {
  try {
    return localStorage.getItem(REMEMBER_KEY) ?? "";
  } catch {
    return "";
  }
}

function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <path d="M4 16c3.5-6 7.5-9 12-9s8.5 3 12 9c-3.5 6-7.5 9-12 9S7.5 22 4 16z" fill="none" stroke="#22d3ee" strokeWidth="2.2" />
      <circle cx="16" cy="16" r="4.2" fill="#22d3ee" />
    </svg>
  );
}

/** Decorative city grid with camera nodes and a sweeping radar, drawn in SVG (no assets). */
function CityRadar() {
  const nodes = [
    [120, 140, "#22c55e"],
    [260, 90, "#22c55e"],
    [330, 220, "#ef4444"],
    [180, 280, "#22c55e"],
    [400, 120, "#f59e0b"],
    [90, 330, "#22c55e"],
    [420, 320, "#22c55e"],
  ] as const;
  return (
    <svg viewBox="0 0 500 420" className="h-auto w-full max-w-lg" aria-hidden>
      <defs>
        <radialGradient id="sweep" cx="0" cy="0" r="1">
          <stop offset="0" stopColor="#22d3ee" stopOpacity="0.35" />
          <stop offset="1" stopColor="#22d3ee" stopOpacity="0" />
        </radialGradient>
      </defs>
      {Array.from({ length: 11 }, (_, i) => (
        <line key={`v${i}`} x1={i * 50} y1="0" x2={i * 50} y2="420" stroke="#1a2531" />
      ))}
      {Array.from({ length: 9 }, (_, i) => (
        <line key={`h${i}`} x1="0" y1={i * 50} x2="500" y2={i * 50} stroke="#1a2531" />
      ))}
      <path d="M20 360 C 140 300, 200 330, 260 250 S 420 150, 480 60" fill="none" stroke="#243242" strokeWidth="10" />
      <path d="M120 140 L260 90 L330 220" fill="none" stroke="#22d3ee" strokeWidth="2" strokeDasharray="6 6" opacity="0.7" />
      <circle cx="250" cy="210" r="170" fill="none" stroke="#243242" />
      <circle cx="250" cy="210" r="110" fill="none" stroke="#243242" />
      <g className="radar-sweep" style={{ transformOrigin: "250px 210px" }}>
        <path d="M250 210 L420 210 A170 170 0 0 0 370 90 Z" fill="url(#sweep)" />
      </g>
      {nodes.map(([x, y, c], i) => (
        <g key={i}>
          {c === "#ef4444" && <circle cx={x} cy={y} r="16" fill="none" stroke={c} strokeWidth="2" className="radar-ping" />}
          <circle cx={x} cy={y} r="6" fill={c} stroke="#0a0e13" strokeWidth="2" />
        </g>
      ))}
    </svg>
  );
}

export function LoginPage() {
  const { user, login } = useAuth();
  const remembered = readRemembered();
  const [username, setUsername] = useState(remembered);
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(!!remembered);
  const [showPwd, setShowPwd] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const name = username.trim().toLowerCase();
    if (name.includes("@") && name.includes(".")) {
      setError("Sign in with your account username (e.g. admin), not an email address.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(name, password);
      try {
        if (remember) localStorage.setItem(REMEMBER_KEY, name);
        else localStorage.removeItem(REMEMBER_KEY);
      } catch {
        /* storage unavailable */
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => setCapsLock(e.getModifierState?.("CapsLock") ?? false);

  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      {/* Product side */}
      <aside className="relative hidden overflow-hidden border-r border-ink-700 bg-ink-950 p-10 lg:flex lg:flex-col">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_20%_10%,rgba(34,211,238,0.12),transparent_55%)]" />
        <div className="relative flex items-center gap-3">
          <Logo className="size-10" />
          <div>
            <div className="text-lg font-bold tracking-[0.2em]">NETRA</div>
            <div className="text-xs text-ink-400">CCTV Intelligence Console</div>
          </div>
        </div>
        <div className="relative mt-12 max-w-lg">
          <h1 className="text-3xl leading-tight font-semibold tracking-tight">
            One screen for every camera, <span className="text-accent">every alert</span>, every movement.
          </h1>
          <p className="mt-3 text-sm text-ink-300">
            Unified monitoring of city CCTV, ONVIF devices, vendor NVRs and patrol-vehicle dashcams, with AI detections correlated against
            watchlists in real time.
          </p>
        </div>
        <div className="relative my-8 flex flex-1 items-center justify-center">
          <CityRadar />
        </div>
        <ul className="relative grid gap-3 text-sm sm:grid-cols-3">
          {[
            { icon: Video, t: "Live & recorded video", d: "RTSP, ONVIF, HLS, vendor APIs and dashcams" },
            { icon: ShieldAlert, t: "Instant watchlist alerts", d: "ANPR and face matches pushed in real time" },
            { icon: MapPinned, t: "Movement tracing", d: "Routes reconstructed across cameras on the map" },
          ].map(({ icon: Icon, t, d }) => (
            <li key={t} className="rounded-lg border border-ink-700 bg-ink-900/60 p-3">
              <Icon size={18} className="mb-1.5 text-accent" />
              <div className="font-medium">{t}</div>
              <div className="text-xs text-ink-400">{d}</div>
            </li>
          ))}
        </ul>
      </aside>

      {/* Sign-in side */}
      <main className="flex items-center justify-center bg-[radial-gradient(ellipse_at_top,#0f2230,transparent_60%)] p-6">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <Logo className="size-10" />
            <div className="text-lg font-bold tracking-[0.2em]">NETRA</div>
          </div>
          <h2 className="text-2xl font-semibold tracking-tight">Sign in</h2>
          <p className="mt-1 mb-6 text-sm text-ink-400">Use your control-room account to continue.</p>

          <form onSubmit={submit} className="space-y-4" noValidate>
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-ink-300">Username</span>
              <div className="relative">
                <User size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-ink-400" />
                <input
                  className="input py-2.5 pl-9"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  placeholder="admin, operator or viewer"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoFocus={!remembered}
                />
              </div>
            </label>

            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-ink-300">Password</span>
              <div className="relative">
                <Lock size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-ink-400" />
                <input
                  className="input py-2.5 pr-10 pl-9"
                  type={showPwd ? "text" : "password"}
                  autoComplete="current-password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyUp={onKey}
                  onKeyDown={onKey}
                  autoFocus={!!remembered}
                />
                <button
                  type="button"
                  className="absolute top-1/2 right-2.5 -translate-y-1/2 rounded p-1 text-ink-400 hover:text-ink-100"
                  onClick={() => setShowPwd((v) => !v)}
                  aria-label={showPwd ? "Hide password" : "Show password"}
                >
                  {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {capsLock && <span className="block text-[11px] text-amber-300">Caps Lock is on</span>}
            </label>

            <label className="flex items-center gap-2 text-xs text-ink-300">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              Remember my username on this device
            </label>

            {error && (
              <div role="alert" className="flex gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                <AlertCircle size={15} className="mt-px shrink-0" />
                {error}
              </div>
            )}

            <button
              className={clsx("btn btn-primary w-full justify-center py-2.5 text-sm", busy && "cursor-wait")}
              disabled={busy || !username.trim() || !password}
            >
              {busy ? (
                <>
                  <Loader2 size={16} className="animate-spin" /> Signing in…
                </>
              ) : (
                "Sign in"
              )}
            </button>
          </form>

          <div className="mt-6 rounded-md border border-ink-700 bg-ink-900/60 p-3 text-[11px] text-ink-400">
            <div className="mb-1 font-medium text-ink-300">Accounts</div>
            <span className="font-mono text-ink-200">admin</span> full access ·{" "}
            <span className="font-mono text-ink-200">operator</span> handles alerts ·{" "}
            <span className="font-mono text-ink-200">viewer</span> read-only
          </div>
          <p className="mt-4 flex items-center gap-1.5 text-[11px] text-ink-500">
            <Lock size={11} /> Encrypted connection · authorised personnel only · every action is audited
          </p>
        </div>
      </main>
    </div>
  );
}
