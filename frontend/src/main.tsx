import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Layout } from "./components/Layout";
import { AuthProvider, useAuth } from "./hooks/auth";
import { RealtimeProvider } from "./hooks/realtime";
// Fonts are bundled (no third-party font requests leak operator IPs)
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/700.css";
import "./index.css";
import { AlertsPage } from "./pages/Alerts";
import { ApiClientsPage } from "./pages/ApiClients";
import { AuditPage } from "./pages/Audit";
import { CamerasPage } from "./pages/Cameras";
import { DashboardPage } from "./pages/Dashboard";
import { EventsPage } from "./pages/Events";
import { LiveWallPage } from "./pages/LiveWall";
import { LoginPage } from "./pages/Login";
import { TracePage } from "./pages/Trace";
import { WatchlistPage } from "./pages/Watchlist";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, retry: 1, refetchOnWindowFocus: false } },
});

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="grid h-full place-items-center text-sm text-ink-400">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <RealtimeProvider>{children}</RealtimeProvider>;
}

function AdminOnly({ children }: { children: ReactNode }) {
  const { can } = useAuth();
  return can("ADMIN") ? <>{children}</> : <Navigate to="/" replace />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              element={
                <Protected>
                  <Layout />
                </Protected>
              }
            >
              <Route index element={<DashboardPage />} />
              <Route path="wall" element={<LiveWallPage />} />
              <Route path="cameras" element={<CamerasPage />} />
              <Route path="alerts" element={<AlertsPage />} />
              <Route path="events" element={<EventsPage />} />
              <Route path="trace" element={<TracePage />} />
              <Route path="trace/:identifier" element={<TracePage />} />
              <Route path="watchlist" element={<WatchlistPage />} />
              <Route path="audit" element={<AdminOnly><AuditPage /></AdminOnly>} />
              <Route path="api-clients" element={<AdminOnly><ApiClientsPage /></AdminOnly>} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          {/* Inside the router: alert toasts render <Link>s */}
          <Toaster theme="dark" position="top-right" richColors closeButton visibleToasts={6} />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
);
