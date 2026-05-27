/**
 * Tests for the URL query-param parser/builder logic.
 *
 * The functions are defined inside RequestPanel.tsx as module-private helpers.
 * We replicate them here to test the algorithm independently (since they are
 * pure functions with no React dependencies). If they ever get extracted to
 * a utility module, these tests can import directly.
 */
import { describe, it, expect } from "vitest";

// --- Replicas of the pure functions from RequestPanel.tsx ---

function parseQueryParams(url: string): {
  base: string;
  params: { key: string; value: string }[];
} {
  const idx = url.indexOf("?");
  if (idx === -1) return { base: url, params: [] };
  const base = url.slice(0, idx);
  const qs = url.slice(idx + 1);
  const params = qs
    .split("&")
    .filter(Boolean)
    .map((part) => {
      const eq = part.indexOf("=");
      if (eq === -1) return { key: decodeURIComponent(part), value: "" };
      return {
        key: decodeURIComponent(part.slice(0, eq)),
        value: decodeURIComponent(part.slice(eq + 1)),
      };
    });
  return { base, params };
}

function buildUrl(base: string, params: { key: string; value: string }[]): string {
  const usable = params.filter((p) => p.key.length > 0);
  if (usable.length === 0) return base;
  const qs = usable
    .map((p) => `${encodeURIComponent(p.key)}=${encodeURIComponent(p.value)}`)
    .join("&");
  return `${base}?${qs}`;
}

// --- Tests ---

describe("parseQueryParams", () => {
  it("extracts params from a URL with query string", () => {
    const result = parseQueryParams("http://api.test/users?page=1&limit=20");
    expect(result.base).toBe("http://api.test/users");
    expect(result.params).toEqual([
      { key: "page", value: "1" },
      { key: "limit", value: "20" },
    ]);
  });

  it("returns empty params for URL without query string", () => {
    const result = parseQueryParams("http://api.test/users");
    expect(result.base).toBe("http://api.test/users");
    expect(result.params).toEqual([]);
  });

  it("handles encoded characters", () => {
    const result = parseQueryParams("http://api.test/search?q=hello%20world&tag=%26special");
    expect(result.params).toEqual([
      { key: "q", value: "hello world" },
      { key: "tag", value: "&special" },
    ]);
  });

  it("handles params with no value (key only)", () => {
    const result = parseQueryParams("http://api.test?verbose");
    expect(result.params).toEqual([{ key: "verbose", value: "" }]);
  });

  it("handles empty value after =", () => {
    const result = parseQueryParams("http://api.test?key=");
    expect(result.params).toEqual([{ key: "key", value: "" }]);
  });

  it("handles multiple = in value", () => {
    const result = parseQueryParams("http://api.test?token=abc=def=ghi");
    expect(result.params).toEqual([{ key: "token", value: "abc=def=ghi" }]);
  });

  it("handles empty query string (just ?)", () => {
    const result = parseQueryParams("http://api.test?");
    expect(result.base).toBe("http://api.test");
    expect(result.params).toEqual([]);
  });
});

describe("buildUrl", () => {
  it("builds URL from base and params", () => {
    const url = buildUrl("http://api.test/users", [
      { key: "page", value: "1" },
      { key: "limit", value: "20" },
    ]);
    expect(url).toBe("http://api.test/users?page=1&limit=20");
  });

  it("returns base only when params are empty", () => {
    const url = buildUrl("http://api.test/users", []);
    expect(url).toBe("http://api.test/users");
  });

  it("skips params with empty keys", () => {
    const url = buildUrl("http://api.test", [
      { key: "", value: "ignored" },
      { key: "valid", value: "yes" },
    ]);
    expect(url).toBe("http://api.test?valid=yes");
  });

  it("encodes special characters in keys and values", () => {
    const url = buildUrl("http://api.test", [
      { key: "search term", value: "hello & world" },
    ]);
    expect(url).toBe("http://api.test?search%20term=hello%20%26%20world");
  });

  it("returns base when all params have empty keys", () => {
    const url = buildUrl("http://api.test", [
      { key: "", value: "a" },
      { key: "", value: "b" },
    ]);
    expect(url).toBe("http://api.test");
  });
});

describe("round-trip: parseQueryParams -> buildUrl", () => {
  it("reconstructs the original URL", () => {
    const original = "http://api.test/endpoint?foo=bar&baz=qux";
    const { base, params } = parseQueryParams(original);
    const rebuilt = buildUrl(base, params);
    expect(rebuilt).toBe(original);
  });

  it("preserves encoded characters through round-trip", () => {
    const original = "http://api.test?q=hello%20world";
    const { base, params } = parseQueryParams(original);
    const rebuilt = buildUrl(base, params);
    // buildUrl re-encodes, so space becomes %20
    expect(rebuilt).toBe("http://api.test?q=hello%20world");
  });
});
