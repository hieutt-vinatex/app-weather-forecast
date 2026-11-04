import { memo, useMemo } from "react";
import type { EChartsOption } from "echarts";

import { EChart } from "./EChart";
import type { GdbRecord, PrizeScope } from "../../types/gdb";
import { buildScatterPoints } from "../../utils/advancedAnalytics";
import type { Theme } from "../../utils/theme";
import { chartTheme } from "../../utils/chartTheme";

interface Props {
  records: GdbRecord[];
  scope: PrizeScope;
  theme: Theme;
}

function build(records: GdbRecord[], scope: PrizeScope, theme: Theme): EChartsOption {
  const t = chartTheme(theme);
  const sortedRecords = [...records].sort((a, b) => a.date.localeCompare(b.date));
  const categories = sortedRecords.map((record) => record.dateLabel);
  const dateIndexes = new Map(sortedRecords.map((record, index) => [record.date, index]));
  const points = buildScatterPoints(records, scope);

  return {
    grid: { left: 44, right: 16, top: 20, bottom: 50 },
    tooltip: {
      trigger: "item",
      backgroundColor: t.tooltipBg,
      borderColor: t.axisLine,
      textStyle: { color: t.tooltipText },
      formatter: (params: unknown) => {
        const p = params as { dataIndex: number };
        const point = points[p.dataIndex];
        if (!point) return "";
        return `<b>${point.dayName}</b><br/>Ngày: ${point.dateLabel}<br/>Số: <b>${point.number}</b><br/>Xuất hiện: ${point.count} lần`;
      },
    },
    xAxis: {
      type: "category",
      data: categories,
      axisLabel: { color: t.label, interval: Math.max(0, Math.floor(records.length / 12)), fontSize: 10 },
      axisLine: { lineStyle: { color: t.axisLine } },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 99,
      name: "00–99",
      nameTextStyle: { color: t.label },
      axisLabel: { color: t.label },
      splitLine: { lineStyle: { color: t.splitLine } },
    },
    series: [
      {
        type: "scatter",
        symbolSize: (value: unknown) => {
          const count = (value as [number, number, number])[2] ?? 1;
          return 7 + Math.min(4, count - 1) * 2;
        },
        data: points.map((point) => [
          dateIndexes.get(point.date) ?? 0,
          point.value,
          point.count,
        ]),
        itemStyle: { color: t.scatter, opacity: 0.85 },
      },
    ],
  };
}

export const HistoryScatterChart = memo(function HistoryScatterChart({
  records,
  scope,
  theme,
}: Props): JSX.Element {
  const option = useMemo(() => build(records, scope, theme), [records, scope, theme]);
  return (
    <EChart
      option={option}
      themeKey={theme}
      height={300}
      ariaLabel="Biểu đồ phân tán kết quả của giải đang chọn theo từng ngày. Kích thước điểm biểu thị số lần trùng, không thể hiện xu hướng dự đoán."
    />
  );
});
