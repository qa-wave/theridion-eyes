import { useEffect, useRef, useState } from "react";
import { Check, Globe, Info, Keyboard, Loader2, Monitor, Plus, Radio, Server, Settings2, Sparkles, Trash2, X } from "lucide-react";
import { sidecar } from "../lib/sidecar";
import { pingHub } from "../lib/sidecar/hub";
import { THEMES, applyTheme, loadTheme, type ThemeId } from "../state/theme";
import { useFocusTrap } from "../hooks/useFocusTrap";

type Tab = "general" | "ai" | "editor" | "proxy" | "hub" | "shortcuts" | "about";

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "general", label: "General", icon: <Settings2 className="h-3.5 w-3.5" /> },
  { id: "ai", label: "AI", icon: <Sparkles className="h-3.5 w-3.5" /> },
  { id: "editor", label: "Editor", icon: <Monitor className="h-3.5 w-3.5" /> },
  { id: "proxy", label: "Proxy", icon: <Radio className="h-3.5 w-3.5" /> },
  { id: "hub", label: "Hub", icon: <Server className="h-3.5 w-3.5" /> },
  { id: "shortcuts", label: "Shortcuts", icon: <Keyboard className="h-3.5 w-3.5" /> },
  { id: "about", label: "About", icon: <Info className="h-3.5 w-3.5" /> },
];

interface Props { open: boolean; onClose: () => void; }

