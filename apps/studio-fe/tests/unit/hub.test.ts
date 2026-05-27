/**
 * Unit tests for the Hub HTTP client (lib/sidecar/hub.ts).
 * All network calls are mocked — no real Hub instance required.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  pingHub,
  getRuns,
  getIncidents,
  getGates,
  type HubConfig,
} from "../../src/lib/sidecar/hub";

const CONFIG: HubConfig = {
  url: "https://hub.example.com",
  token: "test-token-abc",
};

function mockFetch(body: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(JSON.stringify(body)),
    }),
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

// --- pingHub ---

describe("pingHub", () => {
  it("resolves with health data on 200", async () => {
    mockFetch({ status: "ok", version: "1.2.3" });
    const result = await pingHub(CONFIG);
    expect(result.status).toBe("ok");
    expect(result.version).toBe("1.2.3");
  });

  it("sends Authorization header with Bearer token", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: "ok", version: "1.0.0" }),
      text: () => Promise.resolve(""),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await pingHub(CONFIG);

    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://hub.example.com/api/health");
    expect((init.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer test-token-abc",
    );
  });

  it("strips trailing slash from base URL", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: "ok", version: "1.0.0" }),
      text: () => Promise.resolve(""),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await pingHub({ url: "https://hub.example.com/", token: "tok" });

    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://hub.example.com/api/health");
  });

  it("throws HubApiError on non-2xx response", async () => {
    mockFetch({ detail: "Unauthorized" }, 401);
    await expect(pingHub(CONFIG)).rejects.toThrow(/Hub 401/);
  });
});

// --- getRuns ---

describe("getRuns", () => {
  const runsPayload = {
    runs: [
      {
        id: "run-1",
        collection_id: "col-1",
        collection_name: "Auth Suite",
        pass_rate: 95,
        total: 20,
        passed: 19,
        failed: 1,
        duration_ms: 4200,
        started_at: "2026-05-26T10:00:00Z",
        status: "pass" as const,
      },
    ],
    total: 1,
  };

  it("resolves with runs array", async () => {
    mockFetch(runsPayload);
    const result = await getRuns(CONFIG);
    expect(result.runs).toHaveLength(1);
    expect(result.runs[0].collection_name).toBe("Auth Suite");
    expect(result.runs[0].pass_rate).toBe(95);
  });

  it("appends limit query param", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(runsPayload),
      text: () => Promise.resolve(""),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await getRuns(CONFIG, 5);
    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("limit=5");
  });

  it("uses default limit of 20", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(runsPayload),
      text: () => Promise.resolve(""),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await getRuns(CONFIG);
    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("limit=20");
  });

  it("throws on 500 error", async () => {
    mockFetch({ detail: "Internal Server Error" }, 500);
    await expect(getRuns(CONFIG)).rejects.toThrow(/Hub 500/);
  });
});

// --- getIncidents ---

describe("getIncidents", () => {
  const incidentsPayload = {
    incidents: [
      {
        id: "inc-1",
        severity: "high" as const,
        title: "Response time exceeded SLA",
        collection_name: "Payment API",
        opened_at: "2026-05-26T08:30:00Z",
        resolved_at: null,
        status: "open" as const,
      },
    ],
    total: 1,
  };

  it("resolves with incidents array", async () => {
    mockFetch(incidentsPayload);
    const result = await getIncidents(CONFIG);
    expect(result.incidents).toHaveLength(1);
    expect(result.incidents[0].severity).toBe("high");
    expect(result.incidents[0].status).toBe("open");
  });

  it("calls the correct endpoint", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(incidentsPayload),
      text: () => Promise.resolve(""),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await getIncidents(CONFIG);
    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/incidents/recent");
  });
});

// --- getGates ---

describe("getGates", () => {
  const gatesPayload = {
    gates: [
      {
        name: "Pass rate >= 90%",
        status: "pass" as const,
        threshold: 90,
        current: 95,
        unit: "%",
      },
      {
        name: "P95 latency < 500ms",
        status: "fail" as const,
        threshold: 500,
        current: 620,
        unit: "ms",
      },
    ],
  };

  it("resolves with gates array", async () => {
    mockFetch(gatesPayload);
    const result = await getGates(CONFIG);
    expect(result.gates).toHaveLength(2);
    expect(result.gates[0].status).toBe("pass");
    expect(result.gates[1].status).toBe("fail");
  });

  it("includes current vs threshold values", async () => {
    mockFetch(gatesPayload);
    const result = await getGates(CONFIG);
    const failing = result.gates[1];
    expect(failing.current).toBeGreaterThan(failing.threshold);
  });

  it("calls the correct endpoint", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(gatesPayload),
      text: () => Promise.resolve(""),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await getGates(CONFIG);
    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/quality-gates/status");
  });
});
