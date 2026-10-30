import { config, type RangeDays } from "../config";
import type {
  AcceptedOperation,
  OperationRecord,
  SnapshotResponse,
} from "../types/gdb";

export type CloudOperation = "refresh" | "telegram";

const snapshotCache = new Map<
  RangeDays,
  { etag: string | null; snapshot: SnapshotResponse }
>();

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

/**
 * Minimal structural validation of a snapshot payload before it enters cache.
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
    typeof meta.snapshotVersion === "number" &&
    typeof meta.generatedAt === "string" &&
    !Number.isNaN(Date.parse(meta.generatedAt)) &&
    ["current", "updating", "delayed", "stale"].includes(
      String(meta.freshnessStatus),
    ) &&
    typeof meta.lastJobStatus === "string"
  );
}

export async function fetchSnapshot(
  days: RangeDays,
  signal?: AbortSignal,
): Promise<SnapshotResponse> {
  const cached = snapshotCache.get(days);
  const headers: Record<string, string> = {};
  if (cached?.etag) headers["If-None-Match"] = cached.etag;
  const res = await fetch(snapshotUrl(days), { signal, headers });
  if (res.status === 304) {
    if (cached) return cached.snapshot;
    throw new ApiError("Bộ nhớ đệm snapshot không còn hợp lệ", 502);
  }
  if (!res.ok) {
    throw safeApiError(res.status, res.headers);
  }
  const json: unknown = await res.json();
  if (!isSnapshotResponse(json) || json.meta.requestedDays !== days) {
    throw new ApiError("Dữ liệu snapshot không hợp lệ", 500);
  }
  snapshotCache.set(days, { etag: res.headers.get("ETag"), snapshot: json });
  return json;
}

export async function startOperation(
  kind: CloudOperation,
  adminToken: string,
): Promise<AcceptedOperation> {
  const token = adminToken.trim();
  if (!token) throw new ApiError("Cần nhập khóa quản trị", 401);
  const path =
    kind === "refresh" ? "/api/gdb/refresh" : "/api/notifications/send-now";
  const response = await fetch(`${config.apiBaseUrl}${path}`, {
    method: "POST",
    headers: { "X-Notification-Token": token },
  });
  if (response.status !== 202) {
    throw safeApiError(response.status, response.headers);
  }
  const value: unknown = await response.json();
  if (!isAcceptedOperation(value)) {
    throw new ApiError("Phản hồi tác vụ cloud không hợp lệ", 502);
  }
  return value;
}

export async function fetchOperation(
  requestId: string,
  adminToken: string,
): Promise<OperationRecord> {
  const response = await fetch(
    `${config.apiBaseUrl}/api/operations/${encodeURIComponent(requestId)}`,
    { headers: { "X-Notification-Token": adminToken.trim() } },
  );
  if (!response.ok) throw safeApiError(response.status, response.headers);
  const value: unknown = await response.json();
  if (!isOperationRecord(value) || value.requestId !== requestId) {
    throw new ApiError("Trạng thái tác vụ cloud không hợp lệ", 502);
  }
  return value;
}

function isAcceptedOperation(value: unknown): value is AcceptedOperation {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.requestId === "string" &&
    record.status === "queued" &&
    typeof record.statusUrl === "string"
  );
}

function isOperationRecord(value: unknown): value is OperationRecord {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.requestId === "string" &&
    ["data_refresh", "telegram_send"].includes(String(record.kind)) &&
    ["queued", "running", "succeeded", "failed"].includes(
      String(record.status),
    ) &&
    typeof record.createdAt === "string" &&
    typeof record.updatedAt === "string" &&
    typeof record.message === "string"
  );
}

function safeApiError(status: number, headers: Headers): ApiError {
  const retryHeader = headers.get("Retry-After");
  const retryAfter = retryHeader ? Number(retryHeader) : undefined;
  const messages: Record<number, string> = {
    401: "Khóa quản trị không hợp lệ",
    403: "Origin không được phép thực hiện thao tác này",
    429: "Một thao tác cùng loại đang được xử lý",
    502: "Không thể tạo tác vụ cloud",
    503: "Dữ liệu cloud tạm thời chưa sẵn sàng",
  };
  return new ApiError(messages[status] ?? "Yêu cầu cloud thất bại", status, retryAfter);
}

export function snapshotQueryKey(days: RangeDays): readonly ["gdb", RangeDays] {
  return ["gdb", days] as const;
}
