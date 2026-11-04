import { useDaysParam } from "../../hooks/useDaysParam";
import { useGdbSnapshot } from "../../hooks/useGdbSnapshot";
import { usePageActivity } from "../../hooks/usePageActivity";
import { usePrizeParam } from "../../hooks/usePrizeParam";
import { formatPercent } from "../../utils/format";
import { prizeLabel } from "../../utils/prizes";
import { useTheme } from "../../utils/theme";

import { PartialWarning, StaleWarning } from "../../components/Alerts";
import { AbsenceMonitor } from "../../components/AbsenceMonitor";
import { AdvancedAnalyticsSection } from "../../components/AdvancedAnalyticsSection";
import { Disclaimer } from "../../components/Disclaimer";
import { GitHubOperationsLinks } from "../../components/GitHubOperationsLinks";
import { HistoryTable } from "../../components/HistoryTable";
import { KpiCards } from "../../components/KpiCards";
import { ColdNumbersList, TopNumbersList } from "../../components/NumberLists";
import { PrizeNavigation } from "../../components/PrizeNavigation";
import { PrizeResultsBoard } from "../../components/PrizeResultsBoard";
import { DashboardSkeleton } from "../../components/Skeletons";
import { DigitBarChart } from "../../components/charts/DigitBarChart";
import { EvenOddDonut } from "../../components/charts/EvenOddDonut";
import { FrequencyBarChart } from "../../components/charts/FrequencyBarChart";
import { FrequencyHeatmap } from "../../components/charts/FrequencyHeatmap";
import { FrequencyTrendChart } from "../../components/charts/FrequencyTrendChart";
import { SectionCard } from "../../components/ui/Card";
import { effectiveFreshnessStatus, freshnessLabel } from "../../utils/freshness";
import { DashboardHeader } from "./DashboardHeader";

