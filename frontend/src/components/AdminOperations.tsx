import { useState } from "react";

import { useManualRefresh } from "../hooks/useManualRefresh";
import { useSendAbsenceNotification } from "../hooks/useSendAbsenceNotification";
import type { OperationStatus } from "../types/gdb";
import { classNames } from "../utils/format";
import { RefreshIcon } from "./Icons";
import { Card } from "./ui/Card";

const OPERATION_LABELS: Record<OperationStatus | "unknown", string> = {
  queued: "Đã xếp hàng",
  running: "Đang chạy trên cloud",
  succeeded: "Đã hoàn tất",
  failed: "Thất bại",
  unknown: "Chưa rõ kết quả",
};

export function AdminOperations(): JSX.Element {
  const [adminToken, setAdminToken] = useState("");
  const manual = useManualRefresh();
  const telegram = useSendAbsenceNotification();
  const token = adminToken.trim();

  return (
    <Card as="section" className="mt-4">
      <div className="grid gap-4 lg:grid-cols-[minmax(16rem,0.8fr)_minmax(0,1.2fr)]">
        <div>
          <h2 className="text-base font-semibold text-ink dark:text-slate-100">
            Thao tác quản trị trên cloud
          </h2>
          <p id="admin-token-help" className="mt-1 text-sm leading-6 text-ink-soft dark:text-slate-400">
            Các tác vụ được xếp hàng và có thể mất vài phút. Khóa chỉ tồn tại trong
            bộ nhớ của trang này và sẽ mất khi tải lại hoặc đóng trang.
          </p>
          <label className="mt-3 block text-sm font-medium text-ink dark:text-slate-200">
            Khóa quản trị
            <input
              type="password"
              value={adminToken}
              onChange={(event) => setAdminToken(event.target.value)}
              aria-describedby="admin-token-help"
              autoComplete="off"
              className="mt-1 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink outline-none focus:border-lotto-red focus:ring-2 focus:ring-red-100 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:focus:ring-red-900/30"
            />
          </label>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <OperationControl
            title="Cập nhật dữ liệu"
            description="Đồng bộ kết quả mới và xuất bản lại snapshot 30/60/90 ngày."
            buttonLabel="Làm mới dữ liệu"
            disabled={!token || manual.isRefreshing}
            running={manual.isRefreshing}
            status={manual.status}
            message={manual.message}
            isError={manual.isError}
            onClick={() => void manual.refresh(token)}
          />
          <OperationControl
            title="Thông báo Telegram"
            description="Tính lại danh sách số vắng 19–25 ngày và gửi báo cáo ngay."
            warning="Gửi lại sẽ tạo thêm một tin nhắn Telegram."
            buttonLabel="Gửi Telegram ngay"
            disabled={!token || telegram.isSending}
            running={telegram.isSending}
            status={telegram.status}
            message={telegram.message}
            isError={telegram.isError}
            onClick={() => void telegram.send(token)}
          />
        </div>
      </div>
    </Card>
  );
}

function OperationControl({
  title,
  description,
  warning,
  buttonLabel,
  disabled,
  running,
  status,
  message,
  isError,
  onClick,
}: {
  title: string;
  description: string;
  warning?: string;
  buttonLabel: string;
  disabled: boolean;
  running: boolean;
  status: OperationStatus | "idle" | "unknown";
  message: string | null;
  isError: boolean;
  onClick: () => void;
}): JSX.Element {
  return (
    <div className="rounded-xl border border-line p-4 dark:border-slate-700">
      <h3 className="text-sm font-semibold text-ink dark:text-slate-100">{title}</h3>
      <p className="mt-1 text-xs leading-5 text-ink-soft dark:text-slate-400">
        {description}
      </p>
      {warning ? <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">{warning}</p> : null}
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-lotto-red px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lotto-red"
      >
        <RefreshIcon
          width={16}
          height={16}
          className={running ? "motion-safe:animate-spin" : undefined}
        />
        {buttonLabel}
      </button>
      {status !== "idle" ? (
        <div
          role={isError ? "alert" : "status"}
          className={classNames(
            "mt-3 rounded-lg px-3 py-2 text-xs",
            isError
              ? "bg-rose-50 text-state-danger dark:bg-rose-900/20"
              : "bg-sky-50 text-sky-800 dark:bg-sky-900/20 dark:text-sky-200",
          )}
        >
          <p className="font-semibold">{OPERATION_LABELS[status]}</p>
          {message ? <p className="mt-0.5">{message}</p> : null}
        </div>
      ) : null}
    </div>
  );
}
