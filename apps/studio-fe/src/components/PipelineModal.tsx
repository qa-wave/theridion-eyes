import { useState, useEffect } from "react";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Clock,
  Loader2,
  Minus,
  Play,
  Plus,
  SkipForward,
  Workflow,
  X,
  Zap,
} from "lucide-react";
import {
  sidecar,
  type StoredCollection,
  type CollectionItem,
  type PipelineStep,
  type PipelineStepResult,
  type PipelineResult,
  type PipelineTemplate,
  type PipelineExtractor,
} from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
  collections: StoredCollection[];
}

interface DraftStep {
  id: string;
  request_id: string;
  collection_id: string;
  requestName: string;
  delay_ms: number;
  condition: string;
  extractors: PipelineExtractor[];
  on_fail: "stop" | "continue" | "retry";
  retry_count: number;
}

function flattenRequests(
  items: CollectionItem[],
  prefix = "",
): Array<{ id: string; name: string; method: string }> {
  const out: Array<{ id: string; name: string; method: string }> = [];
  for (const item of items) {
    if (item.is_folder) {
      out.push(
        ...flattenRequests(item.items ?? [], `${prefix}${item.name}/`),
      );
    } else {
      out.push({
        id: item.id,
        name: `${prefix}${item.name}`,
        method: item.method ?? "GET",
      });
    }
  }
  return out;
}

function emptyStep(): DraftStep {
  return {
    id: crypto.randomUUID(),
    request_id: "",
    collection_id: "",
    requestName: "",
    delay_ms: 0,
    condition: "",
    extractors: [],
    on_fail: "stop",
    retry_count: 1,
  };
}

