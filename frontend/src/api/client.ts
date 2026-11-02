import type { RangeDays } from "../config";
import type { SnapshotResponse } from "../types/gdb";
import {
  fetchPublication,
  snapshotPath,
  type PublicationPointer,
  type PublishedJobStatus,
} from "./publication";

type PublicationMetaKey =
  | "generatedAt"
  | "freshnessStatus"
  | "lastJobStatus";
type StoredSnapshotResponse = Omit<SnapshotResponse, "meta"> & {
  meta: Omit<SnapshotResponse["meta"], PublicationMetaKey>;
};

const snapshotCache = new Map<string, StoredSnapshotResponse>();
const latestRangeCache = new Map<RangeDays, SnapshotResponse>();

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

/**
 * Minimal structural validation of a snapshot payload before it enters cache.
 */
export function isSnapshotResponse(
  value: unknown,
): value is StoredSnapshotResponse {
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
  return typeof meta.requestedDays === "number" &&
    typeof meta.snapshotVersion === "number";
}

export async function fetchSnapshot(
  days: RangeDays,
  signal?: AbortSignal,
): Promise<SnapshotResponse> {
  let publication;
  try {
    publication = await fetchPublication(Date.now(), signal);
  } catch {
    const retained = latestRangeCache.get(days);
    if (retained) return retained;
    throw new ApiError("Dữ liệu xuất bản tạm thời chưa sẵn sàng", 503);
  }

  const pointers: PublicationPointer[] = [publication.manifest];
  if (publication.manifest.previousPublication) {
    pointers.push(publication.manifest.previousPublication);
  }
  for (const pointer of pointers) {
    const snapshot = await loadVersion(pointer, days, signal);
    if (!snapshot) continue;
    const shaped = withLatestJobStatus(snapshot, pointer, publication.status);
    latestRangeCache.set(days, shaped);
    return shaped;
  }
  throw new ApiError("Dữ liệu snapshot không hợp lệ", 500);
}

async function loadVersion(
  pointer: PublicationPointer,
  days: RangeDays,
  signal?: AbortSignal,
): Promise<StoredSnapshotResponse | null> {
  const cacheKey = `${pointer.version}:${days}`;
  const cached = snapshotCache.get(cacheKey);
  if (cached) return cached;
  try {
    const response = await fetch(snapshotPath(pointer.version, days), {
      cache: "force-cache",
      signal,
    });
    if (!response.ok) return null;
    const value: unknown = await response.json();
    if (!isSnapshotResponse(value) || value.meta.requestedDays !== days) {
      return null;
    }
    snapshotCache.set(cacheKey, value);
    return value;
  } catch {
    return null;
  }
}

function withLatestJobStatus(
  snapshot: StoredSnapshotResponse,
  pointer: PublicationPointer,
  status: PublishedJobStatus | null,
): SnapshotResponse {
  const lastJobStatus = status?.status ?? pointer.lastJob.status;
  const freshnessStatus =
    lastJobStatus === "running"
      ? "updating"
      : lastJobStatus === "failed"
        ? "delayed"
        : "current";
  return {
    ...snapshot,
    meta: {
      ...snapshot.meta,
      generatedAt: pointer.generatedAt,
      lastJobStatus,
      freshnessStatus,
    },
  };
}

export function snapshotQueryKey(days: RangeDays): readonly ["gdb", RangeDays] {
  return ["gdb", days] as const;
}
