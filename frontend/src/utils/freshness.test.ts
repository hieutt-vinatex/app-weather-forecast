import { describe, expect, it } from "vitest";

import { pollIntervalMs } from "./freshness";

describe("pollIntervalMs", () => {
  it("uses active and idle intervals in Vietnam time", () => {
    expect(
      pollIntervalMs({ localTime: "18:00", visible: true, online: true }),
    ).toBe(30_000);
    expect(
      pollIntervalMs({ localTime: "08:00", visible: true, online: true }),
    ).toBe(300_000);
  });

  it("stops polling while hidden or offline", () => {
    expect(
      pollIntervalMs({ localTime: "18:00", visible: false, online: true }),
    ).toBe(false);
    expect(
      pollIntervalMs({ localTime: "18:00", visible: true, online: false }),
    ).toBe(false);
  });

  it("treats both active-window endpoints as active", () => {
    expect(
      pollIntervalMs({ localTime: "17:45", visible: true, online: true }),
    ).toBe(30_000);
    expect(
      pollIntervalMs({ localTime: "19:00", visible: true, online: true }),
    ).toBe(30_000);
    expect(
      pollIntervalMs({ localTime: "19:01", visible: true, online: true }),
    ).toBe(300_000);
  });
});
