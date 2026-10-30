export type FreshnessStatus = "current" | "updating" | "delayed" | "stale";

export interface JobRecord {
  status: string;
  startedAt?: string;
  finishedAt?: string | null;
}

export interface PublicationManifest {
  schemaVersion: 1;
  version: string;
  generatedAt: string;
  historyKey: string;
  snapshotKeys: Record<string, string>;
  sourceReferenceDate: string | null;
  complete: boolean;
  lastJob: JobRecord;
}

export interface SnapshotMeta {
  requestedDays: number;
  snapshotVersion: number;
  generatedAt?: string;
  freshnessStatus?: FreshnessStatus;
  lastJobStatus?: string;
  [key: string]: unknown;
}

export interface SnapshotResponse {
  data: unknown[];
  statistics: Record<string, unknown>;
  statisticsByPrize: Record<string, unknown>;
  meta: SnapshotMeta;
}

export type OperationStatus = "queued" | "running" | "succeeded" | "failed";

export interface OperationRecord {
  requestId: string;
  kind: "data_refresh" | "telegram_send";
  status: OperationStatus;
  createdAt: string;
  updatedAt: string;
  message: string;
}

export interface AcceptedOperation {
  requestId: string;
  status: "queued";
  statusUrl: string;
}

export interface Env {
  SNAPSHOTS: KVNamespace;
  ALLOWED_ORIGINS: string;
  NOTIFICATION_ADMIN_TOKEN: string;
  GITHUB_DISPATCH_TOKEN: string;
  GITHUB_OWNER: string;
  GITHUB_REPO: string;
  OPERATION_TTL_SECONDS?: string;
  ADMIN_COOLDOWN_SECONDS?: string;
  GITHUB_FETCH?: typeof fetch;
}
