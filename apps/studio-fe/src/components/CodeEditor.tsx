import { useEffect, useRef, useState } from "react";
import Editor, { type OnMount } from "@monaco-editor/react";

interface Props {
  value: string;
  onChange?: (next: string) => void;
  language?: "json" | "xml" | "html" | "javascript" | "typescript" | "plaintext";
  /** Auto-pick a language from a Content-Type or content shape. */
  contentTypeHint?: string | null;
  readOnly?: boolean;
  /** Pixels — when omitted, fills its container via flex. */
  height?: number | string;
  placeholder?: string;
  /** Called when the Monaco editor instance is mounted, exposing the editor ref. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onEditorMount?: (editor: any) => void;
}

const DEFAULT_OPTIONS = {
  fontFamily:
    'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, monospace',
  fontSize: 12,
  lineHeight: 18,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  smoothScrolling: true,
  cursorBlinking: "smooth" as const,
  cursorSmoothCaretAnimation: "on" as const,
  renderLineHighlight: "all" as const,
  guides: { indentation: false, highlightActiveIndentation: false },
  scrollbar: {
    vertical: "auto" as const,
    horizontal: "auto" as const,
    verticalScrollbarSize: 8,
    horizontalScrollbarSize: 8,
  },
  padding: { top: 8, bottom: 8 },
  tabSize: 2,
  wordWrap: "on" as const,
  fixedOverflowWidgets: true,
  formatOnPaste: false,
};

export function CodeEditor({
  value,
  onChange,
  language,
  contentTypeHint,
  readOnly = false,
  height,
  placeholder,
  onEditorMount,
}: Props) {
  const [ready, setReady] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const lang = language ?? guessLanguage(value, contentTypeHint);

  const handleMount: OnMount = (editor, monaco) => {
    function applyTheme() {
      const s = getComputedStyle(document.documentElement);
      const accent = (shade: string) => {
        const raw = s.getPropertyValue(`--accent-${shade}`).trim();
        // CSS var is "R G B" space-separated — convert to hex.
        const parts = raw.split(/\s+/).map(Number);
        if (parts.length === 3) return parts.map((n) => n.toString(16).padStart(2, "0")).join("");
        return "06b6d4"; // fallback
      };
      const a500 = accent("500");
      const a300 = accent("300");

      monaco.editor.defineTheme("theridion-dark", {
        base: "vs-dark",
        inherit: true,
        rules: [
          { token: "comment", foreground: "525252", fontStyle: "italic" },
          { token: "string.key.json", foreground: a300 },
          { token: "string.value.json", foreground: "6ee7b7" },
          { token: "number", foreground: "fcd34d" },
          { token: "keyword.json", foreground: "c4b5fd" },
          { token: "keyword", foreground: "c4b5fd" },
          { token: "tag", foreground: "f472b6" },
          { token: "attribute.name", foreground: a300 },
          { token: "attribute.value", foreground: "6ee7b7" },
          { token: "string", foreground: "6ee7b7" },
          { token: "delimiter", foreground: "525252" },
        ],
        colors: {
          "editor.background": "#0c0c0e",
          "editor.foreground": "#d4d4d8",
          "editorLineNumber.foreground": "#3f3f46",
          "editorLineNumber.activeForeground": "#71717a",
          "editor.lineHighlightBackground": "#18181b",
          "editor.lineHighlightBorder": "#00000000",
          "editorCursor.foreground": `#${a500}`,
          "editor.selectionBackground": `#${a500}30`,
          "editorBracketMatch.background": `#${a500}20`,
          "editorBracketMatch.border": `#${a500}60`,
          "editorGutter.background": "#0c0c0e",
          "editor.inactiveSelectionBackground": `#${a500}15`,
          "editorIndentGuide.background1": "#27272a",
          "editorWidget.background": "#18181b",
          "editorWidget.border": "#27272a",
        },
      });
      monaco.editor.setTheme("theridion-dark");
    }

    applyTheme();
    // Re-apply when theme changes (class on <html> switches CSS vars).
    const obs = new MutationObserver(() => applyTheme());
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

    setReady(true);
    requestAnimationFrame(() => editor.layout());
    onEditorMount?.(editor);
  };

  // Re-layout on container resize so the editor stays snug inside flex/grid.
  useEffect(() => {
    if (!ready || !containerRef.current) return;
    const obs = new ResizeObserver(() => {
      window.dispatchEvent(new Event("resize"));
    });
    obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, [ready]);

  const showPlaceholder =
    !!placeholder && value.length === 0 && !readOnly && ready;

  return (
    <div ref={containerRef} className="relative h-full w-full overflow-hidden">
      <Editor
        height={height ?? "100%"}
        language={lang}
        value={value}
        theme="theridion-dark"
        onChange={(v) => onChange?.(v ?? "")}
        onMount={handleMount}
        loading={
          <div className="flex h-full items-center justify-center text-xs text-neutral-600">
            Loading editor…
          </div>
        }
        options={{ ...DEFAULT_OPTIONS, readOnly }}
      />
      {showPlaceholder && (
        <div className="pointer-events-none absolute left-12 top-2 font-mono text-xs text-neutral-700">
          {placeholder}
        </div>
      )}
    </div>
  );
}

function guessLanguage(
  value: string,
  contentType: string | null | undefined,
): Props["language"] {
  const ct = (contentType ?? "").toLowerCase();
  if (ct.includes("json")) return "json";
  if (ct.includes("xml") || ct.includes("soap")) return "xml";
  if (ct.includes("html")) return "html";
  if (ct.includes("javascript")) return "javascript";

  const head = value.trimStart().slice(0, 16);
  if (head.startsWith("{") || head.startsWith("[")) return "json";
  if (head.startsWith("<?xml") || head.startsWith("<")) return "xml";
  return "plaintext";
}
