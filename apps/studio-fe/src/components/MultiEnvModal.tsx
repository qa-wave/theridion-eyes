import { useEffect, useState } from "react";
import { GitCompare, Loader2, Play, X, Zap, Turtle, ArrowLeftRight } from "lucide-react";
import {
  sidecar,
  type CollectionSummary,
  type EnvironmentSummary,
  type MultiEnvResult,
  type SingleRequestMultiEnvOutput,
  type CollectionMultiEnvOutput,
  type EnvRequestResult,
  type ComparisonSummary,
} from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
  /** If provided, run this single request template instead of a collection */
  activeRequest?: {
    method: string;
    url: string;
    headers: Record<string, string>;
    body?: string | null;
  } | null;
  onDiffResponses?: (envA: EnvRequestResult, envB: EnvRequestResult) => void;
}

type RunMode = "collection" | "single";

export function MultiEnvModal({ open, onClose, activeRequest, onDiffResponses }: Props) {
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [environments, setEnvironments] = useState<EnvironmentSummary[]>([]);
  const [collectionId, setCollectionId] = useState("");
  const [selectedEnvs, setSelectedEnvs] = useState<Set<string>>(new Set());
  const [legacyResult, setLegacyResult] = useState<MultiEnvResult | null>(null);
  const [singleResult, setSingleResult] = useState<SingleRequestMultiEnvOutput | null>(null);
  const [collectionResult, setCollectionResult] = useState<CollectionMultiEnvOutput | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<RunMode>(activeRequest ? "single" : "collection");

  useEffect(() => {
    if (!open) return;
    Promise.all([sidecar.listCollections(), sidecar.listEnvironments()])
      .then(([c, e]) => { setCollections(c); setEnvironments(e); })
      .catch(() => {});
    if (activeRequest) setMode("single");
  }, [open, activeRequest]);

  function toggleEnv(id: string) {
    setSelectedEnvs((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function reset() {
    setLegacyResult(null);
    setSingleResult(null);
    setCollectionResult(null);
    setError(null);
  }

  async function run() {
    if (selectedEnvs.size < 2) return;
    setBusy(true); setError(null); reset();
    const envIds = Array.from(selectedEnvs);

    try {
      if (mode === "single" && activeRequest) {
        const res = await sidecar.multiEnvRunSingle({
          request: {
            method: activeRequest.method,
            url: activeRequest.url,
            headers: activeRequest.headers,
            body: activeRequest.body,
          },
          environment_ids: envIds,
          collection_id: collectionId || null,
        });
        setSingleResult(res);
      } else if (mode === "collection" && collectionId) {
        const res = await sidecar.multiEnvRunCollection({
          collection_id: collectionId,
          environment_ids: envIds,
        });
        setCollectionResult(res);
      } else {
        // fallback to legacy
        const res = await sidecar.multiEnvRun({
          collection_id: collectionId,
          environment_ids: envIds,
        });
        setLegacyResult(res);
      }
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  if (!open) return null;

  const hasResult = legacyResult || singleResult || collectionResult;
  const canRun = selectedEnvs.size >= 2 && (mode === "single" ? !!activeRequest : !!collectionId);

  const inputClass = "w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 focus:border-cobweb-500/40 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[620px] w-[800px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <GitCompare className="h-4 w-4 text-cobweb-400" /> Multi-Environment Parallel Runner
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"><X className="h-4 w-4" /></button>
        </div>

        {error && <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">{error}</div>}

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {!hasResult ? (
            <>
              {/* Mode selector */}
              {activeRequest && (
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setMode("single")}
                    className={`rounded-md px-3 py-1 text-xs font-medium transition ${mode === "single" ? "bg-cobweb-600/30 text-cobweb-300" : "text-neutral-500 hover:text-neutral-300"}`}
                  >
                    Active Request
                  </button>
                  <button
                    type="button"
                    onClick={() => setMode("collection")}
                    className={`rounded-md px-3 py-1 text-xs font-medium transition ${mode === "collection" ? "bg-cobweb-600/30 text-cobweb-300" : "text-neutral-500 hover:text-neutral-300"}`}
                  >
                    Collection
                  </button>
                </div>
              )}

              {/* Active request preview */}
              {mode === "single" && activeRequest && (
                <div className="rounded-md border border-glass bg-neutral-900/30 px-3 py-2">
                  <p className="mb-1 text-[11px] uppercase tracking-wider text-neutral-500">Request</p>
                  <p className="text-xs text-neutral-200 font-mono">
                    <span className="text-emerald-400">{activeRequest.method}</span>{" "}
                    {activeRequest.url}
                  </p>
                </div>
              )}

              {/* Collection picker (for collection mode) */}
              {mode === "collection" && (
                <div>
                  <p className="mb-1 text-[11px] uppercase tracking-wider text-neutral-500">Collection</p>
                  <select value={collectionId} onChange={(e) => setCollectionId(e.target.value)} className={inputClass}>
                    <option value="">Select collection...</option>
                    {collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </div>
              )}

              {/* Environment checkboxes */}
              <div>
                <p className="mb-2 text-[11px] uppercase tracking-wider text-neutral-500">
                  Environments <span className="text-neutral-600">(select 2+)</span>
                </p>
                <div className="space-y-1">
                  {environments.map((env) => (
                    <label key={env.id} className="flex items-center gap-2 rounded px-2 py-1 text-xs text-neutral-300 hover:bg-neutral-800/40 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedEnvs.has(env.id)}
                        onChange={() => toggleEnv(env.id)}
                        className="rounded"
                      />
                      {env.name}
                      <span className="text-neutral-600 ml-auto">{env.variable_count} vars</span>
                    </label>
                  ))}
                  {environments.length === 0 && <p className="text-xs text-neutral-600 py-2">No environments defined.</p>}
                </div>
              </div>

              <button
                type="button"
                onClick={run}
                disabled={busy || !canRun}
                className="inline-flex items-center gap-2 rounded-md bg-cobweb-600/20 px-4 py-2 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-50"
              >
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                Run across {selectedEnvs.size} environment(s)
              </button>
            </>
          ) : (
            <div className="space-y-4">
              {/* Single request result */}
              {singleResult && (
                <SingleRequestResults
                  result={singleResult}
                  onDiff={onDiffResponses}
                />
              )}

              {/* Collection result */}
              {collectionResult && (
                <CollectionResults
                  result={collectionResult}
                  onDiff={onDiffResponses}
                />
              )}

              {/* Legacy result (fallback) */}
              {legacyResult && (
                <LegacyResults result={legacyResult} />
              )}

              <button type="button" onClick={reset} className="mt-3 text-xs text-cobweb-400 hover:text-cobweb-300">
                Run again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


// ---- Sub-components for results display -------------------------------------

function ComparisonBadges({ comparison }: { comparison: ComparisonSummary }) {
  return (
    <div className="flex flex-wrap gap-2 text-[10px]">
      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ${comparison.all_same_status ? "bg-emerald-950/40 text-emerald-400" : "bg-amber-950/40 text-amber-400"}`}>
        {comparison.all_same_status ? "Same status" : "Different statuses"}
      </span>
      {comparison.fastest_env && (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950/30 px-2 py-0.5 text-emerald-400">
          <Zap className="h-3 w-3" /> {comparison.fastest_env}
        </span>
      )}
      {comparison.slowest_env && comparison.slowest_env !== comparison.fastest_env && (
        <span className="inline-flex items-center gap-1 rounded-full bg-orange-950/30 px-2 py-0.5 text-orange-400">
          <Turtle className="h-3 w-3" /> {comparison.slowest_env}
        </span>
      )}
      {comparison.response_size_diff && (
        <span className="rounded-full bg-amber-950/30 px-2 py-0.5 text-amber-400">
          Size differs
        </span>
      )}
    </div>
  );
}

function StatusCell({ result }: { result: EnvRequestResult }) {
  if (result.error) {
    return <span className="rounded px-1.5 py-0.5 bg-rose-950/40 text-rose-400 text-[10px]">ERR</span>;
  }
  const status = result.status ?? 0;
  const color = status >= 200 && status < 300
    ? "bg-emerald-950/40 text-emerald-400"
    : status >= 400
      ? "bg-rose-950/40 text-rose-400"
      : "bg-amber-950/40 text-amber-400";
  return <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${color}`}>{status}</span>;
}

function SingleRequestResults({
  result,
  onDiff,
}: {
  result: SingleRequestMultiEnvOutput;
  onDiff?: (a: EnvRequestResult, b: EnvRequestResult) => void;
}) {
  return (
    <div className="space-y-3">
      <ComparisonBadges comparison={result.comparison} />

      <div className="overflow-x-auto rounded border border-glass">
        <table className="w-full text-xs">
          <thead className="bg-neutral-900/60 text-neutral-500">
            <tr>
              <th className="px-3 py-1.5 text-left font-medium">Environment</th>
              <th className="px-3 py-1.5 text-left font-medium">Status</th>
              <th className="px-3 py-1.5 text-left font-medium">Time</th>
              <th className="px-3 py-1.5 text-left font-medium">Size</th>
              <th className="px-3 py-1.5 text-left font-medium">Body Preview</th>
            </tr>
          </thead>
          <tbody>
            {result.results.map((r) => {
              const isFastest = r.env_name === result.comparison.fastest_env;
              const isSlowest = r.env_name === result.comparison.slowest_env && result.comparison.fastest_env !== result.comparison.slowest_env;
              return (
                <tr key={r.env_id} className="border-t border-glass">
                  <td className="px-3 py-1.5 text-neutral-200 font-medium">
                    {r.env_name}
                    {isFastest && <Zap className="inline ml-1 h-3 w-3 text-emerald-400" />}
                    {isSlowest && <Turtle className="inline ml-1 h-3 w-3 text-orange-400" />}
                  </td>
                  <td className="px-3 py-1.5"><StatusCell result={r} /></td>
                  <td className="px-3 py-1.5 text-neutral-400 font-mono">{r.elapsed_ms.toFixed(0)}ms</td>
                  <td className="px-3 py-1.5 text-neutral-400 font-mono">{r.body_size}B</td>
                  <td className="px-3 py-1.5 text-neutral-500 max-w-[200px] truncate font-mono text-[10px]">
                    {r.error ? <span className="text-rose-400">{r.error}</span> : r.body_preview.slice(0, 80)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Diff button for pairs */}
      {onDiff && result.results.length >= 2 && !result.comparison.all_same_status && (
        <div className="flex gap-2">
          {result.results.slice(0, -1).map((a, i) => {
            const b = result.results[i + 1];
            return (
              <button
                key={`${a.env_id}-${b.env_id}`}
                type="button"
                onClick={() => onDiff(a, b)}
                className="inline-flex items-center gap-1.5 rounded-md bg-neutral-800/50 px-3 py-1.5 text-[10px] text-neutral-300 transition hover:bg-neutral-700/50"
              >
                <ArrowLeftRight className="h-3 w-3" />
                Diff: {a.env_name} vs {b.env_name}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function CollectionResults({
  result,
  onDiff,
}: {
  result: CollectionMultiEnvOutput;
  onDiff?: (a: EnvRequestResult, b: EnvRequestResult) => void;
}) {
  const envNames = result.rows[0]?.results.map((r) => r.env_name) ?? [];

  return (
    <div className="space-y-3">
      <ComparisonBadges comparison={result.summary} />

      <div className="overflow-x-auto rounded border border-glass">
        <table className="w-full text-xs">
          <thead className="bg-neutral-900/60 text-neutral-500">
            <tr>
              <th className="px-3 py-1.5 text-left font-medium">Request</th>
              {envNames.map((name) => (
                <th key={name} className="px-3 py-1.5 text-left font-medium">{name}</th>
              ))}
              <th className="px-3 py-1.5 text-left font-medium">Match</th>
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row) => (
              <tr key={row.request_name} className="border-t border-glass">
                <td className="px-3 py-1.5 text-neutral-300">{row.request_name}</td>
                {row.results.map((r) => {
                  const isFastest = r.env_name === row.comparison.fastest_env;
                  return (
                    <td key={r.env_id} className="px-3 py-1.5">
                      <div className="flex items-center gap-1.5">
                        <StatusCell result={r} />
                        <span className="text-neutral-500 font-mono text-[10px]">{r.elapsed_ms.toFixed(0)}ms</span>
                        {isFastest && <Zap className="h-2.5 w-2.5 text-emerald-400" />}
                      </div>
                    </td>
                  );
                })}
                <td className="px-3 py-1.5">
                  <span className={`inline-block h-2 w-2 rounded-full ${row.comparison.all_same_status ? "bg-emerald-500" : "bg-amber-500"}`} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Diff buttons for rows with differences */}
      {onDiff && result.rows.some((row) => !row.comparison.all_same_status) && (
        <div className="flex flex-wrap gap-2">
          {result.rows
            .filter((row) => !row.comparison.all_same_status)
            .slice(0, 5)
            .map((row) => {
              const a = row.results[0];
              const b = row.results[1];
              if (!a || !b) return null;
              return (
                <button
                  key={row.request_name}
                  type="button"
                  onClick={() => onDiff(a, b)}
                  className="inline-flex items-center gap-1.5 rounded-md bg-neutral-800/50 px-3 py-1.5 text-[10px] text-neutral-300 transition hover:bg-neutral-700/50"
                >
                  <ArrowLeftRight className="h-3 w-3" />
                  {row.request_name}
                </button>
              );
            })}
        </div>
      )}
    </div>
  );
}

function LegacyResults({ result }: { result: MultiEnvResult }) {
  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-3 text-xs">
        {result.results.map((r) => (
          <div key={r.env_id} className="rounded-lg border border-glass px-3 py-2">
            <p className="font-medium text-neutral-200">{r.env_name}</p>
            <p className="text-emerald-400">Pass: {r.passed}</p>
            <p className="text-rose-400">Fail: {r.failed}</p>
            <p className="text-neutral-500">{r.elapsed_ms}ms</p>
          </div>
        ))}
      </div>

      {result.comparison.length > 0 && (
        <div className="overflow-x-auto rounded border border-glass">
          <table className="w-full text-xs">
            <thead className="bg-neutral-900/60 text-neutral-500">
              <tr>
                <th className="px-3 py-1.5 text-left font-medium">Request</th>
                {result.results.map((r) => (
                  <th key={r.env_id} className="px-3 py-1.5 text-left font-medium">{r.env_name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.comparison.map((row, idx) => (
                <tr key={idx} className="border-t border-glass">
                  <td className="px-3 py-1.5 text-neutral-300">{row.request_name}</td>
                  {result.results.map((r) => {
                    const status = row.statuses[r.env_id] ?? row.statuses[r.env_name];
                    return (
                      <td key={r.env_id} className="px-3 py-1.5">
                        {status !== undefined ? (
                          <span className={`rounded px-1.5 py-0.5 font-mono ${status >= 200 && status < 300 ? "bg-emerald-950/40 text-emerald-400" : status >= 400 ? "bg-rose-950/40 text-rose-400" : "bg-amber-950/40 text-amber-400"}`}>
                            {status}
                          </span>
                        ) : (
                          <span className="text-neutral-600">-</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
