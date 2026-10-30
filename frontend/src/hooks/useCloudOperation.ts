import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  fetchOperation,
  startOperation,
  type CloudOperation,
} from "../api/client";
import { config } from "../config";
import type { OperationStatus } from "../types/gdb";

export interface CloudOperationState {
  start: (adminToken: string) => Promise<void>;
  status: OperationStatus | "idle";
  isRunning: boolean;
  isError: boolean;
  message: string | null;
}

export function useCloudOperation(kind: CloudOperation): CloudOperationState {
  const [status, setStatus] = useState<OperationStatus | "idle">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [isError, setIsError] = useState(false);
  const activeRef = useRef(false);
  const mountedRef = useRef(true);

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
          const operation = await fetchOperation(accepted.requestId, adminToken);
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
          setStatus("failed");
          setIsError(true);
          setMessage("Tác vụ cloud quá thời gian chờ 15 phút.");
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
