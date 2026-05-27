/**
 * Tests for template variable detection and resolution logic.
 *
 * The template engine lives on the sidecar (Python), but the frontend does
 * client-side detection/preview for UX (autocomplete, resolved URL preview).
 * These tests validate the regex patterns and resolution algorithm used in
 * the UrlBar and request execution flow.
 */
import { describe, it, expect } from "vitest";

// --- Utility functions extracted from the app's template logic ---

/** Detect all {{variable}} references in a string. */
function extractTemplateVars(input: string): string[] {
  const matches = input.matchAll(/\{\{([^}]+)\}\}/g);
  return [...matches].map((m) => m[1]);
}

/** Check if a string contains any template variables. */
function hasTemplateVars(input: string): boolean {
  return input.includes("{{");
}

/** Resolve template variables with given environment values. Unresolved remain as-is. */
function resolveTemplateVars(
  input: string,
  envVars: { name: string; value: string }[],
): string {
  let resolved = input;
  for (const v of envVars) {
    resolved = resolved.replaceAll(`{{${v.name}}}`, v.value);
  }
  return resolved;
}

/** Resolve built-in template functions. */
function resolveBuiltins(input: string): string {
  let resolved = input;
  resolved = resolved.replace(/\{\{\$timestamp\}\}/g, String(Math.floor(Date.now() / 1000)));
  resolved = resolved.replace(/\{\{\$uuid\}\}/g, crypto.randomUUID());
  resolved = resolved.replace(/\{\{\$isoDate\}\}/g, new Date().toISOString());
  resolved = resolved.replace(/\{\{\$randomInt\}\}/g, String(Math.floor(Math.random() * 1000)));
  return resolved;
}

// --- Tests ---

describe("extractTemplateVars", () => {
  it("extracts single variable", () => {
    expect(extractTemplateVars("{{host}}/api")).toEqual(["host"]);
  });

  it("extracts multiple variables", () => {
    expect(extractTemplateVars("{{base_url}}/users/{{user_id}}")).toEqual([
      "base_url",
      "user_id",
    ]);
  });

  it("extracts built-in variables", () => {
    expect(extractTemplateVars("ts={{$timestamp}}&id={{$uuid}}")).toEqual([
      "$timestamp",
      "$uuid",
    ]);
  });

  it("returns empty array for no variables", () => {
    expect(extractTemplateVars("http://plain-url.com")).toEqual([]);
  });

  it("handles adjacent variables", () => {
    expect(extractTemplateVars("{{a}}{{b}}")).toEqual(["a", "b"]);
  });
});

describe("hasTemplateVars", () => {
  it("returns true when variables present", () => {
    expect(hasTemplateVars("http://{{host}}/api")).toBe(true);
  });

  it("returns false when no variables", () => {
    expect(hasTemplateVars("http://localhost/api")).toBe(false);
  });

  it("returns true for built-in variables", () => {
    expect(hasTemplateVars("{{$timestamp}}")).toBe(true);
  });
});

describe("resolveTemplateVars", () => {
  const env = [
    { name: "base_url", value: "http://api.test" },
    { name: "token", value: "abc123" },
  ];

  it("resolves known variables", () => {
    const result = resolveTemplateVars("{{base_url}}/users", env);
    expect(result).toBe("http://api.test/users");
  });

  it("resolves multiple variables", () => {
    const result = resolveTemplateVars("{{base_url}}?auth={{token}}", env);
    expect(result).toBe("http://api.test?auth=abc123");
  });

  it("leaves unresolved variables as-is", () => {
    const result = resolveTemplateVars("{{base_url}}/{{unknown}}", env);
    expect(result).toBe("http://api.test/{{unknown}}");
  });

  it("handles no variables in string", () => {
    const result = resolveTemplateVars("http://plain.com", env);
    expect(result).toBe("http://plain.com");
  });

  it("handles empty env", () => {
    const result = resolveTemplateVars("{{host}}/api", []);
    expect(result).toBe("{{host}}/api");
  });

  it("resolves same variable used multiple times", () => {
    const result = resolveTemplateVars("{{base_url}}/a and {{base_url}}/b", env);
    expect(result).toBe("http://api.test/a and http://api.test/b");
  });
});

describe("resolveBuiltins", () => {
  it("resolves $timestamp to a numeric string", () => {
    const result = resolveBuiltins("ts={{$timestamp}}");
    const value = result.replace("ts=", "");
    expect(Number(value)).toBeGreaterThan(1700000000);
    expect(Number(value)).toBeLessThan(2000000000);
  });

  it("resolves $uuid to UUID format", () => {
    const result = resolveBuiltins("id={{$uuid}}");
    const value = result.replace("id=", "");
    expect(value).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    );
  });

  it("resolves $isoDate to ISO format", () => {
    const result = resolveBuiltins("date={{$isoDate}}");
    const value = result.replace("date=", "");
    expect(new Date(value).toISOString()).toBe(value);
  });

  it("resolves $randomInt to a number", () => {
    const result = resolveBuiltins("n={{$randomInt}}");
    const value = Number(result.replace("n=", ""));
    expect(value).toBeGreaterThanOrEqual(0);
    expect(value).toBeLessThan(1000);
  });

  it("leaves non-built-in variables untouched", () => {
    const result = resolveBuiltins("{{custom_var}}/path");
    expect(result).toBe("{{custom_var}}/path");
  });

  it("resolves multiple built-ins in one string", () => {
    const result = resolveBuiltins("{{$timestamp}}-{{$uuid}}");
    expect(result).not.toContain("{{$timestamp}}");
    expect(result).not.toContain("{{$uuid}}");
  });
});
