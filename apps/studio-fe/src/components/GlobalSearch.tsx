import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FileText, Globe, Search, X } from "lucide-react";
import type { StoredCollection, CollectionItem, EnvironmentSummary } from "../lib/sidecar";
import { HTTP_METHOD_COLOR, type Method } from "../state/types";

export interface GlobalSearchProps {
  open: boolean;
  onClose: () => void;
  collections: StoredCollection[];
  environments: EnvironmentSummary[];
  onOpenRequest: (collectionId: string, item: CollectionItem) => void;
  onManageEnvs: () => void;
  onSelectEnv: (id: string | null) => void;
  onNewTab: () => void;
  onOpenCommandPalette: () => void;
  onOpenSettings: () => void;
}

interface SearchResult {
  id: string;
  category: "requests" | "environments" | "actions";
  label: string;
  sublabel?: string;
  icon: React.ReactNode;
  onSelect: () => void;
}

function flattenRequests(
  collections: StoredCollection[],
  onOpen: (collectionId: string, item: CollectionItem) => void,
): SearchResult[] {
  const results: SearchResult[] = [];
  function walk(collectionId: string, collectionName: string, items: CollectionItem[]) {
    for (const item of items) {
      if (item.is_folder) {
        if (item.items) walk(collectionId, collectionName, item.items);
      } else {
        const method = (item.method ?? "GET") as Method;
        let urlPath = "";
        try { urlPath = item.url ? new URL(item.url).pathname : ""; } catch { /* ignore */ }
        results.push({
          id: `req-${collectionId}-${item.id}`,
          category: "requests",
          label: `${method} ${item.name}`,
          sublabel: urlPath ? `${urlPath}  --  ${collectionName}` : collectionName,
          icon: (
            <span className={`text-[11px] font-bold font-mono ${HTTP_METHOD_COLOR[method] ?? "text-neutral-400"}`}>
              {method.slice(0, 3)}
            </span>
          ),
          onSelect: () => onOpen(collectionId, item),
        });
      }
    }
  }
  for (const col of collections) {
    walk(col.id, col.name, col.items);
  }
  return results;
}

const CATEGORY_LABELS: Record<string, string> = {
  requests: "REQUESTS",
  environments: "ENVIRONMENTS",
  actions: "ACTIONS",
};

const CATEGORY_ORDER = ["actions", "requests", "environments"];

export function GlobalSearch({
  open,
  onClose,
  collections,
  environments,
  onOpenRequest,
  onManageEnvs,
  onSelectEnv,
  onNewTab,
  onOpenCommandPalette,
  onOpenSettings,
}: GlobalSearchProps) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const allResults = useMemo((): SearchResult[] => {
    const requestResults = flattenRequests(collections, onOpenRequest);

    const envResults: SearchResult[] = environments.map((env) => ({
      id: `env-${env.id}`,
      category: "environments" as const,
      label: env.name,
      sublabel: `${env.variable_count} variables`,
      icon: <Globe className="h-3.5 w-3.5 text-neutral-400" />,
      onSelect: () => onSelectEnv(env.id),
    }));

    const actionResults: SearchResult[] = [
      { id: "act-new-tab", category: "actions", label: "New Request Tab", sublabel: "Cmd+T", icon: <FileText className="h-3.5 w-3.5 text-neutral-400" />, onSelect: onNewTab },
      { id: "act-cmd-palette", category: "actions", label: "Command Palette", sublabel: "Cmd+K", icon: <Search className="h-3.5 w-3.5 text-neutral-400" />, onSelect: onOpenCommandPalette },
      { id: "act-settings", category: "actions", label: "Settings", sublabel: "Cmd+,", icon: <FileText className="h-3.5 w-3.5 text-neutral-400" />, onSelect: onOpenSettings },
      { id: "act-manage-envs", category: "actions", label: "Manage Environments", icon: <Globe className="h-3.5 w-3.5 text-neutral-400" />, onSelect: onManageEnvs },
    ];

    return [...actionResults, ...requestResults, ...envResults];
  }, [collections, environments, onOpenRequest, onSelectEnv, onNewTab, onOpenCommandPalette, onOpenSettings, onManageEnvs]);

  const filtered = useMemo(() => {
    if (!query.trim()) return allResults;
    const q = query.toLowerCase();
    return allResults.filter(
      (r) =>
        r.label.toLowerCase().includes(q) ||
        (r.sublabel ?? "").toLowerCase().includes(q),
    );
  }, [allResults, query]);

  // Group by category
  const grouped = useMemo(() => {
    const groups: { category: string; items: SearchResult[] }[] = [];
    for (const cat of CATEGORY_ORDER) {
      const items = filtered.filter((r) => r.category === cat);
      if (items.length > 0) {
        groups.push({ category: cat, items });
      }
    }
    return groups;
  }, [filtered]);

  const flatItems = useMemo(() => filtered, [filtered]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Scroll selected item into view
  useEffect(() => {
    if (!listRef.current) return;
    const el = listRef.current.querySelector(`[data-index="${selectedIndex}"]`);
    if (el) el.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  const handleSelect = useCallback((result: SearchResult) => {
    result.onSelect();
    onClose();
  }, [onClose]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, flatItems.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" && flatItems[selectedIndex]) {
        e.preventDefault();
        handleSelect(flatItems[selectedIndex]);
      } else if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    },
    [flatItems, selectedIndex, onClose, handleSelect],
  );

  if (!open) return null;

  let flatIdx = 0;

  return (
    <div
      className="fixed inset-0 z-[70] flex items-start justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="mt-[10vh] w-full max-w-2xl rounded-xl border border-glass bg-neutral-900/95 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 border-b border-neutral-800 px-4 py-3">
          <Search className="h-5 w-5 text-neutral-400" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search requests, environments, actions..."
            className="flex-1 bg-transparent text-sm text-neutral-100 outline-none placeholder:text-neutral-500"
            spellCheck={false}
          />
          {query && (
            <button type="button" onClick={() => setQuery("")} className="text-neutral-500 hover:text-neutral-300">
              <X className="h-4 w-4" />
            </button>
          )}
          <kbd className="rounded border border-neutral-600 px-1.5 py-0.5 text-[10px] text-neutral-400">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div ref={listRef} className="max-h-[400px] overflow-y-auto py-1">
          {flatItems.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-neutral-500">
              No results found
            </div>
          ) : (
            grouped.map((group) => (
              <div key={group.category}>
                <div className="px-4 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-neutral-600">
                  {CATEGORY_LABELS[group.category] ?? group.category} ({group.items.length})
                </div>
                {group.items.map((result) => {
                  const idx = flatIdx++;
                  return (
                    <button
                      key={result.id}
                      data-index={idx}
                      type="button"
                      className={`flex w-full items-center gap-3 px-4 py-2 text-left text-sm transition ${
                        idx === selectedIndex
                          ? "bg-emerald-600/20 text-emerald-400"
                          : "text-neutral-300 hover:bg-neutral-800"
                      }`}
                      onClick={() => handleSelect(result)}
                      onMouseEnter={() => setSelectedIndex(idx)}
                    >
                      <span className="flex-shrink-0">{result.icon}</span>
                      <span className="flex-1 truncate">{result.label}</span>
                      {result.sublabel && (
                        <span className="truncate text-xs text-neutral-500">{result.sublabel}</span>
                      )}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-4 border-t border-neutral-800 px-4 py-2 text-[10px] text-neutral-600">
          <span><kbd className="font-mono">Up/Down</kbd> navigate</span>
          <span><kbd className="font-mono">Enter</kbd> open</span>
          <span><kbd className="font-mono">Esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}
