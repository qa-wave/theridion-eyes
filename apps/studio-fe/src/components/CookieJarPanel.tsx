import { useCallback, useEffect, useMemo, useState } from "react";
import { Cookie, Plus, Search, Trash2, X } from "lucide-react";
import type { CookieJarEntry } from "../lib/sidecar";
import { sidecar } from "../lib/sidecar";

interface Props {
  environmentId: string | null;
  onClose: () => void;
}

const EMPTY_COOKIE: Omit<CookieJarEntry, "expires" | "httponly" | "secure" | "samesite"> & Partial<Pick<CookieJarEntry, "expires" | "httponly" | "secure" | "samesite">> = {
  name: "",
  value: "",
  domain: "",
  path: "/",
};

export function CookieJarPanel({ environmentId, onClose }: Props) {
  const [cookies, setCookies] = useState<CookieJarEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ ...EMPTY_COOKIE });
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!environmentId) {
      setCookies([]);
      return;
    }
    setLoading(true);
    try {
      const jar = await sidecar.getCookieJar(environmentId);
      setCookies(jar.cookies);
    } catch {
      setCookies([]);
    } finally {
      setLoading(false);
    }
  }, [environmentId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const filtered = useMemo(() => {
    if (!search) return cookies;
    const q = search.toLowerCase();
    return cookies.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.value.toLowerCase().includes(q) ||
        c.domain.toLowerCase().includes(q),
    );
  }, [cookies, search]);

  const domains = useMemo(() => {
    const s = new Set(cookies.map((c) => c.domain || "(no domain)"));
    return [...s].sort();
  }, [cookies]);

  const handleDelete = async (name: string) => {
    if (!environmentId) return;
    try {
      await sidecar.deleteCookie(environmentId, name);
      await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleClearAll = async () => {
    if (!environmentId) return;
    try {
      await sidecar.clearCookieJar(environmentId);
      setCookies([]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleAdd = async () => {
    if (!environmentId || !draft.name.trim()) return;
    try {
      const jar = await sidecar.setCookie(environmentId, {
        ...draft,
        name: draft.name.trim(),
      });
      setCookies(jar.cookies);
      setAdding(false);
      setDraft({ ...EMPTY_COOKIE });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (!environmentId) {
    return (
      <div className="flex h-full flex-col bg-neutral-900 rounded-lg border border-glass">
        <Header count={0} onClose={onClose} />
        <div className="flex flex-1 items-center justify-center px-6 text-center">
          <div>
            <Cookie className="mx-auto mb-3 h-8 w-8 text-neutral-600" />
            <p className="text-sm text-neutral-400">No environment selected</p>
            <p className="mt-1 text-[11px] text-neutral-600">
              Select an environment to view its cookie jar.
              Cookies are automatically captured from responses.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-neutral-900 rounded-lg border border-glass">
      <Header count={cookies.length} onClose={onClose} />

      {error && (
        <div className="flex items-center gap-2 border-b border-rose-800/30 bg-rose-950/20 px-3 py-1.5 text-[11px] text-rose-400">
          {error}
          <button type="button" onClick={() => setError(null)} className="ml-auto">
            <X className="h-3 w-3" />
          </button>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b border-glass px-3 py-1.5">
        <div className="flex flex-1 items-center gap-1.5 rounded-md border border-glass bg-neutral-950/50 px-2 py-1">
          <Search className="h-3 w-3 text-neutral-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by name, value, or domain..."
            className="flex-1 bg-transparent text-xs text-neutral-100 outline-none placeholder:text-neutral-600"
            spellCheck={false}
          />
          {search && (
            <span className="text-[10px] text-neutral-500">
              {filtered.length}/{cookies.length}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="inline-flex items-center gap-1 rounded-md border border-glass px-2 py-1 text-[11px] text-neutral-400 transition hover:bg-white/[0.06] hover:text-neutral-200"
        >
          <Plus className="h-3 w-3" /> Add
        </button>
        <button
          type="button"
          onClick={handleClearAll}
          disabled={cookies.length === 0}
          className="inline-flex items-center gap-1 rounded-md border border-glass px-2 py-1 text-[11px] text-neutral-400 transition hover:bg-rose-950/30 hover:text-rose-400 disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <Trash2 className="h-3 w-3" /> Clear All
        </button>
      </div>

      {/* Domain summary */}
      {domains.length > 1 && (
        <div className="flex items-center gap-1.5 border-b border-glass/60 px-3 py-1">
          <span className="text-[10px] text-neutral-600">Domains:</span>
          {domains.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setSearch(d === "(no domain)" ? "" : d)}
              className="rounded-full bg-neutral-800/60 px-2 py-0.5 text-[10px] text-neutral-400 transition hover:bg-neutral-700/60 hover:text-neutral-200"
            >
              {d}
            </button>
          ))}
        </div>
      )}

      {/* Add cookie row */}
      {adding && (
        <div className="flex items-center gap-2 border-b border-cobweb-500/20 bg-cobweb-950/10 px-3 py-2">
          <input
            type="text"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder="Name"
            className="w-28 rounded border border-glass bg-neutral-950/50 px-2 py-1 text-xs text-neutral-100 outline-none placeholder:text-neutral-600"
            autoFocus
            onKeyDown={(e) => { if (e.key === "Enter") void handleAdd(); if (e.key === "Escape") setAdding(false); }}
          />
          <input
            type="text"
            value={draft.value}
            onChange={(e) => setDraft({ ...draft, value: e.target.value })}
            placeholder="Value"
            className="flex-1 rounded border border-glass bg-neutral-950/50 px-2 py-1 text-xs text-neutral-100 outline-none placeholder:text-neutral-600"
            onKeyDown={(e) => { if (e.key === "Enter") void handleAdd(); if (e.key === "Escape") setAdding(false); }}
          />
          <input
            type="text"
            value={draft.domain}
            onChange={(e) => setDraft({ ...draft, domain: e.target.value })}
            placeholder="Domain"
            className="w-32 rounded border border-glass bg-neutral-950/50 px-2 py-1 text-xs text-neutral-100 outline-none placeholder:text-neutral-600"
            onKeyDown={(e) => { if (e.key === "Enter") void handleAdd(); if (e.key === "Escape") setAdding(false); }}
          />
          <input
            type="text"
            value={draft.path}
            onChange={(e) => setDraft({ ...draft, path: e.target.value })}
            placeholder="Path"
            className="w-16 rounded border border-glass bg-neutral-950/50 px-2 py-1 text-xs text-neutral-100 outline-none placeholder:text-neutral-600"
            onKeyDown={(e) => { if (e.key === "Enter") void handleAdd(); if (e.key === "Escape") setAdding(false); }}
          />
          <button
            type="button"
            onClick={() => void handleAdd()}
            disabled={!draft.name.trim()}
            className="rounded-md bg-cobweb-600/20 px-2.5 py-1 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-40"
          >
            Save
          </button>
          <button
            type="button"
            onClick={() => { setAdding(false); setDraft({ ...EMPTY_COOKIE }); }}
            className="text-neutral-500 hover:text-neutral-300"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Cookie table */}
      <div className="min-h-0 flex-1 overflow-auto">
        {loading ? (
          <div className="flex h-full items-center justify-center text-xs text-neutral-500">
            Loading...
          </div>
        ) : cookies.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center px-6 text-center">
            <Cookie className="mb-3 h-8 w-8 text-neutral-600" />
            <p className="text-sm text-neutral-400">No cookies stored</p>
            <p className="mt-1 text-[11px] text-neutral-600">
              Cookies are automatically captured from Set-Cookie response headers.
              You can also add cookies manually.
            </p>
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-neutral-925/80 text-[11px] uppercase tracking-wider text-neutral-500 backdrop-blur-md [&_tr]:border-b [&_tr]:border-cobweb-500/10">
              <tr>
                <th className="px-3 py-1.5 text-left font-medium">Name</th>
                <th className="px-3 py-1.5 text-left font-medium">Value</th>
                <th className="px-3 py-1.5 text-left font-medium">Domain</th>
                <th className="px-3 py-1.5 text-left font-medium">Path</th>
                <th className="px-3 py-1.5 text-left font-medium">Expires</th>
                <th className="px-3 py-1.5 text-center font-medium">Flags</th>
                <th className="w-8 px-2 py-1.5" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr key={`${c.name}-${c.domain}`} className="border-t border-glass/60 hover:bg-neutral-900/40 group">
                  <td className="px-3 py-1.5 font-mono text-neutral-200">{c.name}</td>
                  <td className="max-w-[200px] truncate px-3 py-1.5 font-mono text-neutral-400" title={c.value}>
                    {c.value}
                  </td>
                  <td className="px-3 py-1.5 text-neutral-400">{c.domain || "-"}</td>
                  <td className="px-3 py-1.5 text-neutral-500">{c.path}</td>
                  <td className="px-3 py-1.5 text-neutral-500">
                    {c.expires ? formatExpiry(c.expires) : "-"}
                  </td>
                  <td className="px-3 py-1.5 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {c.httponly && (
                        <span className="rounded bg-amber-950/30 px-1 py-0.5 text-[9px] text-amber-400" title="HttpOnly">
                          HO
                        </span>
                      )}
                      {c.secure && (
                        <span className="rounded bg-emerald-950/30 px-1 py-0.5 text-[9px] text-emerald-400" title="Secure">
                          S
                        </span>
                      )}
                      {c.samesite && (
                        <span className="rounded bg-cobweb-950/30 px-1 py-0.5 text-[9px] text-cobweb-400" title={`SameSite=${c.samesite}`}>
                          {c.samesite.charAt(0).toUpperCase()}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-2 py-1.5">
                    <button
                      type="button"
                      onClick={() => void handleDelete(c.name)}
                      className="opacity-0 group-hover:opacity-100 text-neutral-600 transition hover:text-rose-400"
                      title="Delete cookie"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Header({ count, onClose }: { count: number; onClose: () => void }) {
  return (
    <div className="flex items-center justify-between border-b border-glass px-3 py-2">
      <div className="flex items-center gap-2">
        <Cookie className="h-4 w-4 text-cobweb-400" />
        <span className="text-sm font-medium text-neutral-200">Cookie Jar</span>
        {count > 0 && (
          <span className="rounded-full bg-cobweb-600/20 px-2 py-0.5 text-[10px] font-medium text-cobweb-400">
            {count}
          </span>
        )}
      </div>
      <button
        type="button"
        onClick={onClose}
        className="rounded p-1 text-neutral-500 transition hover:bg-neutral-800 hover:text-neutral-300"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

function formatExpiry(expires: string): string {
  try {
    const d = new Date(expires);
    if (d.getTime() < Date.now()) return "Expired";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return expires;
  }
}
