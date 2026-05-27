import { useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckSquare,
  ChevronDown,
  ChevronRight,
  FileUp,
  FolderOpen,
  Loader2,
  Search,
  Square,
  Upload,
  X,
} from "lucide-react";
import { sidecar } from "../lib/sidecar";
import { useFocusTrap } from "../hooks/useFocusTrap";

interface Props {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
}

interface PreviewRequest {
  method: string;
  path: string;
  name: string;
}

interface PreviewFolder {
  name: string;
  request_count: number;
  requests: PreviewRequest[];
}

interface PreviewData {
  title: string;
  version: string;
  base_url: string;
  folder_count: number;
  request_count: number;
  folders: PreviewFolder[];
  auth_detected: string | null;
  warnings: string[];
}

interface ImportResult {
  collection_id: string;
  collection_name: string;
  request_count: number;
  folder_count: number;
  warnings: string[];
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

export function OpenAPIImportModal({ open, onClose, onImported }: Props) {
  const [tab, setTab] = useState<"url" | "paste" | "file">("url");
  const [specUrl, setSpecUrl] = useState("");
  const [specContent, setSpecContent] = useState("");
  const [collectionName, setCollectionName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [selectedFolders, setSelectedFolders] = useState<Set<string>>(new Set());
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const trapRef = useRef<HTMLDivElement>(null);
  useFocusTrap(trapRef, open);

  if (!open) return null;

  function getSource(): string {
    if (tab === "url") return specUrl.trim();
    return specContent.trim();
  }

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setSpecContent(text);
    setTab("paste");
  }

  async function handlePreview() {
    const source = getSource();
    if (!source) return;
    setBusy(true);
    setError(null);
    setPreview(null);
    setResult(null);
    try {
      const res = await sidecar.openApiImportPreview({ source });
      setPreview(res);
      // Select all folders by default
      setSelectedFolders(new Set(res.folders.map((f) => f.name)));
      // Expand all
      setExpandedFolders(new Set(res.folders.map((f) => f.name)));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleImport() {
    const source = getSource();
    if (!source) return;
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar.openApiImportFull({
        source,
        collection_name: collectionName || undefined,
      });
      setResult(res);
      onImported();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function toggleFolder(name: string) {
    setSelectedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function toggleExpand(name: string) {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function selectAll() {
    if (!preview) return;
    setSelectedFolders(new Set(preview.folders.map((f) => f.name)));
  }

  function selectNone() {
    setSelectedFolders(new Set());
  }

  const filterLower = filter.toLowerCase();
  const filteredFolders =
    preview?.folders.filter(
      (f) =>
        f.name.toLowerCase().includes(filterLower) ||
        f.requests.some(
          (r) =>
            r.name.toLowerCase().includes(filterLower) ||
            r.path.toLowerCase().includes(filterLower) ||
            r.method.toLowerCase().includes(filterLower)
        )
    ) ?? [];

  const selectedCount = preview
    ? filteredFolders.filter((f) => selectedFolders.has(f.name)).reduce((sum, f) => sum + f.request_count, 0)
    : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div
        ref={trapRef}
        className="glass flex h-[680px] w-[900px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Upload className="h-4 w-4 text-cobweb-400" />
            Import from OpenAPI / Swagger
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Source input */}
        <div className="border-b border-glass px-4 py-3 space-y-2">
          <div className="flex items-center gap-2">
            <div className="flex gap-1">
              {(["url", "paste", "file"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTab(t)}
                  className={`rounded-md px-2.5 py-1 text-[11px] transition ${
                    tab === t
                      ? "bg-white/[0.06] text-neutral-100"
                      : "text-neutral-500 hover:text-neutral-300"
                  }`}
                >
                  {t === "url" ? "From URL" : t === "paste" ? "Paste" : "File"}
                </button>
              ))}
            </div>
            {tab === "file" && (
              <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-glass px-3 py-1.5 text-xs text-neutral-400 transition hover:bg-white/[0.04] hover:text-neutral-200">
                <FileUp className="h-3.5 w-3.5" /> Choose file
                <input
                  type="file"
                  accept=".json,.yaml,.yml"
                  onChange={handleFile}
                  className="hidden"
                />
              </label>
            )}
          </div>

          {tab === "url" ? (
            <input
              value={specUrl}
              onChange={(e) => setSpecUrl(e.target.value)}
              placeholder="https://petstore3.swagger.io/api/v3/openapi.json"
              className="w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
              spellCheck={false}
              onKeyDown={(e) => {
                if (e.key === "Enter") handlePreview();
              }}
            />
          ) : (
            <textarea
              value={specContent}
              onChange={(e) => setSpecContent(e.target.value)}
              placeholder="Paste OpenAPI/Swagger JSON or YAML here..."
              rows={4}
              className="w-full resize-y rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
              spellCheck={false}
            />
          )}

          <div className="flex items-center gap-2">
            <input
              value={collectionName}
              onChange={(e) => setCollectionName(e.target.value)}
              placeholder="Collection name (auto-detect from spec)"
              className="flex-1 rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
            />
            <button
              type="button"
              onClick={handlePreview}
              disabled={busy || !getSource()}
              className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none"
            >
              {busy && !preview ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Search className="h-3.5 w-3.5" />
              )}
              Preview
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">
            {error}
          </div>
        )}

        {/* Success */}
        {result && (
          <div className="border-b border-emerald-800/30 bg-emerald-950/20 px-4 py-2 text-xs text-emerald-400 space-y-1">
            <p>
              Imported &quot;{result.collection_name}&quot; with {result.request_count}{" "}
              requests in {result.folder_count} folders
            </p>
            {result.warnings.length > 0 && (
              <div className="flex items-start gap-1 text-amber-400">
                <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
                <ul className="list-disc pl-3 space-y-0.5">
                  {result.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Preview tree */}
        {preview && !result ? (
          <div className="flex min-h-0 flex-1 flex-col">
            {/* Preview header */}
            <div className="flex items-center justify-between border-b border-glass px-4 py-2">
              <div>
                <span className="text-xs font-semibold text-neutral-100">
                  {preview.title}
                </span>
                <span className="ml-2 text-[10px] text-neutral-500">
                  v{preview.version}
                </span>
                {preview.base_url && (
                  <span className="ml-2 font-mono text-[10px] text-cobweb-400">
                    {preview.base_url}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-[10px]">
                {preview.auth_detected && (
                  <span className="rounded bg-amber-950/30 px-1.5 py-0.5 text-amber-400 border border-amber-800/30">
                    {preview.auth_detected}
                  </span>
                )}
                <span className="text-neutral-500">
                  {preview.request_count} endpoints, {preview.folder_count} folders
                </span>
              </div>
            </div>

            {/* Filter + select all/none */}
            <div className="flex items-center gap-2 border-b border-glass px-4 py-1.5">
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter endpoints..."
                className="flex-1 rounded-md border border-glass bg-neutral-900/50 px-2 py-1 text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
              />
              <button
                type="button"
                onClick={selectAll}
                className="text-[10px] text-neutral-500 hover:text-neutral-200 transition"
              >
                All
              </button>
              <button
                type="button"
                onClick={selectNone}
                className="text-[10px] text-neutral-500 hover:text-neutral-200 transition"
              >
                None
              </button>
            </div>

            {/* Warnings */}
            {preview.warnings.length > 0 && (
              <div className="border-b border-amber-800/30 bg-amber-950/20 px-4 py-1.5 text-xs text-amber-400">
                <div className="flex items-center gap-1 font-medium mb-0.5">
                  <AlertTriangle className="h-3 w-3" /> Warnings
                </div>
                <ul className="list-disc pl-4 space-y-0.5">
                  {preview.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Folder tree */}
            <div className="flex-1 overflow-y-auto">
              {filteredFolders.map((folder) => {
                const isSelected = selectedFolders.has(folder.name);
                const isExpanded = expandedFolders.has(folder.name);
                const filteredReqs = folder.requests.filter(
                  (r) =>
                    !filterLower ||
                    r.name.toLowerCase().includes(filterLower) ||
                    r.path.toLowerCase().includes(filterLower) ||
                    r.method.toLowerCase().includes(filterLower)
                );

                return (
                  <div key={folder.name}>
                    <div
                      className={`flex items-center gap-2 border-b border-glass px-4 py-1.5 transition ${
                        isSelected ? "bg-white/[0.02]" : "opacity-50"
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => toggleExpand(folder.name)}
                        className="text-neutral-500 hover:text-neutral-300"
                      >
                        {isExpanded ? (
                          <ChevronDown className="h-3 w-3" />
                        ) : (
                          <ChevronRight className="h-3 w-3" />
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => toggleFolder(folder.name)}
                        className="text-neutral-400 hover:text-neutral-200"
                      >
                        {isSelected ? (
                          <CheckSquare className="h-3.5 w-3.5 text-cobweb-400" />
                        ) : (
                          <Square className="h-3.5 w-3.5" />
                        )}
                      </button>
                      <FolderOpen className="h-3.5 w-3.5 text-neutral-500" />
                      <span className="flex-1 text-xs font-medium text-neutral-200">
                        {folder.name}
                      </span>
                      <span className="text-[10px] text-neutral-600">
                        {folder.request_count} endpoints
                      </span>
                    </div>
                    {isExpanded &&
                      filteredReqs.map((req, i) => (
                        <div
                          key={`${req.method}-${req.path}-${i}`}
                          className={`flex items-center gap-2 border-b border-glass pl-12 pr-4 py-1 ${
                            isSelected ? "" : "opacity-40"
                          }`}
                        >
                          <span
                            className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-bold ${
                              METHOD_COLORS[req.method] ?? METHOD_COLORS.GET
                            }`}
                          >
                            {req.method}
                          </span>
                          <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-neutral-300">
                            {req.path}
                          </span>
                          <span className="shrink-0 truncate text-[10px] text-neutral-500 max-w-[200px]">
                            {req.name}
                          </span>
                        </div>
                      ))}
                  </div>
                );
              })}
            </div>
          </div>
        ) : !result ? (
          <div className="flex flex-1 flex-col items-center justify-center text-xs text-neutral-600">
            <Upload className="mb-3 h-10 w-10 text-neutral-800" />
            <p>Enter an OpenAPI/Swagger spec URL or paste content</p>
            <p className="mt-1 text-neutral-700">
              Supports OpenAPI 3.0, 3.1, and Swagger 2.0 (JSON/YAML)
            </p>
          </div>
        ) : null}

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-glass px-4 py-3">
          <div className="text-[10px] text-neutral-500">
            {preview && !result && `${selectedCount} endpoints selected`}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-glass px-3 py-1.5 text-xs text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200"
            >
              {result ? "Done" : "Cancel"}
            </button>
            {preview && !result && (
              <button
                type="button"
                onClick={handleImport}
                disabled={busy || selectedCount === 0}
                className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none"
              >
                {busy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Check className="h-3.5 w-3.5" />
                )}
                Import {selectedCount} endpoints
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
