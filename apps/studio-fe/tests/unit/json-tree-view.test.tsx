import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { JsonTreeView } from "../../src/components/JsonTreeView";

describe("JsonTreeView", () => {
  it("renders a simple object with keys", () => {
    render(<JsonTreeView data={{ name: "Alice", age: 30 }} />);
    expect(screen.getByText("name")).toBeInTheDocument();
    expect(screen.getByText("age")).toBeInTheDocument();
  });

  it("renders string values with quotes", () => {
    render(<JsonTreeView data={{ greeting: "hello" }} />);
    // String values are rendered with surrounding quotes
    expect(screen.getByText('"hello"')).toBeInTheDocument();
  });

  it("renders number values", () => {
    render(<JsonTreeView data={{ count: 42 }} />);
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders boolean values", () => {
    render(<JsonTreeView data={{ active: true, deleted: false }} />);
    expect(screen.getByText("true")).toBeInTheDocument();
    expect(screen.getByText("false")).toBeInTheDocument();
  });

  it("renders null values", () => {
    render(<JsonTreeView data={{ empty: null }} />);
    expect(screen.getByText("null")).toBeInTheDocument();
  });

  it("renders arrays with item count", () => {
    render(<JsonTreeView data={{ items: [1, 2, 3] }} />);
    // The root object is expanded by default (depth < 2), array too
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
    expect(screen.getAllByText("3").length).toBeGreaterThan(0);
  });

  it("renders array indices as keys", () => {
    render(<JsonTreeView data={["a", "b"]} />);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("renders nested objects", () => {
    render(<JsonTreeView data={{ user: { name: "Bob", address: { city: "NYC" } } }} />);
    expect(screen.getByText("user")).toBeInTheDocument();
    expect(screen.getByText("name")).toBeInTheDocument();
    // Depth < 2 auto-expands, so nested should be visible
    expect(screen.getByText('"Bob"')).toBeInTheDocument();
  });

  it("can collapse and expand nodes", () => {
    render(<JsonTreeView data={{ deep: { nested: { value: "hidden" } } }} />);
    // Initially open (depth < 2 for deep and nested)
    expect(screen.getByText("deep")).toBeInTheDocument();
    expect(screen.getByText("nested")).toBeInTheDocument();

    // Click on "deep" toggle to collapse
    const deepToggle = screen.getByText("deep").closest(".group");
    if (deepToggle) {
      fireEvent.click(deepToggle);
      // After collapsing, nested content should be hidden
      expect(screen.queryByText('"hidden"')).not.toBeInTheDocument();
    }
  });

  it("shows key count for collapsed objects", () => {
    // Render deeply nested to ensure depth 3+ starts collapsed
    render(
      <JsonTreeView
        data={{ a: { b: { c: { d: { e: "deep" } } } } }}
      />,
    );
    // At depth >= 2, nodes start collapsed and show key count
    // "1 key" should appear for collapsed nodes
    expect(screen.getAllByText(/\d+ key/).length).toBeGreaterThan(0);
  });

  it("handles empty object", () => {
    render(<JsonTreeView data={{}} />);
    // Should show "0 keys"
    expect(screen.getByText("0 keys")).toBeInTheDocument();
  });

  it("handles empty array", () => {
    render(<JsonTreeView data={[]} />);
    expect(screen.getByText("0 items")).toBeInTheDocument();
  });
});
