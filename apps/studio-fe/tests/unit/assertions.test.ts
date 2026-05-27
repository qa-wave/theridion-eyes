/**
 * Tests for assertion types, serialization, and display formatting.
 *
 * The actual assertion evaluation happens on the sidecar (Python), but the
 * frontend handles assertion creation, serialization for storage, and display
 * of results. These tests cover the client-side logic.
 */
import { describe, it, expect } from "vitest";
import type { Assertion, AssertionResult } from "../../src/state/types";

// --- Utility functions that mirror frontend assertion handling ---

/** Format assertion for display in the UI. */
function formatAssertion(a: Assertion): string {
  switch (a.type) {
    case "status":
      return `Status ${a.operator} ${a.expected}`;
    case "response_time":
      return `Response time ${a.operator} ${a.expected}ms`;
    case "json_path":
      return `${a.path} ${a.operator} ${a.expected}`;
    case "header_exists":
      return `Header "${a.expected}" exists`;
    case "header_equals":
      return `Header "${a.path}" ${a.operator} "${a.expected}"`;
    case "body_contains":
      return `Body contains "${a.expected}"`;
    case "body_regex":
      return `Body matches /${a.expected}/`;
    default:
      return `${a.type}: ${a.expected}`;
  }
}

/** Serialize assertions to JSON for storage/transport. */
function serializeAssertions(assertions: Assertion[]): string {
  return JSON.stringify(assertions);
}

/** Deserialize assertions from storage. */
function deserializeAssertions(json: string): Assertion[] {
  return JSON.parse(json) as Assertion[];
}

/** Compute pass rate from assertion results. */
function passRate(results: AssertionResult[]): number {
  if (results.length === 0) return 0;
  const passed = results.filter((r) => r.passed).length;
  return Math.round((passed / results.length) * 100);
}

// --- Tests ---

describe("Assertion formatting", () => {
  it("formats status assertion", () => {
    const a: Assertion = { type: "status", expected: "200", path: "", operator: "eq" };
    expect(formatAssertion(a)).toBe("Status eq 200");
  });

  it("formats response_time assertion", () => {
    const a: Assertion = { type: "response_time", expected: "500", path: "", operator: "lt" };
    expect(formatAssertion(a)).toBe("Response time lt 500ms");
  });

  it("formats json_path assertion", () => {
    const a: Assertion = { type: "json_path", expected: "Alice", path: "$.name", operator: "eq" };
    expect(formatAssertion(a)).toBe("$.name eq Alice");
  });

  it("formats header_exists assertion", () => {
    const a: Assertion = { type: "header_exists", expected: "Content-Type", path: "", operator: "" };
    expect(formatAssertion(a)).toBe('Header "Content-Type" exists');
  });

  it("formats header_equals assertion", () => {
    const a: Assertion = { type: "header_equals", expected: "application/json", path: "Content-Type", operator: "eq" };
    expect(formatAssertion(a)).toBe('Header "Content-Type" eq "application/json"');
  });

  it("formats body_contains assertion", () => {
    const a: Assertion = { type: "body_contains", expected: "success", path: "", operator: "" };
    expect(formatAssertion(a)).toBe('Body contains "success"');
  });

  it("formats body_regex assertion", () => {
    const a: Assertion = { type: "body_regex", expected: "user_\\d+", path: "", operator: "" };
    expect(formatAssertion(a)).toBe("Body matches /user_\\d+/");
  });
});

describe("Assertion serialization", () => {
  it("round-trips assertions through JSON", () => {
    const assertions: Assertion[] = [
      { type: "status", expected: "200", path: "", operator: "eq" },
      { type: "json_path", expected: "true", path: "$.active", operator: "eq" },
      { type: "response_time", expected: "1000", path: "", operator: "lt" },
    ];
    const json = serializeAssertions(assertions);
    const parsed = deserializeAssertions(json);
    expect(parsed).toEqual(assertions);
  });

  it("handles empty assertions array", () => {
    const json = serializeAssertions([]);
    expect(deserializeAssertions(json)).toEqual([]);
  });

  it("preserves all assertion fields", () => {
    const a: Assertion = { type: "header_equals", expected: "v", path: "X-Custom", operator: "contains" };
    const json = serializeAssertions([a]);
    const [parsed] = deserializeAssertions(json);
    expect(parsed.type).toBe("header_equals");
    expect(parsed.expected).toBe("v");
    expect(parsed.path).toBe("X-Custom");
    expect(parsed.operator).toBe("contains");
  });
});

describe("Assertion results", () => {
  it("computes pass rate for all passed", () => {
    const results: AssertionResult[] = [
      { assertion: { type: "status", expected: "200", path: "", operator: "eq" }, passed: true, message: "OK" },
      { assertion: { type: "json_path", expected: "1", path: "$.id", operator: "eq" }, passed: true, message: "OK" },
    ];
    expect(passRate(results)).toBe(100);
  });

  it("computes pass rate for mixed results", () => {
    const results: AssertionResult[] = [
      { assertion: { type: "status", expected: "200", path: "", operator: "eq" }, passed: true, message: "OK" },
      { assertion: { type: "response_time", expected: "100", path: "", operator: "lt" }, passed: false, message: "Too slow" },
      { assertion: { type: "body_contains", expected: "ok", path: "", operator: "" }, passed: true, message: "Found" },
    ];
    expect(passRate(results)).toBe(67);
  });

  it("computes pass rate for all failed", () => {
    const results: AssertionResult[] = [
      { assertion: { type: "status", expected: "200", path: "", operator: "eq" }, passed: false, message: "Got 500" },
    ];
    expect(passRate(results)).toBe(0);
  });

  it("returns 0 for empty results", () => {
    expect(passRate([])).toBe(0);
  });
});