export function PipelineModal({ open, onClose, collections }: Props) {
  const [name, setName] = useState("New Pipeline");
  const [steps, setSteps] = useState<DraftStep[]>([emptyStep()]);
  const [variables, setVariables] = useState<Record<string, string>>({});
  const [newVarName, setNewVarName] = useState("");
  const [newVarValue, setNewVarValue] = useState("");

  const [result, setResult] = useState<PipelineResult | null>(null);
  const [runningIndex, setRunningIndex] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [templates, setTemplates] = useState<PipelineTemplate[]>([]);
  const [showTemplates, setShowTemplates] = useState(false);
  const [expandedStep, setExpandedStep] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      sidecar.getPipelineTemplates().then(setTemplates).catch(() => {});
    }
  }, [open]);

  if (!open) return null;

  function updateStep(id: string, patch: Partial<DraftStep>) {
    setSteps((s) => s.map((st) => (st.id === id ? { ...st, ...patch } : st)));
  }

  function removeStep(id: string) {
    setSteps((s) => s.filter((st) => st.id !== id));
  }

  function addExtractor(stepId: string) {
    setSteps((s) =>
      s.map((st) =>
        st.id === stepId
          ? {
              ...st,
              extractors: [
                ...st.extractors,
                { name: "", source: "body" as const, path: "" },
              ],
            }
          : st,
      ),
    );
  }

  function updateExtractor(
    stepId: string,
    idx: number,
    patch: Partial<PipelineExtractor>,
  ) {
    setSteps((s) =>
      s.map((st) =>
        st.id === stepId
          ? {
              ...st,
              extractors: st.extractors.map((e, i) =>
                i === idx ? { ...e, ...patch } : e,
              ),
            }
          : st,
      ),
    );
  }

  function removeExtractor(stepId: string, idx: number) {
    setSteps((s) =>
      s.map((st) =>
        st.id === stepId
          ? { ...st, extractors: st.extractors.filter((_, i) => i !== idx) }
          : st,
      ),
    );
  }

  function addVariable() {
    if (!newVarName.trim()) return;
    setVariables((v) => ({ ...v, [newVarName.trim()]: newVarValue }));
    setNewVarName("");
    setNewVarValue("");
  }

  function removeVariable(key: string) {
    setVariables((v) => {
      const next = { ...v };
      delete next[key];
      return next;
    });
  }

  function applyTemplate(t: PipelineTemplate) {
    setName(t.name);
    setSteps(
      t.steps.map((s) => ({
        id: crypto.randomUUID(),
        request_id: (s.request_id as string) || "",
        collection_id: (s.collection_id as string) || "",
        requestName: "",
        delay_ms: (s.delay_ms as number) || 0,
        condition: (s.condition as string) || "",
        extractors: ((s.extractors as PipelineExtractor[]) || []).map(
          (e) => ({ ...e }),
        ),
        on_fail: (s.on_fail as DraftStep["on_fail"]) || "stop",
        retry_count: (s.retry_count as number) || 1,
      })),
    );
    setShowTemplates(false);
    setResult(null);
    setError(null);
  }

  function selectRequest(
    stepId: string,
    collectionId: string,
    requestId: string,
    requestName: string,
  ) {
    updateStep(stepId, {
      collection_id: collectionId,
      request_id: requestId,
      requestName,
    });
  }

  async function run() {
    if (steps.length === 0) return;
    setBusy(true);
    setError(null);
    setResult(null);
    setRunningIndex(0);

    try {
      const pipelineSteps: PipelineStep[] = steps.map((s) => ({
        request_id: s.request_id,
        collection_id: s.collection_id,
        delay_ms: s.delay_ms,
        condition: s.condition || null,
        extractors: s.extractors.filter((e) => e.name.trim()),
        on_fail: s.on_fail,
        retry_count: s.retry_count,
      }));

      const res = await sidecar.executePipeline({
        name,
        steps: pipelineSteps,
        variables,
      });
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      setRunningIndex(null);
    }
  }

  const inputClass =
    "w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none";
  const selectClass =
    "rounded-md border border-glass bg-neutral-900/50 px-2 py-1.5 text-xs text-neutral-100 focus:outline-none";

  function stepResultFor(idx: number): PipelineStepResult | undefined {
    return result?.results.find((r) => r.step_index === idx);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[680px] w-[780px] max-h-[92vh] max-w-[96vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Workflow className="h-4 w-4 text-cobweb-400" />
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="bg-transparent text-sm font-medium text-neutral-100 focus:outline-none"
              placeholder="Pipeline name"
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowTemplates(!showTemplates)}
              className="inline-flex items-center gap-1 rounded-md border border-glass px-2 py-1 text-[11px] text-neutral-400 hover:bg-neutral-800/40 hover:text-neutral-200"
            >
              <Zap className="h-3 w-3" /> Templates
              <ChevronDown className="h-3 w-3" />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Template dropdown */}
        {showTemplates && templates.length > 0 && (
          <div className="border-b border-glass bg-neutral-900/50 px-4 py-2 space-y-1">
            <span className="text-[10px] font-medium uppercase tracking-wider text-neutral-500">
              Quick Start Templates
            </span>
            <div className="flex flex-wrap gap-2 pt-1">
              {templates.map((t) => (
                <button
                  key={t.name}
                  type="button"
                  onClick={() => applyTemplate(t)}
                  className="rounded-md border border-glass px-3 py-1.5 text-xs text-neutral-300 hover:bg-cobweb-600/10 hover:border-cobweb-600/30 hover:text-cobweb-400 transition"
                >
                  <div className="font-medium">{t.name}</div>
                  <div className="text-[10px] text-neutral-500">
                    {t.description}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {error && (
          <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">
            {error}
          </div>
        )}

        {/* Steps list */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {steps.map((step, idx) => {
            const sr = stepResultFor(idx);
            const isExpanded = expandedStep === step.id;
            const borderColor = sr
              ? sr.skipped
                ? "border-neutral-700"
                : sr.passed
                  ? "border-emerald-800/50"
                  : "border-rose-800/50"
              : "border-glass";

            return (
              <div
                key={step.id}
                className={`rounded-lg border p-3 space-y-2 ${borderColor}`}
              >
                {/* Step header */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] font-mono text-neutral-400">
                      {idx + 1}
                    </span>
                    {runningIndex === idx && (
                      <Loader2 className="h-3 w-3 animate-spin text-cobweb-400" />
                    )}
                    {sr && !sr.skipped && sr.passed && (
                      <Check className="h-3 w-3 text-emerald-400" />
                    )}
                    {sr && !sr.skipped && !sr.passed && (
                      <AlertTriangle className="h-3 w-3 text-rose-400" />
                    )}
                    {sr?.skipped && (
                      <SkipForward className="h-3 w-3 text-neutral-500" />
                    )}
                    <span className="text-xs text-neutral-300 truncate max-w-[200px]">
                      {step.requestName || "Select request..."}
                    </span>
                    {sr && sr.status != null && (
                      <span
                        className={`text-[10px] font-mono ${sr.status < 400 ? "text-emerald-400" : "text-rose-400"}`}
                      >
                        {sr.status}
                      </span>
                    )}
                    {sr && (
                      <span className="text-[10px] text-neutral-500">
                        {sr.elapsed_ms}ms
                      </span>
                    )}
                    {sr && sr.attempts > 1 && (
                      <span className="text-[10px] text-amber-400">
                        x{sr.attempts}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedStep(isExpanded ? null : step.id)
                      }
                      className="rounded p-1 text-neutral-500 hover:text-neutral-300 hover:bg-neutral-800"
                    >
                      <ChevronDown
                        className={`h-3 w-3 transition ${isExpanded ? "rotate-180" : ""}`}
                      />
                    </button>
                    <button
                      type="button"
                      onClick={() => removeStep(step.id)}
                      className="rounded p-1 text-neutral-600 hover:text-rose-400 hover:bg-neutral-800"
                    >
                      <Minus className="h-3 w-3" />
                    </button>
                  </div>
                </div>

                {/* Request picker */}
                <div className="grid grid-cols-[1fr_1fr] gap-2">
                  <select
                    value={step.collection_id}
                    onChange={(e) => {
                      updateStep(step.id, {
                        collection_id: e.target.value,
                        request_id: "",
                        requestName: "",
                      });
                    }}
                    className={selectClass + " w-full"}
                  >
                    <option value="">Collection...</option>
                    {collections.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                  <select
                    value={step.request_id}
                    onChange={(e) => {
                      const col = collections.find(
                        (c) => c.id === step.collection_id,
                      );
                      if (!col) return;
                      const reqs = flattenRequests(col.items ?? []);
                      const req = reqs.find((r) => r.id === e.target.value);
                      selectRequest(
                        step.id,
                        step.collection_id,
                        e.target.value,
                        req ? `${req.method} ${req.name}` : "",
                      );
                    }}
                    className={selectClass + " w-full"}
                    disabled={!step.collection_id}
                  >
                    <option value="">Request...</option>
                    {step.collection_id &&
                      flattenRequests(
                        collections.find((c) => c.id === step.collection_id)
                          ?.items ?? [],
                      ).map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.method} {r.name}
                        </option>
                      ))}
                  </select>
                </div>

                {/* Expanded details */}
                {isExpanded && (
                  <div className="space-y-2 pt-1">
                    {/* Delay + on_fail + retry */}
                    <div className="grid grid-cols-3 gap-2">
                      <div>
                        <label className="text-[10px] uppercase tracking-wider text-neutral-500">
                          Delay (ms)
                        </label>
                        <input
                          type="number"
                          value={step.delay_ms}
                          onChange={(e) =>
                            updateStep(step.id, {
                              delay_ms: parseInt(e.target.value) || 0,
                            })
                          }
                          className={inputClass}
                          min={0}
                        />
                      </div>
                      <div>
                        <label className="text-[10px] uppercase tracking-wider text-neutral-500">
                          On Fail
                        </label>
                        <select
                          value={step.on_fail}
                          onChange={(e) =>
                            updateStep(step.id, {
                              on_fail: e.target.value as DraftStep["on_fail"],
                            })
                          }
                          className={selectClass + " w-full"}
                        >
                          <option value="stop">Stop</option>
                          <option value="continue">Continue</option>
                          <option value="retry">Retry</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-[10px] uppercase tracking-wider text-neutral-500">
                          Retries
                        </label>
                        <input
                          type="number"
                          value={step.retry_count}
                          onChange={(e) =>
                            updateStep(step.id, {
                              retry_count:
                                Math.max(
                                  1,
                                  Math.min(
                                    10,
                                    parseInt(e.target.value) || 1,
                                  ),
                                ),
                            })
                          }
                          className={inputClass}
                          min={1}
                          max={10}
                          disabled={step.on_fail !== "retry"}
                        />
                      </div>
                    </div>

                    {/* Condition */}
                    <div>
                      <label className="text-[10px] uppercase tracking-wider text-neutral-500">
                        Condition
                      </label>
                      <input
                        value={step.condition}
                        onChange={(e) =>
                          updateStep(step.id, { condition: e.target.value })
                        }
                        placeholder='status == 200 or variable.token != ""'
                        className={inputClass}
                      />
                    </div>

                    {/* Extractors */}
                    <div>
                      <div className="flex items-center justify-between">
                        <label className="text-[10px] uppercase tracking-wider text-neutral-500">
                          Extractors
                        </label>
                        <button
                          type="button"
                          onClick={() => addExtractor(step.id)}
                          className="text-[10px] text-cobweb-400 hover:text-cobweb-300"
                        >
                          + Add
                        </button>
                      </div>
                      {step.extractors.map((ext, ei) => (
                        <div
                          key={ei}
                          className="mt-1 grid grid-cols-[1fr_80px_1fr_24px] gap-1"
                        >
                          <input
                            value={ext.name}
                            onChange={(e) =>
                              updateExtractor(step.id, ei, {
                                name: e.target.value,
                              })
                            }
                            placeholder="var name"
                            className={inputClass}
                          />
                          <select
                            value={ext.source}
                            onChange={(e) =>
                              updateExtractor(step.id, ei, {
                                source: e.target.value as PipelineExtractor["source"],
                              })
                            }
                            className={selectClass}
                          >
                            <option value="body">body</option>
                            <option value="header">header</option>
                            <option value="status">status</option>
                          </select>
                          <input
                            value={ext.path}
                            onChange={(e) =>
                              updateExtractor(step.id, ei, {
                                path: e.target.value,
                              })
                            }
                            placeholder="data.token"
                            className={inputClass}
                          />
                          <button
                            type="button"
                            onClick={() => removeExtractor(step.id, ei)}
                            className="rounded p-1 text-neutral-600 hover:text-rose-400"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </div>
                      ))}
                    </div>

                    {/* Step result details */}
                    {sr?.error && (
                      <div className="rounded border border-rose-800/30 bg-rose-950/10 p-2 text-[11px] font-mono text-rose-400">
                        {sr.error}
                      </div>
                    )}
                    {sr &&
                      Object.keys(sr.captured).length > 0 && (
                        <div className="rounded border border-cobweb-800/30 bg-cobweb-950/10 p-2">
                          <span className="text-[10px] uppercase tracking-wider text-neutral-500">
                            Captured
                          </span>
                          <div className="mt-1 space-y-0.5">
                            {Object.entries(sr.captured).map(([k, v]) => (
                              <div
                                key={k}
                                className="text-[11px] font-mono text-neutral-300"
                              >
                                <span className="text-cobweb-400">{k}</span> ={" "}
                                <span className="text-neutral-400">{v}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                  </div>
                )}
              </div>
            );
          })}

          {/* Add step button */}
          <button
            type="button"
            onClick={() => setSteps((s) => [...s, emptyStep()])}
            className="inline-flex w-full items-center justify-center gap-1 rounded-md border border-dashed border-glass py-2 text-xs text-neutral-500 hover:border-cobweb-500/30 hover:text-neutral-300 transition"
          >
            <Plus className="h-3 w-3" /> Add Step
          </button>

          {/* Variables section */}
          <div className="rounded-lg border border-glass p-3 space-y-2">
            <span className="text-[10px] font-medium uppercase tracking-wider text-neutral-500">
              Pipeline Variables
            </span>
            {Object.entries(variables).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2">
                <span className="text-xs font-mono text-cobweb-400 min-w-[80px]">
                  {k}
                </span>
                <span className="text-xs text-neutral-400 flex-1 truncate">
                  {v}
                </span>
                <button
                  type="button"
                  onClick={() => removeVariable(k)}
                  className="text-neutral-600 hover:text-rose-400"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
            <div className="flex items-center gap-2">
              <input
                value={newVarName}
                onChange={(e) => setNewVarName(e.target.value)}
                placeholder="name"
                className={inputClass + " flex-1"}
                onKeyDown={(e) => e.key === "Enter" && addVariable()}
              />
              <input
                value={newVarValue}
                onChange={(e) => setNewVarValue(e.target.value)}
                placeholder="value"
                className={inputClass + " flex-1"}
                onKeyDown={(e) => e.key === "Enter" && addVariable()}
              />
              <button
                type="button"
                onClick={addVariable}
                className="rounded-md border border-glass px-2 py-1.5 text-xs text-neutral-400 hover:bg-neutral-800/40 hover:text-neutral-200"
              >
                <Plus className="h-3 w-3" />
              </button>
            </div>
          </div>
        </div>

        {/* Footer with results summary */}
        <div className="border-t border-glass px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={run}
              disabled={busy || steps.length === 0}
              className="inline-flex items-center gap-2 rounded-md bg-cobweb-600/20 px-4 py-2 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-50"
            >
              {busy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              Run Pipeline
            </button>
            {result && (
              <div className="flex items-center gap-3 text-[11px]">
                <span className="flex items-center gap-1 text-emerald-400">
                  <Check className="h-3 w-3" /> {result.passed} passed
                </span>
                <span className="flex items-center gap-1 text-rose-400">
                  <AlertTriangle className="h-3 w-3" /> {result.failed} failed
                </span>
                <span className="flex items-center gap-1 text-neutral-500">
                  <Clock className="h-3 w-3" /> {result.total_ms}ms
                </span>
              </div>
            )}
          </div>
          {result && Object.keys(result.variables).length > 0 && (
            <span className="text-[10px] text-neutral-500">
              {Object.keys(result.variables).length} vars
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
