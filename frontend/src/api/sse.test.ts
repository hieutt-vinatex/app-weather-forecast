import { beforeEach, describe, expect, it, vi } from "vitest";

import { RealtimeClient } from "./sse";
import {
  ApiError,
  fetchOperation,
  fetchSnapshot,
  startOperation,
} from "./client";
import type { ConnectionStatus } from "../types/gdb";
import { MockEventSource, installMockEventSource } from "../test/mockEventSource";
import { makeSnapshot } from "../test/fixtures";

function makeClient() {
  const onSnapshot = vi.fn();
  const onUpdate = vi.fn();
  const onStatus = vi.fn<(status: ConnectionStatus) => void>();
  const onHeartbeat = vi.fn();
  const client = new RealtimeClient(
    "http://x/stream?days=30",
    { onSnapshot, onUpdate, onStatus, onHeartbeat },
    { reconnectBaseMs: 1000, reconnectMaxMs: 30000 },
  );
  return { client, onSnapshot, onUpdate, onStatus, onHeartbeat };
}

describe("RealtimeClient", () => {
  beforeEach(() => {
    installMockEventSource();
  });

  it("applies snapshot then online status on open", () => {
    const { client, onSnapshot, onStatus } = makeClient();
    client.connect();
    const es = MockEventSource.last();
    es.emitOpen();
    es.emit("snapshot", makeSnapshot(30, 1));
    expect(onStatus).toHaveBeenCalledWith("connecting");
    expect(onStatus).toHaveBeenCalledWith("online");
    expect(onSnapshot).toHaveBeenCalledTimes(1);
    client.close();
  });

  it("applies newer update but ignores older/equal versions", () => {
    const { client, onUpdate } = makeClient();
    client.connect();
    const es = MockEventSource.last();
    es.emit("snapshot", makeSnapshot(30, 5)); // primes lastVersion=5
    es.emit("update", makeSnapshot(30, 6)); // newer -> applied
    es.emit("update", makeSnapshot(30, 6)); // equal -> ignored
    es.emit("update", makeSnapshot(30, 4)); // older -> ignored
    expect(onUpdate).toHaveBeenCalledTimes(1);
    expect(onUpdate.mock.calls[0]![0].meta.snapshotVersion).toBe(6);
    client.close();
  });

  it("ignores malformed payloads", () => {
    const { client, onUpdate } = makeClient();
    client.connect();
    const es = MockEventSource.last();
    es.emitRaw("update", "{not json");
    es.emit("update", { garbage: true });
    expect(onUpdate).not.toHaveBeenCalled();
    client.close();
  });

  it("reconnects with a new EventSource after an error", () => {
    vi.useFakeTimers();
    const { client, onStatus } = makeClient();
    client.connect();
    const first = MockEventSource.last();
    first.emitError();
    expect(first.closed).toBe(true);
    expect(onStatus).toHaveBeenCalledWith("reconnecting");
    vi.advanceTimersByTime(31000);
    // A new EventSource should have been created.
    expect(MockEventSource.instances.length).toBe(2);
    client.close();
    vi.useRealTimers();
  });

  it("fires heartbeat handler", () => {
    const { client, onHeartbeat } = makeClient();
    client.connect();
    const es = MockEventSource.last();
    es.emit("heartbeat", { sentAt: "2026-07-27T18:25:15+07:00", snapshotVersion: 3 });
    expect(onHeartbeat).toHaveBeenCalledTimes(1);
    client.close();
  });

  it("stops creating connections after close", () => {
    const { client } = makeClient();
    client.connect();
    const es = MockEventSource.last();
    client.close();
    es.emitError();
    expect(MockEventSource.instances.length).toBe(1);
  });
});

describe("cloud REST migration contracts", () => {
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
