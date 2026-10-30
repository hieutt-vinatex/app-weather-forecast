/** Pure formatting helpers (unit-tested). */

export function formatPercent(value: number, digits = 1): string {
  if (!Number.isFinite(value)) return "0%";
  return `${value.toFixed(digits)}%`;
}

/** ISO `YYYY-MM-DD` -> `DD/MM/YYYY`. Returns input unchanged if malformed. */
export function formatIsoDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  return `${m[3]}/${m[2]}/${m[1]}`;
}

/** ISO datetime with offset -> `HH:MM:SS`. */
export function formatClock(iso: string | null): string {
  if (!iso) return "--:--:--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--:--:--";
  return d.toLocaleTimeString("vi-VN", { hour12: false });
}

/** ISO datetime -> Vietnam-local `HH:MM DD/MM/YYYY`. */
export function formatVietnamDateTime(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

/** Relative "x giây trước" style label from an ISO timestamp. */
export function formatRelative(iso: string | null, now = Date.now()): string {
  if (!iso) return "chưa có";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "chưa có";
  const diff = Math.max(0, Math.round((now - then) / 1000));
  if (diff < 5) return "vừa xong";
  if (diff < 60) return `${diff} giây trước`;
  const mins = Math.floor(diff / 60);
  if (mins < 60) return `${mins} phút trước`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} giờ trước`;
  return `${Math.floor(hours / 24)} ngày trước`;
}

export function classNames(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
