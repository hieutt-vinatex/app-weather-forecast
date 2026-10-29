import type {
  Env,
  JobRecord,
  PublicationManifest,
  SnapshotResponse,
} from "./contracts";
import { classifyFreshness } from "./freshness";

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

function responseHeaders(request: Request, env: Env): Headers {
  const headers = new Headers({ Vary: "Origin" });
  const origin = request.headers.get("Origin");
  const allowed = new Set(
    env.ALLOWED_ORIGINS.split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  );
  if (origin && allowed.has(origin)) {
    headers.set("Access-Control-Allow-Origin", origin);
    headers.set("Access-Control-Allow-Methods", "GET, OPTIONS");
    headers.set("Access-Control-Allow-Headers", "Content-Type, If-None-Match");
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
