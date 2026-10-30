import type { Meta } from "../types/gdb";
import { InfoIcon, WarningIcon } from "./Icons";

export function PartialWarning({ meta }: { meta: Meta }): JSX.Element | null {
  if (!meta.partial) return null;
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-xl2 border border-amber-300 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-800 px-4 py-3 text-sm text-amber-800 dark:text-amber-200"
    >
      <WarningIcon className="mt-0.5 shrink-0" />
      <div>
        <p className="font-medium">Dữ liệu chưa đầy đủ</p>
        <p className="mt-0.5">
          {meta.failedCount > 0 ? `Thiếu ${meta.failedCount}/${meta.requestedDays} ngày. ` : ""}
          {meta.incompleteDates.length > 0
            ? `${meta.incompleteDates.length} kỳ đang cập nhật chưa đủ 27 số. `
            : ""}
          Biểu đồ đang dùng {meta.availableNumbers.toLocaleString("vi-VN")} số đã thu thập.
        </p>
      </div>
    </div>
  );
}

export function StaleWarning({ meta }: { meta: Meta }): JSX.Element | null {
  if (meta.freshnessStatus !== "delayed" && meta.freshnessStatus !== "stale") {
    return null;
  }
  const stale = meta.freshnessStatus === "stale";
  return (
    <div
      role="status"
      className={`flex items-start gap-2 rounded-xl2 border px-4 py-3 text-sm ${
        stale
          ? "border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-200"
          : "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200"
      }`}
    >
      <InfoIcon className="mt-0.5 shrink-0" />
      <div>
        <p className="font-medium">
          {stale ? "Dữ liệu đã cũ" : "Dữ liệu chậm cập nhật"}
        </p>
        <p className="mt-0.5">
          Hệ thống vẫn hiển thị đầy đủ snapshot và lịch sử gần nhất; dữ liệu sẽ tự
          cập nhật khi tác vụ cloud hoàn tất.
        </p>
      </div>
    </div>
  );
}
