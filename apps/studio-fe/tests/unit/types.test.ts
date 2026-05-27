import { describe, it, expect } from "vitest";
import {
  newRequestTab,
  isDirty,
  signatureOf,
  parseHeadersText,
  headersToText,
  tabFromSaved,
} from "../../src/state/types";

describe("newRequestTab", () => {
  it("returns correct defaults", () => {
    const tab = newRequestTab();
    expect(tab.id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    );
    expect(tab.name).toBe("Untitled");
    expect(tab.method).toBe("GET");
    expect(tab.url).toBe("");
    expect(tab.headersRaw).toBe("");
    expect(tab.body).toBe("");
    expect(tab.auth).toEqual({ type: "none" });
    expect(tab.assertions).toEqual([]);
    expect(tab.response).toBeNull();
    expect(tab.error).toBeNull();
    expect(tab.busy).toBe(false);
    expect(tab.savedAs).toBeNull();
    expect(tab.pinned).toBe(false);
  });

  it("merges partial overrides", () => {
    const tab = newRequestTab({ name: "My Request", method: "POST", url: "http://example.com" });
    expect(tab.name).toBe("My Request");
    expect(tab.method).toBe("POST");
    expect(tab.url).toBe("http://example.com");
  });

  it("computes cleanSignature from merged state", () => {
    const tab = newRequestTab({ url: "http://test.com" });
    expect(tab.cleanSignature).toBe(signatureOf(tab));
  });
});

describe("isDirty", () => {
  it("returns false for a fresh empty tab", () => {
    const tab = newRequestTab();
    expect(isDirty(tab)).toBe(false);
  });

  it("returns true for unsaved tab with URL", () => {
    const tab = newRequestTab();
    tab.url = "http://localhost";
    expect(isDirty(tab)).toBe(true);
  });

  it("returns true for unsaved tab with headers", () => {
    const tab = newRequestTab();
    tab.headersRaw = "X-Custom: value";
    expect(isDirty(tab)).toBe(true);
  });

  it("returns true for unsaved tab with body", () => {
    const tab = newRequestTab();
    tab.body = '{"key":"value"}';
    expect(isDirty(tab)).toBe(true);
  });

  it("returns true for unsaved tab with non-none auth", () => {
    const tab = newRequestTab();
    tab.auth = { type: "bearer", token: "abc" };
    expect(isDirty(tab)).toBe(true);
  });

  it("detects dirty when saved tab URL changes", () => {
    const tab = newRequestTab({
      savedAs: { collectionId: "c1", requestId: "r1" },
      url: "http://original.com",
    });
    // Initially clean
    expect(isDirty(tab)).toBe(false);
    // Change URL
    tab.url = "http://changed.com";
    expect(isDirty(tab)).toBe(true);
  });

  it("detects dirty when saved tab method changes", () => {
    const tab = newRequestTab({
      savedAs: { collectionId: "c1", requestId: "r1" },
      method: "GET",
    });
    tab.method = "POST";
    expect(isDirty(tab)).toBe(true);
  });
});

describe("signatureOf", () => {
  it("produces same value for identical tabs", () => {
    const tab1 = newRequestTab({ url: "http://a.com", method: "GET" });
    const tab2 = newRequestTab({ url: "http://a.com", method: "GET" });
    expect(signatureOf(tab1)).toBe(signatureOf(tab2));
  });

  it("produces different values for different URLs", () => {
    const tab1 = newRequestTab({ url: "http://a.com" });
    const tab2 = newRequestTab({ url: "http://b.com" });
    expect(signatureOf(tab1)).not.toBe(signatureOf(tab2));
  });

  it("produces different values for different methods", () => {
    const tab1 = newRequestTab({ url: "http://a.com", method: "GET" });
    const tab2 = newRequestTab({ url: "http://a.com", method: "POST" });
    expect(signatureOf(tab1)).not.toBe(signatureOf(tab2));
  });

  it("produces different values for different headers", () => {
    const tab1 = newRequestTab({ headersRaw: "X-A: 1" });
    const tab2 = newRequestTab({ headersRaw: "X-B: 2" });
    expect(signatureOf(tab1)).not.toBe(signatureOf(tab2));
  });
});

