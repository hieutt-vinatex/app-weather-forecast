import type { GdbRecord, PrizeScope } from "../types/gdb";
import { lastTwo, PRIZES, resultsForScope } from "./prizes";

const ALL_NUMBERS = Array.from({ length: 100 }, (_, index) =>
  String(index).padStart(2, "0"),
);

export interface ScatterPoint {
  date: string;
  dateLabel: string;
  dayName: string;
  number: string;
  value: number;
  count: number;
}

export function buildScatterPoints(
  records: GdbRecord[],
  scope: PrizeScope,
): ScatterPoint[] {
  const points = new Map<string, ScatterPoint>();

  for (const record of [...records].sort((a, b) => a.date.localeCompare(b.date))) {
    for (const result of resultsForScope(record, scope)) {
      const number = lastTwo(result);
      const key = `${record.date}:${number}`;
      const existing = points.get(key);

      if (existing) {
        existing.count += 1;
      } else {
        points.set(key, {
          date: record.date,
          dateLabel: record.dateLabel,
          dayName: record.dayName,
          number,
          value: Number(number),
          count: 1,
        });
      }
    }
  }

  return [...points.values()];
}

export interface GapStat {
  number: string;
  currentGap: number;
  maxGap: number;
  observed: boolean;
}

export function buildGapStats(
  records: GdbRecord[],
  scope: PrizeScope,
): GapStat[] {
  const expectedResults =
    scope === "all"
      ? PRIZES.reduce((total, prize) => total + prize.resultsPerDraw, 0)
      : (PRIZES.find((prize) => prize.key === scope)?.resultsPerDraw ?? 0);
  const stats = new Map(
    ALL_NUMBERS.map((number) => [
      number,
      { number, currentGap: 0, maxGap: 0, observed: false },
    ]),
  );

  for (const record of [...records].sort((a, b) => a.date.localeCompare(b.date))) {
    const results = resultsForScope(record, scope);
    if (results.length !== expectedResults) continue;

    const appeared = new Set(results.map(lastTwo));
    for (const item of stats.values()) {
      if (appeared.has(item.number)) {
        item.observed = true;
        item.currentGap = 0;
      } else {
        item.currentGap += 1;
        item.maxGap = Math.max(item.maxGap, item.currentGap);
      }
    }
  }

  return [...stats.values()];
}

export interface TransitionCell {
  fromDigit: number;
  toDigit: number;
  count: number;
  rowPercentage: number;
}

export function buildDigitTransitionMatrix(
  records: GdbRecord[],
  scope: PrizeScope,
): TransitionCell[] {
  const digits = [...records]
    .sort((a, b) => a.date.localeCompare(b.date))
    .flatMap((record) => resultsForScope(record, scope))
    .map((result) => Number(lastTwo(result)[1]));
  const counts = Array.from({ length: 10 }, () => Array<number>(10).fill(0));

  for (let index = 1; index < digits.length; index += 1) {
    const fromDigit = digits[index - 1];
    const toDigit = digits[index];
    counts[fromDigit][toDigit] += 1;
  }

  return counts.flatMap((row, fromDigit) => {
    const total = row.reduce((sum, count) => sum + count, 0);
    return row.map((count, toDigit) => ({
      fromDigit,
      toDigit,
      count,
      rowPercentage: total === 0 ? 0 : Math.round((count / total) * 10_000) / 100,
    }));
  });
}
