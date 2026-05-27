import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  Columns3,
  Plus,
  Upload,
  Globe,
  Radio,
  Zap,
  Settings,
  FileCode,
  Beaker,
  Search,
  Key,
  Database,
  Clock,
  Shield,
  Layers,
  Lock,
  GitCompare,
  GitBranch,
  Gauge,
} from "lucide-react";
import type { StoredCollection, CollectionItem, EnvironmentSummary } from "../lib/sidecar";
import { HTTP_METHOD_COLOR, type Method } from "../state/types";

export interface CommandAction {
  id: string;
  label: string;
  shortcut?: string;
  icon?: React.ReactNode;
  onSelect: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  actions: CommandAction[];
}

/** Categorize actions into groups for display. */
const GROUP_MAP: Record<string, string> = {
  "new-tab": "NAVIGATION",
  "settings": "NAVIGATION",
  "import-curl": "NAVIGATION",
  "import-collection": "NAVIGATION",
  "open-graphql": "PROTOCOLS",
  "open-websocket": "PROTOCOLS",
  "open-grpc": "PROTOCOLS",
  "open-kafka": "PROTOCOLS",
  "open-soap": "PROTOCOLS",
  "open-sse": "PROTOCOLS",
  "swagger-browser": "PROTOCOLS",
  "codegen": "TOOLS",
  "open-mock": "TOOLS",
  "load-test": "TOOLS",
  "security-scanner": "TOOLS",
  "agent-explorer": "TOOLS",
  "owasp-scanner": "TOOLS",
  "request-diff": "TOOLS",
  "jwt-inspector": "TOOLS",
  "batch-runner": "TOOLS",
  "monitors": "TOOLS",
  "manage-envs": "TOOLS",
  "collection-vars": "TOOLS",
  "secrets-vault": "TOOLS",
  "webhooks": "TOOLS",
  "multi-env": "TOOLS",
  "flow-editor": "TOOLS",
  "perf-dashboard": "TOOLS",
  "service-map": "TOOLS",
  "proxy-recorder": "TOOLS",
  "api-changelog": "TOOLS",
  "doc-generator": "TOOLS",
  "release-center": "TOOLS",
  "tpl-get-json": "TEMPLATES",
  "tpl-post-json": "TEMPLATES",
  "tpl-graphql": "TEMPLATES",
  "tpl-soap": "TEMPLATES",
  "tpl-auth-bearer": "TEMPLATES",
};

const RECENT_KEY = "theridion.recentCommands";
const MAX_RECENT = 5;

function loadRecent(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function pushRecent(id: string) {
  const recent = loadRecent().filter((r) => r !== id);
  recent.unshift(id);
  localStorage.setItem(RECENT_KEY, JSON.stringify(recent.slice(0, MAX_RECENT)));
}

const GROUP_ORDER = ["RECENT", "TEMPLATES", "NAVIGATION", "PROTOCOLS", "ENVIRONMENTS", "TOOLS", "REQUESTS"];

type GroupedAction = {
  type: "header";
  label: string;
} | {
  type: "action";
  action: CommandAction;
  flatIndex: number;
}

function groupActions(actions: CommandAction[], showRecent: boolean): GroupedAction[] {
  const groups: Record<string, CommandAction[]> = {};

  // Build RECENT group from localStorage
  if (showRecent) {
    const recentIds = loadRecent();
    const recentActions: CommandAction[] = [];
    for (const rid of recentIds) {
      const found = actions.find((a) => a.id === rid);
      if (found) recentActions.push(found);
    }
    if (recentActions.length > 0) {
      groups["RECENT"] = recentActions;
    }
  }

  for (const action of actions) {
    const group = action.id.startsWith("req-") ? "REQUESTS" : action.id.startsWith("env-") ? "ENVIRONMENTS" : (GROUP_MAP[action.id] ?? "TOOLS");
    if (!groups[group]) groups[group] = [];
    groups[group].push(action);
  }

  const result: GroupedAction[] = [];
  let flatIndex = 0;
  for (const groupName of GROUP_ORDER) {
    const items = groups[groupName];
    if (!items || items.length === 0) continue;
    result.push({ type: "header", label: groupName });
    for (const action of items) {
      result.push({ type: "action", action, flatIndex });
      flatIndex++;
    }
  }
  return result;
}

function fuzzyScore(query: string, text: string): number {
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  if (t.startsWith(q)) return 100;
  if (t.includes(q)) return 90;
  // Subsequence match: "lu" matches "List Users"
  let qi = 0;
  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) qi++;
  }
  if (qi === q.length) return 50 + (q.length / t.length) * 30;
  return 0;
}

