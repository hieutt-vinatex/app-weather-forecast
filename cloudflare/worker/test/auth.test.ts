import { describe, expect, it } from "vitest";

import {
  authorizeAdminRequest,
  secureCompareSecrets,
} from "../src/auth";
import type { Env } from "../src/contracts";

const env = {
  ALLOWED_ORIGINS: "https://app.example",
  NOTIFICATION_ADMIN_TOKEN: "correct-secret",
} as Env;

describe("admin authentication", () => {
  it("compares equal hashes and rejects different secrets", async () => {
    expect(await secureCompareSecrets("correct-secret", "correct-secret")).toBe(
      true,
    );
    expect(await secureCompareSecrets("wrong-secret", "correct-secret")).toBe(
      false,
    );
  });

  it("rejects missing and oversized tokens", async () => {
    const missing = await authorizeAdminRequest(
      new Request("https://api.example/api/gdb/refresh", {
        method: "POST",
        headers: { Origin: "https://app.example" },
      }),
      env,
    );
    const oversized = await authorizeAdminRequest(
      new Request("https://api.example/api/gdb/refresh", {
        method: "POST",
        headers: {
          Origin: "https://app.example",
          "X-Notification-Token": "x".repeat(513),
        },
      }),
      env,
    );

    expect(missing).toBe(401);
    expect(oversized).toBe(401);
  });

  it("rejects a disallowed or missing origin before authentication", async () => {
    const denied = await authorizeAdminRequest(
      new Request("https://api.example/api/gdb/refresh", {
        method: "POST",
        headers: {
          Origin: "https://evil.example",
          "X-Notification-Token": "correct-secret",
        },
      }),
      env,
    );

    expect(denied).toBe(403);
  });
});
