import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, X, Eye, AlertTriangle } from "lucide-react";
import { sidecar } from "../lib/sidecar";
import type { TemplateValidateOutput } from "../lib/sidecar";

/** Template functions available for autocomplete when user types {{$ */
const TEMPLATE_FUNCTIONS = [
  { trigger: "$if", label: "$if condition", snippet: "$if ", description: "Conditional block" },
  { trigger: "$endif", label: "$endif", snippet: "$endif", description: "End conditional" },
  { trigger: "$each", label: "$each items as item", snippet: "$each ", description: "Loop over array" },
  { trigger: "$end", label: "$end", snippet: "$end", description: "End loop" },
  { trigger: "$concat", label: "$concat var1 var2", snippet: "$concat ", description: "String concatenation" },
  { trigger: "$math", label: "$math expr", snippet: "$math ", description: "Arithmetic (+, -, *, /)" },
  { trigger: "$default", label: '$default var "fallback"', snippet: "$default ", description: "Default value" },
  { trigger: "$env", label: "$env VAR_NAME", snippet: "$env ", description: "System env variable" },
  { trigger: "$timestamp", label: "$timestamp", snippet: "$timestamp", description: "Unix timestamp (ms)" },
  { trigger: "$uuid", label: "$uuid", snippet: "$uuid", description: "Random UUID v4" },
  { trigger: "$isoDate", label: "$isoDate", snippet: "$isoDate", description: "ISO 8601 date" },
  { trigger: "$randomInt", label: "$randomInt", snippet: "$randomInt", description: "Random 0–1M" },
] as const;

/** Pipe filters available after | */
const PIPE_FILTERS = [
  { name: "upper", description: "Uppercase" },
  { name: "lower", description: "Lowercase" },
  { name: "base64", description: "Base64 encode" },
  { name: "json", description: "JSON stringify" },
  { name: "urlencode", description: "URL encode" },
  { name: "trim", description: "Trim whitespace" },
  { name: "slice:0:N", description: "Substring" },
] as const;

interface TemplateAutocompleteProps {
  /** Current text value (URL or body) */
  value: string;
  /** Cursor position in the text */
  cursorPosition?: number;
  /** Callback when user selects a completion */
  onInsert: (text: string) => void;
  /** Additional class */
  className?: string;
}

/**
 * Dropdown autocomplete for template expressions.
 * Shows when cursor is inside {{ and user typed $.
 */
