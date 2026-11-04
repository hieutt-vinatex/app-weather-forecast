import { memo, useMemo } from "react";
import type { EChartsOption } from "echarts";

import type { GdbRecord, PrizeScope } from "../../types/gdb";
import { buildGapStats } from "../../utils/advancedAnalytics";
import { chartTheme, palette } from "../../utils/chartTheme";
import type { Theme } from "../../utils/theme";
import { EChart } from "./EChart";

interface Props {
  records: GdbRecord[];
  scope: PrizeScope;
  theme: Theme;
}

function build(records: GdbRecord[], scope: PrizeScope, theme: Theme): EChartsOption {
  const t = chartTheme(theme);
  const stats = buildGapStats(records, scope);

  return {
    grid: { left: 44, right: 18, top: 42, bottom: 66 },
    legend: { top: 0, textStyle: { color: t.label } },
    tooltip: {
      trigger: "axis",
      backgroundColor: t.tooltipBg,
      borderColor: t.axisLine,
      textStyle: { color: t.tooltipText },
      formatter: (params: unknown) => {
        const items = params as Array<{ dataIndex: number }>;
        const stat = stats[items[0]?.dataIndex ?? -1];
        if (!stat) return "";
        const prefix = stat.observed ? "" : "≥ ";
        return `<b>Số ${stat.number}</b><br/>Hiện tại: ${prefix}${stat.currentGap} kỳ<br/>Lớn nhất: ${prefix}${stat.maxGap} kỳ`;
      },
    },
    xAxis: {
      type: "category",
      data: stats.map((stat) => stat.number),
      axisLabel: { color: t.label, fontSize: 10 },
      axisLine: { lineStyle: { color: t.axisLine } },
    },
    yAxis: {
      type: "value",
      min: 0,
      minInterval: 1,
      name: "Số kỳ",
      nameTextStyle: { color: t.label },
      axisLabel: { color: t.label },
      splitLine: { lineStyle: { color: t.splitLine } },
    },
    dataZoom: [
      { type: "inside", start: 0, end: 39 },
      { type: "slider", start: 0, end: 39, height: 16, bottom: 8 },
    ],
    series: [
      {
        name: "Hiện tại",
        type: "bar",
        data: stats.map((stat) => stat.currentGap),
        itemStyle: { color: palette.warning, borderRadius: [3, 3, 0, 0] },
        barMaxWidth: 14,
      },
      {
        name: "Lớn nhất",
        type: "bar",
        data: stats.map((stat) => stat.maxGap),
        itemStyle: { color: palette.blue, borderRadius: [3, 3, 0, 0] },
        barMaxWidth: 14,
      },
    ],
  };
}

export const GapChart = memo(function GapChart({ records, scope, theme }: Props): JSX.Element {
  const option = useMemo(() => build(records, scope, theme), [records, scope, theme]);
  return (
    <EChart
      option={option}
      themeKey={theme}
      height={320}
      ariaLabel="Biểu đồ khoảng cách xuất hiện hiện tại và lớn nhất của các số 00 đến 99 trong giải đang chọn"
    />
  );
});
