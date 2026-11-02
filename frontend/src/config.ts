/**
 * Centralized runtime configuration read from Vite env vars.
 * No API URL is ever hardcoded elsewhere in the app.
 */

function num(value: string | undefined, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

export const config = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(
    /\/$/,
    "",
  ),
  activePollMs: num(import.meta.env.VITE_ACTIVE_POLL_MS, 30000),
  idlePollMs: num(import.meta.env.VITE_IDLE_POLL_MS, 300000),
  operationPollMs: num(import.meta.env.VITE_OPERATION_POLL_MS, 2000),
  operationTimeoutMs: num(import.meta.env.VITE_OPERATION_TIMEOUT_MS, 900000),
  manifestCacheMs: num(import.meta.env.VITE_MANIFEST_CACHE_MS, 30000),
} as const;

export type RangeDays = 30 | 60 | 90;
export const VALID_DAYS: readonly RangeDays[] = [30, 60, 90] as const;

export function isValidDays(value: number): value is RangeDays {
  return VALID_DAYS.includes(value as RangeDays);
}
