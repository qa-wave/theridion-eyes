import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ClipboardPaste,
  FileCode2,
  Loader2,
  Sparkles,
  Upload,
  X,
  Zap,
} from "lucide-react";
import {
  sidecar,
  type TestgenCategory,
  type TestgenParseOutput,
} from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (collectionId: string) => void;
}

const ALL_CATEGORIES: { id: TestgenCategory; label: string; hint: string }[] = [
  {
    id: "is_alive",
    label: "Is alive",
    hint: "Minimal liveness probe — healthcheck or first reachable GET.",
  },
  {
    id: "smoke",
    label: "Smoke tests",
    hint: "One happy-path request per operation with sample data.",
  },
  {
    id: "regression",
    label: "Regression tests",
    hint: "Negative cases: missing ids, empty bodies, invalid enums, SOAP faults.",
  },
];

export function TestGenModal({ open, onClose, onCreated }: Props) {
  const [content, setContent] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [collectionName, setCollectionName] = useState("");
  const [categories, setCategories] = useState<Record<TestgenCategory, boolean>>({
    is_alive: true,
    smoke: true,
    regression: true,
  });
  const [parsed, setParsed] = useState<TestgenParseOutput | null>(null);
  const [parsing, setParsing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Auto-parse when content changes (debounced).
  useEffect(() => {
    if (!content.trim()) {
      setParsed(null);
      setError(null);
      return;
    }
    const handle = setTimeout(() => void parseNow(), 350);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content, baseUrl]);

  const parseNow = useCallback(async () => {
    setParsing(true);
    setError(null);
    try {
      const out = await sidecar.testgenParse({
        content,
        base_url: baseUrl || null,
      });
      setParsed(out);
      if (!collectionName && out.kind !== "unknown") {
        setCollectionName(`${out.service_name} — generated tests`);
      }
      if (out.kind === "unknown") {
        setError("Could not detect an OpenAPI or WSDL definition.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setParsed(null);
    } finally {
      setParsing(false);
    }
  }, [content, baseUrl, collectionName]);

  const generate = useCallback(async () => {
    if (!parsed || parsed.kind === "unknown") return;
    const picked = Object.entries(categories)
      .filter(([, v]) => v)
      .map(([k]) => k as TestgenCategory);
    if (picked.length === 0) {
      setError("Pick at least one category.");
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      const out = await sidecar.testgenGenerate({
        content,
        base_url: baseUrl || null,
        collection_name: collectionName || null,
        categories: picked,
      });
      onCreated(out.collection_id);
      reset();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setGenerating(false);
    }
  }, [parsed, categories, content, baseUrl, collectionName, onCreated, onClose]);

  const reset = useCallback(() => {
    setContent("");
    setBaseUrl("");
    setCollectionName("");
    setParsed(null);
    setError(null);
  }, []);

  const handleFile = useCallback(async (file: File) => {
    const text = await file.text();
    setContent(text);
  }, []);

  const handlePaste = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText();
      setContent(text);
    } catch {
      // clipboard denied
    }
  }, []);

  const projectedCount = useMemo(() => {
    if (!parsed) return 0;
    let n = 0;
    for (const [cat, on] of Object.entries(categories)) {
      if (on) n += parsed.expected_counts[cat] ?? 0;
    }
    return n;
  }, [parsed, categories]);

  if (!open) return null;

  const kindBadge = parsed && parsed.kind !== "unknown" ? (
    <span
      className={
        "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider " +
        (parsed.kind === "openapi"
          ? "bg-emerald-500/15 text-emerald-300"
          : "bg-amber-500/15 text-amber-300")
      }
    >
      {parsed.kind === "openapi" ? "OpenAPI" : "WSDL / SOAP"}
    </span>
  ) : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[80vh] w-[min(1100px,95vw)] flex-col rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Sparkles className="h-4 w-4 text-cobweb-400" />
            Generate tests from service definition
          </div>
          <button
            type="button"
            onClick={() => {
              reset();
              onClose();
            }}
            className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-[1.1fr_0.9fr]">
          {/* ---- LEFT: spec editor ---- */}
          <div className="flex min-h-0 flex-col border-r border-glass">
            <div className="flex items-center gap-2 border-b border-glass px-4 py-2">
              <FileCode2 className="h-3.5 w-3.5 text-neutral-400" />
              <span className="text-[11px] uppercase tracking-widest text-neutral-500">
                Service definition (OpenAPI / WSDL)
              </span>
              <div className="ml-auto flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-neutral-400 transition hover:bg-white/[0.05] hover:text-neutral-200"
                  title="Open file"
                >
                  <Upload className="h-3 w-3" /> Open file
                </button>
                <button
                  type="button"
                  onClick={handlePaste}
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-neutral-400 transition hover:bg-white/[0.05] hover:text-neutral-200"
                  title="Paste from clipboard"
                >
                  <ClipboardPaste className="h-3 w-3" /> Paste
                </button>
                <input
                  type="file"
                  ref={fileRef}
                  className="hidden"
                  accept=".yaml,.yml,.json,.xml,.wsdl,text/*"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void handleFile(f);
                    e.target.value = "";
                  }}
                />
              </div>
            </div>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={"Paste an OpenAPI YAML/JSON or a WSDL XML here, or load a file."}
              className="flex-1 resize-none bg-neutral-925 px-4 py-3 font-mono text-[11px] leading-relaxed text-neutral-200 placeholder-neutral-600 focus:outline-none"
              spellCheck={false}
            />
          </div>

          {/* ---- RIGHT: parsed summary + categories ---- */}
          <div className="flex min-h-0 flex-col">
            <div className="flex items-center gap-2 border-b border-glass px-4 py-2">
              <Zap className="h-3.5 w-3.5 text-neutral-400" />
              <span className="text-[11px] uppercase tracking-widest text-neutral-500">
                Detected
              </span>
              {parsing && <Loader2 className="h-3 w-3 animate-spin text-neutral-500" />}
              {kindBadge}
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-3 text-xs">
              {!content.trim() ? (
                <div className="mt-12 text-center text-neutral-500">
                  Provide a definition on the left to begin.
                </div>
              ) : !parsed || parsed.kind === "unknown" ? (
                <div className="text-neutral-500">
                  {error ?? "Parsing…"}
                </div>
              ) : (
                <>
                  <div className="mb-3 rounded-md border border-glass bg-neutral-900/40 p-3">
                    <div className="text-[11px] uppercase tracking-widest text-neutral-500">
                      Service
                    </div>
                    <div className="mt-0.5 text-sm font-medium text-neutral-100">
                      {parsed.service_name || "(unnamed)"}
                    </div>
                    <div className="mt-2 grid grid-cols-[80px_1fr] gap-y-1 text-[11px]">
                      <span className="text-neutral-500">Base URL</span>
                      <input
                        value={baseUrl || parsed.base_url}
                        onChange={(e) => setBaseUrl(e.target.value)}
                        className="rounded border border-glass bg-neutral-900/60 px-1.5 py-0.5 font-mono text-[11px] text-neutral-200 focus:border-cobweb-500/40 focus:outline-none"
                      />
                      <span className="text-neutral-500">Operations</span>
                      <span className="text-neutral-300">{parsed.operations.length}</span>
                    </div>
                  </div>

                  <div className="mb-3 max-h-44 overflow-y-auto rounded-md border border-glass bg-neutral-900/40">
                    {parsed.operations.map((op, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-2 border-b border-glass-light/30 px-3 py-1.5 text-[11px] last:border-0"
                      >
                        <span
                          className={
                            "rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold " +
                            methodTint(op.method)
                          }
                        >
                          {op.method}
                        </span>
                        <span className="truncate font-mono text-neutral-300">{op.path}</span>
                        {op.summary && (
                          <span className="ml-auto truncate text-neutral-500">{op.summary}</span>
                        )}
                      </div>
                    ))}
                  </div>

                  <div className="mb-2 text-[11px] uppercase tracking-widest text-neutral-500">
                    Test categories
                  </div>
                  <div className="mb-3 space-y-2">
                    {ALL_CATEGORIES.map((c) => {
                      const count = parsed.expected_counts[c.id] ?? 0;
                      const on = categories[c.id];
                      return (
                        <label
                          key={c.id}
                          className={
                            "flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2 transition " +
                            (on
                              ? "border-cobweb-500/40 bg-cobweb-500/[0.06]"
                              : "border-glass bg-neutral-900/30 hover:border-glass-light")
                          }
                        >
                          <input
                            type="checkbox"
                            checked={on}
                            onChange={(e) =>
                              setCategories((prev) => ({ ...prev, [c.id]: e.target.checked }))
                            }
                            className="mt-0.5 h-3.5 w-3.5 accent-cobweb-500"
                          />
                          <div className="flex-1">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-medium text-neutral-100">
                                {c.label}
                              </span>
                              <span className="rounded bg-neutral-800 px-1.5 py-0.5 font-mono text-[10px] text-neutral-300">
                                {count} test{count === 1 ? "" : "s"}
                              </span>
                            </div>
                            <div className="mt-0.5 text-[11px] text-neutral-500">{c.hint}</div>
                          </div>
                        </label>
                      );
                    })}
                  </div>

                  <div className="mb-1 text-[11px] uppercase tracking-widest text-neutral-500">
                    Collection name
                  </div>
                  <input
                    value={collectionName}
                    onChange={(e) => setCollectionName(e.target.value)}
                    className="w-full rounded border border-glass bg-neutral-900/60 px-2 py-1 text-xs text-neutral-200 focus:border-cobweb-500/40 focus:outline-none"
                  />
                </>
              )}
            </div>

            {error && parsed?.kind !== "unknown" && (
              <div className="mx-4 mb-3 rounded-md border border-rose-800/30 bg-rose-950/20 px-2 py-1 text-[11px] text-rose-400">
                {error}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-glass px-4 py-3">
          <div className="text-[11px] text-neutral-500">
            {parsed && parsed.kind !== "unknown" && projectedCount > 0
              ? `${projectedCount} test${projectedCount === 1 ? "" : "s"} will be created in 1 collection.`
              : "Tests appear once the definition is detected."}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                reset();
                onClose();
              }}
              className="rounded-md px-3 py-1.5 text-xs text-neutral-400 transition hover:bg-white/[0.04] hover:text-neutral-200"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={generate}
              disabled={
                generating ||
                !parsed ||
                parsed.kind === "unknown" ||
                projectedCount === 0
              }
              className="flex items-center gap-1.5 rounded-md bg-accent-gradient px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none"
            >
              {generating ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Sparkles className="h-3.5 w-3.5" />
              )}
              Generate tests
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function methodTint(method: string): string {
  switch (method.toUpperCase()) {
    case "GET":
      return "bg-sky-500/15 text-sky-300";
    case "POST":
      return "bg-emerald-500/15 text-emerald-300";
    case "PUT":
      return "bg-amber-500/15 text-amber-300";
    case "PATCH":
      return "bg-violet-500/15 text-violet-300";
    case "DELETE":
      return "bg-rose-500/15 text-rose-300";
    default:
      return "bg-neutral-700/40 text-neutral-300";
  }
}
