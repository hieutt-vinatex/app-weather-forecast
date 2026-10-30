import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  fetchOperation,
  fetchSnapshot,
  startOperation,
} from "./client";
import { makeSnapshot } from "../test/fixtures";

describe("cloud REST contracts", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("sends cached ETag and returns the cached typed snapshot on 304", async () => {
    const snapshot = makeSnapshot(30, 7);
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(snapshot), {
          status: 200,
          headers: { ETag: '"version-7"', "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 304 }));
    vi.stubGlobal("fetch", fetchFn);

    expect(await fetchSnapshot(30)).toEqual(snapshot);
    expect(await fetchSnapshot(30)).toEqual(snapshot);
    expect(fetchFn.mock.calls[1]?.[1]).toEqual(
      expect.objectContaining({
        headers: expect.objectContaining({ "If-None-Match": '"version-7"' }),
      }),
    );
  });

  it("rejects an invalid Worker snapshot before caching it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ data: [], meta: { requestedDays: 30 } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(fetchSnapshot(60)).rejects.toMatchObject({ status: 500 });
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
