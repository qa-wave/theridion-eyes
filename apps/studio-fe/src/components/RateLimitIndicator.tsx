import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Clock, Info, Shield } from "lucide-react";
import { sidecar } from "../lib/sidecar";

export interface RateLimitInfo {
  detected: boolean;
  limit: number | null;
  remaining: number | null;
  reset_at: string | null;
  reset_seconds: number | null;
  retry_after: number | null;
  policy: string | null;
  provider: string | null;
  percentage_used: number | null;
  headers_found: string[];
}

interface Props {
  headers: Record<string, string>;
}

export function RateLimitIndicator({ headers }: Props) {
  const [info, setInfo] = useState<RateLimitInfo | null>(null);
  const [countdown, setCountdown] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Analyze headers when they change
  useEffect(() => {
    let cancelled = false;
    async function analyze() {
      try {
        const result = await sidecar.rateLimitAnalyze(headers);
        if (!cancelled) {
          setInfo(result);
          if (result.reset_seconds && result.reset_seconds > 0) {
            setCountdown(result.reset_seconds);
          } else if (result.retry_after && result.retry_after > 0) {
            setCountdown(result.retry_after);
          } else {
            setCountdown(null);
          }
        }
      } catch {
        if (!cancelled) setInfo(null);
      }
    }
    void analyze();
    return () => { cancelled = true; };
  }, [headers]);

  // Live countdown timer
  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (countdown !== null && countdown > 0) {
      timerRef.current = setInterval(() => {
        setCountdown((prev) => {
          if (prev === null || prev <= 1) {
            if (timerRef.current) clearInterval(timerRef.current);
            return null;
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [countdown]);

  if (!info || !info.detected) return null;

  const percentUsed = info.percentage_used ?? 0;
  const isWarning = percentUsed >= 90;
  const isCritical = info.remaining !== null && info.remaining === 0;

  // Progress bar color
  const barColor = isCritical
    ? "bg-rose-500"
    : isWarning
      ? "bg-amber-500"
      : percentUsed >= 60
        ? "bg-amber-400"
        : "bg-cobweb-400";

  const barBg = "bg-neutral-800";

  return (
    <div className="flex items-center gap-2 border-b border-glass/60 px-3 py-1">
      {/* Icon + label */}
      <div className="flex items-center gap-1">
        {isWarning || isCritical ? (
          <AlertTriangle className="h-3 w-3 text-amber-400" />
        ) : (
          <Shield className="h-3 w-3 text-cobweb-400" />
        )}
        <span className="text-[10px] font-medium text-neutral-400">Rate Limit</span>
      </div>

      {/* Progress bar */}
      {info.limit !== null && info.remaining !== null && (
        <div className="flex items-center gap-1.5">
          <div className={`h-1 w-16 overflow-hidden rounded-full ${barBg}`}>
            <div
              className={`h-full rounded-full transition-all duration-300 ${barColor}`}
              style={{ width: `${Math.min(100, percentUsed)}%` }}
            />
          </div>
          <span className={`text-[10px] font-mono ${isWarning ? "text-amber-400" : isCritical ? "text-rose-400" : "text-neutral-300"}`}>
            {info.remaining}/{info.limit}
          </span>
        </div>
      )}

      {/* Warning badge */}
      {isWarning && !isCritical && (
        <span className="rounded-sm bg-amber-950/40 px-1 py-0.5 text-[9px] font-medium text-amber-400">
          LOW
        </span>
      )}
      {isCritical && (
        <span className="rounded-sm bg-rose-950/40 px-1 py-0.5 text-[9px] font-medium text-rose-400">
          EXHAUSTED
        </span>
      )}

      {/* Countdown */}
      {countdown !== null && countdown > 0 && (
        <div className="flex items-center gap-0.5 text-[10px] text-neutral-500">
          <Clock className="h-2.5 w-2.5" />
          <span className="font-mono">{formatCountdown(countdown)}</span>
        </div>
      )}

      {/* Tooltip trigger with details */}
      <RateLimitTooltip info={info} />
    </div>
  );
}

function RateLimitTooltip({ info }: { info: RateLimitInfo }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative ml-auto">
      <button
        type="button"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className="rounded p-0.5 text-neutral-600 transition hover:bg-neutral-800 hover:text-neutral-400"
      >
        <Info className="h-3 w-3" />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 w-56 rounded-md border border-neutral-700 bg-neutral-900 p-3 shadow-lg">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
            Rate Limit Details
          </p>
          <div className="space-y-1.5 text-[10px]">
            {info.provider && (
              <Row label="Provider" value={info.provider} />
            )}
            {info.limit !== null && (
              <Row label="Limit" value={String(info.limit)} />
            )}
            {info.remaining !== null && (
              <Row label="Remaining" value={String(info.remaining)} />
            )}
            {info.percentage_used !== null && (
              <Row label="Used" value={`${info.percentage_used}%`} />
            )}
            {info.reset_at && (
              <Row label="Resets at" value={new Date(info.reset_at).toLocaleTimeString()} />
            )}
            {info.retry_after !== null && (
              <Row label="Retry after" value={`${info.retry_after}s`} />
            )}
            {info.policy && (
              <Row label="Policy" value={info.policy} />
            )}
            {info.headers_found.length > 0 && (
              <div className="mt-2 border-t border-neutral-800 pt-1.5">
                <p className="text-[9px] text-neutral-600">Headers detected:</p>
                <p className="mt-0.5 font-mono text-[9px] text-neutral-500">
                  {info.headers_found.join(", ")}
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-neutral-500">{label}</span>
      <span className="font-mono text-neutral-300">{value}</span>
    </div>
  );
}

function formatCountdown(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}
