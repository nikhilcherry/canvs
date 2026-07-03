// All fetches to the backend live here. Base URL is proxied by vite
// (see vite.config.ts) so relative /api/* paths work in dev, and the
// same relative paths work if this is ever served behind the same host.
import type {
  CreateRunResponse,
  Graph,
  HealthResponse,
  KaggleRunOptions,
  KillRunResponse,
  MetricsResponse,
  RegistryResponse,
  RunDetailResponse,
  RunHistoryResponse,
  RunTarget,
  ValidateResponse,
} from "./types";

const BASE = "/api";

class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    super(`API error ${status}: ${JSON.stringify(body)}`);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
    }
    throw new ApiError(res.status, body);
  }
  return res.json() as Promise<T>;
}

export { ApiError };

export function getHealth(): Promise<HealthResponse> {
  return request("/health");
}

export function getRegistry(): Promise<RegistryResponse> {
  return request("/registry");
}

export function validateGraph(graph: Graph): Promise<ValidateResponse> {
  return request("/graphs/validate", {
    method: "POST",
    body: JSON.stringify(graph),
  });
}

export async function createRun(
  graph: Graph,
  target: RunTarget,
  kaggle?: KaggleRunOptions
): Promise<{ ok: true; data: CreateRunResponse } | { ok: false; errors: ValidateResponse }> {
  try {
    const data = await request<CreateRunResponse>("/runs", {
      method: "POST",
      body: JSON.stringify(kaggle ? { graph, target, kaggle } : { graph, target }),
    });
    return { ok: true, data };
  } catch (e) {
    if (e instanceof ApiError && e.status === 400) {
      return { ok: false, errors: e.body as ValidateResponse };
    }
    throw e;
  }
}

export function getRun(runId: string): Promise<RunDetailResponse> {
  return request(`/runs/${encodeURIComponent(runId)}`);
}

export function getRunMetrics(runId: string, afterId: number): Promise<MetricsResponse> {
  return request(`/runs/${encodeURIComponent(runId)}/metrics?after_id=${afterId}`);
}

export function killRun(runId: string): Promise<KillRunResponse> {
  return request(`/runs/${encodeURIComponent(runId)}/kill`, { method: "POST" });
}

export function listRuns(): Promise<RunHistoryResponse> {
  return request("/runs");
}
