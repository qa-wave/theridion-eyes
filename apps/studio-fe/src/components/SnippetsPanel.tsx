import { useCallback, useEffect, useState } from "react";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  Download,
  Lock,
  Plus,
  Search,
  Tag,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { sidecar, type Snippet, type SnippetCreate } from "../lib/sidecar";
import { HTTP_METHOD_COLOR } from "../state/types";
import type { Method } from "../state/types";

interface Props {
  onUseSnippet: (snippet: Snippet) => void;
  currentRequest?: {
    method: string;
    url: string;
    headers: Record<string, string>;
    body: string | null;
    auth?: Record<string, unknown> | null;
  } | null;
}

export function SnippetsPanel({ onUseSnippet, currentRequest }: Props) {
  const [snippets, setSnippets] = useState<Snippet[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saveCategory, setSaveCategory] = useState("General");
  const [saveDescription, setSaveDescription] = useState("");
  const [saveTags, setSaveTags] = useState("");

  const load = useCallback(async () => {
    try {
      const params: { category?: string; search?: string } = {};
      if (categoryFilter) params.category = categoryFilter;
      if (search) params.search = search;
      const result = await sidecar.listSnippets(params);
      setSnippets(result.items);
    } catch {
      // sidecar not available
    }
  }, [categoryFilter, search]);

  const loadCategories = useCallback(async () => {
    try {
      const cats = await sidecar.listSnippetCategories();
      setCategories(cats);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void load();
    void loadCategories();
  }, [load, loadCategories]);

  // Group snippets by category
  const grouped = snippets.reduce<Record<string, Snippet[]>>((acc, s) => {
    if (!acc[s.category]) acc[s.category] = [];
    acc[s.category].push(s);
    return acc;
  }, {});

  const toggleCat = (cat: string) => {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const handleDelete = async (id: string) => {
    try {
      await sidecar.deleteSnippet(id);
      void load();
      void loadCategories();
    } catch {
      // ignore
    }
  };

  const handleSave = async () => {
    if (!currentRequest || !saveName.trim()) return;
    const data: SnippetCreate = {
      name: saveName.trim(),
      category: saveCategory || "General",
      description: saveDescription,
      method: currentRequest.method,
      url: currentRequest.url,
      headers: currentRequest.headers,
      body: currentRequest.body,
      auth: currentRequest.auth,
      tags: saveTags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
    };
    try {
      await sidecar.createSnippet(data);
      setSaving(false);
      setSaveName("");
      setSaveCategory("General");
      setSaveDescription("");
      setSaveTags("");
      void load();
      void loadCategories();
    } catch {
      // ignore
    }
  };

  const handleExport = async () => {
    try {
      const data = await sidecar.exportSnippets();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "theridion-snippets.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // ignore
    }
  };

  const handleImport = async () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        const parsed = JSON.parse(text);
        const items = parsed.snippets || parsed;
        if (Array.isArray(items)) {
          await sidecar.importSnippets(items);
          void load();
          void loadCategories();
        }
      } catch {
        // ignore
      }
    };
    input.click();
  };

  return (
    <div className="flex flex-col h-full bg-neutral-950">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-neutral-800">
        <BookOpen size={14} className="text-cobweb-400 shrink-0" />
        <span className="text-[11px] font-medium text-neutral-300 uppercase tracking-wide">
          Snippets
        </span>
        <div className="flex-1" />
        <button
          onClick={() => setSaving(true)}
          className="p-1 rounded hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200"
          title="Save current as snippet"
        >
          <Plus size={13} />
        </button>
        <button
          onClick={handleImport}
          className="p-1 rounded hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200"
          title="Import snippets"
        >
          <Upload size={13} />
        </button>
        <button
          onClick={handleExport}
          className="p-1 rounded hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200"
          title="Export snippets"
        >
          <Download size={13} />
        </button>
      </div>

      {/* Search */}
      <div className="px-3 py-2 border-b border-neutral-800">
        <div className="relative">
          <Search
            size={12}
            className="absolute left-2 top-1/2 -translate-y-1/2 text-neutral-500"
          />
          <input
            className="w-full bg-neutral-900 border border-neutral-800 rounded pl-7 pr-2 py-1 text-[11px] text-neutral-200 placeholder-neutral-500 focus:outline-none focus:border-cobweb-400/50"
            placeholder="Search snippets..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button
              className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-500 hover:text-neutral-300"
              onClick={() => setSearch("")}
            >
              <X size={10} />
            </button>
          )}
        </div>
      </div>

      {/* Category filter chips */}
      {categories.length > 0 && (
        <div className="flex flex-wrap gap-1 px-3 py-1.5 border-b border-neutral-800">
          <button
            onClick={() => setCategoryFilter(null)}
            className={`px-1.5 py-0.5 rounded text-[10px] border transition-colors ${
              categoryFilter === null
                ? "border-cobweb-400/60 text-cobweb-300 bg-cobweb-400/10"
                : "border-neutral-700 text-neutral-400 hover:border-neutral-600"
            }`}
          >
            All
          </button>
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() =>
                setCategoryFilter(categoryFilter === cat ? null : cat)
              }
              className={`px-1.5 py-0.5 rounded text-[10px] border transition-colors ${
                categoryFilter === cat
                  ? "border-cobweb-400/60 text-cobweb-300 bg-cobweb-400/10"
                  : "border-neutral-700 text-neutral-400 hover:border-neutral-600"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      )}

      {/* Save form */}
      {saving && (
        <div className="px-3 py-2 border-b border-neutral-800 bg-neutral-900/50 space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-neutral-400 uppercase">
              Save as Snippet
            </span>
            <button
              onClick={() => setSaving(false)}
              className="text-neutral-500 hover:text-neutral-300"
            >
              <X size={11} />
            </button>
          </div>
          <input
            className="w-full bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-[11px] text-neutral-200 placeholder-neutral-500 focus:outline-none focus:border-cobweb-400/50"
            placeholder="Name"
            value={saveName}
            onChange={(e) => setSaveName(e.target.value)}
          />
          <div className="flex gap-1.5">
            <input
              className="flex-1 bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-[11px] text-neutral-200 placeholder-neutral-500 focus:outline-none focus:border-cobweb-400/50"
              placeholder="Category"
              value={saveCategory}
              onChange={(e) => setSaveCategory(e.target.value)}
            />
            <input
              className="flex-1 bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-[11px] text-neutral-200 placeholder-neutral-500 focus:outline-none focus:border-cobweb-400/50"
              placeholder="Tags (comma-sep)"
              value={saveTags}
              onChange={(e) => setSaveTags(e.target.value)}
            />
          </div>
          <input
            className="w-full bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-[11px] text-neutral-200 placeholder-neutral-500 focus:outline-none focus:border-cobweb-400/50"
            placeholder="Description (optional)"
            value={saveDescription}
            onChange={(e) => setSaveDescription(e.target.value)}
          />
          <button
            onClick={handleSave}
            disabled={!saveName.trim() || !currentRequest}
            className="w-full py-1 rounded text-[11px] font-medium bg-cobweb-500/20 border border-cobweb-400/40 text-cobweb-300 hover:bg-cobweb-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Save Snippet
          </button>
        </div>
      )}

      {/* Snippet list grouped by category */}
      <div className="flex-1 overflow-y-auto">
        {Object.keys(grouped).length === 0 && (
          <div className="px-3 py-6 text-center text-[11px] text-neutral-500">
            No snippets found
          </div>
        )}
        {Object.entries(grouped).map(([cat, items]) => (
          <div key={cat}>
            <button
              onClick={() => toggleCat(cat)}
              className="flex items-center gap-1.5 w-full px-3 py-1.5 text-[10px] font-medium text-neutral-400 uppercase tracking-wide hover:bg-neutral-900/60"
            >
              {expandedCats.has(cat) ? (
                <ChevronDown size={11} />
              ) : (
                <ChevronRight size={11} />
              )}
              {cat}
              <span className="text-neutral-600 ml-auto">{items.length}</span>
            </button>
            {expandedCats.has(cat) && (
              <div className="pb-1">
                {items.map((snippet) => (
                  <div
                    key={snippet.id}
                    className="group mx-2 mb-0.5 px-2 py-1.5 rounded bg-neutral-900 border border-neutral-800/60 hover:border-cobweb-400/30 transition-colors"
                  >
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`text-[9px] font-bold px-1 rounded ${
                          HTTP_METHOD_COLOR[snippet.method as Method] ||
                          "text-neutral-400"
                        }`}
                      >
                        {snippet.method}
                      </span>
                      <span className="text-[11px] text-neutral-200 truncate flex-1">
                        {snippet.name}
                      </span>
                      {snippet.builtin && (
                        <span title="Built-in">
                          <Lock
                            size={10}
                            className="text-neutral-600 shrink-0"
                          />
                        </span>
                      )}
                      <button
                        onClick={() => onUseSnippet(snippet)}
                        className="hidden group-hover:block text-[9px] px-1.5 py-0.5 rounded bg-cobweb-500/20 border border-cobweb-400/40 text-cobweb-300 hover:bg-cobweb-500/30"
                      >
                        Use
                      </button>
                      {!snippet.builtin && (
                        <button
                          onClick={() => handleDelete(snippet.id)}
                          className="hidden group-hover:block p-0.5 rounded text-neutral-600 hover:text-rose-400"
                        >
                          <Trash2 size={10} />
                        </button>
                      )}
                    </div>
                    {snippet.description && (
                      <p className="text-[10px] text-neutral-500 mt-0.5 truncate pl-6">
                        {snippet.description}
                      </p>
                    )}
                    {snippet.tags.length > 0 && (
                      <div className="flex gap-1 mt-1 pl-6 flex-wrap">
                        {snippet.tags.map((tag) => (
                          <span
                            key={tag}
                            className="inline-flex items-center gap-0.5 px-1 py-0 rounded text-[9px] bg-neutral-800 text-neutral-500 border border-neutral-700/50"
                          >
                            <Tag size={7} />
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
