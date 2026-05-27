import { Activity, BookOpen, Bot, Braces, Clock, Command, Database, Globe, MoreHorizontal, Pin, Plus, Search, Server, Terminal, Wifi, X } from "lucide-react";
import { useState, useRef, useEffect, useCallback } from "react";
import { HTTP_METHOD_COLOR, isDirty } from "../state/types";
import type { RequestTab } from "../state/types";
import type { EnvironmentSummary } from "../lib/sidecar";
import { EnvDropdown } from "./EnvDropdown";

interface Props {
  tabs: RequestTab[];
  activeId: string;
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
  onNew: () => void;
  onOpenSoap: () => void;
  onImportCurl: () => void;
  onOpenGraphQL: () => void;
  onOpenWebSocket: () => void;
  onOpenKafka: () => void;
  onOpenGrpc: () => void;
  onOpenMock: () => void;
  onOpenLoadTest: () => void;
  onOpenSwagger: () => void;
  onToggleHistory: () => void;
  historyOpen: boolean;
  historyCount: number;
  environments: EnvironmentSummary[];
  activeEnvId: string | null;
  onSelectEnv: (id: string | null) => void;
  onManageEnv: () => void;
  onOpenAgentExplorer?: () => void;
  onDuplicateTab?: (id: string) => void;
  onPinTab?: (id: string) => void;
  onCloseOtherTabs?: (id: string) => void;
  onCloseTabsToRight?: (id: string) => void;
  onCopyUrl?: (id: string) => void;
  onCopyAsCurl?: () => void;
}

