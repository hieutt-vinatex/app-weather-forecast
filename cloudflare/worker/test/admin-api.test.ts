import { describe, expect, it, vi } from "vitest";

import type { Env } from "../src/contracts";
import { handleRequest } from "../src/index";

class FakeKV {
  readonly values = new Map<string, unknown>();
  readonly puts: Array<{
    key: string;
    value: string;
    options?: KVNamespacePutOptions;
  }> = [];
  readonly deletes: string[] = [];

  async get<T>(key: string, type?: "json"): Promise<T | string | null> {
    void type;
    return (structuredClone(this.values.get(key)) as T | undefined) ?? null;
  }

  async put(
    key: string,
    value: string,
    options?: KVNamespacePutOptions,
  ): Promise<void> {
    this.puts.push({ key, value, options });
    this.values.set(key, JSON.parse(value));
  }

  async delete(key: string): Promise<void> {
    this.deletes.push(key);
    this.values.delete(key);
  }
}

function makeEnv(
  kv: FakeKV,
  githubFetch = vi.fn<typeof fetch>(async () =>
    new Response(null, { status: 204 }),
  ),
): Env {
  return {
    SNAPSHOTS: kv as unknown as KVNamespace,
    ALLOWED_ORIGINS: "https://app.example",
    NOTIFICATION_ADMIN_TOKEN: "correct-secret",
    GITHUB_DISPATCH_TOKEN: "github-secret",
    GITHUB_OWNER: "owner",
    GITHUB_REPO: "repo",
    GITHUB_FETCH: githubFetch as typeof fetch,
    OPERATION_TTL_SECONDS: "86400",
    ADMIN_COOLDOWN_SECONDS: "60",
  };
}

function adminRequest(
  path: string,
  {
    method = "POST",
    token = "correct-secret",
    origin = "https://app.example",
  }: { method?: string; token?: string; origin?: string } = {},
): Request {
  return new Request(`https://api.example${path}`, {
    method,
    headers: {
      Origin: origin,
      "X-Notification-Token": token,
    },
  });
}

describe("admin operation API", () => {
  it("rejects wrong token and origin before KV or GitHub side effects", async () => {
    const kv = new FakeKV();
    const githubFetch = vi.fn<typeof fetch>(async () =>
      new Response(null, { status: 204 }),
    );
    const workerEnv = makeEnv(kv, githubFetch);

    const unauthorized = await handleRequest(
      adminRequest("/api/gdb/refresh", { token: "wrong" }),
      workerEnv,
    );
    const forbidden = await handleRequest(
      adminRequest("/api/gdb/refresh", { origin: "https://evil.example" }),
      workerEnv,
    );

    expect(unauthorized.status).toBe(401);
    expect(forbidden.status).toBe(403);
    expect(kv.puts).toEqual([]);
    expect(githubFetch).not.toHaveBeenCalled();
  });

  it.each([
    ["/api/gdb/refresh", "cloud-data-refresh", "data_refresh"],
    ["/api/notifications/send-now", "cloud-telegram-send", "telegram_send"],
  ])("queues %s and dispatches the exact event", async (path, eventType, kind) => {
    const kv = new FakeKV();
    const githubFetch = vi.fn<typeof fetch>(async () =>
      new Response(null, { status: 204 }),
    );
    const response = await handleRequest(
      adminRequest(path),
      makeEnv(kv, githubFetch),
    );
    const body = (await response.json()) as Record<string, string>;

    expect(response.status).toBe(202);
    expect(body.status).toBe("queued");
    expect(body.requestId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    const operationPut = kv.puts.find((item) =>
      item.key.startsWith("operation:v1:"),
    );
    expect(operationPut?.options?.expirationTtl).toBe(86400);
    expect(JSON.parse(operationPut?.value ?? "{}")).toMatchObject({
      requestId: body.requestId,
      kind,
      status: "queued",
    });
    const request = githubFetch.mock.calls[0]?.[0] as RequestInfo;
    const init = githubFetch.mock.calls[0]?.[1] as RequestInit;
    expect(String(request)).toBe(
      "https://api.github.com/repos/owner/repo/dispatches",
    );
    expect(JSON.parse(String(init.body))).toEqual({
      event_type: eventType,
      client_payload: { request_id: body.requestId },
    });
  });

  it("returns authenticated operation status", async () => {
    const kv = new FakeKV();
    const workerEnv = makeEnv(kv);
    const accepted = await handleRequest(
      adminRequest("/api/gdb/refresh"),
      workerEnv,
    );
    const { requestId } = (await accepted.json()) as { requestId: string };

    const response = await handleRequest(
      adminRequest(`/api/operations/${requestId}`, { method: "GET" }),
      workerEnv,
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ requestId, status: "queued" });
  });

  it("enforces same-kind cooldown without a second dispatch", async () => {
    const kv = new FakeKV();
    const githubFetch = vi.fn<typeof fetch>(async () =>
      new Response(null, { status: 204 }),
    );
    const workerEnv = makeEnv(kv, githubFetch);

    expect(
      (await handleRequest(adminRequest("/api/gdb/refresh"), workerEnv)).status,
    ).toBe(202);
    const second = await handleRequest(
      adminRequest("/api/gdb/refresh"),
      workerEnv,
    );

    expect(second.status).toBe(429);
    expect(second.headers.get("Retry-After")).toBe("60");
    expect(githubFetch).toHaveBeenCalledTimes(1);
  });

  it("removes queued state and returns a safe 502 on GitHub failure", async () => {
    const kv = new FakeKV();
    const githubFetch = vi.fn<typeof fetch>(async () =>
      new Response("token=github-secret private body", { status: 500 }),
    );
    const response = await handleRequest(
      adminRequest("/api/gdb/refresh"),
      makeEnv(kv, githubFetch),
    );
    const body = await response.text();

    expect(response.status).toBe(502);
    expect(body).not.toContain("github-secret");
    expect(body).not.toContain("private body");
    expect(kv.deletes.some((key) => key.startsWith("operation:v1:"))).toBe(true);
  });
});
