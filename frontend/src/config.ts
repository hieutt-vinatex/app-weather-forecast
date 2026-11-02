/**
 * Centralized runtime configuration read from Vite env vars.
 * Only public polling intervals belong in the browser bundle.
 */

function num(value: string | undefined, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

export const config = {
  activePollMs: num(import.meta.env.VITE_ACTIVE_POLL_MS, 30000),
  idlePollMs: num(import.meta.env.VITE_IDLE_POLL_MS, 300000),
  manifestCacheMs: num(import.meta.env.VITE_MANIFEST_CACHE_MS, 30000),
} as const;

export type RangeDays = 30 | 60 | 90;
export const VALID_DAYS: readonly RangeDays[] = [30, 60, 90] as const;

export function isValidDays(value: number): value is RangeDays {
  return VALID_DAYS.includes(value as RangeDays);
}
