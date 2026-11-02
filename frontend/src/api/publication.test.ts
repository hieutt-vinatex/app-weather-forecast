import { describe, expect, it } from "vitest";

import {
  isPublicationManifest,
  manifestPath,
  snapshotPath,
} from "./publication";

const ACTIVE = "20261029T110500000000Z";
const PREVIOUS = "20261029T105500000000Z";

function pointer(version: string) {
  return {
    version,
    generatedAt: "2026-10-29T11:05:00Z",
    snapshotKeys: {
      "30": `snapshot:v1:${version}:30`,
      "60": `snapshot:v1:${version}:60`,
      "90": `snapshot:v1:${version}:90`,
    },
    lastJob: { status: "succeeded" },
  };
}

describe("static publication contract", () => {
  it("accepts an active publication with a complete previous pointer", () => {
    expect(
      isPublicationManifest({
        schemaVersion: 1,
        ...pointer(ACTIVE),
        previousPublication: pointer(PREVIOUS),
      }),
    ).toBe(true);
  });

  it.each([
    "../secret",
    "version/child",
    "",
    ".hidden",
  ])("rejects unsafe version %s", (version) => {
    expect(
      isPublicationManifest({
        schemaVersion: 1,
        ...pointer(version),
        previousPublication: null,
      }),
    ).toBe(false);
  });

  it("rejects a publication missing one range pointer", () => {
    const value = pointer(ACTIVE);
    delete (value.snapshotKeys as Partial<typeof value.snapshotKeys>)["60"];

    expect(
      isPublicationManifest({
        schemaVersion: 1,
        ...value,
        previousPublication: null,
      }),
    ).toBe(false);
  });

  it("builds repository-subpath URLs and buckets manifest cache busting", () => {
    const base = "/app-weather-forecast/";

    expect(snapshotPath(ACTIVE, 30, base)).toBe(
      `/app-weather-forecast/data/versions/${ACTIVE}/snapshot-30.json`,
    );
    expect(manifestPath(30_001, base)).toBe(manifestPath(59_999, base));
    expect(manifestPath(59_999, base)).not.toBe(manifestPath(60_000, base));
  });
});
