import { memo, useMemo } from "react";
import type { EChartsOption } from "echarts";

import type { GdbRecord, PrizeScope } from "../../types/gdb";
import { buildDigitTransitionMatrix } from "../../utils/advancedAnalytics";
import { chartTheme } from "../../utils/chartTheme";
import type { Theme } from "../../utils/theme";
import { EChart } from "./EChart";

interface Props {
  records: GdbRecord[];
  scope: PrizeScope;
  theme: Theme;
}

const DIGITS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];

function build(records: GdbRecord[], scope: PrizeScope, theme: Theme): EChartsOption {
  const t = chartTheme(theme);
  const data: Array<[number, number, number, number]> = buildDigitTransitionMatrix(
    records,
    scope,
  ).map((cell) => [cell.toDigit, cell.fromDigit, cell.rowPercentage, cell.count]);

  return {
    grid: { left: 46, right: 16, top: 18, bottom: 72 },
    tooltip: {
      position: "top",
      backgroundColor: t.tooltipBg,
      borderColor: t.axisLine,
      textStyle: { color: t.tooltipText },
      formatter: (params: unknown) => {
        const [toDigit, fromDigit, percentage, count] = (params as {
          data: [number, number, number, number];
        }).data;
        return `<b>${fromDigit} → ${toDigit}</b><br/>Số lần: ${count}<br/>Tỷ lệ theo hàng: ${percentage.toFixed(2)}%`;
      },
    },
    xAxis: {
      type: "category",
      data: DIGITS,
      name: "TO",
      nameLocation: "middle",
      nameGap: 28,
      nameTextStyle: { color: t.label, fontWeight: "bold" },
      axisLabel: { color: t.label },
      splitArea: { show: true },
    },
    yAxis: {
      type: "category",
      data: DIGITS,
      name: "FROM",
      nameTextStyle: { color: t.label, fontWeight: "bold" },
      axisLabel: { color: t.label },
      splitArea: { show: true },
    },
    visualMap: {
      min: 0,
      max: 100,
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      textStyle: { color: t.label },
      inRange: { color: ["#FFF7ED", "#FDBA74", "#C92A2A"] },
    },
    series: [
      {
        type: "heatmap",
        data,
        label: {
          show: true,
          color: theme === "dark" ? "#0f172a" : "#24272B",
          fontSize: 9,
          formatter: (params: unknown) => {
            const percentage = (params as { data: [number, number, number, number] }).data[2];
            return percentage > 0 ? `${percentage.toFixed(1)}%` : "";
          },
        },
        emphasis: { itemStyle: { shadowBlur: 6, shadowColor: "rgba(0,0,0,0.3)" } },
      },
    ],
  };
}

export const TransitionMatrixChart = memo(function TransitionMatrixChart({
  records,
  scope,
  theme,
}: Props): JSX.Element {
  const option = useMemo(() => build(records, scope, theme), [records, scope, theme]);
  return (
    <EChart
      option={option}
      themeKey={theme}
      height={380}
      ariaLabel="Ma trận chuyển tiếp 10 nhân 10 của chữ số cuối trong giải đang chọn, theo tỷ lệ chuyển tiếp từng hàng"
    />
  );
});
