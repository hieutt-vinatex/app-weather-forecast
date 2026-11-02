import { Card } from "./ui/Card";

const REPOSITORY_ACTIONS_URL =
  "https://github.com/hieutt-vinatex/app-weather-forecast/actions/workflows";

export function GitHubOperationsLinks(): JSX.Element {
  return (
    <section aria-labelledby="github-operations-title">
      <Card>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2
              id="github-operations-title"
              className="text-base font-semibold text-ink dark:text-slate-100"
            >
              Quản trị qua GitHub Actions
            </h2>
            <p className="mt-0.5 text-sm text-ink-soft dark:text-slate-400">
              Chạy thủ công tác vụ cập nhật hoặc gửi thông báo trong trang Actions.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <a
              href={`${REPOSITORY_ACTIONS_URL}/data-sync.yml`}
              target="_blank"
              rel="noreferrer"
              className="rounded-lg border border-line px-3 py-2 text-sm font-medium text-ink transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-brand dark:border-slate-600 dark:text-slate-100 dark:hover:bg-slate-700"
            >
              Làm mới dữ liệu
            </a>
            <a
              href={`${REPOSITORY_ACTIONS_URL}/telegram.yml`}
              target="_blank"
              rel="noreferrer"
              className="rounded-lg bg-brand px-3 py-2 text-sm font-medium text-white transition hover:bg-brand-dark focus:outline-none focus:ring-2 focus:ring-brand focus:ring-offset-2 dark:focus:ring-offset-slate-800"
            >
              Gửi Telegram ngay
            </a>
          </div>
        </div>
      </Card>
    </section>
  );
}
