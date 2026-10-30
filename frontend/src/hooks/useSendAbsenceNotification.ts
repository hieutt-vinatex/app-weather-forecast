import type { OperationStatus } from "../types/gdb";
import { useCloudOperation } from "./useCloudOperation";

export interface SendAbsenceNotificationState {
  send: (adminToken: string) => Promise<void>;
  status: OperationStatus | "idle" | "unknown";
  isSending: boolean;
  message: string | null;
  isError: boolean;
}

export function useSendAbsenceNotification(): SendAbsenceNotificationState {
  const operation = useCloudOperation("telegram");
  return {
    send: operation.start,
    status: operation.status,
    isSending: operation.isRunning,
    message: operation.message,
    isError: operation.isError,
  };
}
