/**
 * Unit tests for NewTestDialog — manual Silk spec authoring.
 * Mocks the sidecar client + Monaco editor (jsdom can't render Monaco).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NewTestDialog } from "../../src/components/NewTestDialog";

// Monaco doesn't render in jsdom — replace with a controlled textarea so we
// can assert on the template content and simulate edits.
vi.mock("@monaco-editor/react", () => ({
  default: ({
    value,
    onChange,
  }: {
    value?: string;
    onChange?: (v: string | undefined) => void;
  }) => (
    <textarea
      data-testid="monaco"
      value={value ?? ""}
      onChange={(e) => onChange?.(e.target.value)}
    />
  ),
}));

vi.mock("../../src/lib/sidecar", () => ({
  sidecar: {
    silkFrameworks: vi.fn(),
    silkSpecSave: vi.fn(),
  },
}));

import { sidecar } from "../../src/lib/sidecar";

const frameworks = [
  {
    id: "playwright-ts",
    label: "Playwright (TypeScript)",
    kind: "web" as const,
    file_extension: ".spec.ts",
    codegen_target: "playwright-test",
    recordable: true,
    runnable: true,
    template: "// PW TS template",
  },
  {
    id: "playwright-python",
    label: "Playwright (Python / pytest)",
    kind: "web" as const,
    file_extension: ".py",
    codegen_target: "python-pytest",
    recordable: true,
    runnable: false,
    template: "# PW PY template",
  },
  {
    id: "maestro",
    label: "Maestro (mobile flows)",
    kind: "mobile" as const,
    file_extension: ".yaml",
    codegen_target: null,
    recordable: false,
    runnable: false,
    template: "appId: com.example",
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(sidecar.silkFrameworks).mockResolvedValue({ frameworks });
  vi.mocked(sidecar.silkSpecSave).mockResolvedValue({
    spec_path: "/home/user/.theridion/silk/specs/my_test.spec.ts",
  });
});

describe("NewTestDialog — mount", () => {
  it("loads frameworks and seeds the default playwright-ts template", async () => {
    await act(async () => {
      render(<NewTestDialog onCancel={vi.fn()} />);
    });
    expect(vi.mocked(sidecar.silkFrameworks)).toHaveBeenCalledOnce();
    await waitFor(() =>
      expect(screen.getByTestId("monaco")).toHaveValue("// PW TS template"),
    );
    expect(screen.getByDisplayValue("my_test.spec.ts")).toBeInTheDocument();
  });

  it("groups frameworks into Web and Mobile optgroups", async () => {
    await act(async () => {
      render(<NewTestDialog onCancel={vi.fn()} />);
    });
    await waitFor(() =>
      expect(screen.getByText("Playwright (TypeScript)")).toBeInTheDocument(),
    );
    expect(screen.getByText("Maestro (mobile flows)")).toBeInTheDocument();
  });
});

describe("NewTestDialog — framework switch", () => {
  it("updates template and filename when framework changes", async () => {
    await act(async () => {
      render(<NewTestDialog onCancel={vi.fn()} />);
    });
    await waitFor(() =>
      expect(screen.getByTestId("monaco")).toHaveValue("// PW TS template"),
    );

    const select = screen.getByRole("combobox");
    await userEvent.selectOptions(select, "playwright-python");

    expect(screen.getByTestId("monaco")).toHaveValue("# PW PY template");
    // .py extension already carries the leading dot — no double dot.
    expect(screen.getByDisplayValue("my_test.py")).toBeInTheDocument();
  });
});

describe("NewTestDialog — save", () => {
  it("posts the spec and surfaces the saved path", async () => {
    const onSaved = vi.fn();
    await act(async () => {
      render(<NewTestDialog onSaved={onSaved} onCancel={vi.fn()} />);
    });
    await waitFor(() =>
      expect(screen.getByTestId("monaco")).toHaveValue("// PW TS template"),
    );

    await userEvent.click(screen.getByRole("button", { name: /Uložit/i }));

    await waitFor(() =>
      expect(vi.mocked(sidecar.silkSpecSave)).toHaveBeenCalledWith(
        expect.objectContaining({
          framework: "playwright-ts",
          filename: "my_test.spec.ts",
          code: "// PW TS template",
        }),
      ),
    );
    expect(onSaved).toHaveBeenCalledWith(
      "/home/user/.theridion/silk/specs/my_test.spec.ts",
    );
    expect(
      screen.getByText("/home/user/.theridion/silk/specs/my_test.spec.ts"),
    ).toBeInTheDocument();
  });

  it("shows an error banner when save fails", async () => {
    vi.mocked(sidecar.silkSpecSave).mockRejectedValue(
      new Error("filename contains illegal path segment"),
    );
    await act(async () => {
      render(<NewTestDialog onCancel={vi.fn()} />);
    });
    await waitFor(() =>
      expect(screen.getByTestId("monaco")).toHaveValue("// PW TS template"),
    );

    await userEvent.click(screen.getByRole("button", { name: /Uložit/i }));

    await waitFor(() =>
      expect(
        screen.getByText(/illegal path segment/i),
      ).toBeInTheDocument(),
    );
  });
});

describe("NewTestDialog — framework load failure", () => {
  it("falls back to a manual-authoring placeholder", async () => {
    vi.mocked(sidecar.silkFrameworks).mockRejectedValue(
      new Error("sidecar down"),
    );
    await act(async () => {
      render(<NewTestDialog onCancel={vi.fn()} />);
    });
    await waitFor(() =>
      expect(screen.getByText(/Nelze načíst seznam frameworků/i)).toBeInTheDocument(),
    );
    expect(screen.getByTestId("monaco")).toHaveValue(
      "// Framework templates not available — write your test manually",
    );
  });
});
