import type { Env } from "./contracts";

export type RepositoryEventType =
  | "cloud-data-refresh"
  | "cloud-telegram-send";

export class GitHubDispatchError extends Error {
  constructor() {
    super("GitHub repository dispatch failed");
    this.name = "GitHubDispatchError";
  }
}

export async function dispatchRepositoryEvent(
  env: Env,
  eventType: RepositoryEventType,
  requestId: string,
): Promise<void> {
  if (!env.GITHUB_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    throw new GitHubDispatchError();
  }
  const owner = encodeURIComponent(env.GITHUB_OWNER);
  const repo = encodeURIComponent(env.GITHUB_REPO);
  const fetcher = env.GITHUB_FETCH ?? fetch;
  let response: Response;
  try {
    response = await fetcher(
      `https://api.github.com/repos/${owner}/${repo}/dispatches`,
      {
        method: "POST",
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          "Content-Type": "application/json",
          "User-Agent": "app-weather-forecast-worker",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        body: JSON.stringify({
          event_type: eventType,
          client_payload: { request_id: requestId },
        }),
      },
    );
  } catch {
    throw new GitHubDispatchError();
  }
  if (!response.ok) throw new GitHubDispatchError();
}
