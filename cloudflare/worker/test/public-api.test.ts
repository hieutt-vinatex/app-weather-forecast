import { describe, expect, it } from "vitest";

import { handleRequest } from "../src/index";
import type { Env } from "../src/contracts";

class FakeKV {
  constructor(
    readonly values: Record<string, unknown>,
    readonly throwOnGet = false,
  ) {}

  async get<T>(key: string, type?: "json"): Promise<T | string | null> {
    void type;
    if (this.throwOnGet) throw new Error("private storage detail");
    return (structuredClone(this.values[key]) as T | undefined) ?? null;
  }
}

function snapshot(days = 30): Record<string, unknown> {
  return {
    data: [],
    statistics: { totalResults: 0 },
    statisticsByPrize: {},
    meta: {
      requestedDays: days,
      snapshotVersion: 7,
      fetchedAt: "2026-10-29T10:55:00Z",
    },
  };
}

function env(
  overrides: Record<string, unknown> = {},
  throwOnGet = false,
): Env {
  const generatedAt = "2026-10-29T10:55:00Z";
  return {
    SNAPSHOTS: new FakeKV(
      {
        "manifest:v1": {
          schemaVersion: 1,
          version: "20261029T105500000000Z",
          generatedAt,
          historyKey: "history:v1:20261029T105500000000Z",
          snapshotKeys: {
            "30": "snapshot:v1:current:30",
            "60": "snapshot:v1:current:60",
            "90": "snapshot:v1:current:90",
          },
          sourceReferenceDate: "2026-10-29",
          complete: true,
          lastJob: { status: "succeeded" },
        },
        "job-status:v1:data": {
          status: "succeeded",
          finishedAt: generatedAt,
        },
        "snapshot:v1:current:30": snapshot(30),
        "snapshot:v1:current:60": snapshot(60),
        "snapshot:v1:current:90": snapshot(90),
        ...overrides,
      },
      throwOnGet,
    ) as unknown as KVNamespace,
    ALLOWED_ORIGINS: "https://app.example,https://preview.example",
    NOTIFICATION_ADMIN_TOKEN: "",
    GITHUB_TOKEN: "",
    GITHUB_OWNER: "",
    GITHUB_REPO: "",
  };
}

const now = new Date("2026-10-29T11:00:00Z");

describe("public Worker API", () => {
  it("rejects missing and unsupported ranges", async () => {
    expect(
      (await handleRequest(new Request("https://api.example/api/gdb"), env(), now))
        .status,
    ).toBe(400);
    expect(
      (
        await handleRequest(
          new Request("https://api.example/api/gdb?days=31"),
          env(),
          now,
        )
      ).status,
    ).toBe(400);
  });

  it("returns safe 503 when no active manifest exists", async () => {
    const response = await handleRequest(
      new Request("https://api.example/api/gdb?days=30"),
      env({ "manifest:v1": null }),
      now,
    );

    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ error: "Dữ liệu chưa sẵn sàng" });
  });

  it("preserves snapshot data and adds freshness metadata and ETag", async () => {
    const response = await handleRequest(
      new Request("https://api.example/api/gdb?days=30", {
        headers: { Origin: "https://app.example" },
      }),
      env(),
      now,
    );
    const body = (await response.json()) as Record<string, any>;

    expect(response.status).toBe(200);
    expect(body.data).toEqual([]);
    expect(body.meta.generatedAt).toBe("2026-10-29T10:55:00Z");
    expect(body.meta.freshnessStatus).toBe("current");
    expect(body.meta.lastJobStatus).toBe("succeeded");
    expect(response.headers.get("ETag")).toBe('"20261029T105500000000Z"');
    expect(response.headers.get("Access-Control-Allow-Origin")).toBe(
      "https://app.example",
    );
  });

  it("returns 304 for the active ETag without reading a partial snapshot", async () => {
    const response = await handleRequest(
      new Request("https://api.example/api/gdb?days=30", {
        headers: { "If-None-Match": '"20261029T105500000000Z"' },
      }),
      env({ "snapshot:v1:current:30": null }),
      now,
    );

    expect(response.status).toBe(304);
  });

  it("does not grant CORS to a disallowed origin", async () => {
    const response = await handleRequest(
      new Request("https://api.example/api/gdb?days=30", {
        headers: { Origin: "https://evil.example" },
      }),
      env(),
      now,
    );

    expect(response.status).toBe(200);
    expect(response.headers.has("Access-Control-Allow-Origin")).toBe(false);
  });

  it("returns safe 503 for malformed, mismatched, or unavailable KV data", async () => {
    const malformedManifest = await handleRequest(
      new Request("https://api.example/api/gdb?days=30"),
      env({ "manifest:v1": { version: "partial" } }),
      now,
    );
    const malformed = await handleRequest(
      new Request("https://api.example/api/gdb?days=30"),
      env({ "snapshot:v1:current:30": { data: "wrong" } }),
      now,
    );
    const mismatched = await handleRequest(
      new Request("https://api.example/api/gdb?days=30"),
      env({ "snapshot:v1:current:30": snapshot(60) }),
      now,
    );
    const unavailable = await handleRequest(
      new Request("https://api.example/api/gdb?days=30"),
      env({}, true),
      now,
    );

    expect(malformedManifest.status).toBe(503);
    expect(malformed.status).toBe(503);
    expect(mismatched.status).toBe(503);
    expect(unavailable.status).toBe(503);
    expect(await unavailable.text()).not.toContain("private storage detail");
  });

  it("reports only safe health metadata", async () => {
    const response = await handleRequest(
      new Request("https://api.example/api/health"),
      env(),
      now,
    );
    const body = (await response.json()) as Record<string, unknown>;

    expect(response.status).toBe(200);
    expect(body).toEqual({
      status: "ok",
      version: "20261029T105500000000Z",
      generatedAt: "2026-10-29T10:55:00Z",
      sourceReferenceDate: "2026-10-29",
      lastJobStatus: "succeeded",
      freshnessStatus: "current",
    });
  });
});
