import type {
  AcceptedOperation,
  Env,
  JobRecord,
  OperationRecord,
  PublicationManifest,
  SnapshotResponse,
} from "./contracts";
import { ADMIN_TOKEN_HEADER, allowedOrigins, authorizeAdminRequest } from "./auth";
import { classifyFreshness } from "./freshness";
import {
  dispatchRepositoryEvent,
  type RepositoryEventType,
} from "./github";

const MANIFEST_KEY = "manifest:v1";
const DATA_JOB_KEY = "job-status:v1:data";
const SUPPORTED_DAYS = new Set([30, 60, 90]);

export async function handleRequest(
  request: Request,
  env: Env,
  now = new Date(),
): Promise<Response> {
  const url = new URL(request.url);
  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: responseHeaders(request, env),
    });
  }
  if (
    request.method === "POST" &&
    (url.pathname === "/api/gdb/refresh" ||
      url.pathname === "/api/notifications/send-now")
  ) {
    const kind =
      url.pathname === "/api/gdb/refresh" ? "data_refresh" : "telegram_send";
    const eventType =
      kind === "data_refresh" ? "cloud-data-refresh" : "cloud-telegram-send";
    return queueOperation(request, env, now, kind, eventType);
  }
  if (request.method === "GET" && url.pathname.startsWith("/api/operations/")) {
    return operationResponse(request, env, url.pathname);
  }
  if (request.method !== "GET") {
    return jsonResponse(
      { error: "Phương thức không được hỗ trợ" },
      405,
      request,
      env,
    );
  }
  if (url.pathname === "/api/gdb") {
    const rawDays = url.searchParams.get("days");
    const days = rawDays === null ? Number.NaN : Number(rawDays);
    if (!Number.isInteger(days) || !SUPPORTED_DAYS.has(days)) {
      return jsonResponse(
        { error: "days phải là 30, 60 hoặc 90" },
        400,
        request,
        env,
      );
    }
    return snapshotResponse(request, env, days, now);
  }
  if (url.pathname === "/api/health") {
    return healthResponse(request, env, now);
  }
  return jsonResponse({ error: "Không tìm thấy" }, 404, request, env);
}

async function queueOperation(
  request: Request,
  env: Env,
  now: Date,
  kind: OperationRecord["kind"],
  eventType: RepositoryEventType,
): Promise<Response> {
  const denied = await authorizeAdminRequest(request, env);
  if (denied !== null) {
    return jsonResponse(
      {
        error:
          denied === 401
            ? "Khóa quản trị không hợp lệ"
            : "Origin không được phép",
      },
      denied,
      request,
      env,
    );
  }

  const cooldownSeconds = boundedInteger(env.ADMIN_COOLDOWN_SECONDS, 60, 10, 900);
  const operationTtl = boundedInteger(
    env.OPERATION_TTL_SECONDS,
    86_400,
    60,
    604_800,
  );
  const lockKey = `operation-lock:v1:${kind}`;
  try {
    if ((await getJson(env, lockKey)) !== null) {
      const response = jsonResponse(
        { error: "Một yêu cầu cùng loại đang được xử lý" },
        429,
        request,
        env,
      );
      response.headers.set("Retry-After", String(cooldownSeconds));
      return response;
    }

    const requestId = crypto.randomUUID();
    const operationKey = `operation:v1:${requestId}`;
    const timestamp = now.toISOString();
    const operation: OperationRecord = {
      requestId,
      kind,
      status: "queued",
      createdAt: timestamp,
      updatedAt: timestamp,
      message: "Yêu cầu đã được xếp hàng trên cloud.",
    };
    await env.SNAPSHOTS.put(
      lockKey,
      JSON.stringify({ requestId, createdAt: timestamp }),
      { expirationTtl: cooldownSeconds },
    );
    try {
      await env.SNAPSHOTS.put(operationKey, JSON.stringify(operation), {
        expirationTtl: operationTtl,
      });
      await dispatchRepositoryEvent(env, eventType, requestId);
    } catch {
      await Promise.allSettled([
        env.SNAPSHOTS.delete(operationKey),
        env.SNAPSHOTS.delete(lockKey),
      ]);
      return jsonResponse(
        { error: "Không thể tạo tác vụ cloud" },
        502,
        request,
        env,
      );
    }
    const accepted: AcceptedOperation = {
      requestId,
      status: "queued",
      statusUrl: `/api/operations/${requestId}`,
    };
    return jsonResponse(accepted, 202, request, env);
  } catch {
    return jsonResponse(
      { error: "Dịch vụ tác vụ tạm thời không sẵn sàng" },
      503,
      request,
      env,
    );
  }
}

