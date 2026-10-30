import type { FreshnessStatus } from "../types/gdb";
import { classNames } from "../utils/format";
import { freshnessLabel } from "../utils/freshness";
import { OfflineIcon, OnlineIcon, ReconnectIcon, WarningIcon } from "./Icons";

interface StatusBadgeProps {
  status: FreshnessStatus;
}

const STYLES: Record<FreshnessStatus, string> = {
  current: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:border-emerald-800",
  updating: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-900/30 dark:text-sky-300 dark:border-sky-800",
  delayed: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800",
  stale: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/30 dark:text-rose-300 dark:border-rose-800",
  offline: "bg-slate-100 text-slate-700 border-slate-300 dark:bg-slate-900/50 dark:text-slate-300 dark:border-slate-700",
};

/** Data freshness status — always text + icon (never color-only). */
export function StatusBadge({ status }: StatusBadgeProps): JSX.Element {
  const Icon =
    status === "current"
      ? OnlineIcon
      : status === "offline"
        ? OfflineIcon
        : status === "updating"
          ? ReconnectIcon
          : WarningIcon;

  return (
    <span
      role="status"
      aria-live="polite"
      className={classNames(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        STYLES[status],
      )}
    >
      <span className="relative flex items-center">
        <Icon width={14} height={14} />
        {status === "updating" ? (
          <span className="motion-safe:animate-ping absolute -right-1 -top-1 h-1.5 w-1.5 rounded-full bg-sky-500" />
        ) : null}
      </span>
      {freshnessLabel(status)}
    </span>
  );
}
