import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { EChartsOption } from "echarts";

import type { GdbRecord, PrizeKey, PrizeResults } from "../../types/gdb";
import { GapChart } from "./GapChart";
import { HistoryScatterChart } from "./HistoryScatterChart";
import { TransitionMatrixChart } from "./TransitionMatrixChart";

interface CapturedChart {
  option: EChartsOption;
  height?: number;
  ariaLabel: string;
}

const capturedCharts = vi.hoisted(() => [] as CapturedChart[]);

vi.mock("./EChart", () => ({
  EChart: (props: CapturedChart) => {
    capturedCharts.push(props);
    return <div role="img" aria-label={props.ariaLabel} />;
  },
}));

describe("advanced chart options", () => {
  beforeEach(() => {
    capturedCharts.length = 0;
  });

  it("renders scoped aggregated scatter points on a fixed 00-99 axis", () => {
    render(
      <HistoryScatterChart
        records={[
          record("2026-10-01", {
            db: ["99999"],
            g7: ["07", "107", "08", "09"],
          }),
        ]}
        scope="g7"
        theme="light"
      />,
    );

    const option = latestOption() as unknown as {
      yAxis: { min: number; max: number };
      series: Array<{
        data: Array<[number, number, number]>;
        symbolSize: (value: [number, number, number]) => number;
      }>;
      tooltip: { formatter: (params: { dataIndex: number }) => string };
    };
    const series = option.series[0];
    if (!series) throw new Error("Expected scatter series");

    expect(option.yAxis).toMatchObject({ min: 0, max: 99 });
    expect(series.data.map((point) => point[1])).toEqual([7, 8, 9]);
    expect(series.symbolSize([0, 7, 2])).toBeGreaterThan(series.symbolSize([0, 8, 1]));
    expect(option.tooltip.formatter({ dataIndex: 0 })).toContain("2 lần");
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("giải đang chọn");
  });

  it("renders all gap categories with current and maximum series", () => {
    render(
      <GapChart
        records={[record("2026-10-01", { g7: ["01", "02", "03", "04"] })]}
        scope="g7"
        theme="light"
      />,
    );

    const option = latestOption() as unknown as {
      xAxis: { data: string[] };
      dataZoom: Array<{ type: string; orient?: string }>;
      series: Array<{ name: string; type: string; data: number[] }>;
      tooltip: {
        formatter: (params: Array<{ dataIndex: number }>) => string;
      };
    };

    expect(option.xAxis.data).toHaveLength(100);
    expect(option.series.map((series) => series.name)).toEqual(["Hiện tại", "Lớn nhất"]);
    expect(option.series.every((series) => series.type === "bar")).toBe(true);
    expect(option.dataZoom.some((zoom) => zoom.type === "slider")).toBe(true);
    expect(option.tooltip.formatter([{ dataIndex: 99 }])).toContain("≥ 1 kỳ");
  });

  it("renders a 10x10 transition heatmap with count and row percentage", () => {
    render(
      <TransitionMatrixChart
        records={[record("2026-10-01", { g7: ["11", "12", "21"] })]}
        scope="g7"
        theme="dark"
      />,
    );

    const option = latestOption() as unknown as {
      xAxis: { data: string[] };
      yAxis: { data: string[] };
      series: Array<{ type: string; data: Array<[number, number, number, number]> }>;
      tooltip: {
        formatter: (params: { data: [number, number, number, number] }) => string;
      };
    };

    expect(option.xAxis.data).toEqual(["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]);
    expect(option.yAxis.data).toEqual(["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]);
    const series = option.series[0];
    if (!series) throw new Error("Expected transition heatmap series");
    expect(series).toMatchObject({ type: "heatmap" });
    expect(series.data).toHaveLength(100);
    expect(option.tooltip.formatter({ data: [2, 1, 100, 1] })).toContain("Số lần: 1");
    expect(option.tooltip.formatter({ data: [2, 1, 100, 1] })).toContain("100.00%");
  });
});

function latestOption(): EChartsOption {
  const captured = capturedCharts[capturedCharts.length - 1];
  if (!captured) throw new Error("Expected EChart to render");
  return captured.option;
}

function record(
  date: string,
  overrides: Partial<Record<PrizeKey, string[]>>,
): GdbRecord {
  const prizes: PrizeResults = {
    db: [],
    g1: [],
    g2: [],
    g3: [],
    g4: [],
    g5: [],
    g6: [],
    g7: [],
    ...overrides,
  };
  return {
    gdb: prizes.db[0]?.slice(-2) ?? null,
    prizes,
    drawComplete: true,
    date,
    dateLabel: `${date.slice(8, 10)}-${date.slice(5, 7)}`,
    dayName: "Thứ Năm",
    sourceUrl: `https://example.test/${date}`,
  };
}
