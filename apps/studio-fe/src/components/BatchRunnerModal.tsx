import { useRef, useState } from "react";
import { ArrowRight, BarChart3, ChevronDown, Clipboard, Database, Download, FileCode, FileText, GitBranch, Globe, Loader2, Play, X } from "lucide-react";
import { sidecar, type BatchOutput, type CollectionSummary, type EnvironmentSummary, type DependencyInfo, type ReportGenerationInput } from "../lib/sidecar";
import { RequestTimeline } from "./RequestTimeline";
import { useFocusTrap } from "../hooks/useFocusTrap";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function BatchRunnerModal({ open, onClose }: Props) {
  const trapRef = useRef<HTMLDivElement>(null);
  useFocusTrap(trapRef, open);
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [environments, setEnvironments] = useState<EnvironmentSummary[]>([]);
  const [collectionId, setCollectionId] = useState("");
  const [envId, setEnvId] = useState("");
  const [dataMode, setDataMode] = useState<"csv" | "json">("json");
  const [dataText, setDataText] = useState("");
  const [result, setResult] = useState<BatchOutput | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [resultsView, setResultsView] = useState<"table" | "timeline">("table");
  const [depOrder, setDepOrder] = useState<DependencyInfo[] | null>(null);
  const [depBusy, setDepBusy] = useState(false);
  const [depUnresolved, setDepUnresolved] = useState<string[]>([]);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);

  if (!open) return null;

  if (!loaded) {
    setLoaded(true);
    sidecar.listCollections().then(setCollections).catch(() => {});
    sidecar.listEnvironments().then(setEnvironments).catch(() => {});
  }

  async function run() {
    if (!collectionId) return;
    setBusy(true); setError(null); setResult(null);
    try {
      let dataset: Array<Record<string, string>> = [];
      if (dataMode === "json" && dataText.trim()) {
        dataset = JSON.parse(dataText);
      }
      const res = await sidecar.runBatch({
        collection_id: collectionId,
        environment_id: envId || undefined,
        dataset,
        dataset_csv: dataMode === "csv" ? dataText : undefined,
      });
      setResult(res);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  function buildReportInput(): ReportGenerationInput | null {
    if (!result) return null;
    const allResults = result.rows.flatMap((row) =>
      row.request_results.map((rr) => ({
        request_id: String(rr.request_id ?? ""),
        request_name: String(rr.name ?? `Row ${row.row_index}`),
        method: String(rr.method ?? "GET"),
        url: String(rr.url ?? ""),
        status: rr.status != null ? Number(rr.status) : null,
        elapsed_ms: Number(rr.elapsed_ms ?? 0),
        error: rr.error ? String(rr.error) : null,
        assertion_results: Array.isArray(rr.assertion_results) ? (rr.assertion_results as Array<Record<string, unknown>>) .map((a) => ({
          assertion: (a.assertion ?? {}) as Record<string, unknown>,
          passed: Boolean(a.passed),
          message: String(a.message ?? ""),
        })) : [],
        assertions_passed: Number(rr.assertions_passed ?? 0),
        assertions_failed: Number(rr.assertions_failed ?? 0),
      })),
    );
    const collName = collections.find((c) => c.id === collectionId)?.name ?? "Batch Run";
    const totalPassed = allResults.filter((r) => r.error == null && r.status != null && r.status < 400).length;
    return {
      collection_id: collectionId,
      collection_name: collName,
      results: allResults,
      total_requests: allResults.length,
      successful_requests: totalPassed,
      failed_requests: allResults.length - totalPassed,
      total_assertions: allResults.reduce((s, r) => s + r.assertions_passed + r.assertions_failed, 0),
      passed_assertions: allResults.reduce((s, r) => s + r.assertions_passed, 0),
      failed_assertions: allResults.reduce((s, r) => s + r.assertions_failed, 0),
      total_elapsed_ms: result.elapsed_ms,
    };
  }

  function downloadFile(content: string, filename: string, mime: string) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function exportHtml() {
    const input = buildReportInput();
    if (!input) return;
    setExportBusy(true);
    try {
      const res = await sidecar.generateHtmlReport(input);
      const w = window.open("", "_blank");
      if (w) { w.document.write(res.html); w.document.close(); }
      else { downloadFile(res.html, `${input.collection_name}-report.html`, "text/html"); }
    } catch { /* ignore */ }
    finally { setExportBusy(false); setExportOpen(false); }
  }

  async function exportJunit() {
    const input = buildReportInput();
    if (!input) return;
    setExportBusy(true);
    try {
      const res = await sidecar.generateJunitReport(input);
      downloadFile(res.xml, `${input.collection_name}-junit.xml`, "application/xml");
    } catch { /* ignore */ }
    finally { setExportBusy(false); setExportOpen(false); }
  }

  async function exportJson() {
    const input = buildReportInput();
    if (!input) return;
    setExportBusy(true);
    try {
      const res = await sidecar.generateJsonReport(input);
      downloadFile(JSON.stringify(res.report, null, 2), `${input.collection_name}-report.json`, "application/json");
    } catch { /* ignore */ }
    finally { setExportBusy(false); setExportOpen(false); }
  }

  async function exportMarkdown() {
    const input = buildReportInput();
    if (!input) return;
    setExportBusy(true);
    try {
      const res = await sidecar.generateMarkdownReport(input);
      await navigator.clipboard.writeText(res.markdown);
    } catch { /* ignore */ }
    finally { setExportBusy(false); setExportOpen(false); }
  }

  const inputClass = "w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 focus:border-cobweb-500/40 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div ref={trapRef} className="glass flex h-[600px] w-[750px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Database className="h-4 w-4 text-cobweb-400" /> Batch Runner
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"><X className="h-4 w-4" /></button>
        </div>

        {error && <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">{error}</div>}

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {!result ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="mb-1 text-[11px] uppercase tracking-wider text-neutral-500">Collection</p>
                  <select value={collectionId} onChange={(e) => setCollectionId(e.target.value)} className={inputClass}>
                    <option value="">Select collection...</option>
                    {collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </div>
                <div>
                  <p className="mb-1 text-[11px] uppercase tracking-wider text-neutral-500">Environment</p>
                  <select value={envId} onChange={(e) => setEnvId(e.target.value)} className={inputClass}>
                    <option value="">None</option>
                    {environments.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
                  </select>
                </div>
              </div>

              <div>
                <div className="mb-1 flex items-center gap-2">
                  <p className="text-[11px] uppercase tracking-wider text-neutral-500">Dataset</p>
                  <div className="flex rounded-md border border-glass overflow-hidden text-[11px]">
                    {(["json", "csv"] as const).map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setDataMode(m)}
                        className={`px-2 py-0.5 transition ${dataMode === m ? "bg-cobweb-600/20 text-cobweb-400" : "text-neutral-500 hover:text-neutral-300"}`}
                      >
                        {m.toUpperCase()}
                      </button>
                    ))}
                  </div>
                </div>
                <textarea
                  value={dataText}
                  onChange={(e) => setDataText(e.target.value)}
                  placeholder={dataMode === "json" ? '[{"name":"Alice"},{"name":"Bob"}]' : "name,email\nAlice,alice@ex.com"}
                  rows={8}
                  className="w-full resize-y rounded-md border border-glass bg-neutral-900/50 px-3 py-2 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
                  spellCheck={false}
                />
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={run}
                  disabled={busy || !collectionId}
                  className="inline-flex items-center gap-2 rounded-md bg-cobweb-600/20 px-4 py-2 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-50"
                >
                  {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                  Run Batch
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    if (!collectionId) return;
                    setDepBusy(true);
                    try {
                      const res = await sidecar.resolveDependencies(collectionId);
                      setDepOrder(res.order);
                      setDepUnresolved(res.unresolved);
                    } catch { /* ignore */ }
                    finally { setDepBusy(false); }
                  }}
                  disabled={depBusy || !collectionId}
                  className="inline-flex items-center gap-2 rounded-md border border-glass px-4 py-2 text-xs text-neutral-400 transition hover:bg-white/[0.04] hover:text-neutral-200 disabled:opacity-50"
                >
                  {depBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <GitBranch className="h-3.5 w-3.5" />}
                  Resolve Dependencies
                </button>
              </div>

              {/* Dependency graph results */}
              {depOrder && (
                <div className="rounded-lg border border-glass bg-neutral-900/30 p-3">
                  <p className="mb-2 text-[11px] uppercase tracking-wider text-neutral-500">
                    Suggested Execution Order
                  </p>
                  {depUnresolved.length > 0 && (
                    <p className="mb-2 text-xs text-amber-400">
                      Unresolved variables: {depUnresolved.join(", ")}
                    </p>
                  )}
                  <div className="space-y-1">
                    {depOrder.map((dep, i) => (
                      <div key={dep.request_id} className="flex items-center gap-2 text-xs">
                        <span className="shrink-0 rounded-full bg-neutral-800 px-2 py-0.5 font-mono text-[10px] text-neutral-400">
                          {i + 1}
                        </span>
                        <span className="font-medium text-neutral-200">{dep.name || dep.request_id}</span>
                        {dep.depends_on.length > 0 && (
                          <span className="flex items-center gap-1 text-neutral-500">
                            <ArrowRight className="h-3 w-3" />
                            depends on: {dep.depends_on.map((d) => {
                              const found = depOrder.find((o) => o.request_id === d);
                              return found?.name || d;
                            }).join(", ")}
                          </span>
                        )}
                        {dep.consumes.length > 0 && (
                          <span className="text-[10px] text-cobweb-400">
                            {"{{" + dep.consumes.join("}}, {{") + "}}"}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div>
              <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-4 text-xs">
                  <span className="text-neutral-400">Rows: <span className="text-neutral-100">{result.total_rows}</span></span>
                  <span className="text-emerald-400">Passed: {result.total_passed}</span>
                  <span className="text-rose-400">Failed: {result.total_failed}</span>
                  <span className="text-neutral-400">Time: {result.elapsed_ms}ms</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setExportOpen(!exportOpen)}
                      disabled={exportBusy}
                      className="inline-flex items-center gap-1.5 rounded-md border border-glass px-2.5 py-1 text-[11px] text-neutral-400 transition hover:bg-white/[0.04] hover:text-neutral-200 disabled:opacity-50"
                    >
                      {exportBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
                      Export
                      <ChevronDown className="h-3 w-3" />
                    </button>
                    {exportOpen && (
                      <div className="absolute right-0 top-full z-10 mt-1 w-44 rounded-lg border border-glass bg-neutral-900 py-1 shadow-xl shadow-black/50">
                        <button type="button" onClick={exportHtml} className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-neutral-300 transition hover:bg-white/[0.06]">
                          <Globe className="h-3.5 w-3.5 text-cobweb-400" /> HTML Report
                        </button>
                        <button type="button" onClick={exportJunit} className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-neutral-300 transition hover:bg-white/[0.06]">
                          <FileCode className="h-3.5 w-3.5 text-amber-400" /> JUnit XML
                        </button>
                        <button type="button" onClick={exportJson} className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-neutral-300 transition hover:bg-white/[0.06]">
                          <FileText className="h-3.5 w-3.5 text-blue-400" /> JSON
                        </button>
                        <button type="button" onClick={exportMarkdown} className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-neutral-300 transition hover:bg-white/[0.06]">
                          <Clipboard className="h-3.5 w-3.5 text-emerald-400" /> Markdown (copy)
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="flex rounded-md border border-glass overflow-hidden text-[11px]">
                    <button
                      type="button"
                      onClick={() => setResultsView("table")}
                      className={`px-2 py-0.5 transition ${resultsView === "table" ? "bg-cobweb-600/20 text-cobweb-400" : "text-neutral-500 hover:text-neutral-300"}`}
                    >
                      Table
                    </button>
                    <button
                      type="button"
                      onClick={() => setResultsView("timeline")}
                      className={`inline-flex items-center gap-1 px-2 py-0.5 transition ${resultsView === "timeline" ? "bg-cobweb-600/20 text-cobweb-400" : "text-neutral-500 hover:text-neutral-300"}`}
                    >
                      <BarChart3 className="h-3 w-3" /> Timeline
                    </button>
                  </div>
                </div>
              </div>

              {resultsView === "table" ? (
                <div className="overflow-hidden rounded border border-glass">
                  <table className="w-full text-xs">
                    <thead className="bg-neutral-900/60 text-neutral-500">
                      <tr>
                        <th className="px-3 py-1.5 text-left font-medium">Row</th>
                        <th className="px-3 py-1.5 text-left font-medium">Variables</th>
                        <th className="px-3 py-1.5 text-left font-medium">Passed</th>
                        <th className="px-3 py-1.5 text-left font-medium">Failed</th>
                        <th className="px-3 py-1.5 text-left font-medium">Errors</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.rows.map((row) => (
                        <tr key={row.row_index} className="border-t border-glass">
                          <td className="px-3 py-1.5 font-mono">{row.row_index}</td>
                          <td className="px-3 py-1.5 font-mono text-neutral-400 truncate max-w-[200px]">
                            {Object.entries(row.variables).map(([k, v]) => `${k}=${v}`).join(", ")}
                          </td>
                          <td className="px-3 py-1.5 text-emerald-400">{row.passed}</td>
                          <td className="px-3 py-1.5 text-rose-400">{row.failed}</td>
                          <td className="px-3 py-1.5 text-amber-400">{row.errors}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <RequestTimeline
                  entries={result.rows.flatMap((row) =>
                    row.request_results.map((rr) => ({
                      name: String(rr.name ?? `Row ${row.row_index}`),
                      method: String(rr.method ?? "GET"),
                      url: String(rr.url ?? ""),
                      status: Number(rr.status ?? 0),
                      elapsed_ms: Number(rr.elapsed_ms ?? 0),
                      error: rr.error ? String(rr.error) : null,
                    })),
                  )}
                />
              )}

              <button
                type="button"
                onClick={() => setResult(null)}
                className="mt-3 text-xs text-cobweb-400 hover:text-cobweb-300"
              >
                Run again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
