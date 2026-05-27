import { useRef, useState } from "react";
import { BookOpen, Copy, Download, ExternalLink, Loader2, X } from "lucide-react";
import { sidecar, type CollectionSummary } from "../lib/sidecar";
import { useFocusTrap } from "../hooks/useFocusTrap";

type DocFormat = "html" | "markdown" | "openapi";
type GroupBy = "folder" | "method" | "tag";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function DocGeneratorModal({ open, onClose }: Props) {
  const trapRef = useRef<HTMLDivElement>(null);
  useFocusTrap(trapRef, open);

  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [collectionId, setCollectionId] = useState("");
  const [format, setFormat] = useState<DocFormat>("html");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [includeExamples, setIncludeExamples] = useState(true);
  const [includeHeaders, setIncludeHeaders] = useState(true);
  const [groupBy, setGroupBy] = useState<GroupBy>("folder");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ content: string; format: string; endpoint_count: number } | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!open) return null;

  if (!loaded) {
    setLoaded(true);
    sidecar.listCollections().then(setCollections).catch(() => {});
  }

  async function generate() {
    if (!collectionId) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await sidecar.generateDocs({
        collection_id: collectionId,
        format,
        options: {
          title: title || undefined,
          description: description || undefined,
          base_url: baseUrl || undefined,
          include_examples: includeExamples,
          include_headers: includeHeaders,
          group_by: groupBy,
        },
      });
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function handleCopy() {
    if (!result) return;
    navigator.clipboard.writeText(result.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  function handleDownload() {
    if (!result) return;
    const ext = result.format === "html" ? "html" : result.format === "openapi" ? "json" : "md";
    const mime = result.format === "html" ? "text/html" : result.format === "openapi" ? "application/json" : "text/markdown";
    const blob = new Blob([result.content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `api-docs.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleOpenInBrowser() {
    if (!result || result.format !== "html") return;
    const blob = new Blob([result.content], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div ref={trapRef} className="glass flex h-[700px] w-[900px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <BookOpen className="h-4 w-4 text-cobweb-400" />
            API Documentation Generator
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Left panel — options */}
          <div className="w-[320px] flex-shrink-0 overflow-y-auto border-r border-glass p-4 space-y-4">
            {/* Collection selector */}
            <div>
              <label className="block text-xs font-medium text-neutral-400 mb-1">Collection</label>
              <select
                value={collectionId}
                onChange={(e) => setCollectionId(e.target.value)}
                className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-2.5 py-1.5 text-sm text-neutral-100 focus:border-cobweb-500 focus:outline-none"
              >
                <option value="">Select a collection...</option>
                {collections.map((c) => (
                  <option key={c.id} value={c.id}>{c.name} ({c.request_count} requests)</option>
                ))}
              </select>
            </div>

            {/* Format */}
            <div>
              <label className="block text-xs font-medium text-neutral-400 mb-1">Format</label>
              <div className="flex gap-1">
                {(["html", "markdown", "openapi"] as const).map((f) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => setFormat(f)}
                    className={`rounded-md px-2.5 py-1.5 text-xs transition ${
                      format === f
                        ? "bg-cobweb-500/20 text-cobweb-300 border border-cobweb-500/30"
                        : "bg-neutral-800 text-neutral-400 border border-neutral-700 hover:text-neutral-200"
                    }`}
                  >
                    {f === "openapi" ? "OpenAPI" : f.charAt(0).toUpperCase() + f.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            {/* Title */}
            <div>
              <label className="block text-xs font-medium text-neutral-400 mb-1">Title (optional)</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Auto from collection name"
                className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-2.5 py-1.5 text-sm text-neutral-100 placeholder:text-neutral-600 focus:border-cobweb-500 focus:outline-none"
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-xs font-medium text-neutral-400 mb-1">Description (optional)</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                placeholder="Brief API description"
                className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-2.5 py-1.5 text-sm text-neutral-100 placeholder:text-neutral-600 focus:border-cobweb-500 focus:outline-none resize-none"
              />
            </div>

            {/* Base URL */}
            <div>
              <label className="block text-xs font-medium text-neutral-400 mb-1">Base URL (optional)</label>
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.example.com"
                className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-2.5 py-1.5 text-sm text-neutral-100 placeholder:text-neutral-600 focus:border-cobweb-500 focus:outline-none"
              />
            </div>

            {/* Group by */}
            <div>
              <label className="block text-xs font-medium text-neutral-400 mb-1">Group By</label>
              <select
                value={groupBy}
                onChange={(e) => setGroupBy(e.target.value as GroupBy)}
                className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-2.5 py-1.5 text-sm text-neutral-100 focus:border-cobweb-500 focus:outline-none"
              >
                <option value="folder">Folder</option>
                <option value="method">HTTP Method</option>
                <option value="tag">Tag</option>
              </select>
            </div>

            {/* Toggles */}
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-xs text-neutral-300 cursor-pointer">
                <input type="checkbox" checked={includeExamples} onChange={(e) => setIncludeExamples(e.target.checked)} className="rounded border-neutral-600" />
                Include request body examples
              </label>
              <label className="flex items-center gap-2 text-xs text-neutral-300 cursor-pointer">
                <input type="checkbox" checked={includeHeaders} onChange={(e) => setIncludeHeaders(e.target.checked)} className="rounded border-neutral-600" />
                Include headers
              </label>
            </div>

            {/* Generate button */}
            <button
              type="button"
              onClick={generate}
              disabled={!collectionId || busy}
              className="w-full flex items-center justify-center gap-2 rounded-md bg-cobweb-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-cobweb-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <BookOpen className="h-4 w-4" />}
              Generate Documentation
            </button>

            {error && (
              <div className="rounded-md border border-red-800/50 bg-red-900/20 p-2 text-xs text-red-300">
                {error}
              </div>
            )}
          </div>

          {/* Right panel — preview */}
          <div className="flex flex-1 flex-col overflow-hidden">
            {result ? (
              <>
                <div className="flex items-center justify-between border-b border-glass px-4 py-2">
                  <span className="text-xs text-neutral-400">
                    {result.endpoint_count} endpoint{result.endpoint_count !== 1 ? "s" : ""} documented
                  </span>
                  <div className="flex gap-1">
                    <button
                      type="button"
                      onClick={handleCopy}
                      className="rounded-md px-2 py-1 text-xs text-neutral-400 hover:bg-white/[0.05] hover:text-neutral-200 transition"
                    >
                      <Copy className="h-3.5 w-3.5 inline mr-1" />
                      {copied ? "Copied!" : "Copy"}
                    </button>
                    <button
                      type="button"
                      onClick={handleDownload}
                      className="rounded-md px-2 py-1 text-xs text-neutral-400 hover:bg-white/[0.05] hover:text-neutral-200 transition"
                    >
                      <Download className="h-3.5 w-3.5 inline mr-1" />
                      Download
                    </button>
                    {result.format === "html" && (
                      <button
                        type="button"
                        onClick={handleOpenInBrowser}
                        className="rounded-md px-2 py-1 text-xs text-neutral-400 hover:bg-white/[0.05] hover:text-neutral-200 transition"
                      >
                        <ExternalLink className="h-3.5 w-3.5 inline mr-1" />
                        Open in Browser
                      </button>
                    )}
                  </div>
                </div>
                <div className="flex-1 overflow-auto p-4">
                  {result.format === "html" ? (
                    <iframe
                      srcDoc={result.content}
                      className="w-full h-full rounded-md border border-neutral-700"
                      title="Documentation Preview"
                      sandbox="allow-scripts"
                    />
                  ) : (
                    <pre className="text-xs text-neutral-300 font-mono whitespace-pre-wrap break-words leading-relaxed">
                      {result.content}
                    </pre>
                  )}
                </div>
              </>
            ) : (
              <div className="flex flex-1 items-center justify-center text-neutral-600 text-sm">
                Select a collection and generate docs to preview here.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
