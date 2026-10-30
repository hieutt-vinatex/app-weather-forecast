import type { RangeDays } from "../config";
import type { SnapshotResponse } from "../types/gdb";

const prizeValues = {
  db: ["53607"],
  g1: ["54279"],
  g2: ["01658", "99875"],
  g3: ["58777", "33062", "70578", "29945", "03967", "90070"],
  g4: ["1440", "4471", "5218", "7377"],
  g5: ["8274", "4475", "3487", "5399", "5678", "2717"],
  g6: ["719", "114", "363"],
  g7: ["78", "95", "84", "51"],
};

function statistics(totalResults: number, resultsPerDraw: number, number = "07") {
  return {
    totalResults,
    availableDraws: 1,
    expectedResults: resultsPerDraw,
    expectedResultsPerDraw: resultsPerDraw,
    averageResultsPerDraw: totalResults,
    uniqueNumbers: 1,
    collectionSuccessRate: 100,
    frequencies: [{ number, count: 1, percentage: 100, lastSeen: "2026-07-27" }],
    topNumbers: [{ number, count: 1, percentage: 100, lastSeen: "2026-07-27" }],
    coldNumbers: [{ number: "00", count: 0, percentage: 0, lastSeen: null }],
    tensDigitFrequency: [{ digit: "0", count: 1, percentage: 100 }],
    unitsDigitFrequency: [{ digit: "7", count: 1, percentage: 100 }],
    evenOdd: { even: 0, odd: 1, evenPercentage: 0, oddPercentage: 100 },
  };
}

export function makeSnapshot(
  days: RangeDays,
  version: number,
  gdb = "07",
): SnapshotResponse {
  return {
    data: [
      {
        gdb,
        prizes: { ...prizeValues, db: [`536${gdb}`] },
        drawComplete: true,
        date: "2026-07-27",
        dateLabel: "27-07",
        dayName: "Thứ Hai",
        sourceUrl: "https://xsmn.mobi/xsmb-27-7-2026.html",
      },
    ],
    statistics: statistics(27, 27, gdb),
    statisticsByPrize: {
      db: statistics(1, 1, gdb),
      g1: statistics(1, 1, "79"),
      g2: statistics(2, 2, "58"),
      g3: statistics(6, 6, "77"),
      g4: statistics(4, 4, "40"),
      g5: statistics(6, 6, "74"),
      g6: statistics(3, 3, "19"),
      g7: statistics(4, 4, "78"),
    },
    meta: {
      requestedDays: days,
      availableRecords: 1,
      failedCount: 0,
      missingDates: [],
      incompleteDates: [],
      availableNumbers: 27,
      errors: [],
      partial: false,
      cached: false,
      stale: false,
      fetchedAt: "2026-07-27T18:25:00+07:00",
      lastSourceCheckAt: "2026-07-27T18:25:01+07:00",
      lastSuccessfulCheckAt: "2026-07-27T18:25:01+07:00",
      lastChangedAt: "2026-07-27T18:24:58+07:00",
      snapshotVersion: version,
      pollIntervalSeconds: 1,
      realtimeEnabled: true,
      source: "xsmn.mobi",
      generatedAt: "2026-07-27T18:25:02+07:00",
      freshnessStatus: "current",
      lastJobStatus: "succeeded",
    },
  };
}
