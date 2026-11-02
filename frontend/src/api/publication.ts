import { config, type RangeDays, VALID_DAYS } from "../config";

export interface PublishedJobStatus {
  kind: "data";
  mode: string;
  status: string;
  startedAt: string;
  finishedAt?: string | null;
  reason?: string | null;
}

export interface PublicationPointer {
  version: string;
  generatedAt: string;
  snapshotKeys: Record<`${RangeDays}`, string>;
  lastJob: { status: string };
}

export interface PublicationManifest extends PublicationPointer {
  schemaVersion: 1;
  previousPublication?: PublicationPointer | null;
}

export interface PublicationState {
  manifest: PublicationManifest;
  status: PublishedJobStatus | null;
}

const VERSION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]*$/;

export function isPublicationManifest(
  value: unknown,
): value is PublicationManifest {
  if (!isRecord(value) || value.schemaVersion !== 1 || !isPointer(value)) {
    return false;
  }
  return (
    value.previousPublication === undefined ||
    value.previousPublication === null ||
    isPointer(value.previousPublication)
  );
}

export function manifestPath(
  now = Date.now(),
  baseUrl = import.meta.env.BASE_URL,
): string {
  const bucket = Math.floor(now / config.manifestCacheMs);
  return `${dataRoot(baseUrl)}manifest.json?v=${bucket}`;
}

export function statusPath(
  now = Date.now(),
  baseUrl = import.meta.env.BASE_URL,
): string {
  const bucket = Math.floor(now / config.manifestCacheMs);
  return `${dataRoot(baseUrl)}status.json?v=${bucket}`;
}

export function snapshotPath(
  version: string,
  days: RangeDays,
  baseUrl = import.meta.env.BASE_URL,
): string {
  if (!VERSION_PATTERN.test(version)) {
    throw new Error("Invalid publication version");
  }
  return `${dataRoot(baseUrl)}versions/${version}/snapshot-${days}.json`;
}

export async function fetchPublication(
  now = Date.now(),
  signal?: AbortSignal,
): Promise<PublicationState> {
  const manifestResponse = await fetch(manifestPath(now), {
    cache: "no-store",
    signal,
  });
  if (!manifestResponse.ok) {
    throw new Error("Publication manifest is unavailable");
  }
  const manifestValue: unknown = await manifestResponse.json();
  if (!isPublicationManifest(manifestValue)) {
    throw new Error("Publication manifest is invalid");
  }

  let status: PublishedJobStatus | null = null;
  try {
    const statusResponse = await fetch(statusPath(now), {
      cache: "no-store",
      signal,
    });
    if (statusResponse.ok) {
      const statusValue: unknown = await statusResponse.json();
      status = isPublishedJobStatus(statusValue) ? statusValue : null;
    }
  } catch (error) {
    if (signal?.aborted) throw error;
  }
  return { manifest: manifestValue, status };
}

function isPointer(value: unknown): value is PublicationPointer {
  const snapshotKeys = isRecord(value) ? value.snapshotKeys : null;
  if (
    !isRecord(value) ||
    typeof value.version !== "string" ||
    !VERSION_PATTERN.test(value.version) ||
    typeof value.generatedAt !== "string" ||
    Number.isNaN(Date.parse(value.generatedAt)) ||
    !isRecord(snapshotKeys) ||
    !isRecord(value.lastJob) ||
    typeof value.lastJob.status !== "string"
  ) {
    return false;
  }
  return VALID_DAYS.every(
    (days) =>
      snapshotKeys[String(days)] ===
      `snapshot:v1:${value.version}:${days}`,
  );
}

function isPublishedJobStatus(value: unknown): value is PublishedJobStatus {
  return (
    isRecord(value) &&
    value.kind === "data" &&
    typeof value.mode === "string" &&
    typeof value.status === "string" &&
    typeof value.startedAt === "string"
  );
}

function dataRoot(baseUrl: string): string {
  const normalized = baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
  return `${normalized}data/`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
