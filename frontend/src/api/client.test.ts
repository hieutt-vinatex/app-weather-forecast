import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  fetchOperation,
  fetchSnapshot,
  startOperation,
} from "./client";
import { makeSnapshot } from "../test/fixtures";

const ACTIVE = "20261029T110500000000Z";
const PREVIOUS = "20261029T105500000000Z";

function publication(version = ACTIVE, previousVersion: string | null = null) {
  const pointer = (itemVersion: string) => ({
    version: itemVersion,
    generatedAt: "2026-10-29T11:05:00Z",
    snapshotKeys: {
      "30": `snapshot:v1:${itemVersion}:30`,
      "60": `snapshot:v1:${itemVersion}:60`,
      "90": `snapshot:v1:${itemVersion}:90`,
    },
    lastJob: { status: "succeeded" },
  });
  return {
    schemaVersion: 1,
    ...pointer(version),
    previousPublication: previousVersion ? pointer(previousVersion) : null,
  };
}

describe("static publication contracts", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("loads an active immutable snapshot when status is absent", async () => {
    const snapshot = makeSnapshot(30, 7);
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(publication()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify(snapshot), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchFn);

    expect(await fetchSnapshot(30)).toEqual(snapshot);
    expect(String(fetchFn.mock.calls[0]?.[0])).toContain("data/manifest.json?v=");
    expect(fetchFn.mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({
        cache: "no-store",
      }),
    );
    expect(String(fetchFn.mock.calls[2]?.[0])).toContain(
      `data/versions/${ACTIVE}/snapshot-30.json`,
    );
    expect(fetchFn.mock.calls[2]?.[1]).toEqual(
      expect.objectContaining({ cache: "force-cache" }),
    );
  });

  it("falls back to the previous publication when the active file is missing", async () => {
    const previous = makeSnapshot(60, 6);
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(publication(ACTIVE, PREVIOUS)), { status: 200 }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify(previous), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchFn);

    expect(await fetchSnapshot(60)).toEqual(previous);
    expect(String(fetchFn.mock.calls[3]?.[0])).toContain(
      `data/versions/${PREVIOUS}/snapshot-60.json`,
    );
  });

  it("rejects invalid active and previous snapshots without exposing bodies", async () => {
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(publication(ACTIVE, PREVIOUS)), { status: 200 }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ private: "active-body" }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ private: "previous-body" }), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchFn);

    const pending = fetchSnapshot(90);

    await expect(pending).rejects.toBeInstanceOf(ApiError);
    await expect(pending).rejects.not.toThrow(/active-body|previous-body/);
  });

  it("overlays a failed data job status without replacing snapshot data", async () => {
    const snapshot = makeSnapshot(30, 9);
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(publication("20261029T111500000000Z")), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            kind: "data",
            mode: "incremental",
            status: "failed",
            startedAt: "2026-10-29T11:15:00Z",
            finishedAt: "2026-10-29T11:16:00Z",
            reason: "invalid_upstream_data",
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(snapshot), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchFn);

    const result = await fetchSnapshot(30);

    expect(result.data).toEqual(snapshot.data);
    expect(result.meta.lastJobStatus).toBe("failed");
    expect(result.meta.freshnessStatus).toBe("delayed");
  });

  it("returns the last valid range when a later manifest request fails", async () => {
    const version = "20261029T113000000000Z";
    const snapshot = makeSnapshot(90, 10);
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(publication(version)), { status: 200 }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify(snapshot), { status: 200 }),
      )
      .mockRejectedValueOnce(new TypeError("offline"));
    vi.stubGlobal("fetch", fetchFn);

    expect(await fetchSnapshot(90)).toEqual(snapshot);
    expect(await fetchSnapshot(90)).toEqual(snapshot);
  });

});

describe("legacy operation contracts", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("handles 202 operations and authenticates status reads", async () => {
    const requestId = "123e4567-e89b-42d3-a456-426614174000";
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            requestId,
            status: "queued",
            statusUrl: `/api/operations/${requestId}`,
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            requestId,
            kind: "data_refresh",
            status: "succeeded",
            createdAt: "2026-10-29T11:00:00Z",
            updatedAt: "2026-10-29T11:01:00Z",
            message: "ok",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchFn);

    const accepted = await startOperation("refresh", "admin-secret");
    const operation = await fetchOperation(accepted.requestId, "admin-secret");

    expect(operation.status).toBe("succeeded");
    expect(fetchFn.mock.calls[1]?.[1]).toEqual(
      expect.objectContaining({
        headers: { "X-Notification-Token": "admin-secret" },
      }),
    );
  });

  it.each([401, 403, 429, 502])("maps HTTP %s to a safe ApiError", async (status) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("private", { status })));

    await expect(startOperation("refresh", "token")).rejects.toBeInstanceOf(
      ApiError,
    );
    await expect(startOperation("refresh", "token")).rejects.not.toThrow(
      /private/,
    );
  });
});
