import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { CheckCircle2, ChevronDown, ClipboardCopy, Globe, Save, Send, XCircle } from "lucide-react";
import { HTTP_METHOD_COLOR, METHODS } from "../state/types";
import type { Method } from "../state/types";
import type { EnvironmentSummary } from "../lib/sidecar";
import { sidecar } from "../lib/sidecar";
import { Tooltip } from "./Tooltip";
import { TemplateValidationIndicator, TemplatePreviewButton } from "./TemplateHelper";

/** Built-in template functions available in {{...}} expressions. */
const BUILTIN_VARS: { name: string; label: string }[] = [
  { name: "$timestamp", label: "Unix timestamp" },
  { name: "$uuid", label: "UUID v4" },
  { name: "$isoDate", label: "ISO 8601 date" },
  { name: "$randomInt", label: "Random integer" },
  { name: "$if ", label: "Conditional block" },
  { name: "$endif", label: "End conditional" },
  { name: "$each ", label: "Loop over array" },
  { name: "$end", label: "End loop" },
  { name: "$concat ", label: "String concatenation" },
  { name: "$math ", label: "Arithmetic expression" },
  { name: "$default ", label: "Default/fallback value" },
  { name: "$env ", label: "System env variable" },
];

/** Pipe filters available after | in template expressions. */
// @ts-ignore reserved for future use
const PIPE_FILTERS: { name: string; label: string }[] = [
  { name: "upper", label: "Uppercase" },
  { name: "lower", label: "Lowercase" },
  { name: "base64", label: "Base64 encode" },
  { name: "json", label: "JSON stringify" },
  { name: "urlencode", label: "URL encode" },
  { name: "trim", label: "Trim whitespace" },
  { name: "slice:0:N", label: "Substring slice" },
];

interface Props {
  method: Method;
  url: string;
  busy: boolean;
  canSend: boolean;
  dirty: boolean;
  onMethodChange: (m: Method) => void;
  onUrlChange: (u: string) => void;
  onSend: () => void;
  onCancel?: () => void;
  onSave: () => void;
  onSaveAs: () => void;
  onCopyAsCurl: () => void;
  onCopyShareable?: () => void;
  activeEnvId?: string | null;
  environments?: EnvironmentSummary[];
  onEnvChange?: (envId: string | null) => void;
  lastStatus?: number | null;
}

