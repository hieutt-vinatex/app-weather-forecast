/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ACTIVE_POLL_MS?: string;
  readonly VITE_IDLE_POLL_MS?: string;
  readonly VITE_MANIFEST_CACHE_MS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
