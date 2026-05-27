/**
 * Hub HTTP client — typed fetch layer for Theridion Hub remote API.
 *
 * Hub runs as a separate service (qa-monitoring or self-hosted Hub server).
 * All calls go directly from the browser/Tauri WebView to the Hub URL —
 * no sidecar proxy involved. The Hub URL and ingest token are stored in
 * ~/.theridion/settings.json under the `hub` key.
 */

export interface HubConfig {
  url: string;
  token: string;
}

export interface RunSummary {
  id: string;
  collection_id: string;
  collection_name: string;
  pass_rate: number;
  total: number;
  passed: number;
  failed: number;
  duration_ms: number;
  started_at: string;
  status: "pass" | "fail" | "running";
}

export interface IncidentSummary {
  id: string;
  severity: "critical" | "high" | "medium" | "low";
  title: string;
  collection_name: string;
  opened_at: string;
  resolved_at: string | null;
  status: "open" | "resolved";
}

export interface QualityGateStatus {
  name: string;
  status: "pass" | "fail" | "pending";
  threshold: number;
  current: number;
  unit: string;
}

export interface HubHealthResponse {
  status: string;
  version: string;
}

export interface HubRunsResponse {
  runs: RunSummary[];
  total: number;
}

export interface HubIncidentsResponse {
  incidents: IncidentSummary[];
  total: number;
}

export interface HubGatesResponse {
  gates: QualityGateStatus[];
}

class HubApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "HubApiError";
  }
}

async function hubFetch<T>(
  config: HubConfig,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const url = `${config.url.replace(/\/$/, "")}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      "content-type": "application/json",
      Authorization: `Bearer ${config.token}`,
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail: string;
    try {
      const j = (await res.json()) as { detail?: unknown };
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j);
    } catch {
      detail = await res.text();
    }
    throw new HubApiError(`Hub ${res.status}: ${detail}`, res.status);
  }
  return (await res.json()) as T;
}

export async function pingHub(config: HubConfig): Promise<HubHealthResponse> {
  return hubFetch<HubHealthResponse>(config, "/api/health");
}

export async function getRuns(
  config: HubConfig,
  limit = 20,
): Promise<HubRunsResponse> {
  return hubFetch<HubRunsResponse>(config, `/api/runs?limit=${limit}`);
}

export async function getIncidents(
  config: HubConfig,
  limit = 20,
): Promise<HubIncidentsResponse> {
  return hubFetch<HubIncidentsResponse>(
    config,
    `/api/incidents/recent?limit=${limit}`,
  );
}

export async function getGates(config: HubConfig): Promise<HubGatesResponse> {
  return hubFetch<HubGatesResponse>(config, "/api/quality-gates/status");
}
