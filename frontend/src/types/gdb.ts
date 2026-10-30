/** Shared types mirroring the backend REST/SSE response model (camelCase). */

export type PrizeKey = "db" | "g1" | "g2" | "g3" | "g4" | "g5" | "g6" | "g7";
export type PrizeScope = "all" | PrizeKey;

export type PrizeResults = Record<PrizeKey, string[]>;

export interface GdbRecord {
  gdb: string | null; // backward-compatible two-digit special prize
  prizes: PrizeResults; // full values exactly as published
  drawComplete: boolean;
  date: string; // ISO YYYY-MM-DD
  dateLabel: string; // DD-MM
  dayName: string; // Vietnamese weekday
  sourceUrl: string;
}

export interface FrequencyItem {
  number: string;
  count: number;
  percentage: number;
  lastSeen: string | null;
}

export interface DigitFrequencyItem {
  digit: string;
  count: number;
  percentage: number;
}

export interface EvenOdd {
  even: number;
  odd: number;
  evenPercentage: number;
  oddPercentage: number;
}

export interface Statistics {
  totalResults: number;
  availableDraws: number;
  expectedResults: number;
  expectedResultsPerDraw: number;
  averageResultsPerDraw: number;
  uniqueNumbers: number;
  collectionSuccessRate: number;
  frequencies: FrequencyItem[];
  topNumbers: FrequencyItem[];
  coldNumbers: FrequencyItem[];
  tensDigitFrequency: DigitFrequencyItem[];
  unitsDigitFrequency: DigitFrequencyItem[];
  evenOdd: EvenOdd;
}

export interface RecordError {
  date: string;
  reason: string;
}

export interface Meta {
  requestedDays: number;
  availableRecords: number;
  failedCount: number;
  missingDates: string[];
  incompleteDates: string[];
  availableNumbers: number;
  errors: RecordError[];
  partial: boolean;
  cached: boolean;
  stale: boolean;
  fetchedAt: string;
  lastSourceCheckAt: string | null;
  lastSuccessfulCheckAt: string | null;
  lastChangedAt: string | null;
  snapshotVersion: number;
  pollIntervalSeconds: number;
  realtimeEnabled: boolean;
  source: string;
  generatedAt: string;
  freshnessStatus: FreshnessStatus;
  lastJobStatus: string;
}

export interface SnapshotResponse {
  data: GdbRecord[];
  statistics: Statistics;
  statisticsByPrize: Record<PrizeKey, Statistics>;
  meta: Meta;
}

export type FreshnessStatus =
  | "current"
  | "updating"
  | "delayed"
  | "stale"
  | "offline";

export type OperationKind = "data_refresh" | "telegram_send";
export type OperationStatus = "queued" | "running" | "succeeded" | "failed";

export interface AcceptedOperation {
  requestId: string;
  status: "queued";
  statusUrl: string;
}

export interface OperationRecord {
  requestId: string;
  kind: OperationKind;
  status: OperationStatus;
  createdAt: string;
  updatedAt: string;
  message: string;
}
