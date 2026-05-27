import { useState } from "react";
import { BookOpen, Loader2, Play, RefreshCw, X } from "lucide-react";
import { sidecar, type ApiDocEndpoint, type ApiDocOutput } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
  onTryEndpoint: (method: string, url: string, headers: Record<string, string>, body: string) => void;
}

const METHOD_COLORS: Record<string, string> = {
  GET: "bg-sky-500/15 text-sky-400 border-sky-500/30",
  POST: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  PUT: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  PATCH: "bg-violet-500/15 text-violet-400 border-violet-500/30",
  DELETE: "bg-rose-500/15 text-rose-400 border-rose-500/30",
  HEAD: "bg-neutral-500/15 text-neutral-400 border-neutral-500/30",
  OPTIONS: "bg-neutral-500/15 text-neutral-400 border-neutral-500/30",
};

export function SwaggerBrowserModal({ open, onClose, onTryEndpoint }: Props) {
  const [specUrl, setSpecUrl] = useState("");
  const [specContent, setSpecContent] = useState("");
  const [doc, setDoc] = useState<ApiDocOutput | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterText, setFilterText] = useState("");
  const [selectedEndpoint, setSelectedEndpoint] = useState<ApiDocEndpoint | null>(null);
  const [importResult, setImportResult] = useState<string | null>(null);
  const [tab, setTab] = useState<"url" | "paste">("url");

  if (!open) return null;

  async function loadSpec() {
    setBusy(true); setError(null); setDoc(null); setSelectedEndpoint(null);
    try {
      const input = tab === "url" ? { url: specUrl } : { content: specContent };
      const res = await sidecar.parseApiDoc(input);
      setDoc(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  async function importAsCollection() {
    if (!doc) return;
    setBusy(true); setImportResult(null);
    try {
      const content = tab === "url" ? (await fetch(specUrl).then((r) => r.text())) : specContent;
      const res = await sidecar.universalImport(content, undefined, "openapi");
      setImportResult(`Imported "${res.collection_name}" with ${res.request_count} requests`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  function tryIt(ep: ApiDocEndpoint) {
    const baseUrl = doc?.base_url ?? "";
    const fullUrl = baseUrl ? `${baseUrl.replace(/\/$/, "")}${ep.path}` : ep.path;
    const headers: Record<string, string> = {};
    if (ep.method === "POST" || ep.method === "PUT" || ep.method === "PATCH") {
      headers["Content-Type"] = "application/json";
    }
    const body = ep.method !== "GET" && ep.method !== "HEAD" && ep.method !== "DELETE"
      ? generateExampleBody(ep)
      : "";
    onTryEndpoint(ep.method, fullUrl, headers, body);
    onClose();
  }

  const filter = filterText.toLowerCase();
  const filteredEndpoints = doc?.endpoints.filter((ep) =>
    ep.path.toLowerCase().includes(filter) ||
    ep.summary.toLowerCase().includes(filter) ||
    ep.method.toLowerCase().includes(filter) ||
    ep.tags.some((t) => t.toLowerCase().includes(filter))
  ) ?? [];

  const tags = [...new Set(doc?.endpoints.flatMap((e) => e.tags) ?? [])].sort();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[720px] w-[1100px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <BookOpen className="h-4 w-4 text-cobweb-400" />
            Swagger / OpenAPI Browser
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* URL / paste input */}
        <div className="border-b border-glass px-4 py-2.5">
          <div className="mb-2 flex gap-2">
            <button type="button" onClick={() => setTab("url")}
              className={`rounded-md px-2.5 py-1 text-[11px] transition ${tab === "url" ? "bg-white/[0.06] text-neutral-100" : "text-neutral-500 hover:text-neutral-300"}`}>
              From URL
            </button>
            <button type="button" onClick={() => setTab("paste")}
              className={`rounded-md px-2.5 py-1 text-[11px] transition ${tab === "paste" ? "bg-white/[0.06] text-neutral-100" : "text-neutral-500 hover:text-neutral-300"}`}>
              Paste Spec
            </button>
          </div>
          <div className="flex items-center gap-2">
            {tab === "url" ? (
              <input
                value={specUrl}
                onChange={(e) => setSpecUrl(e.target.value)}
                placeholder="https://petstore3.swagger.io/api/v3/openapi.json"
                className="flex-1 rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
                spellCheck={false}
                onKeyDown={(e) => { if (e.key === "Enter") loadSpec(); }}
              />
            ) : (
              <textarea
                value={specContent}
                onChange={(e) => setSpecContent(e.target.value)}
                placeholder="Paste OpenAPI/Swagger JSON or YAML here..."
                rows={3}
                className="flex-1 rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
                spellCheck={false}
              />
            )}
            <button type="button" onClick={loadSpec} disabled={busy || (tab === "url" ? !specUrl.trim() : !specContent.trim())}
              className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none">
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              Load
            </button>
          </div>
        </div>

        {error && <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">{error}</div>}
        {importResult && <div className="border-b border-emerald-800/30 bg-emerald-950/20 px-4 py-2 text-xs text-emerald-400">{importResult}</div>}

        {!doc ? (
          <div className="flex flex-1 flex-col items-center justify-center text-xs text-neutral-600">
            <BookOpen className="mb-3 h-10 w-10 text-neutral-800" />
            <p>Enter a Swagger/OpenAPI URL or paste a spec to browse</p>
            <p className="mt-1 text-neutral-700">Supports OpenAPI 3.x and Swagger 2.0 (JSON/YAML)</p>
          </div>
        ) : (
          <div className="flex min-h-0 flex-1">
            {/* Left — endpoint list */}
            <div className="flex w-[420px] shrink-0 flex-col border-r border-glass">
              {/* Spec header */}
              <div className="border-b border-glass px-4 py-2">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-neutral-100">{doc.title || "API"}</h3>
                    <p className="text-[10px] text-neutral-500">v{doc.version} &middot; {doc.endpoints.length} endpoints</p>
                  </div>
                  <button type="button" onClick={importAsCollection} disabled={busy}
                    className="inline-flex items-center gap-1 rounded-md border border-glass px-2 py-1 text-[11px] text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200 disabled:opacity-40">
                    Import All
                  </button>
                </div>
                {doc.base_url && <p className="mt-1 font-mono text-[10px] text-cobweb-400">{doc.base_url}</p>}
              </div>

              {/* Filter */}
              <div className="border-b border-glass px-3 py-1.5">
                <input
                  value={filterText}
                  onChange={(e) => setFilterText(e.target.value)}
                  placeholder="Filter endpoints..."
                  className="w-full rounded-md border border-glass bg-neutral-900/50 px-2 py-1 text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
                />
              </div>

              {/* Tag filter chips */}
              {tags.length > 1 && (
                <div className="flex flex-wrap gap-1 border-b border-glass px-3 py-1.5">
                  {tags.map((tag) => (
                    <button key={tag} type="button"
                      onClick={() => setFilterText(filterText === tag ? "" : tag)}
                      className={`rounded-md px-2 py-0.5 text-[10px] transition ${
                        filterText === tag ? "bg-cobweb-950/30 text-cobweb-300" : "bg-neutral-900/30 text-neutral-500 hover:text-neutral-300"
                      }`}>
                      {tag}
                    </button>
                  ))}
                </div>
              )}

              {/* Endpoint list */}
              <div className="flex-1 overflow-y-auto">
                {filteredEndpoints.map((ep, i) => (
                  <button
                    key={`${ep.method}-${ep.path}-${i}`}
                    type="button"
                    onClick={() => setSelectedEndpoint(ep)}
                    className={`flex w-full items-center gap-2 border-b border-glass px-3 py-2 text-left transition ${
                      selectedEndpoint === ep ? "bg-white/[0.04]" : "hover:bg-white/[0.02]"
                    }`}
                  >
                    <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-bold ${METHOD_COLORS[ep.method] ?? METHOD_COLORS.GET}`}>
                      {ep.method}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-mono text-[11px] text-neutral-200">{ep.path}</p>
                      {ep.summary && <p className="truncate text-[10px] text-neutral-500">{ep.summary}</p>}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* Right — endpoint detail */}
            <div className="flex min-w-0 flex-1 flex-col overflow-y-auto">
              {selectedEndpoint ? (
                <EndpointDetail endpoint={selectedEndpoint} baseUrl={doc.base_url} onTryIt={() => tryIt(selectedEndpoint)} />
              ) : (
                <div className="flex flex-1 items-center justify-center text-xs text-neutral-600">
                  Select an endpoint to view details
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function EndpointDetail({ endpoint: ep, baseUrl, onTryIt }: { endpoint: ApiDocEndpoint; baseUrl: string; onTryIt: () => void }) {
  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className={`rounded border px-2 py-0.5 text-[10px] font-bold ${METHOD_COLORS[ep.method] ?? METHOD_COLORS.GET}`}>
              {ep.method}
            </span>
            <code className="font-mono text-sm text-neutral-100">{ep.path}</code>
          </div>
          {ep.summary && <p className="mt-1 text-xs text-neutral-400">{ep.summary}</p>}
          {ep.description && <p className="mt-1 text-[11px] text-neutral-500">{ep.description}</p>}
          {ep.tags.length > 0 && (
            <div className="mt-1.5 flex gap-1">
              {ep.tags.map((t) => (
                <span key={t} className="rounded bg-neutral-800/50 px-1.5 py-0.5 text-[9px] text-neutral-400">{t}</span>
              ))}
            </div>
          )}
        </div>
        <button type="button" onClick={onTryIt}
          className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition">
          <Play className="h-3.5 w-3.5" /> Try it
        </button>
      </div>

      {/* Parameters */}
      {ep.parameters.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">Parameters</h4>
          <div className="overflow-hidden rounded-lg border border-glass">
            <table className="w-full text-xs">
              <thead className="bg-neutral-900/30 text-[10px] uppercase tracking-widest text-neutral-500">
                <tr>
                  <th className="px-3 py-1.5 text-left font-medium">Name</th>
                  <th className="px-3 py-1.5 text-left font-medium">In</th>
                  <th className="px-3 py-1.5 text-left font-medium">Type</th>
                  <th className="px-3 py-1.5 text-left font-medium">Required</th>
                  <th className="px-3 py-1.5 text-left font-medium">Description</th>
                </tr>
              </thead>
              <tbody>
                {ep.parameters.map((p, i) => (
                  <tr key={i} className="border-t border-glass">
                    <td className="px-3 py-1.5 font-mono text-cobweb-400">{String(p.name ?? "")}</td>
                    <td className="px-3 py-1.5 text-neutral-500">{String(p.in ?? "")}</td>
                    <td className="px-3 py-1.5 text-neutral-400">{String((p.schema as Record<string, unknown>)?.type ?? p.type ?? "")}</td>
                    <td className="px-3 py-1.5">{p.required ? <span className="text-rose-400">yes</span> : <span className="text-neutral-600">no</span>}</td>
                    <td className="px-3 py-1.5 text-neutral-500">{String(p.description ?? "")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Full URL */}
      <div>
        <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">Full URL</h4>
        <code className="block rounded-md border border-glass bg-neutral-900/30 px-3 py-2 font-mono text-[11px] text-neutral-300">
          {baseUrl ? `${baseUrl.replace(/\/$/, "")}${ep.path}` : ep.path}
        </code>
      </div>
    </div>
  );
}

function generateExampleBody(ep: ApiDocEndpoint): string {
  try {
    const rb = ep.parameters.find((p) => String(p.in) === "body");
    if (rb) return JSON.stringify(rb, null, 2);
  } catch { /* ignore */ }
  return "{}";
}