export function SettingsModal({ open, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("general");
  const trapRef = useRef<HTMLDivElement>(null);
  useFocusTrap(trapRef, open);

  // AI settings
  const [provider, setProvider] = useState("ollama");
  const [ollamaUrl, setOllamaUrl] = useState("http://localhost:11434");
  const [ollamaModel, setOllamaModel] = useState("llama3.2");
  const [models, setModels] = useState<Array<{ name: string }>>([]);
  const [pingResult, setPingResult] = useState<{ ok: boolean; version?: string; error?: string } | null>(null);

  // General
  const [theme, setTheme] = useState<ThemeId>(loadTheme);
  const [timeout, setTimeout_] = useState(30);
  const [followRedirects, setFollowRedirects] = useState(true);
  const [http2, setHttp2] = useState(true);

  // Hub
  const [hubUrl, setHubUrl] = useState("");
  const [hubToken, setHubToken] = useState("");
  const [hubPingResult, setHubPingResult] = useState<{ ok: boolean; version?: string; error?: string } | null>(null);
  const [hubPinging, setHubPinging] = useState(false);

  // Editor
  const [fontSize, setFontSize] = useState(12);
  const [wordWrap, setWordWrap] = useState(true);
  const [minimap, setMinimap] = useState(false);
  const [lineNumbers, setLineNumbers] = useState(true);

  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!open) return;
    sidecar.aiSettings().then((s) => {
      setProvider(s.provider);
      setOllamaUrl(s.ollama_base_url);
      setOllamaModel(s.ollama_model);
    }).catch(() => {});
    // Load Hub config from localStorage
    try {
      const raw = window.localStorage.getItem("theridion.hubConfig");
      if (raw) {
        const parsed = JSON.parse(raw) as { url?: string; token?: string };
        setHubUrl(parsed.url ?? "");
        setHubToken(parsed.token ?? "");
      }
    } catch { /* ignore */ }
  }, [open]);

  async function save() {
    setBusy(true);
    try {
      await sidecar.updateAiSettings({ provider, ollama_base_url: ollamaUrl, ollama_model: ollamaModel });
      applyTheme(theme);
      // Persist Hub config
      window.localStorage.setItem("theridion.hubConfig", JSON.stringify({ url: hubUrl.trim(), token: hubToken.trim() }));
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } catch { /* ignore */ }
    finally { setBusy(false); }
  }

  async function testConnection() {
    setPingResult(null);
    const res = await sidecar.aiPing();
    setPingResult(res);
  }

  async function testHubConnection() {
    if (!hubUrl.trim() || !hubToken.trim()) return;
    setHubPinging(true);
    setHubPingResult(null);
    try {
      const res = await pingHub({ url: hubUrl.trim(), token: hubToken.trim() });
      setHubPingResult({ ok: true, version: res.version });
    } catch (e) {
      setHubPingResult({ ok: false, error: e instanceof Error ? e.message : "Connection failed" });
    } finally {
      setHubPinging(false);
    }
  }

  async function loadModels() {
    try {
      const res = await sidecar.aiModels();
      setModels(res.models);
      if (res.models.length > 0 && !res.models.some((m) => m.name === ollamaModel)) setOllamaModel(res.models[0].name);
    } catch { /* ignore */ }
  }

  if (!open) return null;

  const inputClass = "w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none";
  const labelClass = "mb-1 block text-[10px] uppercase tracking-widest text-neutral-500";
  const checkClass = "h-3.5 w-3.5 cursor-pointer accent-cobweb-500";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div ref={trapRef} className="glass flex h-[540px] w-[680px] max-h-[90vh] max-w-[95vw] animate-slide-in overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        {/* Left nav */}
        <div className="flex w-48 shrink-0 flex-col border-r border-glass bg-neutral-950/40">
          <div className="border-b border-glass px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
              <Settings2 className="h-4 w-4 text-cobweb-400" /> Settings
            </div>
          </div>
          <div className="flex-1 overflow-y-auto py-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`flex w-full items-center gap-2.5 px-4 py-2 text-left text-xs transition ${
                  tab === t.id ? "bg-white/[0.05] text-neutral-100" : "text-neutral-400 hover:bg-white/[0.03] hover:text-neutral-200"
                }`}
              >
                {t.icon} {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Right content */}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-glass px-4 py-3">
            <span className="text-xs font-semibold uppercase tracking-widest text-neutral-400">
              {TABS.find((t) => t.id === tab)?.label}
            </span>
            <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4">
            {/* ---- General ---- */}
            {tab === "general" && (
              <div className="space-y-5">
                <Section title="Theme">
                  <div className="grid grid-cols-3 gap-2">
                    {THEMES.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => { setTheme(t.id); applyTheme(t.id); }}
                        className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-xs transition ${
                          theme === t.id ? "border-cobweb-500/40 bg-cobweb-950/20 text-cobweb-200" : "border-glass text-neutral-400 hover:border-glass-light hover:text-neutral-200"
                        }`}
                      >
                        <span className={`inline-block h-3 w-3 rounded-full ${t.dot}`} />
                        {t.label}
                      </button>
                    ))}
                  </div>
                </Section>

                <Section title="Request Defaults">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className={labelClass}>Timeout (seconds)</label>
                      <input type="number" value={timeout} onChange={(e) => setTimeout_(Number(e.target.value))} min={1} max={300} className={inputClass} />
                    </div>
                    <div className="space-y-2 pt-5">
                      <label className="flex items-center gap-2 text-xs text-neutral-300">
                        <input type="checkbox" checked={followRedirects} onChange={(e) => setFollowRedirects(e.target.checked)} className={checkClass} />
                        Follow redirects
                      </label>
                      <label className="flex items-center gap-2 text-xs text-neutral-300">
                        <input type="checkbox" checked={http2} onChange={(e) => setHttp2(e.target.checked)} className={checkClass} />
                        Enable HTTP/2
                      </label>
                    </div>
                  </div>
                </Section>

                <Section title="Global Variables">
                  <GlobalVarsEditor />
                </Section>

                <Section title="Data">
                  <p className="text-[11px] text-neutral-500">
                    Data is stored locally at <span className="font-mono text-cobweb-400">~/.theridion/</span>
                  </p>
                </Section>
              </div>
            )}

            {/* ---- AI ---- */}
            {tab === "ai" && (
              <div className="space-y-4">
                <Section title="Provider">
                  <select
                    data-testid="ai-provider-select"
                    value={provider} onChange={(e) => setProvider(e.target.value)}
                    className="rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 focus:outline-none">
                    <option value="ollama">Ollama (local, private)</option>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                  </select>
                </Section>

                {provider === "ollama" && (
                  <>
                    <Section title="Ollama Base URL">
                      <div className="flex gap-2">
                        <input value={ollamaUrl} onChange={(e) => setOllamaUrl(e.target.value)} className={inputClass} />
                        <button type="button" onClick={testConnection}
                          className="shrink-0 rounded-md border border-glass px-3 py-1.5 text-xs text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200">
                          Ping
                        </button>
                      </div>
                      {pingResult && (
                        <p className={`mt-1 text-[11px] ${pingResult.ok ? "text-emerald-400" : "text-rose-400"}`}>
                          {pingResult.ok ? `Connected (v${pingResult.version})` : pingResult.error}
                        </p>
                      )}
                    </Section>
                    <Section title="Model">
                      <div className="flex gap-2">
                        <select value={ollamaModel} onChange={(e) => setOllamaModel(e.target.value)}
                          className="flex-1 rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 focus:outline-none">
                          {models.length === 0 ? (
                            <option value={ollamaModel}>{ollamaModel}</option>
                          ) : models.map((m) => (
                            <option key={m.name} value={m.name}>{m.name}</option>
                          ))}
                        </select>
                        <button type="button" onClick={loadModels}
                          className="shrink-0 rounded-md border border-glass px-3 py-1.5 text-xs text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200">
                          Refresh
                        </button>
                      </div>
                    </Section>
                  </>
                )}

                <div className="rounded-md border border-glass bg-neutral-900/20 px-3 py-2 text-[11px] text-neutral-500">
                  Ollama runs locally — your data never leaves your machine.
                  Cloud providers send request/response data to external servers.
                </div>
              </div>
            )}

            {/* ---- Editor ---- */}
            {tab === "editor" && (
              <div className="space-y-4">
                <Section title="Font Size">
                  <input type="number" value={fontSize} onChange={(e) => setFontSize(Number(e.target.value))} min={8} max={24} className="w-20 rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 focus:outline-none" />
                  <span className="ml-2 text-xs text-neutral-500">px</span>
                </Section>
                <Section title="Options">
                  <div className="space-y-2">
                    <label className="flex items-center gap-2 text-xs text-neutral-300">
                      <input type="checkbox" checked={wordWrap} onChange={(e) => setWordWrap(e.target.checked)} className={checkClass} />
                      Word wrap
                    </label>
                    <label className="flex items-center gap-2 text-xs text-neutral-300">
                      <input type="checkbox" checked={minimap} onChange={(e) => setMinimap(e.target.checked)} className={checkClass} />
                      Show minimap
                    </label>
                    <label className="flex items-center gap-2 text-xs text-neutral-300">
                      <input type="checkbox" checked={lineNumbers} onChange={(e) => setLineNumbers(e.target.checked)} className={checkClass} />
                      Show line numbers
                    </label>
                  </div>
                </Section>
              </div>
            )}

            {/* ---- Proxy ---- */}
            {tab === "proxy" && (
              <div className="space-y-4">
                <Section title="HTTP Proxy">
                  <p className="text-[11px] text-neutral-500">
                    Configure an upstream proxy for all outgoing requests.
                  </p>
                  <div className="mt-2">
                    <label className={labelClass}>Proxy URL (optional)</label>
                    <input placeholder="http://proxy.corp:8080" className={inputClass} />
                  </div>
                  <label className="mt-2 flex items-center gap-2 text-xs text-neutral-300">
                    <input type="checkbox" className={checkClass} />
                    Bypass proxy for localhost
                  </label>
                </Section>
                <Section title="SSL / TLS">
                  <label className="flex items-center gap-2 text-xs text-neutral-300">
                    <input type="checkbox" defaultChecked className={checkClass} />
                    Verify SSL certificates
                  </label>
                  <div className="mt-2">
                    <label className={labelClass}>CA Bundle (optional)</label>
                    <input placeholder="/path/to/ca-bundle.crt" className={inputClass} />
                  </div>
                </Section>
              </div>
            )}

            {/* ---- Hub ---- */}
            {tab === "hub" && (
              <div className="space-y-4">
                <Section title="Theridion Hub">
                  <p className="mb-3 text-[11px] text-neutral-500">
                    Connect to a running Theridion Hub instance to see run trends, incidents and quality gate statuses in Studio.
                  </p>
                  <div className="space-y-3">
                    <div>
                      <label className={labelClass}>Hub URL</label>
                      <input
                        data-testid="hub-url-input"
                        value={hubUrl}
                        onChange={(e) => setHubUrl(e.target.value)}
                        placeholder="https://hub.theridion.dev"
                        className={inputClass}
                        spellCheck={false}
                      />
                    </div>
                    <div>
                      <label className={labelClass}>Ingest Token</label>
                      <input
                        data-testid="hub-token-input"
                        type="password"
                        value={hubToken}
                        onChange={(e) => setHubToken(e.target.value)}
                        placeholder="••••••••••••••••"
                        className={inputClass}
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        data-testid="hub-test-connection"
                        onClick={() => void testHubConnection()}
                        disabled={hubPinging || !hubUrl.trim() || !hubToken.trim()}
                        className="inline-flex items-center gap-1.5 rounded-md border border-glass px-3 py-1.5 text-xs text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200 disabled:opacity-40"
                      >
                        {hubPinging ? <Loader2 className="h-3 w-3 animate-spin" /> : "Test connection"}
                      </button>
                      {hubPingResult && (
                        <p className={`text-[11px] ${hubPingResult.ok ? "text-emerald-400" : "text-rose-400"}`}>
                          {hubPingResult.ok ? `Connected (v${hubPingResult.version})` : hubPingResult.error}
                        </p>
                      )}
                    </div>
                  </div>
                </Section>
                <div className="rounded-md border border-glass bg-neutral-900/20 px-3 py-2 text-[11px] text-neutral-500">
                  The Hub token is stored locally in your browser. It is never sent to any server other than the Hub URL above.
                </div>
              </div>
            )}

            {/* ---- Shortcuts ---- */}
            {tab === "shortcuts" && (
              <div className="space-y-1">
                <Shortcut keys="⌘ Enter" action="Send request" />
                <Shortcut keys="⌘ S" action="Save request" />
                <Shortcut keys="⌘ ⇧ S" action="Save As..." />
                <Shortcut keys="⌘ T" action="New tab" />
                <Shortcut keys="⌘ W" action="Close tab" />
                <Shortcut keys="⌘ K" action="Command palette" />
                <Shortcut keys="⌘ ," action="Settings" />
                <Shortcut keys="Esc" action="Close modal / cancel" />
              </div>
            )}

            {/* ---- About ---- */}
            {tab === "about" && (
              <div className="space-y-4">
                <div className="text-center">
                  <h2 className="text-lg font-bold text-gradient">Theridion</h2>
                  <p className="mt-1 text-xs text-neutral-500">Modern API testing platform</p>
                  <p className="mt-0.5 font-mono text-[11px] text-neutral-600">v0.0.1</p>
                </div>
                <div className="rounded-md border border-glass bg-neutral-900/20 px-3 py-2 text-[11px] text-neutral-500">
                  <p>Bruno UI/file-based ops + SoapUI WS-* strength + Playwright-style test runner.</p>
                  <p className="mt-1">Protocols: REST, GraphQL, WebSocket, SOAP, Kafka, gRPC</p>
                  <p className="mt-1">Stack: Tauri 2 + React 18 + Python FastAPI</p>
                </div>
                <div className="text-center">
                  <p className="text-[10px] text-neutral-600">
                    Named after the <em>Theridion</em> genus of cobweb spiders — a metaphor for tangled API dependencies.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex justify-end gap-2 border-t border-glass px-4 py-3">
            <button type="button" onClick={onClose} className="rounded-md border border-glass px-3 py-1.5 text-xs text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200">
              Cancel
            </button>
            <button type="button" onClick={save} disabled={busy}
              className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none">
              {saved ? <><Check className="h-3.5 w-3.5" /> Saved</> : busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-neutral-500">{title}</p>
      {children}
    </div>
  );
}

function Shortcut({ keys, action }: { keys: string; action: string }) {
  return (
    <div className="flex items-center justify-between rounded-md px-2 py-1.5 text-xs hover:bg-white/[0.02]">
      <span className="text-neutral-300">{action}</span>
      <kbd className="rounded-md border border-glass bg-neutral-900/50 px-2 py-0.5 font-mono text-[10px] text-neutral-400 shadow-inner-glow">
        {keys}
      </kbd>
    </div>
  );
}

interface GlobalVar {
  name: string;
  value: string;
  enabled: boolean;
}

function GlobalVarsEditor() {
  const [vars, setVars] = useState<GlobalVar[]>([]);
  const [loading, setLoading] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState(false);

  useEffect(() => {
    setLoading(true);
    sidecar
      .getGlobals()
      .then((res) => setVars(res.variables))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  function update(idx: number, field: keyof GlobalVar, val: string | boolean) {
    setVars((prev) => prev.map((v, i) => (i === idx ? { ...v, [field]: val } : v)));
    setDirty(true);
  }

  function add() {
    setVars((prev) => [...prev, { name: "", value: "", enabled: true }]);
    setDirty(true);
  }

  function remove(idx: number) {
    setVars((prev) => prev.filter((_, i) => i !== idx));
    setDirty(true);
  }

  async function save() {
    setSaving(true);
    try {
      const res = await sidecar.putGlobals(vars);
      setVars(res.variables);
      setDirty(false);
      setSavedMsg(true);
      setTimeout(() => setSavedMsg(false), 1500);
    } catch {
      /* ignore */
    } finally {
      setSaving(false);
    }
  }

  const inputClass =
    "w-full rounded-md border border-glass bg-neutral-900/50 px-2 py-1 text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none";
  const checkClass = "h-3.5 w-3.5 cursor-pointer accent-cobweb-500";

  if (loading) {
    return <p className="text-[11px] text-neutral-500">Loading...</p>;
  }

  return (
    <div className="space-y-2">
      <p className="text-[11px] text-neutral-500">
        <Globe className="mr-1 inline h-3 w-3" />
        Variables available in all requests, lowest priority in the resolution chain.
      </p>
      {vars.length > 0 && (
        <div className="overflow-hidden rounded border border-glass">
          <table className="w-full text-xs">
            <thead className="bg-neutral-900/60 text-neutral-500">
              <tr>
                <th className="w-6 px-2 py-1 text-center font-medium">On</th>
                <th className="px-2 py-1 text-left font-medium">Name</th>
                <th className="px-2 py-1 text-left font-medium">Value</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {vars.map((v, idx) => (
                <tr key={idx} className="border-t border-glass">
                  <td className="px-2 py-1 text-center">
                    <input
                      type="checkbox"
                      checked={v.enabled}
                      onChange={(e) => update(idx, "enabled", e.target.checked)}
                      className={checkClass}
                    />
                  </td>
                  <td className="px-1 py-1">
                    <input
                      value={v.name}
                      onChange={(e) => update(idx, "name", e.target.value)}
                      placeholder="name"
                      className={inputClass}
                      spellCheck={false}
                    />
                  </td>
                  <td className="px-1 py-1">
                    <input
                      value={v.value}
                      onChange={(e) => update(idx, "value", e.target.value)}
                      placeholder="value"
                      className={inputClass}
                      spellCheck={false}
                    />
                  </td>
                  <td className="px-1 py-1 text-center">
                    <button
                      type="button"
                      onClick={() => remove(idx)}
                      className="rounded p-0.5 text-neutral-600 transition hover:text-rose-400"
                      title="Remove"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="flex items-center gap-2">
        <button type="button" onClick={add} className="inline-flex items-center gap-1 text-xs text-cobweb-400 hover:text-cobweb-300">
          <Plus className="h-3 w-3" /> Add variable
        </button>
        {dirty && (
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="ml-auto inline-flex items-center gap-1 rounded-md border border-glass px-2 py-0.5 text-xs text-neutral-400 transition hover:bg-white/[0.04] hover:text-neutral-200 disabled:opacity-40"
          >
            {savedMsg ? (
              <><Check className="h-3 w-3 text-emerald-400" /> Saved</>
            ) : saving ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              "Save globals"
            )}
          </button>
        )}
      </div>
    </div>
  );
}
