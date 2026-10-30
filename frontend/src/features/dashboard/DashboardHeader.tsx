import type { FreshnessStatus, Meta } from "../../types/gdb";
import type { RangeDays } from "../../config";
import { RangeSelector } from "../../components/RangeSelector";
import { StatusBadge } from "../../components/StatusBadge";
import { ThemeToggle } from "../../components/ThemeToggle";
import { formatIsoDate, formatVietnamDateTime } from "../../utils/format";

interface Props {
  meta: Meta | undefined;
  freshness: FreshnessStatus;
  sourceReferenceDate: string | undefined;
  days: RangeDays;
  onDaysChange: (d: RangeDays) => void;
}

export function DashboardHeader({
  meta,
  freshness,
  sourceReferenceDate,
  days,
  onDaysChange,
}: Props): JSX.Element {
  return (
    <header className="overflow-hidden rounded-xl3 border border-line bg-surface-card shadow-card dark:border-slate-700 dark:bg-slate-800/70">
      <div className="h-1 bg-lotto-red" />
      <div className="p-4 sm:p-6">
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <div
                className="grid h-11 w-11 shrink-0 place-items-center rounded-xl2 bg-lotto-red text-sm font-black tracking-tight text-white shadow-lg shadow-red-900/20"
                style={{ backgroundColor: "#C92A2A", color: "#FFFFFF" }}
              >
                XSMB
              </div>
              <div className="min-w-0">
                <h1 className="text-lg sm:text-xl font-bold text-ink dark:text-slate-100">
                  Kết quả & thống kê XSMB
                </h1>
                <p className="text-sm text-ink-soft dark:text-slate-400">
                  Đầy đủ ĐB, G1–G7 · tự động cập nhật từ cloud
                </p>
              </div>
            </div>

            <dl className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-2 text-xs">
              <MetaItem
                label="Cập nhật lúc"
                value={formatVietnamDateTime(meta?.generatedAt ?? null)}
              />
              <MetaItem
                label="Kỳ dữ liệu gần nhất"
                value={sourceReferenceDate ? formatIsoDate(sourceReferenceDate) : "—"}
              />
              <MetaItem
                label="Nguồn dữ liệu"
                value={
                  meta
                    ? `${meta.source}${meta.cached ? " · cache" : ""}${meta.stale ? " · lưu tạm" : ""}`
                    : "—"
                }
              />
              <MetaItem label="Tác vụ gần nhất" value={meta?.lastJobStatus ?? "—"} />
            </dl>
          </div>

          <div className="flex w-full min-w-0 flex-col items-start gap-3 lg:w-auto lg:items-end">
            <div className="flex items-center gap-2">
              <StatusBadge status={freshness} />
              <ThemeToggle />
            </div>
            <div className="flex w-full max-w-full flex-wrap items-center justify-start gap-3 lg:w-auto lg:justify-end">
              <RangeSelector value={days} onChange={onDaysChange} />
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

function MetaItem({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div>
      <dt className="text-ink-soft dark:text-slate-500">{label}</dt>
      <dd className="font-medium text-ink dark:text-slate-200 tabular-nums">{value}</dd>
    </div>
  );
}
