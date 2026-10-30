// Vercel function: Drive change notification -> GitHub repository_dispatch -> Deploy workflow.
// Env: WEBHOOK_TOKEN (same as DRIVE_WEBHOOK_TOKEN), GITHUB_DISPATCH_TOKEN, GITHUB_REPO=owner/name.
import { timingSafeEqual } from "node:crypto";

// Must stay below the debounce sleep in .github/workflows/deploy.yml, so a run this recent
// has not synced yet and will include the change.
const THROTTLE_SECONDS = 60;
// Per warm instance; saves the GitHub check (and its rate limit) during long bursts.
let lastDispatchAt = 0;

function tokenMatches(received, expected) {
  if (!received || !expected) return false;
  const a = Buffer.from(received);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

// A failed check counts as "no recent run", so a change is never dropped.
async function recentDispatchRunExists(repo, headers) {
  const since = new Date(Date.now() - THROTTLE_SECONDS * 1000).toISOString();
  const query = `event=repository_dispatch&per_page=1&created=${encodeURIComponent(`>=${since}`)}`;
  try {
    const response = await fetch(
      `https://api.github.com/repos/${repo}/actions/workflows/deploy.yml/runs?${query}`,
      { headers, signal: AbortSignal.timeout(3000) },
    );
    if (!response.ok) {
      console.error(`Recent-run check failed with status ${response.status}`);
      await response.body?.cancel();
      return false;
    }
    const { total_count: count } = await response.json();
    return count > 0;
  } catch (error) {
    console.error(`Recent-run check failed: ${error.name}`);
    return false;
  }
}

export async function POST(request) {
  const { WEBHOOK_TOKEN, GITHUB_DISPATCH_TOKEN, GITHUB_REPO } = process.env;
  if (!tokenMatches(request.headers.get("x-goog-channel-token"), WEBHOOK_TOKEN)) {
    return new Response("Forbidden", { status: 403 });
  }
  // Drive sends "sync" once when a channel is created; it is not a change.
  if (request.headers.get("x-goog-resource-state") === "sync") {
    return new Response("OK", { status: 200 });
  }
  const headers = {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${GITHUB_DISPATCH_TOKEN}`,
    "User-Agent": "portfolio-drive-webhook",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  // Drive sends one notification per file change and channel; one run per minute is enough.
  if (
    Date.now() - lastDispatchAt < THROTTLE_SECONDS * 1000 ||
    (await recentDispatchRunExists(GITHUB_REPO, headers))
  ) {
    return new Response("OK", { status: 200 });
  }
  let response;
  try {
    response = await fetch(`https://api.github.com/repos/${GITHUB_REPO}/dispatches`, {
      method: "POST",
      headers,
      body: JSON.stringify({ event_type: "drive-changed" }),
    });
  } catch (error) {
    console.error(`GitHub dispatch failed: ${error.name}`);
    return new Response("Dispatch failed", { status: 502 });
  }
  if (!response.ok) {
    console.error(`GitHub dispatch failed with status ${response.status}`);
    return new Response("Dispatch failed", { status: 502 });
  }
  lastDispatchAt = Date.now();
  return new Response("OK", { status: 200 });
}
