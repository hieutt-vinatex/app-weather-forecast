import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useGdbSnapshot } from "./useGdbSnapshot";
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
