import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// In development the API runs on :8000 (make dev-backend or docker compose). Video is served by
// the gateway behind Caddy, so use the full stack (https://localhost:8443) to see live feeds.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", ws: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks: {
          map: ["leaflet", "react-leaflet"],
          charts: ["recharts"],
          video: ["hls.js"],
        },
      },
    },
  },
});
