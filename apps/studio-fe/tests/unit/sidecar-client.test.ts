/**
 * Tests for the sidecar HTTP client layer (URL construction, error handling).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// We test the `call` function from the sidecar client module.
// Since it uses `import.meta.env` and dynamic imports for Tauri,
// we need to mock appropriately.

// Mock import.meta.env
vi.stubEnv("VITE_SIDECAR_URL", "http://127.0.0.1:9999");

// We need to import after stubbing env
const { call, getSidecarBaseUrl, isTauri } = await import("../../src/lib/sidecar/client");

describe("isTauri", () => {
  it("returns false in test environment (no __TAURI_INTERNALS__)", () => {
    expect(isTauri()).toBe(false);
  });
});

describe("getSidecarBaseUrl", () => {
  it("resolves to VITE_SIDECAR_URL when set", async () => {
    const url = await getSidecarBaseUrl();
    expect(url).toBe("http://127.0.0.1:9999");
  });
});

describe("call", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    // Re-stub the env for other tests
    vi.stubEnv("VITE_SIDECAR_URL", "http://127.0.0.1:9999");
  });

  it("constructs full URL from base + path", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: "ok" }),
    });

    await call("/api/health");

    expect(fetchSpy).toHaveBeenCalledWith(
      "http://127.0.0.1:9999/api/health",
      expect.objectContaining({
        headers: expect.objectContaining({ "content-type": "application/json" }),
      }),
    );
  });

  it("passes request body and method", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "123" }),
    });

    const body = JSON.stringify({ name: "test" });
    await call("/api/collections", { method: "POST", body });

    expect(fetchSpy).toHaveBeenCalledWith(
      "http://127.0.0.1:9999/api/collections",
      expect.objectContaining({
        method: "POST",
        body,
      }),
    );
  });

  it("merges custom headers with content-type default", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    });

    await call("/api/test", {
      headers: { "X-Custom": "value" },
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: {
          "content-type": "application/json",
          "X-Custom": "value",
        },
      }),
    );
  });

  it("throws on 4xx with detail from JSON response", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: "Not found" }),
    });

    await expect(call("/api/missing")).rejects.toThrow("sidecar 404: Not found");
  });

  it("throws on 5xx with detail from JSON response", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: "Internal server error" }),
    });

    await expect(call("/api/broken")).rejects.toThrow("sidecar 500: Internal server error");
  });

  it("falls back to text body when JSON parsing fails", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 502,
      json: async () => { throw new Error("not json"); },
      text: async () => "Bad Gateway",
    });

    await expect(call("/api/down")).rejects.toThrow("sidecar 502: Bad Gateway");
  });

  it("throws on network error", async () => {
    fetchSpy.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await expect(call("/api/unreachable")).rejects.toThrow("Failed to fetch");
  });

  it("returns parsed JSON on success", async () => {
    const payload = { collections: [{ id: "1", name: "Test" }] };
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => payload,
    });

    const result = await call("/api/collections");
    expect(result).toEqual(payload);
  });

  it("stringifies non-string detail from error response", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: async () => ({ detail: [{ loc: ["body", "name"], msg: "required" }] }),
    });

    await expect(call("/api/validate")).rejects.toThrow("sidecar 422:");
  });
});
