import { useEffect, useRef, useState } from "react";
import { Activity, Settings2 } from "lucide-react";
import type { EnvironmentSummary, HealthResponse } from "../lib/sidecar";
import { applyTheme, loadTheme } from "../state/theme";
import { envColor } from "./EnvDropdown";

interface Props {
  sidecarStatus:
    | { state: "checking" }
    | { state: "ok"; info: HealthResponse }
    | { state: "down"; error: string };
  appVersion: string;
  onOpenSettings: () => void;
  requestCount?: number;
  lastStatus?: number | null;
  networkOpen?: boolean;
  networkEntryCount?: number;
  onToggleNetwork?: () => void;
  activeEnvId?: string | null;
  environments?: EnvironmentSummary[];
  onManageEnv?: () => void;
  onToggleHistory?: () => void;
  onOpenDiagnostics?: () => void;
}

export function StatusBar({ sidecarStatus, appVersion, onOpenSettings, requestCount = 0, lastStatus = null, networkOpen = false, networkEntryCount = 0, onToggleNetwork, activeEnvId, environments = [], onManageEnv, onToggleHistory, onOpenDiagnostics }: Props) {
  const ok = sidecarStatus.state === "ok";
  const checking = sidecarStatus.state === "checking";
  const label = ok
    ? `sidecar v${sidecarStatus.info.version}`
    : checking
    ? "connecting\u2026"
    : "sidecar offline";
  const title = sidecarStatus.state === "down" ? sidecarStatus.error : undefined;

  // Apply saved theme on mount.
  useEffect(() => { applyTheme(loadTheme()); }, []);

  // Session duration tracker
  const startRef = useRef(Date.now());
  const [sessionDuration, setSessionDuration] = useState("0m");
  useEffect(() => {
    const id = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startRef.current) / 1000);
      setSessionDuration(formatUptime(elapsed));
    }, 30_000);
    return () => clearInterval(id);
  }, []);

  // Derive pass/fail counts from requestCount and lastStatus
  const passedCount = requestCount > 0 && lastStatus !== null && lastStatus < 400
    ? requestCount - (lastStatus >= 400 ? 1 : 0)
    : requestCount;
  const failedCount = requestCount - passedCount;

  return (
    <footer className="glass noise-overlay relative flex shrink-0 items-center gap-1 border-t border-glass px-2 py-1.5 text-[11px] tracking-wide">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cobweb-500/20 to-transparent" />

      {/* Sidecar status + session uptime */}
      <div
        className="stat-card !rounded-lg !px-2.5 !py-1 flex items-center gap-2 cursor-pointer transition hover:!bg-white/[0.05]"
        onClick={onOpenDiagnostics}
        role="button"
        tabIndex={0}
      >
        <span className="relative flex h-2 w-2">
          {ok && (
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-40" />
          )}
          <span
            className={`relative inline-flex h-2 w-2 rounded-full ${
              ok
                ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]"
                : checking
                  ? "animate-pulse bg-neutral-500"
                  : "bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.5)]"
            }`}
          />
        </span>
        <span className={ok ? "text-neutral-300" : "text-neutral-500"} title={title}>{label}</span>
        {ok && (
          <span className="text-neutral-600">
            &middot; {formatUptime(sidecarStatus.info.uptime_seconds)}
          </span>
        )}
        <span className="text-neutral-600">&middot; {sessionDuration}</span>
      </div>

      {/* Request stats */}
      {requestCount > 0 && (
        <div
          className="stat-card !rounded-lg !px-2.5 !py-1 flex items-center gap-2 cursor-pointer transition hover:!bg-white/[0.05]"
          onClick={onToggleHistory}
          role="button"
          tabIndex={0}
        >
          <span className="font-mono font-bold text-neutral-200">{requestCount}</span>
          <span className="text-neutral-500">req</span>
          <span className="text-neutral-700">&middot;</span>
          <span className="font-mono font-bold text-emerald-400">{passedCount}</span>
          <span className="text-emerald-500/60">&#10003;</span>
          {failedCount > 0 && (
            <>
              <span className="text-neutral-700">&middot;</span>
              <span className="font-mono font-bold text-rose-400">{failedCount}</span>
              <span className="text-rose-500/60">&#10007;</span>
            </>
          )}
          {lastStatus !== null && (
            <span
              className={`inline-flex items-center rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-bold ${
                lastStatus >= 500
                  ? "border-rose-700/40 bg-rose-500/10 text-rose-400"
                  : lastStatus >= 400
                    ? "border-amber-700/40 bg-amber-500/10 text-amber-400"
                    : lastStatus >= 300
                      ? "border-cobweb-700/40 bg-cobweb-500/10 text-cobweb-400"
                      : "border-emerald-700/40 bg-emerald-500/10 text-emerald-400"
              }`}
            >
              {lastStatus}
            </span>
          )}
        </div>
      )}

      {/* Active environment badge (#10) */}
      {(() => {
        const activeEnv = environments.find((e) => e.id === activeEnvId);
        return (
          <button
            type="button"
            onClick={onManageEnv}
            className="stat-card !rounded-lg !px-2.5 !py-1 inline-flex items-center gap-1.5 text-neutral-400 transition hover:!bg-white/[0.05] hover:text-neutral-200"
            title={activeEnv ? `Environment: ${activeEnv.name}` : "No environment selected"}
          >
            {activeEnv ? (
              <>
                <span className={`h-2 w-2 shrink-0 rounded-full ${envColor(activeEnv.name)}`} />
                <span className="text-[11px]">{activeEnv.name}</span>
              </>
            ) : (
              <span className="text-[11px] text-neutral-600">No env</span>
            )}
          </button>
        );
      })()}

      {/* Network toggle */}
      <span className="ml-auto flex items-center gap-1.5">
        {onToggleNetwork && (
          <button
            type="button"
            onClick={onToggleNetwork}
            className={`stat-card !rounded-lg !px-2.5 !py-1 inline-flex items-center gap-1.5 transition ${
              networkOpen
                ? "!bg-cobweb-500/15 !border-cobweb-500/20 text-cobweb-400"
                : "text-neutral-500 hover:!bg-white/[0.05] hover:text-neutral-300"
            }`}
            title="Network Console"
          >
            <Activity className="h-3 w-3" />
            {networkEntryCount > 0 && (
              <span className="rounded-full bg-cobweb-500/30 px-1.5 text-[9px] font-bold text-cobweb-300">
                {networkEntryCount}
              </span>
            )}
          </button>
        )}
        <button
          type="button"
          onClick={onOpenSettings}
          className="stat-card !rounded-lg !px-2 !py-1 inline-flex items-center text-neutral-500 transition hover:!bg-white/[0.05] hover:text-neutral-300"
          title="Settings"
        >
          <Settings2 className="h-3 w-3" />
        </button>
        <span className="font-mono text-[10px] text-neutral-600">
          v{appVersion}
        </span>
      </span>
    </footer>
  );
}

function formatUptime(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}
