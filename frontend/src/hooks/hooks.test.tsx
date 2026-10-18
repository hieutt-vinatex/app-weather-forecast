import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useGdbRealtime } from "./useGdbRealtime";
import { useGdbSnapshot } from "./useGdbSnapshot";
import { useManualRefresh } from "./useManualRefresh";
import { useSendAbsenceNotification } from "./useSendAbsenceNotification";
import { snapshotQueryKey } from "../api/client";
import { MockEventSource, installMockEventSource } from "../test/mockEventSource";
import { makeSnapshot } from "../test/fixtures";
import type { SnapshotResponse } from "../types/gdb";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

describe("useGdbRealtime", () => {
  beforeEach(() => installMockEventSource());
  afterEach(() => vi.restoreAllMocks());

  it("writes snapshot events into the query cache", async () => {
    const { qc, wrapper } = makeWrapper();
    renderHook(() => useGdbRealtime(30), { wrapper });
    const es = MockEventSource.last();
    act(() => {
      es.emitOpen();
      es.emit("snapshot", makeSnapshot(30, 1));
    });
    await waitFor(() => {
      const cached = qc.getQueryData<SnapshotResponse>(snapshotQueryKey(30));
      expect(cached?.meta.snapshotVersion).toBe(1);
    });
  });

  it("closes the old stream when days changes and opens a new one", () => {
    const { wrapper } = makeWrapper();
    const { rerender } = renderHook(({ d }) => useGdbRealtime(d), {
      wrapper,
      initialProps: { d: 30 as 30 | 60 | 90 },
    });
    const first = MockEventSource.last();
    expect(first.url).toContain("days=30");
    rerender({ d: 60 });
    expect(first.closed).toBe(true);
    const second = MockEventSource.last();
    expect(second.url).toContain("days=60");
  });

  it("ignores events for a different range", async () => {
    const { qc, wrapper } = makeWrapper();
    renderHook(() => useGdbRealtime(30), { wrapper });
    const es = MockEventSource.last();
    act(() => es.emit("update", makeSnapshot(60, 2)));
    const cached = qc.getQueryData<SnapshotResponse>(snapshotQueryKey(30));
    expect(cached).toBeUndefined();
  });
});

describe("useGdbSnapshot fallback polling", () => {
  afterEach(() => vi.restoreAllMocks());

  function stubFetch() {
    const fn = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => makeSnapshot(30, 1),
    }));
    vi.stubGlobal("fetch", fn as unknown as typeof fetch);
    return fn;
  }

  it("polls repeatedly when a poll interval is provided", async () => {
    const fetchFn = stubFetch();
    const { qc, wrapper } = makeWrapper();
    const { unmount } = renderHook(() => useGdbSnapshot(30, 50), { wrapper });
    // With a 50ms interval, several fetches should occur within the window.
    await waitFor(() => expect(fetchFn.mock.calls.length).toBeGreaterThan(1), {
      timeout: 2000,
    });
    await act(async () => {
      unmount();
      qc.clear();
    });
  });

  it("does not poll when fallback is disabled", async () => {
    const fetchFn = stubFetch();
    const { qc, wrapper } = makeWrapper();
    const { unmount } = renderHook(() => useGdbSnapshot(30, false), { wrapper });
    await waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 250));
    });
    expect(fetchFn).toHaveBeenCalledTimes(1);
    await act(async () => {
      unmount();
      qc.clear();
    });
  });
});

describe("useManualRefresh", () => {
  afterEach(() => vi.restoreAllMocks());

  it("handles 429 with cooldown and message", async () => {
    const headers = new Headers({ "Retry-After": "5" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 429, headers })) as unknown as typeof fetch,
    );
    const { result } = renderHook(() => useManualRefresh());
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.isError).toBe(true);
    expect(result.current.cooldownUntil).not.toBeNull();
    expect(result.current.message).toContain("chờ");
  });

  it("reports success on 200", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ triggered: true, changed: true, snapshotVersion: 2, message: "ok" }),
      })) as unknown as typeof fetch,
    );
    const { result } = renderHook(() => useManualRefresh());
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.isError).toBe(false);
    expect(result.current.message).toContain("Đã cập nhật");
  });
});

describe("useSendAbsenceNotification", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends the admin token and reports a successful immediate delivery", async () => {
    const fetchFn = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        status: "delivered",
        success: true,
        dryRun: false,
        message: "Đã gửi 3 số đang vắng 19–25 ngày.",
        checkedAt: "2026-10-15T22:30:00+07:00",
        referenceDate: "2026-10-15",
        minDays: 19,
        maxDays: 25,
        candidateCount: 3,
        candidates: [],
        reason: null,
        results: [],
      }),
    }));
    vi.stubGlobal("fetch", fetchFn as unknown as typeof fetch);
    const { result } = renderHook(() => useSendAbsenceNotification());

    await act(async () => {
      await result.current.send("  admin-secret  ");
    });

    expect(fetchFn).toHaveBeenCalledWith(
      expect.stringContaining("/api/notifications/send-now"),
      expect.objectContaining({
        method: "POST",
        headers: { "X-Notification-Token": "admin-secret" },
      }),
    );
    expect(result.current.isError).toBe(false);
    expect(result.current.message).toContain("Đã gửi 3 số");
  });

  it("explains an invalid admin token", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 401 })) as unknown as typeof fetch,
    );
    const { result } = renderHook(() => useSendAbsenceNotification());

    await act(async () => {
      await result.current.send("wrong-token");
    });

    expect(result.current.isError).toBe(true);
    expect(result.current.message).toContain("không đúng");
  });
});
