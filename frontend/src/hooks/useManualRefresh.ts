import type { OperationStatus } from "../types/gdb";
import { useCloudOperation } from "./useCloudOperation";

export interface ManualRefreshState {
  refresh: (adminToken: string) => Promise<void>;
  status: OperationStatus | "idle" | "unknown";
  isRefreshing: boolean;
  message: string | null;
  isError: boolean;
}

export function useManualRefresh(): ManualRefreshState {
  const operation = useCloudOperation("refresh");
  return {
    refresh: operation.start,
    status: operation.status,
    isRefreshing: operation.isRunning,
    message: operation.message,
    isError: operation.isError,
  };
}
