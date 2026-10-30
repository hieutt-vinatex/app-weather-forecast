import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  fetchOperation,
  startOperation,
  type CloudOperation,
} from "../api/client";
import { config } from "../config";
import type { OperationStatus } from "../types/gdb";
import { usePageActivity } from "./usePageActivity";

export interface CloudOperationState {
  start: (adminToken: string) => Promise<void>;
  status: OperationStatus | "idle" | "unknown";
  isRunning: boolean;
  isError: boolean;
  message: string | null;
}

export function useCloudOperation(kind: CloudOperation): CloudOperationState {
  const [status, setStatus] = useState<OperationStatus | "idle" | "unknown">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [isError, setIsError] = useState(false);
  const activeRef = useRef(false);
  const mountedRef = useRef(true);
  const activity = usePageActivity();
  const activityRef = useRef(activity);

  useEffect(() => {
    activityRef.current = activity;
  }, [activity]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const start = useCallback(
    async (adminToken: string) => {
      if (activeRef.current) return;
      activeRef.current = true;
      setIsError(false);
      setMessage(null);
      try {
        const accepted = await startOperation(kind, adminToken);
        if (!mountedRef.current) return;
        setStatus("queued");
        setMessage("Tác vụ đã được xếp hàng trên cloud.");
        const deadline = Date.now() + config.operationTimeoutMs;
        while (Date.now() < deadline) {
          await wait(config.operationPollMs);
          if (!activityRef.current.visible || !activityRef.current.online) {
            continue;
          }
          let operation;
          try {
            operation = await fetchOperation(accepted.requestId, adminToken);
          } catch (error) {
            if (
              error instanceof ApiError &&
              (error.status === 401 || error.status === 403)
            ) {
              throw error;
            }
            if (mountedRef.current) {
              setMessage("Tạm thời chưa đọc được trạng thái; đang thử lại.");
            }
            continue;
          }
          if (!mountedRef.current) return;
          setStatus(operation.status);
          setMessage(operation.message);
          if (operation.status === "succeeded") return;
          if (operation.status === "failed") {
            setIsError(true);
            return;
          }
        }
        if (mountedRef.current) {
          setStatus("unknown");
          setIsError(true);
          setMessage("Chưa xác nhận được kết quả tác vụ cloud trong thời gian chờ.");
        }
      } catch (error) {
        if (!mountedRef.current) return;
        setStatus("failed");
        setIsError(true);
        setMessage(operationErrorMessage(error));
      } finally {
        activeRef.current = false;
      }
    },
    [kind],
  );

  return {
    start,
    status,
    isRunning: status === "queued" || status === "running",
    isError,
    message,
  };
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function operationErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Không thể xử lý tác vụ cloud.";
  if (error.status === 401) return "Khóa quản trị không đúng.";
  if (error.status === 403) return "Trang hiện tại không được phép thao tác.";
  if (error.status === 429) return "Một tác vụ cùng loại đang được xử lý.";
  return error.message;
}
