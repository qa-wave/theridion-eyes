/**
 * EventCenter — bell-icon tray in the top bar showing the last 30 events.
 *
 * Click bell → dropdown list; click event row → action sheet.
 * Events are kept in-memory (session only) — no persistence required.
 */

import { useEffect, useRef, useState } from "react";
import {
  Bell,
  AlertTriangle,
  CheckCircle2,
  Info,
  XCircle,
  X,
  Zap,
} from "lucide-react";
import { useEventListener } from "../hooks/useEventListener";
import type {
  TheridionEventPayload,
  TheridionEventAction,
} from "./EventToast";

// ---------------------------------------------------------------------------
// Helpers (re-use same logic as EventToast)
// ---------------------------------------------------------------------------

const MAX_HISTORY = 100;

function localiseType(type: string): string {
  const map: Record<string, string> = {
    "test.failed": "Test failed",
    "test.passed": "Test passed",
    "run.completed": "Run completed",
    "incident.opened": "Incident opened",
    "incident.resolved": "Incident resolved",
    "gate.blocked": "Gate blocked",
    "gate.passed": "Gate passed",
    "scheduled.alert": "Scheduled alert",
  };
  return map[type] ?? type.replace(/[._]/g, " ");
}

function toneForType(type: string): "error" | "success" | "warning" | "info" {
  if (type.endsWith(".failed") || type.endsWith(".blocked") || type === "incident.opened")
    return "error";
  if (type.endsWith(".passed") || type.endsWith(".resolved") || type === "run.completed")
    return "success";
  if (type === "scheduled.alert") return "warning";
  return "info";
}

function TypeIcon({ type, className }: { type: string; className?: string }) {
  const tone = toneForType(type);
  if (tone === "error") return <XCircle className={className} />;
  if (tone === "success") return <CheckCircle2 className={className} />;
  if (tone === "warning") return <AlertTriangle className={className} />;
  return <Info className={className} />;
}

const DOT_CLASSES = {
  error: "bg-rose-500",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  info: "bg-cobweb-400",
} as const;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface HistoryEntry {
  id: string;
  payload: TheridionEventPayload;
  receivedAt: number;
}

interface Props {
  /** Extra className for the button wrapper. */
  className?: string;
}

// ---------------------------------------------------------------------------
// EventCenter component
// ---------------------------------------------------------------------------

export function EventCenter({ className }: Props) {
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<HistoryEntry | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEventListener<TheridionEventPayload>("theridion://event", (payload) => {
    setHistory((prev) =>
      [{ id: crypto.randomUUID(), payload, receivedAt: Date.now() }, ...prev].slice(
        0,
        MAX_HISTORY
      )
    );
    if (!open) {
      setUnread((u) => u + 1);
    }
  });

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
        setSelected(null);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  function toggleOpen() {
    setOpen((o) => {
      if (!o) setUnread(0);
      return !o;
    });
    setSelected(null);
  }

  return (
    <div className={`relative ${className ?? ""}`} ref={dropdownRef}>
      {/* Bell button */}
      <button
        onClick={toggleOpen}
        className="relative flex h-7 w-7 items-center justify-center rounded text-neutral-400 hover:bg-neutral-800 hover:text-neutral-200 transition-colors"
        title="Event Center"
        aria-label={`Event Center${unread > 0 ? ` (${unread} unread)` : ""}`}
      >
        <Bell className="h-3.5 w-3.5" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-rose-500 text-[8px] font-bold text-white leading-none">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 top-full z-[80] mt-1 w-80 rounded-xl border border-neutral-800 bg-neutral-900 shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-neutral-800 px-4 py-2.5">
            <span className="text-xs font-semibold text-neutral-200">
              Event Center
            </span>
            <div className="flex items-center gap-2">
              {history.length > 0 && (
                <button
                  onClick={() => { setHistory([]); setUnread(0); }}
                  className="text-[10px] text-neutral-500 hover:text-neutral-300 transition-colors"
                >
                  Clear all
                </button>
              )}
              <button
                onClick={() => { setOpen(false); setSelected(null); }}
                className="text-neutral-500 hover:text-neutral-300 transition-colors"
                aria-label="Close"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {/* List or detail */}
          <div className="max-h-80 overflow-y-auto">
            {selected ? (
              <ActionSheet
                entry={selected}
                onBack={() => setSelected(null)}
              />
            ) : history.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-neutral-500">
                <Zap className="mb-2 h-6 w-6 opacity-30" />
                <p className="text-xs">No events yet</p>
              </div>
            ) : (
              history.map((entry) => (
                <EventRow
                  key={entry.id}
                  entry={entry}
                  onClick={() => setSelected(entry)}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// EventRow
// ---------------------------------------------------------------------------

function EventRow({
  entry,
  onClick,
}: {
  entry: HistoryEntry;
  onClick: () => void;
}) {
  const tone = toneForType(entry.payload.event_type);
  const title = localiseType(entry.payload.event_type);
  const summary = entry.payload.data?.context?.summary ?? "";
  const relTime = formatRelTime(entry.receivedAt);

  return (
    <button
      onClick={onClick}
      className="flex w-full items-start gap-3 border-b border-neutral-800/60 px-4 py-2.5 text-left hover:bg-neutral-800/50 transition-colors last:border-b-0"
    >
      <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${DOT_CLASSES[tone]}`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[11px] font-semibold text-neutral-200">{title}</span>
          <span className="shrink-0 text-[10px] text-neutral-500">{relTime}</span>
        </div>
        {summary && (
          <p className="mt-0.5 truncate text-[10px] text-neutral-400">{summary}</p>
        )}
      </div>
      <TypeIcon
        type={entry.payload.event_type}
        className={`mt-0.5 h-3.5 w-3.5 shrink-0 opacity-60 ${
          tone === "error"
            ? "text-rose-400"
            : tone === "success"
            ? "text-emerald-400"
            : tone === "warning"
            ? "text-amber-400"
            : "text-cobweb-400"
        }`}
      />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Action sheet
// ---------------------------------------------------------------------------

function ActionSheet({
  entry,
  onBack,
}: {
  entry: HistoryEntry;
  onBack: () => void;
}) {
  const actions: TheridionEventAction[] = entry.payload.data?.actions ?? [];
  const summary = entry.payload.data?.context?.summary ?? "";
  const title = localiseType(entry.payload.event_type);

  return (
    <div className="px-4 py-3">
      <button
        onClick={onBack}
        className="mb-2 text-[10px] text-neutral-500 hover:text-neutral-300 transition-colors"
      >
        ← Back
      </button>
      <p className="mb-1 text-[11px] font-semibold text-neutral-200">{title}</p>
      {summary && (
        <p className="mb-3 text-[11px] text-neutral-400">{summary}</p>
      )}
      {actions.length === 0 ? (
        <p className="text-[10px] text-neutral-500">No actions available.</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {actions.map((a) => (
            <button
              key={a.command}
              className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-left text-[11px] text-neutral-200 hover:bg-neutral-700 hover:border-neutral-600 transition-colors"
              onClick={onBack}
              title={a.command}
            >
              {a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Util
// ---------------------------------------------------------------------------

function formatRelTime(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}
