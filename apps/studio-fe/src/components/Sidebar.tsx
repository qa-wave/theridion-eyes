import { useEffect, useRef, useState, useCallback } from "react";
import {
  BarChart3,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  FolderClosed,
  FolderOpen,
  FolderPlus,
  Loader2,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Star,
  Terminal,
  Trash2,
  Upload,
} from "lucide-react";
import { HTTP_METHOD_COLOR } from "../state/types";
import type { CollectionItem, StoredCollection, FavoriteItem } from "../lib/sidecar";
import { sidecar } from "../lib/sidecar";
import { Tooltip } from "./Tooltip";
import { TagPills, TagFilterBar } from "./TagManager";

/** Stored in localStorage per request: last run result for hover preview. */
interface LastResponseInfo {
  status: number;
  elapsed_ms: number;
  preview: string;
  timestamp: number;
}

const LAST_RESPONSES_KEY = "theridion.last-responses";
const COLLECTION_HEALTH_KEY = "theridion.collection-health";

type HealthStatus = "green" | "amber" | "red" | "gray";

function getLastResponses(): Map<string, LastResponseInfo> {
  try {
    const raw = localStorage.getItem(LAST_RESPONSES_KEY);
    if (!raw) return new Map();
    return new Map(Object.entries(JSON.parse(raw)));
  } catch {
    return new Map();
  }
}

function getCollectionHealth(): Map<string, HealthStatus> {
  try {
    const raw = localStorage.getItem(COLLECTION_HEALTH_KEY);
    if (!raw) return new Map();
    return new Map(Object.entries(JSON.parse(raw)));
  } catch {
    return new Map();
  }
}

interface Props {
  collections: StoredCollection[];
  loading: boolean;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onOpen: (collectionId: string, item: CollectionItem) => void;
  onNewCollection: () => void;
  onGenerateTests: () => void;
  onNewFolder: (collectionId: string, parentFolderId: string | null) => void;
  onDeleteCollection: (id: string) => void;
  onDeleteRequest: (collectionId: string, requestId: string) => void;
  onDeleteFolder: (collectionId: string, folderId: string) => void;
  onRenameCollection: (id: string, name: string) => void;
  onRenameItem: (collectionId: string, itemId: string, name: string) => void;
  onRefresh: () => void;
  onContextMenu?: (e: React.MouseEvent, collectionId: string, item: CollectionItem) => void;
  onReorder?: (collectionId: string, parentFolderId: string | null, itemIds: string[]) => void;
  onMoveToFolder?: (collectionId: string, itemId: string, targetFolderId: string | null) => void;
  onExportCurl?: (collectionId: string) => void;
  onExportPostman?: (collectionId: string) => void;
  onViewStats?: (collectionId: string) => void;
  onImport?: () => void;
  onRunCollection?: () => void;
  inlineNewName?: { type: "collection" | "folder"; parentId?: string; collectionId?: string } | null;
  onInlineNewCommit?: (name: string) => void;
  onInlineNewCancel?: () => void;
  onFileImport?: (content: string, filename: string) => void;
}

