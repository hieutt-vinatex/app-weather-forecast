import { describe, expect, it } from "vitest";

import {
  classifyFreshness,
  type FreshnessInput,
} from "../src/freshness";

function at(
  localTime: string,
  ageMinutes: number,
  lastJobStatus: string,
): FreshnessInput {
  const now = new Date(`2026-10-29T${localTime}:00+07:00`);
  return {
    now,
    generatedAt: new Date(now.getTime() - ageMinutes * 60_000).toISOString(),
    lastJobStatus,
  };
}

describe("classifyFreshness", () => {
  it("uses the exact active-window boundaries", () => {
    expect(classifyFreshness(at("18:00", 10, "succeeded"))).toBe("current");
    expect(classifyFreshness(at("18:00", 11, "succeeded"))).toBe("delayed");
    expect(classifyFreshness(at("18:00", 21, "succeeded"))).toBe("stale");
  });

  it("uses the exact idle-window boundaries", () => {
    expect(classifyFreshness(at("08:00", 26 * 60, "succeeded"))).toBe("current");
    expect(classifyFreshness(at("08:00", 26 * 60 + 1, "succeeded"))).toBe(
      "delayed",
    );
    expect(classifyFreshness(at("08:00", 48 * 60 + 1, "succeeded"))).toBe(
      "stale",
    );
  });

  it("surfaces running and failed jobs without discarding age", () => {
    expect(classifyFreshness(at("18:00", 2, "running"))).toBe("updating");
    expect(classifyFreshness(at("18:00", 2, "failed"))).toBe("delayed");
    expect(classifyFreshness(at("18:00", 21, "failed"))).toBe("stale");
  });
});
