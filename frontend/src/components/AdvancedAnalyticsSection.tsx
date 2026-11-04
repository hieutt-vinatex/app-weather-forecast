import { useId, useState } from "react";

import type { GdbRecord, PrizeScope } from "../types/gdb";
import type { Theme } from "../utils/theme";
import { GapChart } from "./charts/GapChart";
import { HistoryScatterChart } from "./charts/HistoryScatterChart";
import { TransitionMatrixChart } from "./charts/TransitionMatrixChart";
import { Card, SectionCard } from "./ui/Card";

interface AdvancedAnalyticsSectionProps {
  records: GdbRecord[];
  scope: PrizeScope;
  scopeLabel: string;
  theme: Theme;
}

export function AdvancedAnalyticsSection(
  props: AdvancedAnalyticsSectionProps,
): JSX.Element {
  const [isOpen, setIsOpen] = useState(false);
  const panelId = useId();

  return (
    <Card as="section">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-ink dark:text-slate-100">
            Phân tích nâng cao · {props.scopeLabel}
          </h2>
          <p className="mt-0.5 text-sm text-ink-soft dark:text-slate-400">
            Mở khi cần xem khoảng cách, phân tán và ma trận chuyển tiếp.
          </p>
        </div>
        <button
          type="button"
          aria-expanded={isOpen}
          aria-controls={panelId}
          onClick={() => setIsOpen((value) => !value)}
          className="rounded-full border border-line px-4 py-2 text-sm font-medium text-ink transition-colors hover:border-lotto-red hover:text-lotto-red focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lotto-red dark:border-slate-600 dark:text-slate-100"
        >
          {isOpen ? "Đóng phân tích" : "Mở phân tích"}
        </button>
      </div>

      {isOpen ? (
        <div id={panelId} className="mt-4 space-y-4">
          <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-2">
            <SectionCard
              title="Khoảng cách xuất hiện 00–99"
              description="So sánh số kỳ chưa xuất hiện hiện tại với khoảng vắng lớn nhất trong phạm vi."
              className="min-w-0 overflow-hidden"
            >
              <GapChart records={props.records} scope={props.scope} theme={props.theme} />
            </SectionCard>

            <SectionCard
              title="Phân tán theo kỳ"
              description="Mỗi điểm là một số đuôi theo ngày; điểm lớn hơn biểu thị kết quả trùng trong cùng kỳ."
              className="min-w-0 overflow-hidden"
            >
              <HistoryScatterChart
                records={props.records}
                scope={props.scope}
                theme={props.theme}
              />
            </SectionCard>
          </div>

          <SectionCard
            title="Ma trận chuyển tiếp chữ số cuối 0–9"
            description="Hàng là chữ số trước, cột là chữ số sau; màu thể hiện tỷ lệ chuyển tiếp trong từng hàng."
            className="min-w-0 overflow-hidden"
          >
            <TransitionMatrixChart
              records={props.records}
              scope={props.scope}
              theme={props.theme}
            />
          </SectionCard>
        </div>
      ) : null}
    </Card>
  );
}
