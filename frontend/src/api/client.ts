import { config, type RangeDays } from "../config";
import type {
  RefreshResponse,
  SendNotificationNowResponse,
  SnapshotResponse,
} from "../types/gdb";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function snapshotUrl(days: RangeDays): string {
  return `${config.apiBaseUrl}/api/gdb?days=${days}`;
}

export function streamUrl(days: RangeDays): string {
  return `${config.apiBaseUrl}/api/gdb/stream?days=${days}`;
}

/**
 * Minimal structural validation of a snapshot payload. We do NOT trust raw
 * SSE / REST data blindly before pushing it into the query cache.
 */
export function isSnapshotResponse(value: unknown): value is SnapshotResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  if (!Array.isArray(v.data)) return false;
  if (typeof v.statistics !== "object" || v.statistics === null) return false;
  if (typeof v.statisticsByPrize !== "object" || v.statisticsByPrize === null) return false;
  if (typeof v.meta !== "object" || v.meta === null) return false;
  if (
    v.data.some(
      (record) =>
        typeof record !== "object" ||
        record === null ||
        typeof (record as Record<string, unknown>).prizes !== "object",
    )
  ) {
    return false;
  }
  const meta = v.meta as Record<string, unknown>;
  return (
    typeof meta.requestedDays === "number" &&
    typeof meta.snapshotVersion === "number"
  );
}

export async function fetchSnapshot(
  days: RangeDays,
  signal?: AbortSignal,
): Promise<SnapshotResponse> {
  const res = await fetch(snapshotUrl(days), { signal });
  if (!res.ok) {
    throw new ApiError(`Snapshot request failed`, res.status);
  }
  const json: unknown = await res.json();
  if (!isSnapshotResponse(json)) {
    throw new ApiError("Dữ liệu snapshot không hợp lệ", 500);
  }
  return json;
}

export async function triggerRefresh(): Promise<RefreshResponse> {
  const res = await fetch(`${config.apiBaseUrl}/api/gdb/refresh`, {
    method: "POST",
  });
  if (res.status === 429) {
    const retryAfterHeader = res.headers.get("Retry-After");
    const retryAfter = retryAfterHeader ? Number(retryAfterHeader) : undefined;
    throw new ApiError("Đang trong thời gian chờ làm mới", 429, retryAfter);
  }
  if (!res.ok) {
    throw new ApiError("Làm mới thất bại", res.status);
  }
  return (await res.json()) as RefreshResponse;
}

export async function sendAbsenceNotificationNow(
  adminToken: string,
): Promise<SendNotificationNowResponse> {
  const res = await fetch(`${config.apiBaseUrl}/api/notifications/send-now`, {
    method: "POST",
    headers: {
      "X-Notification-Token": adminToken,
    },
  });
  if (res.status === 401) {
    throw new ApiError("Khóa quản trị không hợp lệ", 401);
  }
  if (res.status === 404) {
    throw new ApiError("API gửi thông báo chưa được bật", 404);
  }
  if (!res.ok) {
    throw new ApiError("Gửi thông báo thất bại", res.status);
  }
  return (await res.json()) as SendNotificationNowResponse;
}

export function snapshotQueryKey(days: RangeDays): readonly ["gdb", RangeDays] {
  return ["gdb", days] as const;
}
