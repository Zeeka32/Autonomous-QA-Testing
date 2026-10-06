import type {
  AcceptedRun,
  Artifact,
  ArtifactListing,
  Run,
  StartRunInput,
} from "./types";

export const apiPath = (path: string) => `/api${path}`;

async function readJson<T>(response: Response): Promise<T> {
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    if (data && typeof data === "object" && "detail" in data) {
      const detail = data.detail;
      if (typeof detail === "string") message = detail;
      if (Array.isArray(detail)) {
        message = detail.map((item) => item.msg ?? "Invalid input").join("; ");
      }
    }
    throw new Error(message);
  }
  return data as T;
}

export async function startQaRun(input: StartRunInput): Promise<AcceptedRun> {
  const parsed = new URL(input.url.trim());
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("Enter an HTTP or HTTPS website URL.");
  }
  const response = await fetch(apiPath("/runs"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: parsed.toString(),
      request: input.request.trim() || null,
      provider: input.provider,
    }),
  });
  return readJson<AcceptedRun>(response);
}

export async function getQaRun(
  runId: string,
  signal: AbortSignal,
): Promise<Run> {
  const response = await fetch(apiPath(`/runs/${runId}`), { signal });
  return readJson<Run>(response);
}

export async function getRunArtifacts(
  runId: string,
  signal: AbortSignal,
): Promise<Artifact[]> {
  const response = await fetch(apiPath(`/runs/${runId}/artifacts`), {
    signal,
  });
  const listing = await readJson<ArtifactListing>(response);
  return listing.artifacts;
}