export function TemplateAutocomplete({ value, cursorPosition, onInsert, className }: TemplateAutocompleteProps) {
  const [visible, setVisible] = useState(false);
  const [filter, setFilter] = useState("");
  const [mode, setMode] = useState<"functions" | "filters">("functions");

  useEffect(() => {
    if (cursorPosition == null) { setVisible(false); return; }

    const textBefore = value.slice(0, cursorPosition);

    // Check if we're inside {{ and just typed $
    const funcMatch = textBefore.match(/\{\{\s*(\$\w*)$/);
    if (funcMatch) {
      setMode("functions");
      setFilter(funcMatch[1]);
      setVisible(true);
      return;
    }

    // Check if we're after a pipe |
    const pipeMatch = textBefore.match(/\{\{[^}]*\|\s*(\w*)$/);
    if (pipeMatch) {
      setMode("filters");
      setFilter(pipeMatch[1]);
      setVisible(true);
      return;
    }

    setVisible(false);
  }, [value, cursorPosition]);

  const items = useMemo(() => {
    if (mode === "functions") {
      return TEMPLATE_FUNCTIONS.filter(f =>
        f.trigger.toLowerCase().startsWith(filter.toLowerCase())
      );
    }
    return PIPE_FILTERS.filter(f =>
      f.name.toLowerCase().startsWith(filter.toLowerCase())
    );
  }, [mode, filter]);

  if (!visible || items.length === 0) return null;

  return (
    <div className={`absolute z-50 mt-1 max-h-48 overflow-y-auto rounded border border-neutral-700 bg-neutral-900 shadow-lg ${className ?? ""}`}>
      {items.map((item, i) => (
        <button
          key={i}
          className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-neutral-800"
          onMouseDown={(e) => {
            e.preventDefault();
            const text = mode === "functions"
              ? (item as typeof TEMPLATE_FUNCTIONS[number]).snippet
              : (item as typeof PIPE_FILTERS[number]).name;
            onInsert(text);
            setVisible(false);
          }}
        >
          <span className="font-mono text-emerald-400">
            {mode === "functions" ? (item as typeof TEMPLATE_FUNCTIONS[number]).trigger : (item as typeof PIPE_FILTERS[number]).name}
          </span>
          <span className="text-neutral-400">
            {"description" in item ? item.description : ""}
          </span>
        </button>
      ))}
    </div>
  );
}

// ---- Template Validation Indicator ----

interface TemplateValidationProps {
  template: string;
  className?: string;
}

/**
 * Small indicator (green check / red X) showing if a template is valid.
 * Validates on change with debounce.
 */
export function TemplateValidationIndicator({ template, className }: TemplateValidationProps) {
  const [result, setResult] = useState<TemplateValidateOutput | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    // Only validate if template contains {{ expressions
    if (!template.includes("{{")) {
      setResult(null);
      return;
    }

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const r = await sidecar.templateValidate({ template });
        setResult(r);
      } catch {
        setResult(null);
      }
    }, 400);

    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [template]);

  if (!result) return null;

  return (
    <span className={`inline-flex items-center gap-1 text-xs ${className ?? ""}`} title={result.errors.join("; ")}>
      {result.valid ? (
        <Check className="h-3.5 w-3.5 text-emerald-500" />
      ) : (
        <AlertTriangle className="h-3.5 w-3.5 text-red-400" />
      )}
    </span>
  );
}

// ---- Template Preview Button ----

interface TemplatePreviewProps {
  template: string;
  variables: Record<string, unknown>;
  className?: string;
}

/**
 * "Preview rendered" button that shows the template output with current env vars.
 */
export function TemplatePreviewButton({ template, variables, className }: TemplatePreviewProps) {
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showPopover, setShowPopover] = useState(false);

  const handlePreview = useCallback(async () => {
    if (!template.includes("{{")) return;
    setLoading(true);
    try {
      const r = await sidecar.templateRender({ template, variables });
      setPreview(r.rendered);
      setShowPopover(true);
    } catch (e) {
      setPreview(`Error: ${e instanceof Error ? e.message : String(e)}`);
      setShowPopover(true);
    } finally {
      setLoading(false);
    }
  }, [template, variables]);

  // Only show button if template has expressions
  if (!template.includes("{{")) return null;

  return (
    <div className={`relative inline-block ${className ?? ""}`}>
      <button
        className="flex items-center gap-1 rounded px-2 py-1 text-xs text-neutral-400 hover:bg-neutral-800 hover:text-neutral-200"
        onClick={handlePreview}
        disabled={loading}
        title="Preview rendered template"
      >
        <Eye className="h-3.5 w-3.5" />
        <span>Preview</span>
      </button>
      {showPopover && preview !== null && (
        <div className="absolute right-0 top-full z-50 mt-1 max-h-40 max-w-md overflow-auto rounded border border-neutral-700 bg-neutral-900 p-2 text-xs shadow-lg">
          <div className="mb-1 flex items-center justify-between">
            <span className="font-medium text-neutral-300">Rendered output</span>
            <button
              className="text-neutral-500 hover:text-neutral-300"
              onClick={() => setShowPopover(false)}
            >
              <X className="h-3 w-3" />
            </button>
          </div>
          <pre className="whitespace-pre-wrap font-mono text-neutral-200">{preview}</pre>
        </div>
      )}
    </div>
  );
}
