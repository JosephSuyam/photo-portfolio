// Vercel function: Drive change notification -> GitHub repository_dispatch -> Deploy workflow.
// Env: WEBHOOK_TOKEN (same as DRIVE_WEBHOOK_TOKEN), GITHUB_DISPATCH_TOKEN, GITHUB_REPO=owner/name.
import { timingSafeEqual } from "node:crypto";

function tokenMatches(received, expected) {
  if (!received || !expected) return false;
  const a = Buffer.from(received);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
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
  let response;
  try {
    response = await fetch(`https://api.github.com/repos/${GITHUB_REPO}/dispatches`, {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${GITHUB_DISPATCH_TOKEN}`,
        "User-Agent": "portfolio-drive-webhook",
        "X-GitHub-Api-Version": "2022-11-28",
      },
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
  return new Response("OK", { status: 200 });
}