async function operationResponse(
  request: Request,
  env: Env,
  path: string,
): Promise<Response> {
  const denied = await authorizeAdminRequest(request, env);
  if (denied !== null) {
    return jsonResponse(
      {
        error:
          denied === 401
            ? "Khóa quản trị không hợp lệ"
            : "Origin không được phép",
      },
      denied,
      request,
      env,
    );
  }
  const requestId = path.slice("/api/operations/".length);
  if (!isUuid(requestId)) {
    return jsonResponse({ error: "Mã tác vụ không hợp lệ" }, 400, request, env);
  }
  try {
    const operation = parseOperation(
      await getJson(env, `operation:v1:${requestId}`),
      requestId,
    );
    if (operation === null) {
      return jsonResponse({ error: "Không tìm thấy tác vụ" }, 404, request, env);
    }
    return jsonResponse(operation, 200, request, env);
  } catch {
    return jsonResponse(
      { error: "Không thể đọc trạng thái tác vụ" },
      503,
      request,
      env,
    );
  }
}

async function snapshotResponse(
  request: Request,
  env: Env,
  days: number,
  now: Date,
): Promise<Response> {
  try {
    const manifest = parseManifest(await getJson(env, MANIFEST_KEY));
    const etag = `"${manifest.version}"`;
    if (request.headers.get("If-None-Match") === etag) {
      const headers = responseHeaders(request, env);
      headers.set("ETag", etag);
      headers.set("Cache-Control", "public, max-age=30, stale-while-revalidate=60");
      return new Response(null, { status: 304, headers });
    }

    const rawJob = await getJson(env, DATA_JOB_KEY);
    const job = parseJob(rawJob) ?? manifest.lastJob;
    const key = manifest.snapshotKeys[String(days)];
    if (!key) throw new StoredDataError();
    const snapshot = parseSnapshot(await getJson(env, key), days);
    const freshnessStatus = classifyFreshness({
      now,
      generatedAt: manifest.generatedAt,
      lastJobStatus: job.status,
    });
    const body: SnapshotResponse = {
      ...snapshot,
      meta: {
        ...snapshot.meta,
        generatedAt: manifest.generatedAt,
        freshnessStatus,
        lastJobStatus: job.status,
      },
    };
    const headers = responseHeaders(request, env);
    headers.set("Content-Type", "application/json; charset=utf-8");
    headers.set("Cache-Control", "public, max-age=30, stale-while-revalidate=60");
    headers.set("ETag", etag);
    return new Response(JSON.stringify(body), { status: 200, headers });
  } catch {
    return jsonResponse(
      { error: "Dữ liệu chưa sẵn sàng" },
      503,
      request,
      env,
    );
  }
}

async function healthResponse(
  request: Request,
  env: Env,
  now: Date,
): Promise<Response> {
  try {
    const manifest = parseManifest(await getJson(env, MANIFEST_KEY));
    const job = parseJob(await getJson(env, DATA_JOB_KEY)) ?? manifest.lastJob;
    const freshnessStatus = classifyFreshness({
      now,
      generatedAt: manifest.generatedAt,
      lastJobStatus: job.status,
    });
    return jsonResponse(
      {
        status: freshnessStatus === "stale" ? "degraded" : "ok",
        version: manifest.version,
        generatedAt: manifest.generatedAt,
        sourceReferenceDate: manifest.sourceReferenceDate,
        lastJobStatus: job.status,
        freshnessStatus,
      },
      200,
      request,
      env,
    );
  } catch {
    return jsonResponse(
      { error: "Dữ liệu chưa sẵn sàng" },
      503,
      request,
      env,
    );
  }
}

async function getJson(env: Env, key: string): Promise<unknown> {
  return env.SNAPSHOTS.get<unknown>(key, "json");
}

