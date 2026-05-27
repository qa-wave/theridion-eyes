import { useCallback, useState } from "react";
import { Columns3, Loader2, Play, X } from "lucide-react";
import {
  sidecar,
  type CollectionItem,
  type EnvironmentSummary,
  type StoredCollection,
} from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
  collections: StoredCollection[];
  environments: EnvironmentSummary[];
}

interface EnvResult {
  envId: string;
  envName: string;
  status: number;
  elapsed_ms: number;
  bodySize: number;
  bodyPreview: string;
  error: string | null;
}

function flattenRequests(
  items: CollectionItem[],
  path: string[] = [],
): Array<{ item: CollectionItem; path: string[] }> {
  const result: Array<{ item: CollectionItem; path: string[] }> = [];
  for (const item of items) {
    if (item.is_folder) {
      result.push(...flattenRequests(item.items ?? [], [...path, item.name]));
    } else {
      result.push({ item, path });
    }
  }
  return result;
}

export function ComparisonTableModal({
  open,
  onClose,
  collections,
  environments,
}: Props) {
  const [selectedCollectionId, setSelectedCollectionId] = useState<string>("");
  const [selectedRequestId, setSelectedRequestId] = useState<string>("");
  const [selectedEnvIds, setSelectedEnvIds] = useState<string[]>([]);
  const [results, setResults] = useState<EnvResult[]>([]);
  const [running, setRunning] = useState(false);

  const selectedCollection = collections.find(
    (c) => c.id === selectedCollectionId,
  );
  const allRequests = selectedCollection
    ? flattenRequests(selectedCollection.items)
    : [];
  const selectedRequest = allRequests.find(
    (r) => r.item.id === selectedRequestId,
  );

  const toggleEnv = useCallback(
    (envId: string) => {
      setSelectedEnvIds((prev) =>
        prev.includes(envId)
          ? prev.filter((id) => id !== envId)
          : prev.length < 4
            ? [...prev, envId]
            : prev,
      );
    },
    [],
  );

  const runComparison = useCallback(async () => {
    if (!selectedRequest || selectedEnvIds.length < 2) return;
    setRunning(true);
    setResults([]);

    const item = selectedRequest.item;
    const envResults: EnvResult[] = [];

    for (const envId of selectedEnvIds) {
      const envName =
        environments.find((e) => e.id === envId)?.name ?? envId;
      try {
        const response = await sidecar.execute({
          method: item.method ?? "GET",
          url: item.url ?? "",
          headers: item.headers ?? {},
          body: item.body ?? null,
          auth: item.auth?.type !== "none" ? item.auth : null,
          environment_id: envId,
          collection_id: selectedCollectionId || null,
        });
        envResults.push({
          envId,
          envName,
          status: response.status,
          elapsed_ms: response.elapsed_ms,
          bodySize: response.body_size_bytes,
          bodyPreview: response.body.slice(0, 200),
          error: null,
        });
      } catch (e) {
        envResults.push({
          envId,
          envName,
          status: 0,
          elapsed_ms: 0,
          bodySize: 0,
          bodyPreview: "",
          error: e instanceof Error ? e.message : String(e),
        });
      }
    }

    setResults(envResults);
    setRunning(false);
  }, [
    selectedRequest,
    selectedEnvIds,
    environments,
    selectedCollectionId,
  ]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-3xl rounded-xl border border-glass bg-neutral-900/95 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass px-5 py-3">
          <div className="flex items-center gap-2">
            <Columns3 className="h-4 w-4 text-cobweb-400" />
            <h2 className="text-sm font-semibold text-neutral-100">
              Compare Across Environments
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-neutral-500 hover:bg-neutral-800 hover:text-neutral-300"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[70vh] overflow-y-auto p-5 space-y-4">
          {/* Collection picker */}
          <div>
            <label className="mb-1 block text-[11px] font-medium text-neutral-500">
              Collection
            </label>
            <select
              value={selectedCollectionId}
              onChange={(e) => {
                setSelectedCollectionId(e.target.value);
                setSelectedRequestId("");
                setResults([]);
              }}
              className="w-full rounded-md border border-glass bg-neutral-800 px-3 py-1.5 text-xs text-neutral-100"
            >
              <option value="">Select a collection...</option>
              {collections.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          {/* Request picker */}
          {selectedCollectionId && (
            <div>
              <label className="mb-1 block text-[11px] font-medium text-neutral-500">
                Request
              </label>
              <select
                value={selectedRequestId}
                onChange={(e) => {
                  setSelectedRequestId(e.target.value);
                  setResults([]);
                }}
                className="w-full rounded-md border border-glass bg-neutral-800 px-3 py-1.5 text-xs text-neutral-100"
              >
                <option value="">Select a request...</option>
                {allRequests.map((r) => (
                  <option key={r.item.id} value={r.item.id}>
                    {r.path.length > 0 ? `${r.path.join(" / ")} / ` : ""}
                    {r.item.method ?? "GET"} {r.item.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Environment selector */}
          {selectedRequestId && (
            <div>
              <label className="mb-1 block text-[11px] font-medium text-neutral-500">
                Environments (select 2-4)
              </label>
              <div className="flex flex-wrap gap-2">
                {environments.map((env) => {
                  const isSelected = selectedEnvIds.includes(env.id);
                  return (
                    <button
                      key={env.id}
                      type="button"
                      onClick={() => toggleEnv(env.id)}
                      className={`rounded-md border px-3 py-1 text-xs font-medium transition ${
                        isSelected
                          ? "border-cobweb-500/40 bg-cobweb-500/20 text-cobweb-300"
                          : "border-glass text-neutral-500 hover:bg-neutral-800 hover:text-neutral-300"
                      }`}
                    >
                      {env.name}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Run button */}
          {selectedEnvIds.length >= 2 && selectedRequestId && (
            <button
              type="button"
              onClick={runComparison}
              disabled={running}
              className="inline-flex items-center gap-2 rounded-md bg-cobweb-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-cobweb-500 disabled:opacity-50"
            >
              {running ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              Run Comparison
            </button>
          )}

          {/* Results table */}
          {results.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-glass text-left text-neutral-500">
                    <th className="px-3 py-2 font-medium">Environment</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Time</th>
                    <th className="px-3 py-2 font-medium">Size</th>
                    <th className="px-3 py-2 font-medium">Preview</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r) => (
                    <tr
                      key={r.envId}
                      className="border-b border-glass/50 hover:bg-neutral-800/30"
                    >
                      <td className="px-3 py-2 font-medium text-neutral-200">
                        {r.envName}
                      </td>
                      <td className="px-3 py-2">
                        {r.error ? (
                          <span className="text-rose-400">Error</span>
                        ) : (
                          <span
                            className={
                              r.status >= 400
                                ? "text-rose-400"
                                : r.status >= 300
                                  ? "text-amber-400"
                                  : "text-emerald-400"
                            }
                          >
                            {r.status}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono text-neutral-400">
                        {r.error ? "--" : `${Math.round(r.elapsed_ms)}ms`}
                      </td>
                      <td className="px-3 py-2 font-mono text-neutral-400">
                        {r.error
                          ? "--"
                          : r.bodySize < 1024
                            ? `${r.bodySize} B`
                            : `${(r.bodySize / 1024).toFixed(1)} KB`}
                      </td>
                      <td className="max-w-[200px] truncate px-3 py-2 font-mono text-neutral-600">
                        {r.error ?? r.bodyPreview}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Key differences summary */}
              {results.length >= 2 && !results.some((r) => r.error) && (
                <div className="mt-3 rounded-md border border-glass bg-neutral-800/30 p-3">
                  <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
                    Key Differences
                  </h4>
                  <div className="space-y-1 text-xs text-neutral-400">
                    {(() => {
                      const statuses = new Set(results.map((r) => r.status));
                      if (statuses.size > 1) {
                        return (
                          <div>
                            Status codes differ:{" "}
                            {results
                              .map((r) => `${r.envName}=${r.status}`)
                              .join(", ")}
                          </div>
                        );
                      }
                      return null;
                    })()}
                    {(() => {
                      const times = results.map((r) => r.elapsed_ms);
                      const maxT = Math.max(...times);
                      const minT = Math.min(...times);
                      if (maxT > 0 && maxT - minT > maxT * 0.3) {
                        return (
                          <div>
                            Response time variance:{" "}
                            {Math.round(minT)}ms - {Math.round(maxT)}ms (
                            {Math.round(((maxT - minT) / minT) * 100)}% spread)
                          </div>
                        );
                      }
                      return null;
                    })()}
                    {(() => {
                      const sizes = new Set(results.map((r) => r.bodySize));
                      if (sizes.size > 1) {
                        return (
                          <div>
                            Body sizes differ:{" "}
                            {results
                              .map((r) => `${r.envName}=${r.bodySize}B`)
                              .join(", ")}
                          </div>
                        );
                      }
                      return null;
                    })()}
                    {(() => {
                      const statuses = new Set(results.map((r) => r.status));
                      const sizes = new Set(results.map((r) => r.bodySize));
                      if (statuses.size === 1 && sizes.size === 1) {
                        return (
                          <div className="text-emerald-400">
                            No significant differences detected
                          </div>
                        );
                      }
                      return null;
                    })()}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