export function CommandPalette({ open, onClose, actions }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const filtered = useMemo(() => {
    if (!query.trim()) return actions;
    const scored = actions
      .map((a) => ({ action: a, score: fuzzyScore(query, a.label) }))
      .filter((s) => s.score > 0)
      .sort((a, b) => b.score - a.score);
    return scored.map((s) => s.action);
  }, [actions, query]);

  const showRecent = !query.trim();
  const grouped = useMemo(() => groupActions(filtered, showRecent), [filtered, showRecent]);
  const flatActions = useMemo(() =>
    grouped.filter((g): g is GroupedAction & { type: "action" } => g.type === "action"),
    [grouped],
  );

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      // Focus after the modal renders.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [filtered.length]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, flatActions.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" && flatActions[selectedIndex]) {
        e.preventDefault();
        pushRecent(flatActions[selectedIndex].action.id);
        flatActions[selectedIndex].action.onSelect();
        onClose();
      } else if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    },
    [flatActions, selectedIndex, onClose],
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" />

      {/* Palette */}
      <div
        className="relative w-full max-w-lg rounded-lg border border-neutral-700 bg-neutral-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        {/* Search input */}
        <div className="flex items-center gap-2 border-b border-neutral-700 px-4 py-3">
          <Search size={16} className="text-neutral-400" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a command..."
            className="flex-1 bg-transparent text-sm text-neutral-100 outline-none placeholder:text-neutral-500"
          />
          <kbd className="rounded border border-neutral-600 px-1.5 py-0.5 text-[10px] text-neutral-400">
            ESC
          </kbd>
        </div>

        {/* Results — grouped with section headers */}
        <div className="max-h-[360px] overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-neutral-500">
              No matching commands
            </div>
          ) : (
            grouped.map((entry, i) => {
              if (entry.type === "header") {
                return (
                  <div key={`hdr-${entry.label}`} className={`${i > 0 ? "mt-1 border-t border-neutral-800 pt-1" : ""}`}>
                    <div className="px-4 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-neutral-600">
                      {entry.label}
                    </div>
                  </div>
                );
              }
              const { action, flatIndex } = entry;
              return (
                <button
                  key={action.id}
                  className={`flex w-full items-center gap-3 px-4 py-2 text-left text-sm ${
                    flatIndex === selectedIndex
                      ? "bg-emerald-600/20 text-emerald-400"
                      : "text-neutral-300 hover:bg-neutral-800"
                  }`}
                  onClick={() => {
                    pushRecent(action.id);
                    action.onSelect();
                    onClose();
                  }}
                  onMouseEnter={() => setSelectedIndex(flatIndex)}
                >
                  {action.icon && (
                    <span className="flex-shrink-0 text-neutral-400">
                      {action.icon}
                    </span>
                  )}
                  <span className="flex-1">{action.label}</span>
                  {action.shortcut && (
                    <kbd className="rounded border border-neutral-600 px-1.5 py-0.5 text-[10px] text-neutral-500">
                      {action.shortcut}
                    </kbd>
                  )}
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

/** Flatten all collection items into a list of request actions. */
function flattenCollectionRequests(
  collections: StoredCollection[],
  onOpen: (collectionId: string, item: CollectionItem) => void,
): CommandAction[] {
  const results: CommandAction[] = [];
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
          label: `${method} ${item.name}`,
          shortcut: urlPath ? `${urlPath}  ${collectionName}` : collectionName,
          icon: (
            <span className={`text-[11px] font-bold ${HTTP_METHOD_COLOR[method] ?? "text-neutral-400"}`}>
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

/** Default set of command palette actions. Callers should pass callbacks. */
export function useDefaultActions(callbacks: {
  newTab: (seed?: { method?: string; url?: string; headersRaw?: string; body?: string; name?: string }) => void;
  importCurl: () => void;
  openGraphQL: () => void;
  openWebSocket: () => void;
  openKafka: () => void;
  openSoap: () => void;
  manageEnvs: () => void;
  openCodegen: () => void;
  openGrpc?: () => void;
  openMock?: () => void;
  openLoadTest?: () => void;
  openSettings?: () => void;
  importCollection?: () => void;
  openServiceMap?: () => void;
  openProxy?: () => void;
  openSwagger?: () => void;
  openOpenapiImport?: () => void;
  openJwt?: () => void;
  openBatch?: () => void;
  openMonitors?: () => void;
  openSecurity?: () => void;
  openCollVars?: () => void;
  openSecrets?: () => void;
  openWebhooks?: () => void;
  openMultiEnv?: () => void;
  openFlowEditor?: () => void;
  openPerfDash?: () => void;
  openAgentExplorer?: () => void;
  openOwaspScanner?: () => void;
  openRequestDiff?: () => void;
  openBodyDiff?: () => void;
  openEnvComparison?: () => void;
  openSSE?: () => void;
  openChangelog?: () => void;
  openPipeline?: () => void;
  openDocGenerator?: () => void;
  openDepGraph?: () => void;
  openReleaseCenter?: () => void;
  collections?: StoredCollection[];
  onOpenRequest?: (collectionId: string, item: CollectionItem) => void;
  environments?: EnvironmentSummary[];
  activeEnvId?: string | null;
  onSelectEnv?: (id: string | null) => void;
}): CommandAction[] {
  const requestActions = useMemo(
    () =>
      callbacks.collections && callbacks.onOpenRequest
        ? flattenCollectionRequests(callbacks.collections, callbacks.onOpenRequest)
        : [],
    [callbacks.collections, callbacks.onOpenRequest],
  );

  const envActions: CommandAction[] = useMemo(() => {
    if (!callbacks.environments || !callbacks.onSelectEnv) return [];
    const actions: CommandAction[] = callbacks.environments.map((env) => ({
      id: `env-${env.id}`,
      label: `${callbacks.activeEnvId === env.id ? "\u2713 " : ""}${env.name}`,
      icon: <Settings size={14} />,
      onSelect: () => callbacks.onSelectEnv!(env.id),
    }));
    actions.push({
      id: "env-none",
      label: `${callbacks.activeEnvId === null ? "\u2713 " : ""}No environment`,
      icon: <Settings size={14} />,
      onSelect: () => callbacks.onSelectEnv!(null),
    });
    return actions;
  }, [callbacks.environments, callbacks.activeEnvId, callbacks.onSelectEnv]);

  return useMemo(
    () => [
      {
        id: "new-tab",
        label: "New Request Tab",
        shortcut: "Cmd+T",
        icon: <Plus size={14} />,
        onSelect: callbacks.newTab,
      },
      {
        id: "import-curl",
        label: "Import cURL",
        icon: <Upload size={14} />,
        onSelect: callbacks.importCurl,
      },
      {
        id: "open-graphql",
        label: "Open GraphQL",
        icon: <Globe size={14} />,
        onSelect: callbacks.openGraphQL,
      },
      {
        id: "open-websocket",
        label: "Open WebSocket",
        icon: <Radio size={14} />,
        onSelect: callbacks.openWebSocket,
      },
      {
        id: "open-kafka",
        label: "Open Kafka",
        icon: <Zap size={14} />,
        onSelect: callbacks.openKafka,
      },
      {
        id: "open-soap",
        label: "Open SOAP / WSDL",
        icon: <FileCode size={14} />,
        onSelect: callbacks.openSoap,
      },
      {
        id: "manage-envs",
        label: "Manage Environments",
        icon: <Settings size={14} />,
        onSelect: callbacks.manageEnvs,
      },
      {
        id: "codegen",
        label: "Generate Code Snippet",
        icon: <Beaker size={14} />,
        onSelect: callbacks.openCodegen,
      },
      ...(callbacks.openGrpc ? [{
        id: "open-grpc", label: "Open gRPC", icon: <Zap size={14} />, onSelect: callbacks.openGrpc,
      }] : []),
      ...(callbacks.openMock ? [{
        id: "open-mock", label: "Mock Server", icon: <Globe size={14} />, onSelect: callbacks.openMock,
      }] : []),
      ...(callbacks.openLoadTest ? [{
        id: "load-test", label: "Load Test", icon: <Zap size={14} />, onSelect: callbacks.openLoadTest,
      }] : []),
      ...(callbacks.openSettings ? [{
        id: "settings", label: "Settings", shortcut: "Cmd+,", icon: <Settings size={14} />, onSelect: callbacks.openSettings,
      }] : []),
      ...(callbacks.importCollection ? [{
        id: "import-collection", label: "Import Collection (Postman/Insomnia)", icon: <Upload size={14} />, onSelect: callbacks.importCollection,
      }] : []),
      ...(callbacks.openServiceMap ? [{
        id: "service-map", label: "Service Dependency Map", icon: <Globe size={14} />, onSelect: callbacks.openServiceMap,
      }] : []),
      ...(callbacks.openProxy ? [{
        id: "proxy-recorder", label: "Proxy Recorder (capture traffic)", icon: <Radio size={14} />, onSelect: callbacks.openProxy,
      }] : []),
      ...(callbacks.openSwagger ? [{
        id: "swagger-browser", label: "Swagger / OpenAPI Browser", icon: <FileCode size={14} />, onSelect: callbacks.openSwagger,
      }] : []),
      ...(callbacks.openOpenapiImport ? [{
        id: "openapi-import", label: "Import from OpenAPI / Swagger", icon: <FileCode size={14} />, onSelect: callbacks.openOpenapiImport,
      }] : []),
      ...(callbacks.openJwt ? [{
        id: "jwt-inspector", label: "JWT Inspector", icon: <Key size={14} />, onSelect: callbacks.openJwt,
      }] : []),
      ...(callbacks.openBatch ? [{
        id: "batch-runner", label: "Batch Runner", icon: <Database size={14} />, onSelect: callbacks.openBatch,
      }] : []),
      ...(callbacks.openMonitors ? [{
        id: "monitors", label: "Monitors (Scheduled Runs)", icon: <Clock size={14} />, onSelect: callbacks.openMonitors,
      }] : []),
      ...(callbacks.openSecurity ? [{
        id: "security-scanner", label: "Security Scanner", icon: <Shield size={14} />, onSelect: callbacks.openSecurity,
      }] : []),
      ...(callbacks.openCollVars ? [{
        id: "collection-vars", label: "Collection Variables", icon: <Layers size={14} />, onSelect: callbacks.openCollVars,
      }] : []),
      ...(callbacks.openSecrets ? [{
        id: "secrets-vault", label: "Secrets Vault", icon: <Lock size={14} />, onSelect: callbacks.openSecrets,
      }] : []),
      ...(callbacks.openWebhooks ? [{
        id: "webhooks", label: "Webhooks", icon: <Globe size={14} />, onSelect: callbacks.openWebhooks,
      }] : []),
      ...(callbacks.openMultiEnv ? [{
        id: "multi-env", label: "Multi-Environment Runner", icon: <GitCompare size={14} />, onSelect: callbacks.openMultiEnv,
      }] : []),
      ...(callbacks.openFlowEditor ? [{
        id: "flow-editor", label: "Flow Editor", icon: <GitBranch size={14} />, onSelect: callbacks.openFlowEditor,
      }] : []),
      ...(callbacks.openPerfDash ? [{
        id: "perf-dashboard", label: "Performance Dashboard", icon: <BarChart3 size={14} />, onSelect: callbacks.openPerfDash,
      }] : []),
      ...(callbacks.openAgentExplorer ? [{
        id: "agent-explorer", label: "AI: Explore API", icon: <Search size={14} />, onSelect: callbacks.openAgentExplorer,
      }] : []),
      ...(callbacks.openOwaspScanner ? [{
        id: "owasp-scanner", label: "OWASP Security Scanner", icon: <Shield size={14} />, onSelect: callbacks.openOwaspScanner,
      }] : []),
      ...(callbacks.openRequestDiff ? [{
        id: "request-diff", label: "Request Diff (compare two requests)", icon: <GitCompare size={14} />, onSelect: callbacks.openRequestDiff,
      }] : []),
      ...(callbacks.openBodyDiff ? [{
        id: "body-diff", label: "Body Diff (compare request bodies)", icon: <GitCompare size={14} />, onSelect: callbacks.openBodyDiff,
      }] : []),
      ...(callbacks.openEnvComparison ? [{
        id: "env-comparison", label: "Compare across environments", icon: <Columns3 size={14} />, onSelect: callbacks.openEnvComparison,
      }] : []),
      ...(callbacks.openSSE ? [{
        id: "open-sse", label: "Server-Sent Events (SSE)", icon: <Radio size={14} />, onSelect: callbacks.openSSE,
      }] : []),
      ...(callbacks.openChangelog ? [{
        id: "api-changelog", label: "API Changelog Detector", icon: <GitCompare size={14} />, onSelect: callbacks.openChangelog,
      }] : []),
      ...(callbacks.openPipeline ? [{
        id: "pipeline", label: "Request Pipeline", icon: <GitBranch size={14} />, onSelect: callbacks.openPipeline,
      }] : []),
      ...(callbacks.openDocGenerator ? [{
        id: "doc-generator", label: "Generate API Documentation", icon: <FileCode size={14} />, onSelect: callbacks.openDocGenerator,
      }] : []),
      ...(callbacks.openDepGraph ? [{
        id: "dep-graph", label: "Dependency Graph", icon: <GitBranch size={14} />, onSelect: callbacks.openDepGraph,
      }] : []),
      ...(callbacks.openReleaseCenter ? [{
        id: "release-center", label: "Release Center", icon: <Gauge size={14} />, onSelect: callbacks.openReleaseCenter,
      }] : []),
      {
        id: "tpl-get-json",
        label: "Template: GET JSON",
        icon: <FileCode size={14} />,
        onSelect: () => callbacks.newTab({ method: "GET", url: "https://httpbin.org/get", name: "GET JSON" }),
      },
      {
        id: "tpl-post-json",
        label: "Template: POST JSON",
        icon: <FileCode size={14} />,
        onSelect: () => callbacks.newTab({
          method: "POST",
          url: "https://httpbin.org/post",
          headersRaw: "Content-Type: application/json",
          body: JSON.stringify({ key: "value", number: 42 }, null, 2),
          name: "POST JSON",
        }),
      },
      {
        id: "tpl-graphql",
        label: "Template: GraphQL",
        icon: <FileCode size={14} />,
        onSelect: () => callbacks.newTab({
          method: "POST",
          url: "https://api.example.com/graphql",
          headersRaw: "Content-Type: application/json",
          body: JSON.stringify({ query: "{\n  viewer {\n    id\n    name\n  }\n}" }, null, 2),
          name: "GraphQL Query",
        }),
      },
      {
        id: "tpl-soap",
        label: "Template: SOAP",
        icon: <FileCode size={14} />,
        onSelect: () => callbacks.newTab({
          method: "POST",
          url: "https://api.example.com/soap",
          headersRaw: "Content-Type: text/xml; charset=utf-8\nSOAPAction: \"\"",
          body: `<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Header/>
  <soap:Body>
    <YourOperation xmlns="http://example.com/ns">
      <param>value</param>
    </YourOperation>
  </soap:Body>
</soap:Envelope>`,
          name: "SOAP Request",
        }),
      },
      {
        id: "tpl-auth-bearer",
        label: "Template: Auth Bearer",
        icon: <Key size={14} />,
        onSelect: () => callbacks.newTab({
          method: "GET",
          url: "https://httpbin.org/bearer",
          headersRaw: "Authorization: Bearer YOUR_TOKEN_HERE",
          name: "Bearer Auth",
        }),
      },
      ...envActions,
      ...requestActions,
    ],
    [callbacks, requestActions, envActions],
  );
}