class StoredDataError extends Error {}

function parseManifest(value: unknown): PublicationManifest {
  if (!isObject(value)) throw new StoredDataError();
  if (
    value.schemaVersion !== 1 ||
    typeof value.version !== "string" ||
    !/^[A-Za-z0-9_.:-]+$/.test(value.version) ||
    typeof value.generatedAt !== "string" ||
    Number.isNaN(new Date(value.generatedAt).getTime()) ||
    typeof value.historyKey !== "string" ||
    !isObject(value.snapshotKeys) ||
    (value.sourceReferenceDate !== null &&
      typeof value.sourceReferenceDate !== "string") ||
    typeof value.complete !== "boolean"
  ) {
    throw new StoredDataError();
  }
  const lastJob = parseJob(value.lastJob);
  if (lastJob === null) throw new StoredDataError();
  const snapshotKeys: Record<string, string> = {};
  for (const days of [30, 60, 90]) {
    const key = value.snapshotKeys[String(days)];
    if (typeof key !== "string" || key.length === 0) throw new StoredDataError();
    snapshotKeys[String(days)] = key;
  }
  return {
    schemaVersion: 1,
    version: value.version,
    generatedAt: value.generatedAt,
    historyKey: value.historyKey,
    snapshotKeys,
    sourceReferenceDate: value.sourceReferenceDate as string | null,
    complete: value.complete,
    lastJob,
  };
}

function parseJob(value: unknown): JobRecord | null {
  if (!isObject(value) || typeof value.status !== "string") return null;
  return {
    status: value.status,
    startedAt:
      typeof value.startedAt === "string" ? value.startedAt : undefined,
    finishedAt:
      typeof value.finishedAt === "string" || value.finishedAt === null
        ? value.finishedAt
        : undefined,
  };
}

function parseSnapshot(value: unknown, days: number): SnapshotResponse {
  if (
    !isObject(value) ||
    !Array.isArray(value.data) ||
    !isObject(value.statistics) ||
    !isObject(value.statisticsByPrize) ||
    !isObject(value.meta) ||
    value.meta.requestedDays !== days ||
    typeof value.meta.snapshotVersion !== "number"
  ) {
    throw new StoredDataError();
  }
  return value as unknown as SnapshotResponse;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseOperation(
  value: unknown,
  expectedRequestId: string,
): OperationRecord | null {
  if (value === null) return null;
  if (
    !isObject(value) ||
    value.requestId !== expectedRequestId ||
    (value.kind !== "data_refresh" && value.kind !== "telegram_send") ||
    !["queued", "running", "succeeded", "failed"].includes(
      String(value.status),
    ) ||
    typeof value.createdAt !== "string" ||
    typeof value.updatedAt !== "string" ||
    typeof value.message !== "string"
  ) {
    throw new StoredDataError();
  }
  return value as unknown as OperationRecord;
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    value,
  );
}

function boundedInteger(
  raw: string | undefined,
  fallback: number,
  minimum: number,
  maximum: number,
): number {
  const parsed = raw === undefined ? fallback : Number(raw);
  return Number.isInteger(parsed) && parsed >= minimum && parsed <= maximum
    ? parsed
    : fallback;
}

function responseHeaders(request: Request, env: Env): Headers {
  const headers = new Headers({ Vary: "Origin" });
  const origin = request.headers.get("Origin");
  const allowed = allowedOrigins(env);
  if (origin && allowed.has(origin)) {
    headers.set("Access-Control-Allow-Origin", origin);
    headers.set("Access-Control-Allow-Methods", "GET, OPTIONS");
    headers.set(
      "Access-Control-Allow-Headers",
      `Content-Type, If-None-Match, ${ADMIN_TOKEN_HEADER}`,
    );
  }
  return headers;
}

function jsonResponse(
  body: unknown,
  status: number,
  request: Request,
  env: Env,
): Response {
  const headers = responseHeaders(request, env);
  headers.set("Content-Type", "application/json; charset=utf-8");
  headers.set("Cache-Control", "no-store");
  return new Response(JSON.stringify(body), { status, headers });
}

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    return handleRequest(request, env);
  },
};
