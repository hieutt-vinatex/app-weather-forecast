import type { FreshnessStatus } from "./contracts";

export interface FreshnessInput {
  now: Date;
  generatedAt: string;
  lastJobStatus?: string;
}

const ACTIVE_START_MINUTES = 17 * 60 + 45;
const ACTIVE_END_MINUTES = 19 * 60;
const ACTIVE_CURRENT_MINUTES = 10;
const ACTIVE_STALE_MINUTES = 20;
const IDLE_CURRENT_MINUTES = 26 * 60;
const IDLE_STALE_MINUTES = 48 * 60;

const vietnamTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Ho_Chi_Minh",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export function classifyFreshness(input: FreshnessInput): FreshnessStatus {
  const generatedAt = new Date(input.generatedAt);
  if (Number.isNaN(generatedAt.getTime()) || Number.isNaN(input.now.getTime())) {
    return "stale";
  }
  const ageMinutes = Math.max(
    0,
    (input.now.getTime() - generatedAt.getTime()) / 60_000,
  );
  const active = isActiveWindow(input.now);
  const currentLimit = active
    ? ACTIVE_CURRENT_MINUTES
    : IDLE_CURRENT_MINUTES;
  const staleLimit = active ? ACTIVE_STALE_MINUTES : IDLE_STALE_MINUTES;

  if (ageMinutes > staleLimit) return "stale";
  if (input.lastJobStatus === "running") return "updating";
  if (input.lastJobStatus === "failed") return "delayed";
  if (ageMinutes > currentLimit) return "delayed";
  return "current";
}

export function isActiveWindow(now: Date): boolean {
  const parts = vietnamTime.formatToParts(now);
  const hour = Number(parts.find((part) => part.type === "hour")?.value);
  const minute = Number(parts.find((part) => part.type === "minute")?.value);
  if (!Number.isInteger(hour) || !Number.isInteger(minute)) return false;
  const localMinutes = hour * 60 + minute;
  return (
    localMinutes >= ACTIVE_START_MINUTES && localMinutes <= ACTIVE_END_MINUTES
  );
}
