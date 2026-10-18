import { useEffect, useMemo, useState } from "react";

import { useAbsenceNotifications } from "../hooks/useAbsenceNotifications";
import { useSendAbsenceNotification } from "../hooks/useSendAbsenceNotification";
import type { FrequencyItem, GdbRecord, Meta } from "../types/gdb";
import {
  buildAbsenceStatuses,
  filterAbsenceStatuses,
  type AbsenceStatus,
} from "../utils/absence";
import { classNames, formatIsoDate } from "../utils/format";
import type { Theme } from "../utils/theme";
import { AbsenceTimelineChart } from "./charts/AbsenceTimelineChart";
import { Card } from "./ui/Card";

const ALL_NUMBERS = Array.from({ length: 100 }, (_, index) => String(index).padStart(2, "0"));

interface Props {
  records: GdbRecord[];
  frequencies: FrequencyItem[];
  meta: Meta;
  theme: Theme;
}

export function AbsenceMonitor({ records, frequencies, meta, theme }: Props): JSX.Element | null {
  const [minDays, setMinDays] = useState(19);
  const [maxDays, setMaxDays] = useState(25);
  const [notificationAdminToken, setNotificationAdminToken] = useState("");
  const immediateNotification = useSendAbsenceNotification();
  const referenceDate = records[records.length - 1]?.date ?? "";
  const coverageStartDate = records[0]?.date ?? referenceDate;
  const statuses = useMemo(
    () =>
      referenceDate
        ? buildAbsenceStatuses(frequencies, referenceDate, coverageStartDate)
        : [],
    [coverageStartDate, frequencies, referenceDate],
  );
  const candidates = useMemo(
    () => filterAbsenceStatuses(statuses, minDays, maxDays),
    [maxDays, minDays, statuses],
  );
  const [selectedNumber, setSelectedNumber] = useState(
    () => candidates[0]?.number ?? statuses[0]?.number ?? "00",
  );

  useEffect(() => {
    if (candidates.length > 0 && !statuses.some((item) => item.number === selectedNumber)) {
      setSelectedNumber(candidates[0]?.number ?? "00");
    }
  }, [candidates, selectedNumber, statuses]);

  const notifications = useAbsenceNotifications({
    candidates,
    referenceDate,
    minDays,
    maxDays,
  });
  const statusByNumber = useMemo(
    () => new Map(statuses.map((status) => [status.number, status])),
    [statuses],
  );
  const selectedStatus = statusByNumber.get(selectedNumber);
  const longestExact = statuses.reduce(
    (max, item) => Math.max(max, item.daysAbsent ?? 0),
    0,
  );

  if (!referenceDate) return null;

  return (
    <Card as="section" className="mt-4 border-amber-200 dark:border-amber-900/70">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <h2 className="text-lg font-semibold text-ink dark:text-slate-100">
            Theo dõi số chưa xuất hiện · ĐB + G1–G7
          </h2>
          <p className="mt-1 text-sm text-ink-soft dark:text-slate-400">
            “Số ngày chưa xuất hiện” là số ngày lịch kể từ lần gần nhất hai số cuối xuất
            hiện ở bất kỳ giải nào. Mặc định lọc từ ngày 19 đến ngày 25, tính đến kỳ {" "}
            {formatIsoDate(referenceDate)}.
          </p>
        </div>

        <div className="flex flex-wrap items-end gap-2" aria-label="Bộ lọc số ngày chưa xuất hiện">
          <DayInput
            label="Từ ngày"
            value={minDays}
            onChange={(value) => setMinDays(Math.min(value, maxDays))}
          />
          <DayInput
            label="Đến ngày"
            value={maxDays}
            onChange={(value) => setMaxDays(Math.max(value, minDays))}
          />
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Metric label={`Trong khoảng ${minDays}–${maxDays} ngày`} value={String(candidates.length)} />
        <Metric label="Gan dài nhất xác định được" value={`${longestExact} ngày`} />
        <Metric
          label="Kỳ dữ liệu gần nhất"
          value={formatIsoDate(referenceDate)}
          note={meta.partial ? "Dữ liệu đang thiếu; kết quả có thể thay đổi." : "Đã thu thập đủ các kỳ trong phạm vi."}
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(18rem,0.65fr)]">
        <div className="rounded-xl border border-line p-3 dark:border-slate-700">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-ink dark:text-slate-100">Bản đồ 00–99</h3>
              <p className="text-xs text-ink-soft dark:text-slate-400">
                Chọn một số để xem diễn biến theo ngày. “≥” nghĩa là chưa thấy trong toàn bộ phạm vi dữ liệu.
              </p>
            </div>
            <div className="flex flex-wrap gap-3 text-xs text-ink-soft dark:text-slate-400">
              <Legend swatch="bg-amber-400" label={`${minDays}–${maxDays} ngày`} />
              <Legend swatch="bg-rose-500" label={`Trên ${maxDays} ngày`} />
              <Legend swatch="bg-slate-300 dark:bg-slate-600" label="Dưới ngưỡng" />
            </div>
          </div>
          <div className="grid grid-cols-5 gap-1.5 sm:grid-cols-10">
            {ALL_NUMBERS.map((number) => {
              const status = statusByNumber.get(number);
              return (
                <NumberCell
                  key={number}
                  status={status}
                  selected={number === selectedNumber}
                  minDays={minDays}
                  maxDays={maxDays}
                  onClick={() => setSelectedNumber(number)}
                />
              );
            })}
          </div>
        </div>

        <div className="rounded-xl border border-line p-4 dark:border-slate-700">
          <h3 className="text-sm font-semibold text-ink dark:text-slate-100">
            Thông báo trình duyệt lúc 09:00 sáng hôm sau
          </h3>
          <p className="mt-1 text-xs leading-5 text-ink-soft dark:text-slate-400">
            Gửi thông báo trình duyệt một lần cho mỗi kỳ nếu có số nằm trong khoảng {minDays}–{maxDays} ngày.
            Trình duyệt cần đang mở. Telegram, Zalo và Facebook được cấu hình riêng trên backend.
          </p>
          <dl className="mt-3 space-y-2 text-sm">
            <StatusRow label="Trạng thái" value={notifications.enabled ? "Đang bật" : "Đang tắt"} />
            <StatusRow
              label="Quyền trình duyệt"
              value={permissionLabel(notifications.permission)}
            />
            <StatusRow
              label="Mốc cảnh báo kỳ này"
              value={formatSchedule(notifications.scheduledAt)}
            />
            {notifications.lastSentAt ? (
              <StatusRow label="Đã gửi gần nhất" value={formatDateTime(notifications.lastSentAt)} />
            ) : null}
          </dl>
          <button
            type="button"
            onClick={() => {
              if (notifications.enabled) notifications.disable();
              else void notifications.enable();
            }}
            className={classNames(
              "mt-4 w-full rounded-lg px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2",
              notifications.enabled
                ? "border border-line text-ink hover:bg-slate-50 focus-visible:outline-slate-500 dark:border-slate-600 dark:text-slate-100 dark:hover:bg-slate-700"
                : "bg-lotto-red text-white hover:bg-red-700 focus-visible:outline-lotto-red",
            )}
          >
            {notifications.enabled ? "Tắt thông báo" : "Bật thông báo 09:00"}
          </button>
          {notifications.permission === "denied" ? (
            <p className="mt-2 text-xs text-state-danger">
              Quyền thông báo đang bị chặn trong cài đặt trình duyệt.
            </p>
          ) : null}

          <div className="mt-4 border-t border-line pt-4 dark:border-slate-700">
            <h4 className="text-sm font-semibold text-ink dark:text-slate-100">
              Gửi thông báo qua backend ngay
            </h4>
            <p id="send-now-help" className="mt-1 text-xs leading-5 text-ink-soft dark:text-slate-400">
              Làm mới dữ liệu và gửi báo cáo các số chưa xuất hiện từ 19–25 ngày đến
              Telegram, Zalo hoặc Facebook đã cấu hình. Khóa chỉ được giữ trong bộ nhớ
              của trang hiện tại.
            </p>
            <form
              className="mt-3 space-y-2"
              onSubmit={(event) => {
                event.preventDefault();
                if (notificationAdminToken.trim()) {
                  void immediateNotification.send(notificationAdminToken);
                }
              }}
            >
              <label className="block text-xs font-medium text-ink-soft dark:text-slate-400">
                Khóa quản trị thông báo
                <input
                  type="password"
                  value={notificationAdminToken}
                  onChange={(event) => setNotificationAdminToken(event.target.value)}
                  aria-describedby="send-now-help"
                  autoComplete="off"
                  placeholder="NOTIFICATION_ADMIN_TOKEN"
                  className="mt-1 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink outline-none focus:border-lotto-red focus:ring-2 focus:ring-red-100 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:focus:ring-red-900/30"
                />
              </label>
              <button
                type="submit"
                disabled={
                  immediateNotification.isSending || !notificationAdminToken.trim()
                }
                className="w-full rounded-lg bg-lotto-red px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lotto-red"
              >
                {immediateNotification.isSending
                  ? "Đang tính và gửi…"
                  : "Gửi thông báo 19–25 ngày ngay"}
              </button>
            </form>
            {immediateNotification.message ? (
              <p
                role={immediateNotification.isError ? "alert" : "status"}
                className={classNames(
                  "mt-2 text-xs",
                  immediateNotification.isError
                    ? "text-state-danger"
                    : "text-state-success",
                )}
              >
                {immediateNotification.message}
              </p>
            ) : null}
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(22rem,0.75fr)]">
        <div className="min-w-0 rounded-xl border border-line p-3 dark:border-slate-700">
          <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-ink dark:text-slate-100">
                Diễn biến số {selectedNumber} theo từng ngày
              </h3>
              <p className="text-xs text-ink-soft dark:text-slate-400">
                {selectedStatus?.lastSeen
                  ? `Lần gần nhất: ${formatIsoDate(selectedStatus.lastSeen)} · hiện tại ${selectedStatus.daysAbsent} ngày.`
                  : `Chưa thấy trong phạm vi; ít nhất ${selectedStatus?.lowerBoundDays ?? 0} ngày.`}
              </p>
            </div>
            <label className="flex items-center gap-2 text-xs text-ink-soft dark:text-slate-400">
              Chọn số
              <select
                value={selectedNumber}
                onChange={(event) => setSelectedNumber(event.target.value)}
                className="rounded-lg border border-line bg-white px-2 py-1.5 text-sm font-semibold text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-lotto-red dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              >
                {ALL_NUMBERS.map((number) => (
                  <option key={number} value={number}>{number}</option>
                ))}
              </select>
            </label>
          </div>
          <AbsenceTimelineChart
            records={records}
            number={selectedNumber}
            minDays={minDays}
            maxDays={maxDays}
            theme={theme}
          />
        </div>

        <div className="min-w-0 rounded-xl border border-line p-3 dark:border-slate-700">
          <h3 className="text-sm font-semibold text-ink dark:text-slate-100">
            Danh sách cần theo dõi ({candidates.length})
          </h3>
          <p className="mt-0.5 text-xs text-ink-soft dark:text-slate-400">
            Sắp theo số ngày chưa xuất hiện giảm dần; bấm một hàng để mở biểu đồ.
          </p>
          <div className="mt-3 max-h-[300px] overflow-auto">
            {candidates.length === 0 ? (
              <p className="rounded-lg bg-slate-50 p-4 text-sm text-ink-soft dark:bg-slate-900/50 dark:text-slate-400">
                Không có số nào nằm trong khoảng đã chọn.
              </p>
            ) : (
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-surface-card text-xs text-ink-soft dark:bg-slate-800 dark:text-slate-400">
                  <tr>
                    <th className="px-2 py-2 font-medium">Số</th>
                    <th className="px-2 py-2 font-medium">Chưa xuất hiện</th>
                    <th className="px-2 py-2 font-medium">Lần gần nhất</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line dark:divide-slate-700">
                  {candidates.map((item) => (
                    <tr
                      key={item.number}
                      tabIndex={0}
                      role="button"
                      onClick={() => setSelectedNumber(item.number)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelectedNumber(item.number);
                        }
                      }}
                      className="cursor-pointer hover:bg-amber-50 focus:bg-amber-50 focus:outline-none dark:hover:bg-amber-900/20 dark:focus:bg-amber-900/20"
                    >
                      <td className="px-2 py-2 font-bold tabular-nums text-lotto-red">{item.number}</td>
                      <td className="px-2 py-2 tabular-nums">{item.daysAbsent} ngày</td>
                      <td className="px-2 py-2 tabular-nums text-ink-soft dark:text-slate-400">
                        {item.lastSeen ? formatIsoDate(item.lastSeen) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

function DayInput({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }): JSX.Element {
  return (
    <label className="text-xs font-medium text-ink-soft dark:text-slate-400">
      {label}
      <span className="mt-1 flex items-center rounded-lg border border-line bg-white px-2 dark:border-slate-600 dark:bg-slate-800">
        <input
          type="number"
          min={1}
          max={90}
          value={value}
          onChange={(event) => onChange(clampDays(Number(event.target.value)))}
          className="w-14 bg-transparent py-1.5 text-right text-sm font-semibold tabular-nums text-ink outline-none dark:text-slate-100"
        />
        <span className="ml-1">ngày</span>
      </span>
    </label>
  );
}

function clampDays(value: number): number {
  if (!Number.isFinite(value)) return 1;
  return Math.min(90, Math.max(1, Math.round(value)));
}

function Metric({ label, value, note }: { label: string; value: string; note?: string }): JSX.Element {
  return (
    <div className="rounded-xl bg-slate-50 px-4 py-3 dark:bg-slate-900/50">
      <p className="text-xs text-ink-soft dark:text-slate-400">{label}</p>
      <p className="mt-1 text-xl font-bold tabular-nums text-ink dark:text-slate-100">{value}</p>
      {note ? <p className="mt-1 text-xs text-ink-soft dark:text-slate-500">{note}</p> : null}
    </div>
  );
}

function NumberCell({
  status,
  selected,
  minDays,
  maxDays,
  onClick,
}: {
  status: AbsenceStatus | undefined;
  selected: boolean;
  minDays: number;
  maxDays: number;
  onClick: () => void;
}): JSX.Element {
  const days = status?.daysAbsent;
  const inBand = days !== null && days !== undefined && days >= minDays && days <= maxDays;
  const overBand = days !== null && days !== undefined && days > maxDays;
  const value = days === null || days === undefined ? `≥${status?.lowerBoundDays ?? 0}` : String(days);

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      aria-label={`Số ${status?.number ?? ""}, chưa xuất hiện ${value} ngày`}
      className={classNames(
        "min-h-14 rounded-lg border px-1 py-1 text-center transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-lotto-red",
        selected && "ring-2 ring-lotto-red ring-offset-1 dark:ring-offset-slate-800",
        inBand && "border-amber-500 bg-amber-100 text-amber-950 dark:bg-amber-900/40 dark:text-amber-100",
        overBand && "border-rose-500 bg-rose-100 text-rose-950 dark:bg-rose-900/35 dark:text-rose-100",
        !inBand && !overBand && "border-line bg-slate-50 text-ink dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-100",
      )}
    >
      <span className="block text-sm font-bold tabular-nums">{status?.number}</span>
      <span className="block text-[10px] tabular-nums opacity-75">{value} ngày</span>
    </button>
  );
}

function Legend({ swatch, label }: { swatch: string; label: string }): JSX.Element {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={classNames("h-2.5 w-2.5 rounded-sm", swatch)} />
      {label}
    </span>
  );
}

function StatusRow({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-ink-soft dark:text-slate-400">{label}</dt>
      <dd className="text-right font-medium text-ink dark:text-slate-200">{value}</dd>
    </div>
  );
}

function permissionLabel(permission: NotificationPermission | "unsupported"): string {
  return {
    granted: "Đã cho phép",
    denied: "Đã chặn",
    default: "Chưa hỏi",
    unsupported: "Không hỗ trợ",
  }[permission];
}

function formatSchedule(value: Date | null): string {
  if (!value) return "Chưa có dữ liệu";
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(value);
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

