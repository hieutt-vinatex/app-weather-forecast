import type { Env } from "./contracts";

export const ADMIN_TOKEN_HEADER = "X-Notification-Token";
const MAX_TOKEN_BYTES = 512;

export async function authorizeAdminRequest(
  request: Request,
  env: Env,
): Promise<401 | 403 | null> {
  const origin = request.headers.get("Origin");
  if (!origin || !allowedOrigins(env).has(origin)) return 403;

  const supplied = request.headers.get(ADMIN_TOKEN_HEADER);
  const expected = env.NOTIFICATION_ADMIN_TOKEN;
  if (
    !supplied ||
    !expected ||
    new TextEncoder().encode(supplied).byteLength > MAX_TOKEN_BYTES
  ) {
    return 401;
  }
  return (await secureCompareSecrets(supplied, expected)) ? null : 401;
}

export async function secureCompareSecrets(
  supplied: string,
  expected: string,
): Promise<boolean> {
  const encoder = new TextEncoder();
  const [suppliedHash, expectedHash] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(supplied)),
    crypto.subtle.digest("SHA-256", encoder.encode(expected)),
  ]);
  const left = new Uint8Array(suppliedHash);
  const right = new Uint8Array(expectedHash);
  let difference = left.length ^ right.length;
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    difference |= (left[index] ?? 0) ^ (right[index] ?? 0);
  }
  return difference === 0;
}

export function allowedOrigins(env: Env): Set<string> {
  return new Set(
    env.ALLOWED_ORIGINS.split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  );
}