export function Dashboard(): JSX.Element {
  const [days, setDays] = useDaysParam();
  const [prizeScope, setPrizeScope] = usePrizeParam();
  const { theme } = useTheme();

  const activity = usePageActivity();
  const query = useGdbSnapshot(days);

  const data = query.data;
  const freshness = data
    ? effectiveFreshnessStatus({
        serverStatus: data.meta.freshnessStatus,
        generatedAt: data.meta.generatedAt,
        online: activity.online,
        requestFailed: query.isError,
      })
    : activity.online
      ? "updating"
      : "offline";

  const statistics = data
    ? prizeScope === "all"
      ? data.statistics
      : data.statisticsByPrize[prizeScope]
    : undefined;
  const latest = data?.data[data.data.length - 1];
  const scopeLabel = prizeLabel(prizeScope);

  return (
    <div className="min-h-screen bg-surface-bg text-ink dark:bg-slate-900 dark:text-slate-100">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:text-ink focus:shadow"
      >
        Bỏ qua tới nội dung chính
      </a>

      <div className="mx-auto max-w-[1480px] space-y-4 px-3 py-4 sm:px-6 sm:py-6">
        <DashboardHeader
          meta={data?.meta}
          freshness={freshness}
          sourceReferenceDate={latest?.date}
          days={days}
          onDaysChange={setDays}
        />

        <GitHubOperationsLinks />

        <main id="main">
          {query.isError && !data ? (
            <ErrorState onRetry={() => query.refetch()} />
          ) : !data || !statistics ? (
            <DashboardSkeleton />
          ) : (
            <>
              <StaleWarning meta={data.meta} />
              <PartialWarning meta={data.meta} />

              <AbsenceMonitor
                records={data.data}
                frequencies={data.statistics.frequencies}
                meta={data.meta}
                theme={theme}
              />

              <div className="mt-4 grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[11rem_minmax(0,1fr)]">
                <aside className="min-w-0 lg:sticky lg:top-4 lg:self-start">
                  <PrizeNavigation value={prizeScope} onChange={setPrizeScope} />
                </aside>

                <div className="min-w-0 space-y-4">
                  {latest ? (
                    <SectionCard
                      title={`Kết quả mới nhất · ${scopeLabel}`}
                      description="Giữ nguyên số đầy đủ từ nguồn; hai số cuối được tô màu vì là đơn vị dùng trong thống kê."
                    >
                      <PrizeResultsBoard record={latest} scope={prizeScope} showHeader />
                    </SectionCard>
                  ) : null}

                  <KpiCards stats={statistics} statusHint={freshnessLabel(freshness)} />

                  <div className="grid gap-4 xl:grid-cols-2">
                    <SectionCard
                      title={`Tần suất 00–99 · ${scopeLabel}`}
                      description={`Số lần xuất hiện trong ${days} ngày. Mẫu số hiện tại: ${statistics.totalResults.toLocaleString("vi-VN")} số.`}
                    >
                      <FrequencyBarChart
                        frequencies={statistics.frequencies}
                        topNumbers={statistics.topNumbers}
                        theme={theme}
                      />
                    </SectionCard>

                    <SectionCard
                      title="Nhịp xuất hiện trong 7 kỳ"
                      description="Đường lăn 7 kỳ của 5 số phổ biến nhất trong phạm vi đang chọn."
                    >
                      <FrequencyTrendChart
                        records={data.data}
                        scope={prizeScope}
                        topNumbers={statistics.topNumbers}
                        theme={theme}
                      />
                    </SectionCard>
                  </div>

                  <div className="grid gap-4 xl:grid-cols-[1.08fr_0.92fr]">
                    <SectionCard
                      title={`Bản đồ nhiệt 00–99 · ${scopeLabel}`}
                      description="Hàng là chữ số hàng chục, cột là hàng đơn vị; ô đậm hơn xuất hiện nhiều hơn."
                    >
                      <FrequencyHeatmap frequencies={statistics.frequencies} theme={theme} />
                    </SectionCard>

                    <div className="space-y-4">
                      <SectionCard
                        title="Tần suất từng chữ số"
                        description="So sánh chữ số ở hàng chục và hàng đơn vị của các số đuôi."
                      >
                        <DigitBarChart
                          tens={statistics.tensDigitFrequency}
                          units={statistics.unitsDigitFrequency}
                          theme={theme}
                        />
                      </SectionCard>

                      <SectionCard
                        title="Cơ cấu chẵn / lẻ"
                        description={`Chẵn ${formatPercent(statistics.evenOdd.evenPercentage)} · Lẻ ${formatPercent(statistics.evenOdd.oddPercentage)}`}
                      >
                        <EvenOddDonut evenOdd={statistics.evenOdd} theme={theme} />
                      </SectionCard>
                    </div>
                  </div>

                  <div className="grid gap-4 xl:grid-cols-2">
                    <SectionCard
                      title="Xuất hiện nhiều"
                      description="Top 10 số đuôi theo số lần xuất hiện, có ngày gần nhất để đối chiếu."
                    >
                      <TopNumbersList items={statistics.topNumbers} />
                    </SectionCard>
                    <SectionCard
                      title="Ít / chưa xuất hiện"
                      description="Các số đuôi có tần suất thấp nhất trong phạm vi và giải đang chọn."
                    >
                      <ColdNumbersList items={statistics.coldNumbers} />
                    </SectionCard>
                  </div>

                  <AdvancedAnalyticsSection
                    records={data.data}
                    scope={prizeScope}
                    scopeLabel={scopeLabel}
                    theme={theme}
                  />

                  <SectionCard
                    title={`Lịch sử từng kỳ · ${scopeLabel}`}
                    description="Kết quả đầy đủ theo ngày, sắp xếp từ mới nhất; đổi menu giải để thu gọn từng hàng."
                  >
                    <HistoryTable records={data.data} scope={prizeScope} />
                  </SectionCard>
                </div>
              </div>
            </>
          )}

          <Disclaimer />
        </main>
      </div>
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }): JSX.Element {
  return (
    <div
      role="alert"
      className="rounded-xl2 border border-rose-300 bg-rose-50 p-8 text-center dark:border-rose-800 dark:bg-rose-900/20"
    >
      <p className="text-lg font-semibold text-rose-800 dark:text-rose-200">
        Không tải được dữ liệu
      </p>
      <p className="mt-1 text-sm text-rose-700 dark:text-rose-300">
        Nguồn dữ liệu có thể tạm thời không phản hồi.
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 rounded-full bg-lotto-red px-5 py-2 text-sm font-medium text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lotto-red"
      >
        Thử lại
      </button>
    </div>
  );
}
