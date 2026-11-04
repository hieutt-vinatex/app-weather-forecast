import { describe, expect, it } from "vitest";

import type { GdbRecord, PrizeKey, PrizeResults } from "../types/gdb";
import {
  buildDigitTransitionMatrix,
  buildGapStats,
  buildScatterPoints,
} from "./advancedAnalytics";

describe("advanced analytics", () => {
  describe("buildScatterPoints", () => {
    it("aggregates duplicate scoped results by chronological draw", () => {
      const earlierRecord = record("2026-10-01", { g7: ["02", "03", "04", "05"] });
      const laterRecord = record("2026-10-02", { g7: ["07", "107", "08", "09"] });

      const points = buildScatterPoints([laterRecord, earlierRecord], "g7");

      expect(points.map((point) => point.date)).toEqual([
        "2026-10-01",
        "2026-10-01",
        "2026-10-01",
        "2026-10-01",
        "2026-10-02",
        "2026-10-02",
        "2026-10-02",
      ]);
      expect(points.find((point) => point.date === "2026-10-02" && point.number === "07"))
        .toEqual({
          date: "2026-10-02",
          dateLabel: "02-10",
          dayName: "Thứ Sáu",
          number: "07",
          value: 7,
          count: 2,
        });
    });

    it("does not leak results from another prize", () => {
      const points = buildScatterPoints(
        [record("2026-10-01", { db: ["99999"], g7: ["07", "08", "09", "10"] })],
        "db",
      );

      expect(points).toEqual([
        {
          date: "2026-10-01",
          dateLabel: "01-10",
          dayName: "Thứ Năm",
          number: "99",
          value: 99,
          count: 1,
        },
      ]);
    });
  });

  describe("buildGapStats", () => {
    it("computes current and maximum gaps in complete scoped draws", () => {
      const records = [
        record("2026-10-01", { g7: ["10", "01", "02", "03"] }),
        record("2026-10-02", { g7: ["11", "12", "13", "14"] }),
        record("2026-10-03", { g7: ["10", "15", "16", "17"] }),
      ];

      const gaps = buildGapStats(records, "g7");
      const byNumber = new Map(gaps.map((item) => [item.number, item]));

      expect(byNumber.get("10")).toMatchObject({
        currentGap: 0,
        maxGap: 1,
        observed: true,
      });
      expect(byNumber.get("99")).toMatchObject({
        currentGap: 3,
        maxGap: 3,
        observed: false,
      });
      expect(gaps).toHaveLength(100);
    });

    it("ignores incomplete scoped draws", () => {
      const gaps = buildGapStats(
        [
          record("2026-10-01", { g7: ["10", "01", "02", "03"] }),
          record("2026-10-02", { g7: ["11"] }),
          record("2026-10-03", { g7: ["12", "13", "14", "15"] }),
        ],
        "g7",
      );

      expect(gaps.find((item) => item.number === "10")).toMatchObject({
        currentGap: 1,
        maxGap: 1,
        observed: true,
      });
    });

    it("marks all never-seen numbers as lower bounds", () => {
      const gaps = buildGapStats(
        [
          record("2026-10-01", { g7: ["01", "02", "03", "04"] }),
          record("2026-10-02", { g7: ["05", "06", "07", "08"] }),
        ],
        "g7",
      );

      expect(gaps.find((item) => item.number === "99")).toEqual({
        number: "99",
        currentGap: 2,
        maxGap: 2,
        observed: false,
      });
      expect(gaps.filter((item) => !item.observed)).toHaveLength(92);
    });
  });

  describe("buildDigitTransitionMatrix", () => {
    it("counts adjacent final-digit transitions in chronological scope order", () => {
      const cells = buildDigitTransitionMatrix(
        [
          record("2026-10-02", { g7: ["21"] }),
          record("2026-10-01", { g7: ["11", "12"] }),
        ],
        "g7",
      );

      expect(cells).toHaveLength(100);
      expect(cells.find((cell) => cell.fromDigit === 1 && cell.toDigit === 2))
        .toMatchObject({ count: 1, rowPercentage: 100 });
      expect(cells.find((cell) => cell.fromDigit === 2 && cell.toDigit === 1))
        .toMatchObject({ count: 1, rowPercentage: 100 });
      expect(cells.reduce((sum, cell) => sum + cell.count, 0)).toBe(2);
    });

    it("normalizes percentages per from row", () => {
      const cells = buildDigitTransitionMatrix(
        [record("2026-10-01", { g7: ["11", "12", "21", "13"] })],
        "g7",
      );
      const fromOne = cells.filter((cell) => cell.fromDigit === 1);

      expect(fromOne.find((cell) => cell.toDigit === 2)?.rowPercentage).toBe(50);
      expect(fromOne.find((cell) => cell.toDigit === 3)?.rowPercentage).toBe(50);
      expect(fromOne.reduce((sum, cell) => sum + cell.rowPercentage, 0)).toBe(100);
    });

    it("returns finite zero cells for fewer than two results", () => {
      for (const cells of [
        buildDigitTransitionMatrix([], "db"),
        buildDigitTransitionMatrix([record("2026-10-01", { db: ["11"] })], "db"),
      ]) {
        expect(cells).toHaveLength(100);
        expect(cells.every((cell) => cell.count === 0)).toBe(true);
        expect(cells.every((cell) => cell.rowPercentage === 0)).toBe(true);
        expect(cells.every((cell) => Number.isFinite(cell.rowPercentage))).toBe(true);
      }
    });
  });
});

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
    dayName: date === "2026-10-01" ? "Thứ Năm" : "Thứ Sáu",
    sourceUrl: `https://example.test/${date}`,
  };
}
