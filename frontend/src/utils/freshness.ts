import { config } from "../config";
import type { FreshnessStatus } from "../types/gdb";

const FRESHNESS_LABELS: Record<FreshnessStatus, string> = {
  current: "Dữ liệu hiện tại",
  updating: "Đang cập nhật",
  delayed: "Chậm cập nhật",
  stale: "Dữ liệu đã cũ",
  offline: "Ngoại tuyến",
};

export interface PollingContext {
  localTime: string;
  visible: boolean;
  online: boolean;
  activePollMs?: number;
  idlePollMs?: number;
}

const ACTIVE_START = 17 * 60 + 45;
const ACTIVE_END = 19 * 60;

const vietnamClock = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Ho_Chi_Minh",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export function pollIntervalMs(input: PollingContext): number | false {
  if (!input.visible || !input.online) return false;
  const minutes = parseLocalTime(input.localTime);
  const active = minutes !== null && minutes >= ACTIVE_START && minutes <= ACTIVE_END;
  return active
    ? (input.activePollMs ?? config.activePollMs)
    : (input.idlePollMs ?? config.idlePollMs);
}

export function vietnamLocalTime(now = new Date()): string {
  return vietnamClock.format(now);
}

export function freshnessLabel(status: FreshnessStatus): string {
  return FRESHNESS_LABELS[status];
}

function parseLocalTime(value: string): number | null {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour > 23 || minute > 59) return null;
  return hour * 60 + minute;
}