export function RequestTabBar({
  tabs,
  activeId,
  onSelect,
  onClose,
  onNew,
  onOpenSoap,
  onImportCurl,
  onOpenGraphQL,
  onOpenWebSocket,
  onOpenKafka,
  onOpenGrpc,
  onOpenMock,
  onOpenLoadTest,
  onOpenSwagger,
  onToggleHistory,
  historyOpen,
  historyCount,
  environments,
  activeEnvId,
  onSelectEnv,
  onManageEnv,
  onOpenAgentExplorer,
  onDuplicateTab,
  onPinTab,
  onCloseOtherTabs,
  onCloseTabsToRight,
  onCopyUrl,
  onCopyAsCurl,
}: Props) {
  const [overflowOpen, setOverflowOpen] = useState(false);
  const overflowRef = useRef<HTMLDivElement>(null);
  const [ctxMenu, setCtxMenu] = useState<{ open: boolean; x: number; y: number; tabId: string } | null>(null);
  const ctxRef = useRef<HTMLDivElement>(null);
  const [tabSearchOpen, setTabSearchOpen] = useState(false);
  const [tabSearchQuery, setTabSearchQuery] = useState("");
  const tabSearchRef = useRef<HTMLInputElement>(null);

  // Close context menu on outside click.
  useEffect(() => {
    if (!ctxMenu?.open) return;
    function onMouseDown(e: MouseEvent) {
      if (ctxRef.current && !ctxRef.current.contains(e.target as Node)) {
        setCtxMenu(null);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setCtxMenu(null);
    }
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [ctxMenu?.open]);

  const handleTabContextMenu = useCallback((e: React.MouseEvent, tabId: string) => {
    e.preventDefault();
    setCtxMenu({ open: true, x: e.clientX, y: e.clientY, tabId });
  }, []);

  // Close overflow menu on outside click.
  useEffect(() => {
    if (!overflowOpen) return;
    function onMouseDown(e: MouseEvent) {
      if (overflowRef.current && !overflowRef.current.contains(e.target as Node)) {
        setOverflowOpen(false);
      }
    }
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [overflowOpen]);

  return (
    <div className="flex items-stretch gap-px border-b border-glass bg-neutral-925/80 pl-1">
      <div className="flex flex-1 items-stretch gap-0.5 overflow-x-auto py-1 pl-1">
        {/* Tab search (visible only with 5+ tabs) */}
        {tabs.length >= 5 && (
          tabSearchOpen ? (
            <div className="flex items-center gap-1 rounded-md border border-glass bg-neutral-900/60 px-1.5 mr-1">
              <Search className="h-3 w-3 text-neutral-500" />
              <input
                ref={tabSearchRef}
                type="text"
                value={tabSearchQuery}
                onChange={(e) => setTabSearchQuery(e.target.value)}
                onBlur={() => { if (!tabSearchQuery) setTabSearchOpen(false); }}
                onKeyDown={(e) => { if (e.key === "Escape") { setTabSearchQuery(""); setTabSearchOpen(false); } }}
                placeholder="Filter tabs..."
                className="w-24 bg-transparent py-1 text-xs text-neutral-100 outline-none placeholder:text-neutral-600"
                autoFocus
                spellCheck={false}
              />
              {tabSearchQuery && (
                <button type="button" onClick={() => { setTabSearchQuery(""); setTabSearchOpen(false); }} className="text-neutral-500 hover:text-neutral-300">
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
          ) : (
            <button
              type="button"
              onClick={() => { setTabSearchOpen(true); setTimeout(() => tabSearchRef.current?.focus(), 50); }}
              className="mr-1 flex items-center rounded-md px-1.5 py-1 text-neutral-600 transition hover:bg-neutral-800/40 hover:text-neutral-400"
              title="Search tabs"
            >
              <Search className="h-3 w-3" />
            </button>
          )
        )}
        {/* Pinned tabs first, then unpinned; group by collection when 4+ tabs */}
        {(() => {
          const sorted = [...tabs].sort((a, b) => (a.pinned === b.pinned ? 0 : a.pinned ? -1 : 1)).filter((t) => !tabSearchQuery || t.name.toLowerCase().includes(tabSearchQuery.toLowerCase()) || t.url.toLowerCase().includes(tabSearchQuery.toLowerCase()));

          // Group tabs by collection for visual separator (only when 4+ tabs)
          const showGroups = tabs.length >= 4;
          const METHOD_GROUP_COLORS: Record<string, string> = {
            GET: "border-t-sky-500",
            POST: "border-t-emerald-500",
            PUT: "border-t-amber-500",
            PATCH: "border-t-violet-500",
            DELETE: "border-t-rose-500",
            HEAD: "border-t-neutral-500",
            OPTIONS: "border-t-neutral-500",
          };

          return sorted.map((t) => {
          const active = t.id === activeId;

          // Top border color based on collection's first method
          const topBorderClass = showGroups && t.savedAs
            ? `border-t-2 ${METHOD_GROUP_COLORS[t.method] ?? "border-t-neutral-600"}`
            : showGroups ? "border-t-2 border-t-transparent" : "";
          const durationColor = t.response
            ? t.response.elapsed_ms < 200 ? "text-emerald-400"
            : t.response.elapsed_ms <= 1000 ? "text-amber-400"
            : "text-rose-400"
            : "text-neutral-500";
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => onSelect(t.id)}
              onContextMenu={(e) => handleTabContextMenu(e, t.id)}
              className={`group relative flex items-center gap-2 rounded-md py-1.5 text-xs transition-all duration-150 ${topBorderClass} ${
                t.pinned ? "max-w-[120px] px-2" : "max-w-[240px] px-3"
              } ${
                active
                  ? "bg-neutral-800/70 text-neutral-100 shadow-inner-glow"
                  : "text-neutral-500 hover:bg-neutral-800/40 hover:text-neutral-300"
              }`}
            >
              {t.pinned && (
                <Pin className="h-2.5 w-2.5 shrink-0 text-cobweb-400" />
              )}
              <span
                className={`shrink-0 font-mono text-[10px] font-bold tracking-wide ${HTTP_METHOD_COLOR[t.method]}`}
              >
                {t.method}
              </span>
              <span className="truncate">{t.name}</span>
              {/* Response metadata on active tab with duration colors */}
              {active && t.response && (
                <span className="ml-1 flex items-center gap-1 font-mono text-[10px]">
                  <span className={
                    t.response.status >= 500 ? "text-rose-400"
                    : t.response.status >= 400 ? "text-amber-400"
                    : t.response.status >= 300 ? "text-cobweb-400"
                    : "text-emerald-400"
                  }>
                    {t.response.status}
                  </span>
                  <span className="text-neutral-600">&middot;</span>
                  <span className={durationColor}>{t.response.elapsed_ms < 1000 ? `${Math.round(t.response.elapsed_ms)}ms` : `${(t.response.elapsed_ms / 1000).toFixed(1)}s`}</span>
                </span>
              )}
              {isDirty(t) && (
                <span
                  aria-label="unsaved"
                  className="h-1.5 w-1.5 rounded-full bg-cobweb-400 shadow-[0_0_4px_rgba(34,211,238,0.4)]"
                />
              )}
              {/* Status dot */}
              {!active && t.response && (
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                  t.response.status >= 500 ? "bg-rose-500"
                  : t.response.status >= 300 ? "bg-amber-500"
                  : "bg-emerald-500"
                }`} />
              )}
              {!t.pinned && (
                <button
                  type="button"
                  aria-label="Close tab"
                  onClick={(e) => {
                    e.stopPropagation();
                    onClose(t.id);
                  }}
                  className="ml-0.5 rounded p-0.5 text-neutral-600 opacity-0 transition hover:bg-neutral-700/60 hover:text-neutral-300 group-hover:opacity-100"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </button>
          );
        });
        })()}
      </div>

      {/* Action buttons -- right side */}
      <div className="flex items-center gap-0.5 px-1">
        <BarButton onClick={onNew} title="New request (Cmd+T)">
          <Plus className="h-3.5 w-3.5" />
        </BarButton>

        {/* Command palette hint */}
        <BarButton onClick={() => { /* Cmd+K is handled globally */ const e = new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true }); window.dispatchEvent(e); }} title="Command palette (Cmd+K)">
          <Command className="h-3.5 w-3.5" />
          <span className="text-[11px]">Cmd+K</span>
        </BarButton>

        {/* Overflow menu for protocol/tool buttons */}
        <div className="relative" ref={overflowRef}>
          <BarButton onClick={() => setOverflowOpen((o) => !o)} title="More tools" active={overflowOpen}>
            <MoreHorizontal className="h-3.5 w-3.5" />
            <span className="text-[11px]">More</span>
          </BarButton>
          {overflowOpen && (
            <div className="absolute right-0 top-full z-50 mt-1 w-48 rounded-lg border border-neutral-800 bg-neutral-900 py-1 shadow-xl">
              <OverflowItem icon={<Terminal className="h-3.5 w-3.5" />} label="cURL import" onClick={() => { onImportCurl(); setOverflowOpen(false); }} />
              <OverflowItem icon={<BookOpen className="h-3.5 w-3.5" />} label="Swagger / OpenAPI" onClick={() => { onOpenSwagger(); setOverflowOpen(false); }} />
              <OverflowItem icon={<Braces className="h-3.5 w-3.5" />} label="GraphQL" onClick={() => { onOpenGraphQL(); setOverflowOpen(false); }} />
              <OverflowItem icon={<Wifi className="h-3.5 w-3.5" />} label="WebSocket" onClick={() => { onOpenWebSocket(); setOverflowOpen(false); }} />
              <OverflowItem icon={<Database className="h-3.5 w-3.5" />} label="Kafka" onClick={() => { onOpenKafka(); setOverflowOpen(false); }} />
              <OverflowItem icon={<Server className="h-3.5 w-3.5" />} label="gRPC" onClick={() => { onOpenGrpc(); setOverflowOpen(false); }} />
              <OverflowItem icon={<Server className="h-3.5 w-3.5" />} label="Mock Server" onClick={() => { onOpenMock(); setOverflowOpen(false); }} />
              <OverflowItem icon={<Activity className="h-3.5 w-3.5" />} label="Load Test" onClick={() => { onOpenLoadTest(); setOverflowOpen(false); }} />
              <OverflowItem icon={<Globe className="h-3.5 w-3.5" />} label="SOAP / WSDL" onClick={() => { onOpenSoap(); setOverflowOpen(false); }} />
              {onOpenAgentExplorer && (
                <OverflowItem icon={<Bot className="h-3.5 w-3.5" />} label="AI: Explore API" onClick={() => { onOpenAgentExplorer(); setOverflowOpen(false); }} />
              )}
            </div>
          )}
        </div>

        <BarButton
          onClick={onToggleHistory}
          title="Toggle history"
          active={historyOpen}
        >
          <Clock className="h-3.5 w-3.5" />
          <span className="text-[11px]">
            History
            {historyCount > 0 && (
              <span className="ml-1 text-neutral-600">{historyCount}</span>
            )}
          </span>
        </BarButton>
        <div className="ml-1 flex items-center border-l border-neutral-800/40 pl-2 pr-1">
          <EnvDropdown
            environments={environments}
            activeId={activeEnvId}
            onSelect={onSelectEnv}
            onManage={onManageEnv}
          />
        </div>
      </div>

      {/* Tab context menu */}
      {ctxMenu?.open && (() => {
        const ctxTab = tabs.find((t) => t.id === ctxMenu.tabId);
        const safeX = Math.min(ctxMenu.x, window.innerWidth - 200);
        const safeY = Math.min(ctxMenu.y, window.innerHeight - 240);
        return (
          <div
            ref={ctxRef}
            className="fixed z-[60] min-w-[180px] animate-slide-in rounded-lg border border-glass-light bg-neutral-900 py-1 shadow-2xl shadow-black/60"
            style={{ left: safeX, top: safeY }}
          >
            <TabCtxItem label={ctxTab?.pinned ? "Unpin tab" : "Pin tab"} onClick={() => { onPinTab?.(ctxMenu.tabId); setCtxMenu(null); }} />
            <TabCtxItem label="Duplicate tab" onClick={() => { onDuplicateTab?.(ctxMenu.tabId); setCtxMenu(null); }} />
            <div className="mx-2 my-1 border-t border-neutral-800" />
            <TabCtxItem label="Copy URL" onClick={() => { onCopyUrl?.(ctxMenu.tabId); setCtxMenu(null); }} />
            <TabCtxItem label="Copy as cURL" onClick={() => { onCopyAsCurl?.(); setCtxMenu(null); }} />
            <div className="mx-2 my-1 border-t border-neutral-800" />
            {!ctxTab?.pinned && (
              <TabCtxItem label="Close tab" onClick={() => { onClose(ctxMenu.tabId); setCtxMenu(null); }} />
            )}
            <TabCtxItem label="Close other tabs" onClick={() => { onCloseOtherTabs?.(ctxMenu.tabId); setCtxMenu(null); }} />
            <TabCtxItem label="Close tabs to the right" onClick={() => { onCloseTabsToRight?.(ctxMenu.tabId); setCtxMenu(null); }} />
          </div>
        );
      })()}
    </div>
  );
}

function TabCtxItem({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center px-3 py-1.5 text-xs text-neutral-300 transition hover:bg-neutral-800/60 hover:text-neutral-100"
    >
      {label}
    </button>
  );
}

function OverflowItem({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-2.5 px-3 py-1.5 text-xs text-neutral-400 transition hover:bg-neutral-800/60 hover:text-neutral-200"
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

function BarButton({
  onClick,
  title,
  active,
  children,
}: {
  onClick: () => void;
  title: string;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`inline-flex items-center gap-1 rounded-md px-2 py-1.5 transition-all duration-150 hover:bg-neutral-800/50 ${
        active
          ? "text-cobweb-400"
          : "text-neutral-500 hover:text-neutral-300"
      }`}
    >
      {children}
    </button>
  );
}