export function UrlBar({
  method,
  url,
  busy,
  canSend,
  dirty,
  onMethodChange,
  onUrlChange,
  onSend,
  onCancel,
  onSave,
  onSaveAs,
  onCopyAsCurl,
  onCopyShareable,
  activeEnvId,
  environments,
  onEnvChange,
  lastStatus,
}: Props) {
  const [copied, setCopied] = useState(false);
  const [sendFlash, setSendFlash] = useState<"ok" | "err" | null>(null);

  // Flash the send button on status change.
  useEffect(() => {
    if (lastStatus === null || lastStatus === undefined) return;
    const tone = lastStatus < 400 ? "ok" : "err";
    setSendFlash(tone);
    const timer = setTimeout(() => setSendFlash(null), 1000);
    return () => clearTimeout(timer);
  }, [lastStatus]);
  const [autocompleteOpen, setAutocompleteOpen] = useState(false);
  const [autocompleteItems, setAutocompleteItems] = useState<{ name: string; label: string }[]>([]);
  const [autocompleteIdx, setAutocompleteIdx] = useState(0);
  const [varPrefix, setVarPrefix] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const [envVars, setEnvVars] = useState<{ name: string; value: string }[]>([]);
  const [globalVars, setGlobalVars] = useState<{ name: string; value: string }[]>([]);

  // Load env and global variables on mount and when env changes.
  useEffect(() => {
    sidecar.getGlobals().then((r) => setGlobalVars(r.variables.filter(v => v.enabled).map(v => ({ name: v.name, value: v.value })))).catch(() => {});
    if (activeEnvId) {
      sidecar.getEnvironment(activeEnvId).then((env) => setEnvVars(env.variables.filter(v => v.enabled).map(v => ({ name: v.name, value: v.value })))).catch(() => {});
    } else {
      setEnvVars([]);
    }
  }, [activeEnvId]);

  // URL history for autocomplete (stored in localStorage).
  const URL_HISTORY_KEY = "theridion.url-history";
  const MAX_URL_HISTORY = 50;
  const [urlHistory] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(URL_HISTORY_KEY) ?? "[]"); } catch { return []; }
  });
  const [urlSuggestions, setUrlSuggestions] = useState<string[]>([]);
  const [urlSuggestOpen, setUrlSuggestOpen] = useState(false);
  const [urlSuggestIdx, setUrlSuggestIdx] = useState(0);

  // Record URL to history on send.
  useEffect(() => {
    if (lastStatus === null || lastStatus === undefined || !url) return;
    const hist: string[] = JSON.parse(localStorage.getItem(URL_HISTORY_KEY) ?? "[]");
    const filtered = hist.filter((u) => u !== url);
    filtered.unshift(url);
    localStorage.setItem(URL_HISTORY_KEY, JSON.stringify(filtered.slice(0, MAX_URL_HISTORY)));
  }, [lastStatus, url]);

  const allVars = useCallback(() => {
    const items: { name: string; label: string }[] = [];
    for (const g of globalVars) items.push({ name: g.name, label: `global: ${g.value}` });
    for (const e of envVars) items.push({ name: e.name, label: `env: ${e.value}` });
    for (const b of BUILTIN_VARS) items.push(b);
    return items;
  }, [globalVars, envVars]);

  function checkAutocomplete(value: string, cursorPos: number) {
    // Check if cursor is after "{{" and before "}}"
    const before = value.slice(0, cursorPos);
    const lastOpen = before.lastIndexOf("{{");
    if (lastOpen !== -1) {
      const afterOpen = before.slice(lastOpen + 2);
      if (!afterOpen.includes("}}")) {
        // Check if user is typing after a pipe | for filter autocomplete
        const pipeMatch = afterOpen.match(/\|\s*(\w*)$/);
        if (pipeMatch) {
          const filterPrefix = pipeMatch[1].toLowerCase();
          setVarPrefix(pipeMatch[1]);
          const items = PIPE_FILTERS.filter(f => f.name.toLowerCase().startsWith(filterPrefix));
          if (items.length > 0) {
            setAutocompleteItems(items);
            setAutocompleteIdx(0);
            setAutocompleteOpen(true);
            setUrlSuggestOpen(false);
            return;
          }
        }
        // Regular variable/function autocomplete
        const prefix = afterOpen.toLowerCase();
        setVarPrefix(afterOpen);
        const items = allVars().filter(v => v.name.toLowerCase().includes(prefix));
        if (items.length > 0) {
          setAutocompleteItems(items);
          setAutocompleteIdx(0);
          setAutocompleteOpen(true);
          setUrlSuggestOpen(false);
          return;
        }
      }
    }
    setAutocompleteOpen(false);
    // URL history suggestions (when not in variable mode)
    if (value.length >= 3 && !value.includes("{{")) {
      const q = value.toLowerCase();
      const matches = urlHistory.filter((u) => u.toLowerCase().includes(q) && u !== value).slice(0, 6);
      if (matches.length > 0) {
        setUrlSuggestions(matches);
        setUrlSuggestIdx(0);
        setUrlSuggestOpen(true);
      } else {
        setUrlSuggestOpen(false);
      }
    } else {
      setUrlSuggestOpen(false);
    }
  }

  function insertAutocomplete(varName: string) {
    const el = inputRef.current;
    if (!el) return;
    const cursorPos = el.selectionStart ?? url.length;
    const before = url.slice(0, cursorPos);
    const lastOpen = before.lastIndexOf("{{");
    if (lastOpen === -1) return;
    const after = url.slice(cursorPos);
    const closeIdx = after.indexOf("}}");
    const newUrl = url.slice(0, lastOpen) + "{{" + varName + "}}" + (closeIdx >= 0 ? after.slice(closeIdx + 2) : after);
    onUrlChange(newUrl);
    setAutocompleteOpen(false);
    // Restore focus
    setTimeout(() => { el.focus(); el.setSelectionRange(lastOpen + varName.length + 4, lastOpen + varName.length + 4); }, 0);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (autocompleteOpen) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setAutocompleteIdx((i) => Math.min(i + 1, autocompleteItems.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setAutocompleteIdx((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        if (autocompleteItems[autocompleteIdx]) {
          insertAutocomplete(autocompleteItems[autocompleteIdx].name);
        }
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setAutocompleteOpen(false);
        return;
      }
    }
    if (urlSuggestOpen) {
      if (e.key === "ArrowDown") { e.preventDefault(); setUrlSuggestIdx((i) => Math.min(i + 1, urlSuggestions.length - 1)); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setUrlSuggestIdx((i) => Math.max(i - 1, 0)); return; }
      if (e.key === "Enter" || e.key === "Tab") {
        if (urlSuggestions[urlSuggestIdx]) { e.preventDefault(); onUrlChange(urlSuggestions[urlSuggestIdx]); setUrlSuggestOpen(false); return; }
      }
      if (e.key === "Escape") { e.preventDefault(); setUrlSuggestOpen(false); return; }
    }
    if (e.key === "Enter" && canSend) {
      e.preventDefault();
      onSend();
    }
  }

  const resolvedUrl = useMemo(() => {
    if (!url.includes("{{")) return null;
    let resolved = url;
    for (const v of envVars) resolved = resolved.replaceAll(`{{${v.name}}}`, v.value);
    for (const v of globalVars) resolved = resolved.replaceAll(`{{${v.name}}}`, v.value);
    // Built-in vars preview
    resolved = resolved.replace(/\{\{\$timestamp\}\}/g, String(Math.floor(Date.now() / 1000)));
    resolved = resolved.replace(/\{\{\$uuid\}\}/g, "xxxxxxxx-...");
    resolved = resolved.replace(/\{\{\$isoDate\}\}/g, new Date().toISOString().split("T")[0]);
    resolved = resolved.replace(/\{\{\$randomInt\}\}/g, "42");
    if (resolved === url) return null; // nothing resolved
    return resolved;
  }, [url, envVars, globalVars]);

  return (
    <div className="flex flex-col border-b border-glass bg-neutral-950/80">
    <div className="flex items-stretch gap-2.5 px-4 py-3">
      {/* Method + URL input group */}
      <div className="flex flex-1 items-stretch overflow-hidden rounded-xl border border-neutral-800/80 bg-neutral-900/60 shadow-[inset_0_1px_3px_rgba(0,0,0,0.3),inset_0_1px_0_rgba(255,255,255,0.03)] transition-all duration-200 focus-within:border-cobweb-500/40 focus-within:shadow-glow-sm">
        <Tooltip content="HTTP Method" side="bottom">
          <div className="relative">
            <select
              data-testid="http-method-select"
              value={method}
              onChange={(e) => onMethodChange(e.target.value as Method)}
              className={`appearance-none bg-transparent py-2.5 pl-3.5 pr-8 font-mono text-xs font-bold tracking-wide focus:outline-none ${HTTP_METHOD_COLOR[method]}`}
            >
              {METHODS.map((m) => (
                <option key={m} value={m} className="bg-neutral-900">
                  {m}
                </option>
              ))}
            </select>
            <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-neutral-600">
              &#x25BE;
            </span>
          </div>
        </Tooltip>
        <div className="my-1.5 w-px bg-neutral-700/40" />
        <div className="relative flex-1">
          <input
            ref={inputRef}
            value={url}
            onChange={(e) => {
              onUrlChange(e.target.value);
              checkAutocomplete(e.target.value, e.target.selectionStart ?? e.target.value.length);
            }}
            onKeyDown={onKeyDown}
            onBlur={() => setTimeout(() => setAutocompleteOpen(false), 200)}
            placeholder="https://api.example.com/v1/resource"
            className={`w-full bg-transparent px-3 py-2.5 font-mono text-[13px] placeholder-neutral-600 focus:outline-none ${url.includes("{{") ? "text-transparent caret-neutral-100" : "text-neutral-100"}`}
            autoComplete="off"
            spellCheck={false}
            style={url.includes("{{") ? { caretColor: "rgb(245 245 245)" } : undefined}
          />
          {url.includes("{{") && (
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0 flex items-center px-3 font-mono text-[13px]"
            >
              <span className="truncate">
                {url.split(/(\{\{[^}]*\}\})/).map((part, i) =>
                  /^\{\{[^}]*\}\}$/.test(part) ? (
                    <span key={i} className="rounded-sm bg-cobweb-500/15 px-0.5 text-cobweb-400">{part}</span>
                  ) : (
                    <span key={i} className="text-neutral-100">{part}</span>
                  ),
                )}
              </span>
            </div>
          )}
          {/* Template variable autocomplete dropdown */}
          {autocompleteOpen && autocompleteItems.length > 0 && (
            <div className="absolute left-0 top-full z-50 mt-1 w-72 rounded-md border border-neutral-700 bg-neutral-900 py-1 shadow-xl">
              <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
                Variables {varPrefix && <span className="normal-case text-neutral-600">matching &ldquo;{varPrefix}&rdquo;</span>}
              </p>
              {autocompleteItems.slice(0, 10).map((item, i) => (
                <button
                  key={item.name}
                  type="button"
                  onMouseDown={(e) => { e.preventDefault(); insertAutocomplete(item.name); }}
                  className={`flex w-full items-center justify-between px-3 py-1.5 text-left text-xs transition ${
                    i === autocompleteIdx ? "bg-cobweb-600/20 text-cobweb-300" : "text-neutral-300 hover:bg-neutral-800"
                  }`}
                >
                  <span className="font-mono">{`{{${item.name}}}`}</span>
                  <span className="ml-2 truncate text-[10px] text-neutral-500">{item.label}</span>
                </button>
              ))}
            </div>
          )}
          {/* URL history suggestions */}
          {urlSuggestOpen && urlSuggestions.length > 0 && !autocompleteOpen && (
            <div className="absolute left-0 top-full z-50 mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 py-1 shadow-xl">
              <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">Recent URLs</p>
              {urlSuggestions.map((u, i) => (
                <button
                  key={u}
                  type="button"
                  onMouseDown={(e) => { e.preventDefault(); onUrlChange(u); setUrlSuggestOpen(false); }}
                  className={`flex w-full items-center px-3 py-1.5 text-left font-mono text-xs transition ${
                    i === urlSuggestIdx ? "bg-cobweb-600/20 text-cobweb-300" : "text-neutral-400 hover:bg-neutral-800"
                  }`}
                >
                  <span className="truncate">{u}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Save button group */}
      <div className="inline-flex items-stretch overflow-hidden rounded-lg border border-neutral-800/60 bg-neutral-900/40 shadow-inner-glow">
        <button
          type="button"
          onClick={onSave}
          disabled={url.length === 0}
          title={dirty ? "Save (⌘S)" : "Saved"}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium hover:bg-white/[0.04] disabled:cursor-not-allowed disabled:opacity-40 ${
            dirty && url.length > 0
              ? "text-neutral-200"
              : "text-neutral-500"
          }`}
        >
          <Save className="h-3.5 w-3.5" />
          Save
          {dirty && url.length > 0 && (
            <span className="ml-0.5 h-1.5 w-1.5 rounded-full bg-cobweb-400 shadow-[0_0_4px_rgba(34,211,238,0.5)]" aria-label="unsaved" />
          )}
        </button>
        <button
          type="button"
          onClick={onSaveAs}
          disabled={url.length === 0}
          title="Save to\u2026 (\u2318\u21E7S)"
          className="border-l border-neutral-800/60 px-1.5 text-neutral-500 hover:bg-white/[0.04] hover:text-neutral-300 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Copy as cURL */}
      <button
        type="button"
        onClick={() => {
          onCopyAsCurl();
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
        disabled={url.length === 0}
        title="Copy as cURL"
        className="inline-flex items-center gap-1.5 rounded-lg border border-neutral-800/60 bg-neutral-900/40 px-3 py-1.5 text-xs text-neutral-400 shadow-inner-glow hover:border-neutral-700 hover:text-neutral-200 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <ClipboardCopy className="h-3.5 w-3.5" />
        {copied ? "Copied!" : "cURL"}
      </button>

      {/* Copy as shareable text */}
      {onCopyShareable && (
        <button
          type="button"
          onClick={onCopyShareable}
          disabled={url.length === 0}
          title="Copy as shareable text"
          className="inline-flex items-center gap-1.5 rounded-lg border border-neutral-800/60 bg-neutral-900/40 px-2 py-1.5 text-xs text-neutral-400 shadow-inner-glow hover:border-neutral-700 hover:text-neutral-200 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Share
        </button>
      )}

      {/* Environment quick switcher */}
      {environments && environments.length > 0 && onEnvChange && (
        <Tooltip content="Active environment" side="bottom">
          <div className="relative inline-flex items-stretch overflow-hidden rounded-lg border border-neutral-800/60 bg-neutral-900/40 shadow-inner-glow">
            <Globe className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-neutral-500" />
            <select
              value={activeEnvId ?? ""}
              onChange={(e) => onEnvChange(e.target.value || null)}
              className="appearance-none bg-transparent py-1.5 pl-7 pr-6 text-xs text-neutral-300 focus:outline-none"
            >
              <option value="" className="bg-neutral-900">No environment</option>
              {environments.map((env) => (
                <option key={env.id} value={env.id} className="bg-neutral-900">
                  {env.name}
                </option>
              ))}
            </select>
            <span className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 text-[10px] text-neutral-600">&#x25BE;</span>
          </div>
        </Tooltip>
      )}

      {/* Send / Cancel button — hero action */}
      {busy && onCancel ? (
        <button
          type="button"
          onClick={onCancel}
          className="relative inline-flex items-center gap-2 overflow-hidden rounded-xl bg-rose-600/80 px-6 py-2.5 text-sm font-semibold tracking-wide text-white shadow-glow-emerald transition-all duration-200 hover:bg-rose-600 hover:scale-[1.03] active:scale-[0.97]"
        >
          <XCircle className="h-4 w-4" />
          Cancel
        </button>
      ) : (
        <button
          type="button"
          onClick={onSend}
          disabled={!canSend}
          className={`relative inline-flex items-center gap-2 overflow-hidden rounded-xl px-6 py-2.5 text-sm font-semibold tracking-wide text-white transition-all duration-200 disabled:cursor-not-allowed disabled:bg-neutral-800 disabled:text-neutral-500 disabled:shadow-none ${
            canSend
              ? "bg-accent-gradient shadow-glow-emerald hover:shadow-glow hover:scale-[1.03] active:scale-[0.97]"
              : ""
          } ${
            sendFlash === "ok"
              ? "ring-2 ring-emerald-400/60"
              : sendFlash === "err"
              ? "ring-2 ring-rose-400/60"
              : ""
          }`}
        >
          {sendFlash === "ok" ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-300" />
          ) : sendFlash === "err" ? (
            <XCircle className="h-4 w-4 text-rose-300" />
          ) : (
            <Send className="h-4 w-4" />
          )}
          Send
        </button>
      )}
    </div>
    {url.includes("{{") && (
      <div className="flex items-center gap-2 px-4 pb-1.5 -mt-1">
        {resolvedUrl && (
          <p className="flex-1 truncate font-mono text-[10px] text-neutral-600" title={resolvedUrl}>
            <span className="text-neutral-500">→</span> {resolvedUrl}
          </p>
        )}
        <TemplateValidationIndicator template={url} />
        <TemplatePreviewButton
          template={url}
          variables={Object.fromEntries([...globalVars, ...envVars].map(v => [v.name, v.value]))}
        />
      </div>
    )}
    {!url.includes("{{") && resolvedUrl && (
      <div className="px-4 pb-1.5 -mt-1">
        <p className="truncate font-mono text-[10px] text-neutral-600" title={resolvedUrl}>
          <span className="text-neutral-500">→</span> {resolvedUrl}
        </p>
      </div>
    )}
    </div>
  );
}
