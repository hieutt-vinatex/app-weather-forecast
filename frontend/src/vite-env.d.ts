/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_ACTIVE_POLL_MS?: string;
  readonly VITE_IDLE_POLL_MS?: string;
  readonly VITE_OPERATION_POLL_MS?: string;
  readonly VITE_OPERATION_TIMEOUT_MS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
