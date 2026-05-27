/**
 * Unit tests for HubOverviewPanel component.
 * Mocks fetch + localStorage — no real Hub or sidecar required.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HubOverviewPanel } from "../../src/components/HubOverviewPanel";

// Stub all hub module fetches
vi.mock("../../src/lib/sidecar/hub", () => ({
  pingHub: vi.fn(),
  getRuns: vi.fn(),
  getIncidents: vi.fn(),
  getGates: vi.fn(),
}));

// Stub the sidecar module used indirectly
vi.mock("../../src/lib/sidecar", () => ({
  sidecar: {},
}));

import { getRuns, getIncidents, getGates } from "../../src/lib/sidecar/hub";

const mockRuns = {
  runs: [
    {
      id: "r1",
      collection_id: "c1",
      collection_name: "Auth Suite",
      pass_rate: 90,
      total: 10,
      passed: 9,
      failed: 1,
      duration_ms: 2000,
      started_at: "2026-05-26T10:00:00Z",
      status: "pass" as const,
    },
    {
      id: "r2",
      collection_id: "c2",
      collection_name: "Payment API",
      pass_rate: 50,
      total: 10,
      passed: 5,
      failed: 5,
      duration_ms: 5000,
      started_at: "2026-05-26T11:00:00Z",
      status: "fail" as const,
    },
  ],
  total: 2,
};

const mockIncidents = {
  incidents: [
    {
      id: "i1",
      severity: "high" as const,
      title: "SLA breach",
      collection_name: "Payment API",
      opened_at: "2026-05-26T09:00:00Z",
      resolved_at: null,
      status: "open" as const,
    },
  ],
  total: 1,
};

const mockGates = {
  gates: [
    {
      name: "Pass rate >= 90%",
      status: "pass" as const,
      threshold: 90,
      current: 92,
      unit: "%",
    },
  ],
};

function setupLocalStorage(url = "https://hub.test", token = "tok-123") {
  window.localStorage.setItem(
    "theridion.hubConfig",
    JSON.stringify({ url, token }),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  vi.mocked(getRuns).mockResolvedValue(mockRuns);
  vi.mocked(getIncidents).mockResolvedValue(mockIncidents);
  vi.mocked(getGates).mockResolvedValue(mockGates);
});

// --- Empty state ---

describe("HubOverviewPanel — empty state", () => {
  it("shows empty state when Hub is not configured", () => {
    render(<HubOverviewPanel />);
    expect(screen.getByText(/Hub not configured/i)).toBeInTheDocument();
  });

  it("shows Open Settings button when callback is provided", () => {
    const onOpenSettings = vi.fn();
    render(<HubOverviewPanel onOpenSettings={onOpenSettings} />);
    expect(screen.getByText(/Open Settings/i)).toBeInTheDocument();
  });

  it("calls onOpenSettings on button click", async () => {
    const onOpenSettings = vi.fn();
    render(<HubOverviewPanel onOpenSettings={onOpenSettings} />);
    await userEvent.click(screen.getByText(/Open Settings/i));
    expect(onOpenSettings).toHaveBeenCalledOnce();
  });
});

// --- With Hub config ---

describe("HubOverviewPanel — with Hub config", () => {
  it("renders Hub Overview header when configured", async () => {
    setupLocalStorage();
    await act(async () => {
      render(<HubOverviewPanel />);
    });
    expect(screen.getByText(/Hub Overview/i)).toBeInTheDocument();
  });

  it("shows category sidebar with Runs / Incidents / Quality Gates", async () => {
    setupLocalStorage();
    await act(async () => {
      render(<HubOverviewPanel />);
    });
    expect(screen.getByText("Runs")).toBeInTheDocument();
    expect(screen.getByText("Incidents")).toBeInTheDocument();
    expect(screen.getByText("Quality Gates")).toBeInTheDocument();
  });

  it("displays run collection names", async () => {
    setupLocalStorage();
    await act(async () => {
      render(<HubOverviewPanel />);
    });
    expect(screen.getByText("Auth Suite")).toBeInTheDocument();
    expect(screen.getByText("Payment API")).toBeInTheDocument();
  });

  it("calls getRuns, getIncidents, getGates on mount", async () => {
    setupLocalStorage();
    await act(async () => {
      render(<HubOverviewPanel />);
    });
    expect(vi.mocked(getRuns)).toHaveBeenCalledOnce();
    expect(vi.mocked(getIncidents)).toHaveBeenCalledOnce();
    expect(vi.mocked(getGates)).toHaveBeenCalledOnce();
  });

  it("renders the refresh button", async () => {
    setupLocalStorage();
    await act(async () => {
      render(<HubOverviewPanel />);
    });
    // Refresh button has title "Refresh (Ctrl+R)"
    expect(screen.getByTitle(/Refresh/i)).toBeInTheDocument();
  });

  it("switches to Incidents tab on click", async () => {
    setupLocalStorage();
    await act(async () => {
      render(<HubOverviewPanel />);
    });
    await userEvent.click(screen.getByText("Incidents"));
    expect(screen.getByText("SLA breach")).toBeInTheDocument();
  });

  it("switches to Quality Gates tab on click", async () => {
    setupLocalStorage();
    await act(async () => {
      render(<HubOverviewPanel />);
    });
    await userEvent.click(screen.getByText("Quality Gates"));
    expect(screen.getByText("Pass rate >= 90%")).toBeInTheDocument();
  });
});

// --- Error state ---

describe("HubOverviewPanel — error state", () => {
  it("shows error banner when fetch fails", async () => {
    vi.mocked(getRuns).mockRejectedValue(new Error("Hub 401: Unauthorized"));
    vi.mocked(getIncidents).mockRejectedValue(new Error("Hub 401: Unauthorized"));
    vi.mocked(getGates).mockRejectedValue(new Error("Hub 401: Unauthorized"));
    setupLocalStorage();

    await act(async () => {
      render(<HubOverviewPanel />);
    });
    // Error banner should be visible
    expect(screen.getByText(/Hub 401/i)).toBeInTheDocument();
  });
});

// --- onOpenCollection callback ---

describe("HubOverviewPanel — failed run click", () => {
  it("calls onOpenCollection with collection_id when failed run is clicked", async () => {
    const onOpenCollection = vi.fn();
    setupLocalStorage();

    await act(async () => {
      render(<HubOverviewPanel onOpenCollection={onOpenCollection} />);
    });

    // Payment API has status=fail — click on its row triggers onOpenCollection
    const row = screen.getByTitle("Click to open collection");
    await userEvent.click(row);
    expect(onOpenCollection).toHaveBeenCalledWith("c2");
  });
});
