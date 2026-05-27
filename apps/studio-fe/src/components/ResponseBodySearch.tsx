import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, CaseSensitive, Regex, X } from "lucide-react";
import type { BodySearchMatch, JsonPathMatch, XPathMatch } from "../lib/sidecar";
import { sidecar } from "../lib/sidecar";

type SearchMode = "text" | "jsonpath" | "xpath";

interface Props {
  body: string;
  visible: boolean;
  onClose: () => void;
  /** Called with match ranges so parent can highlight in Monaco. */
  onMatchesChange: (matches: BodySearchMatch[]) => void;
  /** Called with current match index so parent can scroll to it. */
  onCurrentMatchChange: (index: number) => void;
  /** Whether the body is XML (shows XPath tab). */
  isXml?: boolean;
}

export function ResponseBodySearch({ body, visible, onClose, onMatchesChange, onCurrentMatchChange, isXml }: Props) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("text");
  const [useRegex, setUseRegex] = useState(false);
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [, setMatches] = useState<BodySearchMatch[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [total, setTotal] = useState(0);
  const [queryValid, setQueryValid] = useState(true);
  const [jsonPathMatches, setJsonPathMatches] = useState<JsonPathMatch[]>([]);
  const [xpathMatches, setXpathMatches] = useState<XPathMatch[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  // Focus input when search becomes visible
  useEffect(() => {
    if (visible) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery("");
      setMatches([]);
      setTotal(0);
      setCurrentIndex(0);
      onMatchesChange([]);
    }
  }, [visible, onMatchesChange]);

  const doSearch = useCallback(async (q: string) => {
    if (!q || !body) {
      setMatches([]);
      setTotal(0);
      setQueryValid(true);
      setJsonPathMatches([]);
      setXpathMatches([]);
      onMatchesChange([]);
      return;
    }

    if (mode === "text") {
      try {
        const result = await sidecar.searchBody({ body, query: q, regex: useRegex, case_sensitive: caseSensitive });
        setMatches(result.matches);
        setTotal(result.total);
        setQueryValid(result.query_valid);
        setCurrentIndex(result.total > 0 ? 0 : -1);
        onMatchesChange(result.matches);
        if (result.total > 0) onCurrentMatchChange(0);
      } catch {
        setMatches([]);
        setTotal(0);
        setQueryValid(false);
        onMatchesChange([]);
      }
    } else if (mode === "jsonpath") {
      try {
        const result = await sidecar.searchJsonPath({ body, path: q });
        setJsonPathMatches(result.matches);
        setTotal(result.total);
        setMatches([]);
        onMatchesChange([]);
      } catch {
        setJsonPathMatches([]);
        setTotal(0);
      }
    } else if (mode === "xpath") {
      try {
        const result = await sidecar.searchXPath({ body, xpath: q });
        setXpathMatches(result.matches);
        setTotal(result.total);
        setMatches([]);
        onMatchesChange([]);
      } catch {
        setXpathMatches([]);
        setTotal(0);
      }
    }
  }, [body, mode, useRegex, caseSensitive, onMatchesChange, onCurrentMatchChange]);

  // Debounced search on query/options change
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void doSearch(query);
    }, 200);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, doSearch]);

  const goNext = useCallback(() => {
    if (total <= 0) return;
    const next = (currentIndex + 1) % total;
    setCurrentIndex(next);
    onCurrentMatchChange(next);
  }, [currentIndex, total, onCurrentMatchChange]);

  const goPrev = useCallback(() => {
    if (total <= 0) return;
    const prev = (currentIndex - 1 + total) % total;
    setCurrentIndex(prev);
    onCurrentMatchChange(prev);
  }, [currentIndex, total, onCurrentMatchChange]);

  // Keyboard shortcuts
  const onKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      goNext();
    } else if (e.key === "Enter" && e.shiftKey) {
      e.preventDefault();
      goPrev();
    }
  }, [onClose, goNext, goPrev]);

  if (!visible) return null;

  return (
    <div className="absolute left-0 right-0 top-0 z-30 flex flex-col border-b border-glass bg-neutral-900/95 backdrop-blur-sm">
      {/* Mode tabs */}
      <div className="flex items-center gap-0.5 border-b border-glass/50 px-2 pt-1">
        <ModeTab active={mode === "text"} onClick={() => setMode("text")}>Text</ModeTab>
        <ModeTab active={mode === "jsonpath"} onClick={() => setMode("jsonpath")}>JSONPath</ModeTab>
        {isXml && <ModeTab active={mode === "xpath"} onClick={() => setMode("xpath")}>XPath</ModeTab>}
      </div>
      {/* Search input row */}
      <div className="flex items-center gap-1.5 px-2 py-1.5">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={mode === "text" ? "Search in body..." : mode === "jsonpath" ? "$.path.to.value" : "//xpath/expression"}
          className={`min-w-0 flex-1 rounded-md border bg-neutral-950 px-2 py-1 text-xs text-neutral-100 placeholder-neutral-600 outline-none transition ${
            !queryValid ? "border-rose-500/60 focus:border-rose-400" : "border-glass focus:border-cobweb-500/60"
          }`}
        />
        {mode === "text" && (
          <>
            <button
              type="button"
              onClick={() => setUseRegex((r) => !r)}
              className={`rounded p-1 transition ${useRegex ? "bg-cobweb-600/20 text-cobweb-400" : "text-neutral-500 hover:text-neutral-300"}`}
              title="Use regex"
            >
              <Regex className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setCaseSensitive((c) => !c)}
              className={`rounded p-1 transition ${caseSensitive ? "bg-cobweb-600/20 text-cobweb-400" : "text-neutral-500 hover:text-neutral-300"}`}
              title="Case sensitive"
            >
              <CaseSensitive className="h-3.5 w-3.5" />
            </button>
          </>
        )}
        {/* Match counter */}
        {query && mode === "text" && (
          <span className={`whitespace-nowrap text-[11px] ${total > 0 ? "text-neutral-400" : "text-neutral-600"}`}>
            {total > 0 ? `${currentIndex + 1}/${total}` : "No matches"}
          </span>
        )}
        {query && mode !== "text" && (
          <span className={`whitespace-nowrap text-[11px] ${total > 0 ? "text-neutral-400" : "text-neutral-600"}`}>
            {total > 0 ? `${total} match${total !== 1 ? "es" : ""}` : "No matches"}
          </span>
        )}
        {/* Navigation arrows (text mode only) */}
        {mode === "text" && (
          <>
            <button
              type="button"
              onClick={goPrev}
              disabled={total === 0}
              className="rounded p-1 text-neutral-500 transition hover:text-neutral-300 disabled:opacity-30"
              title="Previous match (Shift+Enter)"
            >
              <ArrowUp className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={goNext}
              disabled={total === 0}
              className="rounded p-1 text-neutral-500 transition hover:text-neutral-300 disabled:opacity-30"
              title="Next match (Enter)"
            >
              <ArrowDown className="h-3.5 w-3.5" />
            </button>
          </>
        )}
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-neutral-500 transition hover:text-neutral-300"
          title="Close (Escape)"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      {/* JSONPath / XPath results */}
      {mode === "jsonpath" && jsonPathMatches.length > 0 && (
        <div className="max-h-40 overflow-auto border-t border-glass/50 px-2 py-1">
          {jsonPathMatches.map((m, i) => (
            <div key={i} className="flex items-start gap-2 py-0.5 text-[11px]">
              <span className="shrink-0 text-cobweb-400 font-mono">{m.path}</span>
              <span className="text-neutral-500">=</span>
              <span className="truncate text-neutral-300 font-mono">{typeof m.value === "string" ? m.value : JSON.stringify(m.value)}</span>
              <span className="shrink-0 text-neutral-600">({m.type})</span>
            </div>
          ))}
        </div>
      )}
      {mode === "xpath" && xpathMatches.length > 0 && (
        <div className="max-h-40 overflow-auto border-t border-glass/50 px-2 py-1">
          {xpathMatches.map((m, i) => (
            <div key={i} className="flex items-start gap-2 py-0.5 text-[11px]">
              <span className="shrink-0 text-cobweb-400 font-mono">{m.path}</span>
              <span className="text-neutral-500">=</span>
              <span className="truncate text-neutral-300 font-mono">{m.value}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ModeTab({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-2 py-1 text-[11px] font-medium transition ${
        active ? "border-b border-cobweb-500 text-neutral-100" : "text-neutral-500 hover:text-neutral-300"
      }`}
    >
      {children}
    </button>
  );
}
