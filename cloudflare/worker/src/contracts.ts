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

export interface Env {
  SNAPSHOTS: KVNamespace;
  ALLOWED_ORIGINS: string;
}
