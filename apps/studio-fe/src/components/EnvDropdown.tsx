import { useEffect, useRef, useState } from "react";
import { ChevronDown, Layers, Settings2 } from "lucide-react";
import type { EnvironmentSummary } from "../lib/sidecar";

interface Props {
  environments: EnvironmentSummary[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
  onManage: () => void;
}

const ENV_COLORS: Record<string, string> = {
  prod: "bg-rose-500",
  production: "bg-rose-500",
  staging: "bg-amber-500",
  stage: "bg-amber-500",
  dev: "bg-emerald-500",
  development: "bg-emerald-500",
  local: "bg-emerald-500",
};
const AUTO_COLORS = ["bg-sky-500", "bg-violet-500", "bg-pink-500", "bg-cyan-500", "bg-orange-500", "bg-lime-500"];

export function envColor(name: string): string {
  const lower = name.toLowerCase();
  if (ENV_COLORS[lower]) return ENV_COLORS[lower];
  // Simple hash-based assignment
  let hash = 0;
  for (let i = 0; i < lower.length; i++) hash = ((hash << 5) - hash + lower.charCodeAt(i)) | 0;
  return AUTO_COLORS[Math.abs(hash) % AUTO_COLORS.length];
}

export function EnvDropdown({ environments, activeId, onSelect, onManage }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const active = environments.find((e) => e.id === activeId) ?? null;

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    const t = window.setTimeout(
      () => window.addEventListener("mousedown", onClick),
      0,
    );
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
      window.clearTimeout(t);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] transition ${
          active
            ? "border-cobweb-700/40 bg-cobweb-950/30 text-cobweb-300 hover:border-cobweb-600/50"
            : "border-glass bg-neutral-900/40 text-neutral-400 hover:border-neutral-700/60 hover:text-neutral-200"
        }`}
        title={active ? `Active environment: ${active.name}` : "No environment"}
      >
        {active ? (
          <span className={`h-2 w-2 shrink-0 rounded-full ${envColor(active.name)}`} />
        ) : (
          <Layers className="h-3 w-3" />
        )}
        <span className="max-w-[110px] truncate">
          {active ? active.name : "No env"}
        </span>
        <ChevronDown className="h-3 w-3 opacity-60" />
      </button>
      {open && (
        <div
          role="menu"
          className="glass absolute right-0 top-full z-30 mt-1.5 w-56 animate-fade-in rounded-lg border border-glass-light shadow-xl shadow-black/50"
        >
          <div className="border-b border-glass px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
            Environment
          </div>
          <button
            type="button"
            onClick={() => { onSelect(null); setOpen(false); }}
            className={`flex w-full items-center justify-between px-3 py-1.5 text-left text-xs transition ${
              activeId === null
                ? "bg-white/[0.04] text-neutral-100"
                : "text-neutral-400 hover:bg-white/[0.03] hover:text-neutral-200"
            }`}
          >
            <span>None</span>
            {activeId === null && <span className="text-cobweb-400">&#x25CF;</span>}
          </button>
          {environments.length > 0 && (
            <div className="max-h-56 overflow-y-auto border-t border-glass">
              {environments.map((e) => (
                <button
                  key={e.id}
                  type="button"
                  onClick={() => { onSelect(e.id); setOpen(false); }}
                  className={`flex w-full items-center justify-between px-3 py-1.5 text-left text-xs transition ${
                    activeId === e.id
                      ? "bg-cobweb-950/30 text-cobweb-200"
                      : "text-neutral-400 hover:bg-white/[0.03] hover:text-neutral-200"
                  }`}
                >
                  <span className="flex items-center gap-1.5 truncate">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${envColor(e.name)}`} />
                    {e.name}
                  </span>
                  <span className="ml-2 shrink-0 text-[10px] text-neutral-600">
                    {e.variable_count} vars
                  </span>
                </button>
              ))}
            </div>
          )}
          <button
            type="button"
            onClick={() => { onManage(); setOpen(false); }}
            className="flex w-full items-center gap-2 border-t border-glass px-3 py-2 text-left text-xs text-neutral-400 transition hover:bg-white/[0.03] hover:text-neutral-200"
          >
            <Settings2 className="h-3 w-3" />
            Manage environments&hellip;
          </button>
        </div>
      )}
    </div>
  );
}