export function Sidebar({
  collections,
  loading,
  collapsed,
  onToggleCollapse,
  onOpen,
  onNewCollection,
  onGenerateTests,
  onNewFolder,
  onDeleteCollection,
  onDeleteRequest,
  onDeleteFolder,
  onRenameCollection,
  onRenameItem,
  onRefresh,
  onContextMenu,
  onReorder,
  onMoveToFolder,
  onExportCurl,
  onExportPostman,
  onViewStats,
  onImport,
  onRunCollection,
  inlineNewName,
  onInlineNewCommit,
  onInlineNewCancel,
  onFileImport,
}: Props) {
  const [query, setQuery] = useState("");
  const filter = query.toLowerCase();
  const [fileDragOver, setFileDragOver] = useState(false);
  const [activeTagFilters, setActiveTagFilters] = useState<string[]>([]);
  const [favorites, setFavorites] = useState<FavoriteItem[]>([]);
  const [favOpen, setFavOpen] = useState(true);
  const [dragItemId, setDragItemId] = useState<string | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);
  const lastResponses = getLastResponses();
  const collectionHealthMap = getCollectionHealth();

  const handleDragStart = useCallback((itemId: string) => {
    setDragItemId(itemId);
  }, []);
  const handleDragEnd = useCallback(() => {
    setDragItemId(null);
    setDropTargetId(null);
  }, []);

  useEffect(() => {
    sidecar.listFavorites().then((r) => setFavorites(r.items)).catch(() => {});
  }, [collections]);

  async function toggleFavorite(collectionId: string, item: CollectionItem) {
    const exists = favorites.some((f) => f.collection_id === collectionId && f.request_id === item.id);
    try {
      if (exists) {
        const res = await sidecar.removeFavorite(collectionId, item.id);
        setFavorites(res.items);
      } else {
        const res = await sidecar.addFavorite({
          collection_id: collectionId,
          request_id: item.id,
          name: item.name,
          method: item.method ?? "GET",
          url: item.url ?? "",
        });
        setFavorites(res.items);
      }
    } catch {
      // non-critical
    }
  }

  /* --- Collapsed (icon-only) sidebar --- */
  if (collapsed) {
    return (
      <aside className="flex h-full w-16 flex-col items-center border-r border-glass bg-neutral-925/90 transition-all duration-200 ease-in-out">
        <div className="pt-4 pb-3">
          <span className="text-gradient text-sm font-bold">T</span>
        </div>
        <div className="flex-1 overflow-y-auto py-1">
          {collections.map((c) => (
            <CollapsedCollectionNode
              key={c.id}
              collection={c}
              onOpen={(item) => onOpen(c.id, item)}
            />
          ))}
        </div>
        <button
          type="button"
          onClick={onToggleCollapse}
          className="mb-3 flex h-8 w-8 items-center justify-center rounded-lg text-neutral-500 transition hover:bg-neutral-800 hover:text-neutral-200"
          title="Expand sidebar"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </aside>
    );
  }

  /* --- Expanded sidebar --- */
  return (
    <aside
      className="relative flex h-full flex-col border-r border-glass bg-neutral-925/90 transition-all duration-200 ease-in-out"
      onDragOver={(e) => {
        e.preventDefault();
        if (e.dataTransfer.types.includes("Files")) setFileDragOver(true);
      }}
      onDragLeave={(e) => {
        // Only reset when leaving the aside itself, not its children
        if (e.currentTarget === e.target || !e.currentTarget.contains(e.relatedTarget as Node)) {
          setFileDragOver(false);
        }
      }}
      onDrop={(e) => {
        e.preventDefault();
        setFileDragOver(false);
        if (!onFileImport) return;
        const files = Array.from(e.dataTransfer.files);
        for (const file of files) {
          const ext = file.name.split(".").pop()?.toLowerCase();
          if (ext && ["json", "yaml", "yml", "har", "bru"].includes(ext)) {
            file.text().then((content) => onFileImport(content, file.name));
          }
        }
      }}
    >
      {/* File drag overlay */}
      {fileDragOver && (
        <div className="pointer-events-none absolute inset-0 z-50 flex items-center justify-center rounded-lg border-2 border-dashed border-sky-500/60 bg-sky-500/10 backdrop-blur-sm">
          <p className="text-sm font-medium text-sky-300">Drop to import collection</p>
        </div>
      )}
      {/* Branding header */}
      <div className="px-4 pt-4 pb-2">
        <h1 className="brand-gradient text-sm font-bold tracking-widest uppercase">Theridion</h1>
      </div>

      {/* Favorites section */}
      {favorites.length > 0 && (
        <div className="border-b border-glass">
          <div className="flex items-center gap-1 px-3 pt-2 pb-1">
            <button type="button" onClick={() => setFavOpen(!favOpen)} className="shrink-0 text-neutral-500">
              {favOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            </button>
            <Star className="h-3 w-3 text-amber-500" />
            <span className="text-[10px] font-semibold uppercase tracking-widest text-neutral-500">Favorites</span>
            <span className="ml-auto text-[10px] text-neutral-600">{favorites.length}</span>
          </div>
          {favOpen && (
            <div className="px-1 pb-2">
              {favorites.map((f) => (
                <button
                  key={`${f.collection_id}-${f.request_id}`}
                  type="button"
                  onClick={() => onOpen(f.collection_id, { id: f.request_id, name: f.name, is_folder: false, method: f.method as CollectionItem["method"], url: f.url })}
                  className="group flex h-9 w-full items-center gap-2 rounded px-2 text-xs text-neutral-300 hover:bg-neutral-800/60"
                >
                  <Star className="h-2.5 w-2.5 fill-amber-500 text-amber-500" />
                  <span className={`w-9 shrink-0 font-mono text-[10px] font-bold tabular-nums ${HTTP_METHOD_COLOR[f.method as keyof typeof HTTP_METHOD_COLOR] ?? "text-neutral-400"}`}>
                    {f.method}
                  </span>
                  <span className="truncate">{f.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-1 px-3 pt-3 pb-2">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          Collections
        </span>
        <Tooltip content="Refresh" side="bottom">
          <button
            type="button"
            onClick={onRefresh}
            className="ml-auto rounded p-1 text-neutral-500 transition hover:bg-neutral-800 hover:text-neutral-200"
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
          </button>
        </Tooltip>
        <Tooltip content="Generate tests" shortcut="OpenAPI / WSDL" side="bottom">
          <button
            type="button"
            onClick={onGenerateTests}
            className="rounded p-1 text-neutral-500 transition hover:bg-neutral-800 hover:text-cobweb-300"
          >
            <Sparkles className="h-3.5 w-3.5" />
          </button>
        </Tooltip>
        <Tooltip content="New collection" side="bottom">
          <button
            type="button"
            onClick={onNewCollection}
            className="rounded p-1 text-neutral-500 transition hover:bg-neutral-800 hover:text-neutral-200"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </Tooltip>
        {onImport && (
          <Tooltip content="Import collection" side="bottom">
            <button
              type="button"
              onClick={onImport}
              className="rounded p-1 text-neutral-500 transition hover:bg-neutral-800 hover:text-neutral-200"
            >
              <Upload className="h-3.5 w-3.5" />
            </button>
          </Tooltip>
        )}
      </div>

      <div className="px-3 pb-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-neutral-500" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter…"
            className="w-full rounded-md border border-glass bg-neutral-900/50 py-1.5 pl-7 pr-2 text-xs placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
          />
        </div>
      </div>

      <TagFilterBar
        activeTags={activeTagFilters}
        onToggleTag={(tag) => setActiveTagFilters((prev) =>
          prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
        )}
        onClear={() => setActiveTagFilters([])}
      />

      <div className="flex-1 overflow-y-auto px-1 pb-3">
        {inlineNewName?.type === "collection" && onInlineNewCommit && onInlineNewCancel && (
          <div className="px-2 py-1">
            <InlineRenameInput
              initial="New collection"
              onCommit={onInlineNewCommit}
              onCancel={onInlineNewCancel}
            />
          </div>
        )}
        {collections.length === 0 && !inlineNewName ? (
          <EmptyState onNewCollection={onNewCollection} />
        ) : (
          collections.map((c) => (
            <CollectionNode
              key={c.id}
              collection={c}
              filter={filter}
              onOpen={(item) => onOpen(c.id, item)}
              onNewFolder={(parentId) => onNewFolder(c.id, parentId)}
              onDeleteCollection={() => onDeleteCollection(c.id)}
              onDeleteFolder={(fid) => onDeleteFolder(c.id, fid)}
              onDeleteRequest={(rid) => onDeleteRequest(c.id, rid)}
              onRenameCollection={(name) => onRenameCollection(c.id, name)}
              onRenameItem={(itemId, name) => onRenameItem(c.id, itemId, name)}
              favorites={favorites}
              onToggleFavorite={(item) => toggleFavorite(c.id, item)}
              onContextMenu={onContextMenu ? (e, item) => onContextMenu(e, c.id, item) : undefined}
              dragItemId={dragItemId}
              dropTargetId={dropTargetId}
              onDragStart={handleDragStart}
              onDragEnd={handleDragEnd}
              onDropTargetChange={setDropTargetId}
              onReorder={onReorder ? (parentFolderId, itemIds) => onReorder(c.id, parentFolderId, itemIds) : undefined}
              onMoveToFolder={onMoveToFolder ? (itemId, folderId) => onMoveToFolder(c.id, itemId, folderId) : undefined}
              onExportCurl={onExportCurl ? () => onExportCurl(c.id) : undefined}
              onExportPostman={onExportPostman ? () => onExportPostman(c.id) : undefined}
              onViewStats={onViewStats ? () => onViewStats(c.id) : undefined}
              onRunCollection={onRunCollection}
              onGenerateDocs={async () => {
                try {
                  const result = await sidecar.generateDocs({ collection_id: c.id, format: "html" });
                  const blob = new Blob([result.content], { type: "text/html" });
                  const url = URL.createObjectURL(blob);
                  window.open(url, "_blank");
                } catch (e) {
                  console.error("failed to generate docs", e);
                }
              }}
              healthStatus={collectionHealthMap.get(c.id) ?? "gray"}
              lastResponses={lastResponses}
              inlineNewFolder={inlineNewName?.type === "folder" && inlineNewName.collectionId === c.id ? { type: "folder" as const, parentId: inlineNewName.parentId, collectionId: inlineNewName.collectionId } : null}
              onInlineNewCommit={onInlineNewCommit}
              onInlineNewCancel={onInlineNewCancel}
              tagFilters={activeTagFilters}
            />
          ))
        )}
      </div>

      {/* Collapse toggle + shortcuts hint at bottom */}
      <div className="border-t border-glass px-3 py-2">
        <button
          type="button"
          onClick={onToggleCollapse}
          className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-neutral-500 transition hover:bg-neutral-800 hover:text-neutral-200"
          title="Collapse sidebar"
        >
          <ChevronLeft className="h-4 w-4" />
          <span>Collapse</span>
        </button>
        <button
          type="button"
          onClick={() => {
            // Dispatch "?" key to trigger the shortcut overlay
            window.dispatchEvent(new KeyboardEvent("keydown", { key: "?", bubbles: true }));
          }}
          className="mt-1 flex w-full items-center justify-center rounded-lg px-2 py-1 text-[10px] text-neutral-600 transition hover:bg-neutral-800 hover:text-neutral-400"
          title="Keyboard shortcuts"
        >
          Shortcuts &#x2318;?
        </button>
      </div>
    </aside>
  );
}

/** Collapsed sidebar: show folder icon + method badges with tooltips. */
function CollapsedCollectionNode({
  collection,
  onOpen,
}: {
  collection: StoredCollection;
  onOpen: (item: CollectionItem) => void;
}) {
  function flatRequests(items: CollectionItem[]): CollectionItem[] {
    const out: CollectionItem[] = [];
    for (const it of items) {
      if (it.is_folder) out.push(...flatRequests(it.items ?? []));
      else out.push(it);
    }
    return out;
  }
  const requests = flatRequests(collection.items);
  return (
    <div className="mb-2 flex flex-col items-center gap-0.5">
      <div className="group relative flex h-9 w-9 items-center justify-center rounded-lg text-neutral-400 hover:bg-neutral-800/60" title={collection.name}>
        <FolderClosed className="h-4 w-4" />
        <span className="pointer-events-none absolute left-full ml-2 hidden whitespace-nowrap rounded-md bg-neutral-800 px-2 py-1 text-xs text-neutral-100 shadow-lg group-hover:block">
          {collection.name}
        </span>
      </div>
      {requests.slice(0, 6).map((it) => (
        <button
          key={it.id}
          type="button"
          onClick={() => onOpen(it)}
          className="group relative flex h-7 w-9 items-center justify-center rounded text-neutral-500 hover:bg-neutral-800/60"
        >
          <span className={`font-mono text-[9px] font-bold ${it.method ? HTTP_METHOD_COLOR[it.method] : "text-neutral-400"}`}>
            {(it.method ?? "GET").slice(0, 3)}
          </span>
          <span className="pointer-events-none absolute left-full ml-2 hidden whitespace-nowrap rounded-md bg-neutral-800 px-2 py-1 text-xs text-neutral-100 shadow-lg group-hover:block">
            {it.name}
          </span>
        </button>
      ))}
      {requests.length > 6 && (
        <span className="text-[9px] text-neutral-600">+{requests.length - 6}</span>
      )}
    </div>
  );
}

function EmptyState({ onNewCollection }: { onNewCollection: () => void }) {
  return (
    <div className="mx-2 mt-6 rounded-xl border border-dashed border-neutral-800/60 bg-neutral-900/20 px-5 py-10 text-center">
      <div className="mx-auto mb-4 w-fit rounded-2xl bg-neutral-800/30 p-5">
        <FolderClosed className="h-8 w-8 text-neutral-600" />
      </div>
      <p className="text-sm font-medium text-neutral-300">No collections yet</p>
      <p className="mx-auto mt-2 max-w-[200px] text-xs leading-relaxed text-neutral-600">
        Create your first collection to organize and save API requests.
      </p>
      <p className="mt-3 text-[11px] text-neutral-600">
        Or save a request with{" "}
        <kbd className="rounded-md border border-neutral-800 bg-neutral-900/80 px-1.5 py-0.5 font-mono text-[10px] shadow-inner-glow">
          &#x2318;S
        </kbd>
      </p>
      <button
        type="button"
        onClick={onNewCollection}
        className="mt-4 rounded-lg bg-accent-gradient px-4 py-2 text-xs font-semibold text-white shadow-glow-sm transition hover:shadow-glow"
      >
        + New collection
      </button>
    </div>
  );
}

function InlineRenameInput({
  initial,
  onCommit,
  onCancel,
}: {
  initial: string;
  onCommit: (name: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initial);
  const ref = useRef<HTMLInputElement>(null);
  return (
    <input
      ref={ref}
      autoFocus
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => {
        if (value.trim() && value !== initial) onCommit(value.trim());
        else onCancel();
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          if (value.trim() && value !== initial) onCommit(value.trim());
          else onCancel();
        } else if (e.key === "Escape") {
          onCancel();
        }
      }}
      className="w-full rounded-md border border-cobweb-500/50 bg-neutral-900/60 px-1 py-0 text-xs text-neutral-100 focus:outline-none"
      spellCheck={false}
    />
  );
}

function CollectionNode({
  collection,
  filter,
  onOpen,
  onNewFolder,
  onDeleteCollection,
  onDeleteFolder,
  onDeleteRequest,
  onRenameCollection,
  onRenameItem,
  favorites,
  onToggleFavorite,
  onContextMenu,
  dragItemId,
  dropTargetId,
  onDragStart,
  onDragEnd,
  onDropTargetChange,
  onReorder,
  onMoveToFolder,
  onExportCurl,
  onExportPostman,
  onViewStats,
  onRunCollection,
  onGenerateDocs,
  healthStatus,
  lastResponses,
  inlineNewFolder,
  onInlineNewCommit,
  onInlineNewCancel,
  tagFilters,
}: {
  collection: StoredCollection;
  filter: string;
  onOpen: (item: CollectionItem) => void;
  onNewFolder: (parentId: string | null) => void;
  onDeleteCollection: () => void;
  onDeleteFolder: (id: string) => void;
  onDeleteRequest: (id: string) => void;
  onRenameCollection: (name: string) => void;
  onRenameItem: (itemId: string, name: string) => void;
  favorites?: FavoriteItem[];
  onToggleFavorite?: (item: CollectionItem) => void;
  onContextMenu?: (e: React.MouseEvent, item: CollectionItem) => void;
  dragItemId?: string | null;
  dropTargetId?: string | null;
  onDragStart?: (itemId: string) => void;
  onDragEnd?: () => void;
  onDropTargetChange?: (id: string | null) => void;
  onReorder?: (parentFolderId: string | null, itemIds: string[]) => void;
  onMoveToFolder?: (itemId: string, targetFolderId: string | null) => void;
  onExportCurl?: () => void;
  onExportPostman?: () => void;
  onViewStats?: () => void;
  onRunCollection?: () => void;
  onGenerateDocs?: () => void;
  healthStatus?: HealthStatus;
  lastResponses?: Map<string, LastResponseInfo>;
  inlineNewFolder?: { type: "folder"; parentId?: string; collectionId?: string } | null;
  onInlineNewCommit?: (name: string) => void;
  onInlineNewCancel?: () => void;
  tagFilters?: string[];
}) {
  const [open, setOpen] = useState(true);
  const [renaming, setRenaming] = useState(false);
  const visibleItems = (filter || tagFilters?.length)
    ? filterTree(collection.items, filter, tagFilters)
    : collection.items;

  if ((filter || tagFilters?.length) && visibleItems.length === 0) return null;

  const itemCount = countRequests(collection.items);

  return (
    <div className={`select-none ${open ? "border-l-2 border-cobweb-500/30" : "border-l-2 border-transparent"} ml-1 transition-colors`}>
      <div className="group flex items-center gap-1 rounded px-2 py-1 hover:bg-neutral-800/60">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="shrink-0 text-neutral-500"
        >
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        </button>
        {open ? (
          <FolderOpen className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
        ) : (
          <FolderClosed className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
        )}
        {renaming ? (
          <InlineRenameInput
            initial={collection.name}
            onCommit={(name) => { onRenameCollection(name); setRenaming(false); }}
            onCancel={() => setRenaming(false)}
          />
        ) : (
          <button
            type="button"
            onClick={() => setOpen(!open)}
            onDoubleClick={() => setRenaming(true)}
            className="flex-1 truncate text-left text-xs font-semibold text-neutral-100"
          >
            {collection.name}
          </button>
        )}
        {itemCount > 0 && !renaming && (
          <span className="rounded-full bg-neutral-800/80 px-1.5 py-0.5 text-[9px] font-bold text-neutral-500">
            {itemCount}
          </span>
        )}
        {healthStatus && healthStatus !== "gray" && (
          <span className={`h-2 w-2 rounded-full ${
            healthStatus === "green" ? "bg-emerald-500" :
            healthStatus === "amber" ? "bg-amber-500" :
            "bg-rose-500"
          }`} title={`Last run: ${healthStatus === "green" ? "all passed" : healthStatus === "amber" ? "some failures" : "errors"}`} />
        )}
        <button
          type="button"
          onClick={() => setRenaming(true)}
          className="rounded p-0.5 text-neutral-600 opacity-0 transition hover:bg-neutral-800 hover:text-neutral-200 group-hover:opacity-100"
          title="Rename"
        >
          <Pencil className="h-3 w-3" />
        </button>
        <button
          type="button"
          onClick={() => onNewFolder(null)}
          className="rounded p-0.5 text-neutral-600 opacity-0 transition hover:bg-neutral-800 hover:text-neutral-200 group-hover:opacity-100"
          title="New folder at root"
        >
          <FolderPlus className="h-3 w-3" />
        </button>
        {onRunCollection && (
          <button
            type="button"
            onClick={onRunCollection}
            className="rounded p-0.5 text-neutral-600 opacity-0 transition hover:bg-neutral-800 hover:text-emerald-400 group-hover:opacity-100"
            title="Run collection"
          >
            <Play className="h-3 w-3" />
          </button>
        )}
        {onExportCurl && (
          <button
            type="button"
            onClick={onExportCurl}
            className="rounded p-0.5 text-neutral-600 opacity-0 transition hover:bg-neutral-800 hover:text-neutral-200 group-hover:opacity-100"
            title="Export as cURL"
          >
            <Terminal className="h-3 w-3" />
          </button>
        )}
        {onExportPostman && (
          <button
            type="button"
            onClick={onExportPostman}
            className="rounded p-0.5 text-neutral-600 opacity-0 transition hover:bg-neutral-800 hover:text-amber-400 group-hover:opacity-100"
            title="Export as Postman"
          >
            <Download className="h-3 w-3" />
          </button>
        )}
        {onViewStats && (
          <button
            type="button"
            onClick={onViewStats}
            className="rounded p-0.5 text-neutral-600 opacity-0 transition hover:bg-neutral-800 hover:text-violet-400 group-hover:opacity-100"
            title="View Statistics"
          >
            <BarChart3 className="h-3 w-3" />
          </button>
        )}
        {onGenerateDocs && (
          <button
            type="button"
            onClick={onGenerateDocs}
            className="rounded p-0.5 text-neutral-600 opacity-0 transition hover:bg-neutral-800 hover:text-cobweb-400 group-hover:opacity-100"
            title="Generate Docs"
          >
            <FileText className="h-3 w-3" />
          </button>
        )}
        <button
          type="button"
          onClick={() => onDeleteCollection()}
          className="rounded p-0.5 text-neutral-600 opacity-0 transition hover:bg-neutral-800 hover:text-rose-400 group-hover:opacity-100"
          title="Delete collection"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
      {open && (
        <div className="folder-children-enter">
        {inlineNewFolder && !inlineNewFolder.parentId && onInlineNewCommit && onInlineNewCancel && (
          <div className="py-0.5" style={{ paddingLeft: "1.25rem" }}>
            <InlineRenameInput
              initial="New folder"
              onCommit={onInlineNewCommit}
              onCancel={onInlineNewCancel}
            />
          </div>
        )}
        <ItemList
          items={visibleItems}
          depth={1}
          onOpen={onOpen}
          onNewFolder={onNewFolder}
          onDeleteFolder={onDeleteFolder}
          onDeleteRequest={onDeleteRequest}
          onRenameItem={onRenameItem}
          favorites={favorites}
          onToggleFavorite={onToggleFavorite}
          collectionId={collection.id}
          onContextMenu={onContextMenu}
          parentFolderId={null}
          dragItemId={dragItemId}
          dropTargetId={dropTargetId}
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
          onDropTargetChange={onDropTargetChange}
          onReorder={onReorder}
          onMoveToFolder={onMoveToFolder}
          lastResponses={lastResponses}
        />
        </div>
      )}
      {open && collection.items.length === 0 && (
        <p className="px-8 py-1 text-[11px] italic text-neutral-600">
          (empty)
        </p>
      )}
    </div>
  );
}

function ItemList({
  items,
  depth,
  onOpen,
  onNewFolder,
  onDeleteFolder,
  onDeleteRequest,
  onRenameItem,
  favorites,
  onToggleFavorite,
  collectionId,
  onContextMenu,
  parentFolderId,
  dragItemId,
  dropTargetId,
  onDragStart,
  onDragEnd,
  onDropTargetChange,
  onReorder,
  onMoveToFolder,
  lastResponses,
}: {
  items: CollectionItem[];
  depth: number;
  onOpen: (item: CollectionItem) => void;
  onNewFolder: (parentId: string | null) => void;
  onDeleteFolder: (id: string) => void;
  onDeleteRequest: (id: string) => void;
  onRenameItem: (itemId: string, name: string) => void;
  favorites?: FavoriteItem[];
  onToggleFavorite?: (item: CollectionItem) => void;
  collectionId?: string;
  onContextMenu?: (e: React.MouseEvent, item: CollectionItem) => void;
  parentFolderId?: string | null;
  dragItemId?: string | null;
  dropTargetId?: string | null;
  onDragStart?: (itemId: string) => void;
  onDragEnd?: () => void;
  onDropTargetChange?: (id: string | null) => void;
  onReorder?: (parentFolderId: string | null, itemIds: string[]) => void;
  onMoveToFolder?: (itemId: string, targetFolderId: string | null) => void;
  lastResponses?: Map<string, LastResponseInfo>;
}) {
  const handleDrop = useCallback((targetIndex: number) => {
    if (!dragItemId || !onReorder) return;
    const currentIndex = items.findIndex((it) => it.id === dragItemId);
    if (currentIndex === -1 || currentIndex === targetIndex) return;
    const ids = items.map((it) => it.id);
    ids.splice(currentIndex, 1);
    ids.splice(targetIndex > currentIndex ? targetIndex - 1 : targetIndex, 0, dragItemId);
    onReorder(parentFolderId ?? null, ids);
  }, [dragItemId, items, onReorder, parentFolderId]);

  return (
    <>
      {items.map((it, idx) =>
        it.is_folder ? (
          <FolderNode
            key={it.id}
            folder={it}
            depth={depth}
            onOpen={onOpen}
            onNewFolder={onNewFolder}
            onDeleteFolder={onDeleteFolder}
            onDeleteRequest={onDeleteRequest}
            onRenameItem={onRenameItem}
            favorites={favorites}
            onToggleFavorite={onToggleFavorite}
            collectionId={collectionId}
            onContextMenu={onContextMenu}
            dragItemId={dragItemId}
            dropTargetId={dropTargetId}
            onDragStart={onDragStart}
            onDragEnd={onDragEnd}
            onDropTargetChange={onDropTargetChange}
            onReorder={onReorder}
            onMoveToFolder={onMoveToFolder}
            onDropBefore={() => handleDrop(idx)}
            lastResponses={lastResponses}
          />
        ) : (
          <RequestRow
            key={it.id}
            request={it}
            depth={depth}
            onOpen={() => onOpen(it)}
            onDelete={() => onDeleteRequest(it.id)}
            onRename={(name) => onRenameItem(it.id, name)}
            isFavorite={favorites?.some((f) => f.collection_id === collectionId && f.request_id === it.id)}
            onToggleFavorite={onToggleFavorite ? () => onToggleFavorite(it) : undefined}
            onContextMenu={onContextMenu ? (e) => onContextMenu(e, it) : undefined}
            isDragging={dragItemId === it.id}
            isDropTarget={dropTargetId === it.id}
            onDragStart={onDragStart ? () => onDragStart(it.id) : undefined}
            onDragEnd={onDragEnd}
            onDropBefore={() => handleDrop(idx)}
            onDropTargetChange={onDropTargetChange}
            itemId={it.id}
            lastResponseInfo={lastResponses?.get(it.id)}
          />
        ),
      )}
    </>
  );
}

function FolderNode({
  folder,
  depth,
  onOpen,
  onNewFolder,
  onDeleteFolder,
  onDeleteRequest,
  onRenameItem,
  favorites,
  onToggleFavorite,
  collectionId,
  onContextMenu,
  dragItemId,
  dropTargetId,
  onDragStart,
  onDragEnd,
  onDropTargetChange,
  onReorder,
  onMoveToFolder,
  onDropBefore: _onDropBefore,
  lastResponses,
}: {
  folder: CollectionItem;
  depth: number;
  onOpen: (item: CollectionItem) => void;
  onNewFolder: (parentId: string | null) => void;
  onDeleteFolder: (id: string) => void;
  onDeleteRequest: (id: string) => void;
  onRenameItem: (itemId: string, name: string) => void;
  favorites?: FavoriteItem[];
  onToggleFavorite?: (item: CollectionItem) => void;
  collectionId?: string;
  onContextMenu?: (e: React.MouseEvent, item: CollectionItem) => void;
  dragItemId?: string | null;
  dropTargetId?: string | null;
  onDragStart?: (itemId: string) => void;
  onDragEnd?: () => void;
  onDropTargetChange?: (id: string | null) => void;
  onReorder?: (parentFolderId: string | null, itemIds: string[]) => void;
  onMoveToFolder?: (itemId: string, targetFolderId: string | null) => void;
  onDropBefore?: () => void;
  lastResponses?: Map<string, LastResponseInfo>;
}) {
  const [open, setOpen] = useState(true);
  const [renaming, setRenaming] = useState(false);
  const [folderHighlight, setFolderHighlight] = useState(false);
  const padLeft = `${0.5 + depth * 0.75}rem`;
  return (
    <div>
      <div
        className={`group flex items-center rounded text-xs hover:bg-neutral-800/60 ${folderHighlight ? "ring-1 ring-cobweb-500/50 bg-cobweb-500/10" : ""}`}
        style={{ paddingLeft: padLeft }}
        onDragOver={(e) => {
          e.preventDefault();
          e.stopPropagation();
          if (dragItemId && dragItemId !== folder.id) {
            setFolderHighlight(true);
          }
        }}
        onDragLeave={() => setFolderHighlight(false)}
        onDrop={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setFolderHighlight(false);
          if (dragItemId && dragItemId !== folder.id && onMoveToFolder) {
            onMoveToFolder(dragItemId, folder.id);
          }
          onDragEnd?.();
        }}
      >
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="shrink-0 py-1 text-neutral-500"
        >
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        </button>
        {open ? (
          <FolderOpen className="mx-1 h-3 w-3 shrink-0 text-neutral-400" />
        ) : (
          <FolderClosed className="mx-1 h-3 w-3 shrink-0 text-neutral-400" />
        )}
        {renaming ? (
          <InlineRenameInput
            initial={folder.name}
            onCommit={(name) => { onRenameItem(folder.id, name); setRenaming(false); }}
            onCancel={() => setRenaming(false)}
          />
        ) : (
          <button
            type="button"
            onClick={() => setOpen(!open)}
            onDoubleClick={() => setRenaming(true)}
            className="flex-1 truncate py-1 pr-2 text-left text-neutral-200"
          >
            {folder.name}
          </button>
        )}
        {!renaming && countRequests(folder.items ?? []) > 0 && (
          <span className="text-[10px] text-neutral-600 ml-auto mr-0.5">
            {countRequests(folder.items ?? [])}
          </span>
        )}
        <button
          type="button"
          onClick={() => setRenaming(true)}
          className="rounded p-0.5 text-neutral-600 opacity-0 transition hover:bg-neutral-800 hover:text-neutral-200 group-hover:opacity-100"
          title="Rename"
        >
          <Pencil className="h-3 w-3" />
        </button>
        <button
          type="button"
          onClick={() => onNewFolder(folder.id)}
          className="rounded p-0.5 text-neutral-600 opacity-0 transition hover:bg-neutral-800 hover:text-neutral-200 group-hover:opacity-100"
          title="New subfolder"
        >
          <FolderPlus className="h-3 w-3" />
        </button>
        <button
          type="button"
          onClick={() => onDeleteFolder(folder.id)}
          className="mr-1 rounded p-0.5 text-neutral-600 opacity-0 transition hover:bg-neutral-800 hover:text-rose-400 group-hover:opacity-100"
          title="Delete folder"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
      {open && (folder.items?.length ?? 0) > 0 && (
        <div className="folder-children-enter">
        <ItemList
          items={folder.items ?? []}
          depth={depth + 1}
          onOpen={onOpen}
          onNewFolder={onNewFolder}
          onDeleteFolder={onDeleteFolder}
          onDeleteRequest={onDeleteRequest}
          onRenameItem={onRenameItem}
          favorites={favorites}
          onToggleFavorite={onToggleFavorite}
          collectionId={collectionId}
          onContextMenu={onContextMenu}
          parentFolderId={folder.id}
          dragItemId={dragItemId}
          dropTargetId={dropTargetId}
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
          onDropTargetChange={onDropTargetChange}
          onReorder={onReorder}
          onMoveToFolder={onMoveToFolder}
          lastResponses={lastResponses}
        />
        </div>
      )}
    </div>
  );
}

function RequestRow({
  request,
  depth,
  onOpen,
  onDelete,
  onRename,
  isFavorite,
  onToggleFavorite,
  onContextMenu,
  isDragging,
  isDropTarget,
  onDragStart,
  onDragEnd,
  onDropBefore,
  onDropTargetChange,
  itemId,
  lastResponseInfo,
}: {
  request: CollectionItem;
  depth: number;
  onOpen: () => void;
  onDelete: () => void;
  onRename: (name: string) => void;
  isFavorite?: boolean;
  onToggleFavorite?: () => void;
  onContextMenu?: (e: React.MouseEvent) => void;
  isDragging?: boolean;
  isDropTarget?: boolean;
  onDragStart?: () => void;
  onDragEnd?: () => void;
  onDropBefore?: () => void;
  onDropTargetChange?: (id: string | null) => void;
  itemId?: string;
  lastResponseInfo?: LastResponseInfo;
}) {
  const methodBorderColor: Record<string, string> = {
    GET: "border-l-sky-500", POST: "border-l-emerald-500",
    PUT: "border-l-amber-500", PATCH: "border-l-violet-500",
    DELETE: "border-l-rose-500", HEAD: "border-l-neutral-500",
    OPTIONS: "border-l-neutral-500",
  };
  const [renaming, setRenaming] = useState(false);
  const [hovering, setHovering] = useState(false);
  const hoverTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const padLeft = `${1.25 + depth * 0.75}rem`;
  const borderClass = methodBorderColor[request.method ?? "GET"] ?? "border-l-neutral-500";
  return (
    <div
      className={`group relative flex items-center rounded text-xs hover:bg-neutral-800/60 border-l-2 ${borderClass} ${isDragging ? "opacity-50" : ""} ${isDropTarget ? "border-t-2 border-cobweb-500" : ""}`}
      onContextMenu={onContextMenu}
      onMouseEnter={() => {
        if (lastResponseInfo) {
          hoverTimeout.current = setTimeout(() => setHovering(true), 500);
        }
      }}
      onMouseLeave={() => {
        if (hoverTimeout.current) clearTimeout(hoverTimeout.current);
        setHovering(false);
      }}
      draggable={!renaming}
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", request.id);
        onDragStart?.();
      }}
      onDragEnd={() => {
        onDragEnd?.();
      }}
      onDragOver={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onDropTargetChange?.(itemId ?? null);
      }}
      onDragLeave={() => {
        onDropTargetChange?.(null);
      }}
      onDrop={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onDropBefore?.();
        onDragEnd?.();
      }}
    >
      {renaming ? (
        <div className="flex flex-1 items-center gap-2 py-0.5" style={{ paddingLeft: padLeft }}>
          <span
            className={`w-9 shrink-0 font-mono text-[10px] font-bold tabular-nums ${
              request.method ? HTTP_METHOD_COLOR[request.method] : "text-neutral-400"
            }`}
          >
            {request.method ?? ""}
          </span>
          <InlineRenameInput
            initial={request.name}
            onCommit={(name) => { onRename(name); setRenaming(false); }}
            onCancel={() => setRenaming(false)}
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={onOpen}
          onDoubleClick={(e) => { e.stopPropagation(); setRenaming(true); }}
          className="flex flex-1 items-center gap-2 py-1 pr-2 text-left text-neutral-300"
          style={{ paddingLeft: padLeft }}
          title={request.url}
        >
          <span
            className={`w-9 shrink-0 font-mono text-[10px] font-bold tabular-nums ${
              request.method ? HTTP_METHOD_COLOR[request.method] : "text-neutral-400"
            }`}
          >
            {request.method ?? ""}
          </span>
          <span className="truncate">{request.name}</span>
          <TagPills tags={request.tags ?? []} />
        </button>
      )}
      {onToggleFavorite && (
        <button
          type="button"
          onClick={onToggleFavorite}
          className={`rounded p-0.5 transition ${
            isFavorite
              ? "text-amber-500"
              : "text-neutral-600 opacity-0 hover:text-amber-400 group-hover:opacity-100"
          } hover:bg-neutral-800`}
          title={isFavorite ? "Remove from favorites" : "Add to favorites"}
        >
          <Star className={`h-3 w-3 ${isFavorite ? "fill-amber-500" : ""}`} />
        </button>
      )}
      <button
        type="button"
        onClick={() => setRenaming(true)}
        className="rounded p-0.5 text-neutral-600 opacity-0 transition hover:bg-neutral-800 hover:text-neutral-200 group-hover:opacity-100"
        title="Rename"
      >
        <Pencil className="h-3 w-3" />
      </button>
      <button
        type="button"
        onClick={() => onDelete()}
        className="mr-1 rounded p-0.5 text-neutral-600 opacity-0 transition hover:bg-neutral-800 hover:text-rose-400 group-hover:opacity-100"
        title="Delete request"
      >
        <Trash2 className="h-3 w-3" />
      </button>
      {/* Inline response preview tooltip */}
      {hovering && lastResponseInfo && (
        <div className="absolute left-full top-0 z-40 ml-2 w-56 rounded-md border border-neutral-700 bg-neutral-900 p-2.5 shadow-xl">
          <div className="flex items-center gap-2 text-[11px]">
            <span className={`font-mono font-bold ${
              lastResponseInfo.status < 300 ? "text-emerald-400" :
              lastResponseInfo.status < 400 ? "text-cobweb-400" :
              lastResponseInfo.status < 500 ? "text-amber-400" :
              "text-rose-400"
            }`}>{lastResponseInfo.status}</span>
            <span className="text-neutral-500">{lastResponseInfo.elapsed_ms}ms</span>
            <span className="ml-auto text-[10px] text-neutral-600">{new Date(lastResponseInfo.timestamp).toLocaleTimeString()}</span>
          </div>
          {lastResponseInfo.preview && (
            <pre className="mt-1.5 max-h-12 overflow-hidden rounded bg-neutral-800/50 px-2 py-1 font-mono text-[10px] text-neutral-400 leading-relaxed">{lastResponseInfo.preview.slice(0, 150)}</pre>
          )}
        </div>
      )}
    </div>
  );
}

/** Count non-folder requests in a tree recursively. */
function countRequests(items: CollectionItem[]): number {
  let count = 0;
  for (const it of items) {
    if (it.is_folder) {
      count += countRequests(it.items ?? []);
    } else {
      count += 1;
    }
  }
  return count;
}

/** Filter the tree, keeping any branch where some descendant matches. */
function filterTree(items: CollectionItem[], q: string, tagFilters?: string[]): CollectionItem[] {
  const out: CollectionItem[] = [];
  for (const it of items) {
    if (it.is_folder) {
      const subItems = filterTree(it.items ?? [], q, tagFilters);
      const selfMatches = !q || it.name.toLowerCase().includes(q);
      if (subItems.length > 0 || (selfMatches && !tagFilters?.length)) {
        out.push({ ...it, items: subItems });
      }
    } else {
      const textMatch = !q || it.name.toLowerCase().includes(q) || (it.url ?? "").toLowerCase().includes(q);
      const tagMatch = !tagFilters?.length || tagFilters.some((t) => (it.tags ?? []).includes(t));
      if (textMatch && tagMatch) {
        out.push(it);
      }
    }
  }
  return out;
}
