import { useEffect, useRef } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { fetchSnapshot, snapshotQueryKey } from "../api/client";
import type { RangeDays } from "../config";
import type { SnapshotResponse } from "../types/gdb";
import { pollIntervalMs, vietnamLocalTime } from "../utils/freshness";
import { usePageActivity } from "./usePageActivity";

/**
 * REST snapshot query. Used for the initial load and as controlled fallback
 * polling when the SSE stream is not connected (`fallbackPollMs`).
 */
export function useGdbSnapshot(
  days: RangeDays,
  migrationPollOverride?: number | false,
) {
  const activity = usePageActivity();
  const interval =
    migrationPollOverride ??
    pollIntervalMs({
      localTime: vietnamLocalTime(),
      visible: activity.visible,
      online: activity.online,
    });
  const wasActive = useRef(activity.visible && activity.online);
  const query = useQuery<SnapshotResponse>({
    queryKey: snapshotQueryKey(days),
    queryFn: ({ signal }) => fetchSnapshot(days, signal),
    // Keep the previous range's data visible while the new one loads so charts
    // do not flash empty.
    placeholderData: keepPreviousData,
    staleTime: 5_000,
    refetchInterval: interval,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 1,
  });
  const { refetch } = query;
  useEffect(() => {
    const active = activity.visible && activity.online;
    if (active && !wasActive.current) void refetch();
    wasActive.current = active;
  }, [activity.online, activity.visible, refetch]);
  return query;
}
