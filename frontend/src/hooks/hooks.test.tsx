import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useGdbSnapshot } from "./useGdbSnapshot";
import { useCloudOperation } from "./useCloudOperation";
import { useManualRefresh } from "./useManualRefresh";
import { useSendAbsenceNotification } from "./useSendAbsenceNotification";
import { makeSnapshot } from "../test/fixtures";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

describe("useGdbSnapshot adaptive polling", () => {
  afterEach(() => vi.restoreAllMocks());

  function stubFetch() {
    const version = "20261029T110500000000Z";
    const fn = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("manifest.json")) {
        return new Response(
          JSON.stringify({
            schemaVersion: 1,
            version,
            generatedAt: "2026-10-29T11:05:00Z",
            snapshotKeys: {
              "30": `snapshot:v1:${version}:30`,
              "60": `snapshot:v1:${version}:60`,
              "90": `snapshot:v1:${version}:90`,
            },
            lastJob: { status: "succeeded" },
            previousPublication: null,
          }),
          { status: 200 },
        );
      }
      if (url.includes("status.json")) {
        return new Response(null, { status: 404 });
      }
      return new Response(JSON.stringify(makeSnapshot(30, 1)), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fn as unknown as typeof fetch);
    return fn;
  }

  it("polls repeatedly when a poll interval is provided", async () => {
    const fetchFn = stubFetch();
    const { qc, wrapper } = makeWrapper();
    const { unmount } = renderHook(() => useGdbSnapshot(30, 50), { wrapper });
    // With a 50ms interval, several fetches should occur within the window.
    await waitFor(
      () =>
        expect(
          fetchFn.mock.calls.filter(([url]) =>
            String(url).includes("manifest.json"),
          ).length,
        ).toBeGreaterThan(1),
      { timeout: 2000 },
    );
    await act(async () => {
      unmount();
      qc.clear();
    });
  });

  it("does not poll when an interval override is disabled", async () => {
    const fetchFn = stubFetch();
    const { qc, wrapper } = makeWrapper();
    const { unmount } = renderHook(() => useGdbSnapshot(30, false), { wrapper });
    await waitFor(() =>
      expect(
        fetchFn.mock.calls.filter(([url]) => String(url).includes("manifest.json")),
      ).toHaveLength(1),
    );
    await act(async () => {
      await new Promise((r) => setTimeout(r, 250));
    });
    expect(
      fetchFn.mock.calls.filter(([url]) => String(url).includes("manifest.json")),
    ).toHaveLength(1);
    await act(async () => {
      unmount();
      qc.clear();
    });
  });
});

describe("useManualRefresh", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("reports a wrong cloud admin token safely", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 401 })));
    const { result } = renderHook(() => useManualRefresh());
    await act(async () => {
      await result.current.refresh("wrong-token");
    });
    expect(result.current.isError).toBe(true);
    expect(result.current.message).toContain("Khóa quản trị không đúng");
  });
});

describe("useCloudOperation", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("polls a queued operation through running until success", async () => {
    vi.useFakeTimers();
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
            status: "running",
            createdAt: "2026-10-29T11:00:00Z",
            updatedAt: "2026-10-29T11:00:30Z",
            message: "Đang cập nhật dữ liệu",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
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
            message: "Đã cập nhật",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchFn);
    const { result } = renderHook(() => useCloudOperation("refresh"));

    let pending: Promise<void>;
    act(() => {
      pending = result.current.start("admin-secret");
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(result.current.status).toBe("running");
    expect(result.current.message).toContain("Đang cập nhật");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
      await pending!;
    });

    expect(result.current.status).toBe("succeeded");
    expect(result.current.message).toContain("Đã cập nhật");
  });

  it("surfaces a terminal failed operation", async () => {
    vi.useFakeTimers();
    const requestId = "123e4567-e89b-42d3-a456-426614174001";
    vi.stubGlobal(
      "fetch",
      vi
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
              kind: "telegram_send",
              status: "failed",
              createdAt: "2026-10-29T11:00:00Z",
              updatedAt: "2026-10-29T11:01:00Z",
              message: "Telegram tạm thời không gửi được",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        ),
    );
    const { result } = renderHook(() => useCloudOperation("telegram"));

    let pending: Promise<void>;
    act(() => {
      pending = result.current.start("admin-secret");
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
      await pending!;
    });

    expect(result.current.status).toBe("failed");
    expect(result.current.isError).toBe(true);
    expect(result.current.message).toContain("không gửi được");
  });

  it("retries a transient observation failure until the operation succeeds", async () => {
    vi.useFakeTimers();
    const requestId = "123e4567-e89b-42d3-a456-426614174002";
    vi.stubGlobal(
      "fetch",
      vi
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
          new Response(JSON.stringify({ error: "KV đang lan truyền" }), {
            status: 503,
            headers: { "Content-Type": "application/json" },
          }),
        )
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              requestId,
              kind: "data_refresh",
              status: "succeeded",
              createdAt: "2026-10-29T11:00:00Z",
              updatedAt: "2026-10-29T11:01:00Z",
              message: "Đã cập nhật",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        ),
    );
    const { result } = renderHook(() => useCloudOperation("refresh"));

    let pending: Promise<void>;
    act(() => {
      pending = result.current.start("admin-secret");
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4_000);
      await pending!;
    });

    expect(result.current.status).toBe("succeeded");
    expect(result.current.isError).toBe(false);
  });
});

describe("useSendAbsenceNotification", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("explains a duplicate cloud Telegram operation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(null, {
          status: 429,
          headers: { "Retry-After": "60" },
        }),
      ),
    );
    const { result } = renderHook(() => useSendAbsenceNotification());

    await act(async () => {
      await result.current.send("admin-secret");
    });

    expect(result.current.isError).toBe(true);
    expect(result.current.message).toContain("cùng loại đang được xử lý");
  });
});
