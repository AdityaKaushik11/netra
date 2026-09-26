/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend WebSocket URL when the console is hosted separately (e.g. wss://api.example/api/v1/ws) */
  readonly VITE_WS_URL?: string;
}