describe("parseHeadersText", () => {
  it("parses simple header lines", () => {
    const result = parseHeadersText("Content-Type: application/json\nAccept: text/html");
    expect(result).toEqual({
      "Content-Type": "application/json",
      "Accept": "text/html",
    });
  });

  it("skips blank lines", () => {
    const result = parseHeadersText("X-A: 1\n\n\nX-B: 2");
    expect(result).toEqual({ "X-A": "1", "X-B": "2" });
  });

  it("skips comment lines starting with #", () => {
    const result = parseHeadersText("# This is a comment\nX-A: 1");
    expect(result).toEqual({ "X-A": "1" });
  });

  it("skips lines without colon", () => {
    const result = parseHeadersText("invalid line\nX-A: 1");
    expect(result).toEqual({ "X-A": "1" });
  });

  it("handles header values containing colons", () => {
    const result = parseHeadersText("Authorization: Bearer abc:def:ghi");
    expect(result).toEqual({ "Authorization": "Bearer abc:def:ghi" });
  });

  it("returns empty object for empty input", () => {
    expect(parseHeadersText("")).toEqual({});
  });

  it("handles CRLF line endings", () => {
    const result = parseHeadersText("X-A: 1\r\nX-B: 2");
    expect(result).toEqual({ "X-A": "1", "X-B": "2" });
  });
});

describe("headersToText", () => {
  it("serializes record to multi-line text", () => {
    const text = headersToText({ "Content-Type": "application/json", "Accept": "text/html" });
    expect(text).toBe("Content-Type: application/json\nAccept: text/html");
  });

  it("returns empty string for empty record", () => {
    expect(headersToText({})).toBe("");
  });

  it("round-trips with parseHeadersText", () => {
    const original = { "X-Foo": "bar", "X-Baz": "qux" };
    const text = headersToText(original);
    const parsed = parseHeadersText(text);
    expect(parsed).toEqual(original);
  });
});

describe("tabFromSaved", () => {
  it("maps saved request to tab with savedAs reference", () => {
    const saved = {
      id: "req-1",
      name: "Get Users",
      method: "GET" as const,
      url: "http://api.test/users",
      headers: { "Accept": "application/json" },
      body: "",
      auth: { type: "bearer" as const, token: "tok" },
      assertions: [{ type: "status" as const, expected: "200", path: "", operator: "eq" }],
      pre_request_script: "console.log('pre')",
      post_response_script: "console.log('post')",
      notes: "Some notes",
      captures: [{ name: "user_id", source: "body" as const, path: "$.id" }],
      is_folder: false,
      children: [],
    };

    const tab = tabFromSaved("col-1", saved);
    expect(tab.savedAs).toEqual({ collectionId: "col-1", requestId: "req-1" });
    expect(tab.name).toBe("Get Users");
    expect(tab.method).toBe("GET");
    expect(tab.url).toBe("http://api.test/users");
    expect(tab.headersRaw).toBe("Accept: application/json");
    expect(tab.auth).toEqual({ type: "bearer", token: "tok" });
    expect(tab.assertions).toHaveLength(1);
    expect(tab.preRequestScript).toBe("console.log('pre')");
    expect(tab.postResponseScript).toBe("console.log('post')");
    expect(tab.notes).toBe("Some notes");
    expect(tab.extractors).toEqual([{ name: "user_id", source: "body", path: "$.id" }]);
  });

  it("handles missing optional fields gracefully", () => {
    const saved = {
      id: "req-2",
      name: "Minimal",
      is_folder: false,
      children: [],
    };

    const tab = tabFromSaved("col-1", saved as any);
    expect(tab.method).toBe("GET");
    expect(tab.url).toBe("");
    expect(tab.headersRaw).toBe("");
    expect(tab.body).toBe("");
    expect(tab.auth).toEqual({ type: "none" });
    expect(tab.assertions).toEqual([]);
    expect(tab.extractors).toEqual([]);
  });
});
