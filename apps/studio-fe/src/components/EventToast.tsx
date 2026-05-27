/**
 * EventToast — slide-in toast for cross-module Theridion events.
 *
 * Stacks max 3 visible toasts; additional ones are queued.
 * Each toast auto-dismisses after 8 s unless the user clicks an action.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  XCircle,
  X,
} from "lucide-react";
import { useEventListener } from "../hooks/useEventListener";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TheridionEventAction {
  label: string;
  command: string;
  args: Record<string, unknown>;
}

export interface TheridionEventContext {
  request_id?: string;
  collection_id?: string;
  url?: string;
  summary?: string;
}

export interface TheridionEventData {
  version: string;
  type: string;
  source: string;
  timestamp: string;
  context: TheridionEventContext;
  actions: TheridionEventAction[];
}

export interface TheridionEventPayload {
  workspace_path: string;
  event_type: string;
  data: TheridionEventData;
}

interface EventToastItem {
  id: string;
  payload: TheridionEventPayload;
  arrivedAt: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MAX_VISIBLE = 3;
const AUTO_DISMISS_MS = 8000;

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

const TONE_CLASSES = {
  error: "border-rose-600/40 bg-rose-950/90 text-rose-200",
  success: "border-emerald-600/40 bg-emerald-950/90 text-emerald-200",
  warning: "border-amber-600/40 bg-amber-950/90 text-amber-200",
  info: "border-cobweb-600/30 bg-neutral-800/95 text-neutral-200",
} as const;

const ICON_CLASSES = {
  error: "text-rose-400",
  success: "text-emerald-400",
  warning: "text-amber-400",
  info: "text-cobweb-400",
} as const;

const PROGRESS_CLASSES = {
  error: "bg-rose-500",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  info: "bg-cyan-500",
} as const;

function TypeIcon({ type, className }: { type: string; className?: string }) {
  const tone = toneForType(type);
  if (tone === "error") return <XCircle className={className} />;
  if (tone === "success") return <CheckCircle2 className={className} />;
  if (tone === "warning") return <AlertTriangle className={className} />;
  return <Info className={className} />;
}

// ---------------------------------------------------------------------------
// Single toast item
// ---------------------------------------------------------------------------

function EventToastItem({
  item,
  onDismiss,
}: {
  item: EventToastItem;
  onDismiss: (id: string) => void;
}) {
  const [exiting, setExiting] = useState(false);
  const tone = toneForType(item.payload.event_type);
  const title = localiseType(item.payload.event_type);
  const summary = item.payload.data?.context?.summary ?? "";
  const actions = item.payload.data?.actions ?? [];

  const dismiss = useCallback(() => {
    setExiting(true);
    setTimeout(() => onDismiss(item.id), 200);
  }, [item.id, onDismiss]);

  useEffect(() => {
    const fade = setTimeout(() => setExiting(true), AUTO_DISMISS_MS - 200);
    const remove = setTimeout(() => onDismiss(item.id), AUTO_DISMISS_MS);
    return () => {
      clearTimeout(fade);
      clearTimeout(remove);
    };
  }, [item.id, onDismiss]);

  return (
    <div
      className={`pointer-events-auto w-80 overflow-hidden rounded-lg border text-xs font-medium shadow-xl backdrop-blur ${
        TONE_CLASSES[tone]
      } ${exiting ? "toast-exit" : "toast-enter"}`}
    >
      <div className="flex items-start gap-2 px-4 py-3">
        <TypeIcon
          type={item.payload.event_type}
          className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${ICON_CLASSES[tone]}`}
        />
        <div className="min-w-0 flex-1">
          <p className="font-semibold leading-tight">{title}</p>
          {summary && (
            <p className="mt-0.5 truncate text-[11px] opacity-75">{summary}</p>
          )}
          {actions.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {actions.slice(0, 2).map((a) => (
                <button
                  key={a.command}
                  className="rounded border border-current/30 px-2 py-0.5 text-[10px] font-medium opacity-80 hover:opacity-100 transition-opacity"
                  onClick={dismiss}
                  title={a.command}
                >
                  {a.label}
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          onClick={dismiss}
          className="mt-0.5 shrink-0 opacity-50 hover:opacity-100 transition-opacity"
          aria-label="Dismiss"
        >
          <X className="h-3 w-3" />
        </button>
      </div>
      <div
        className={`h-[2px] ${PROGRESS_CLASSES[tone]}`}
        style={{ animation: `toast-progress ${AUTO_DISMISS_MS}ms linear forwards` }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Container — mounts global listener, manages queue
// ---------------------------------------------------------------------------

export function EventToastContainer() {
  const [queue, setQueue] = useState<EventToastItem[]>([]);

  useEventListener<TheridionEventPayload>("theridion://event", (payload) => {
    setQueue((prev) => [
      ...prev,
      { id: crypto.randomUUID(), payload, arrivedAt: Date.now() },
    ]);
  });

  const dismiss = useCallback((id: string) => {
    setQueue((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const visible = queue.slice(-MAX_VISIBLE);

  if (visible.length === 0) return null;

  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      className="pointer-events-none fixed bottom-14 right-4 z-[75] flex flex-col items-end gap-2"
    >
      {visible.map((item) => (
        <EventToastItem key={item.id} item={item} onDismiss={dismiss} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Queue badge — count of queued (not yet visible) events
// ---------------------------------------------------------------------------

export function useEventQueue(): { count: number } {
  const countRef = useRef(0);
  const [count, setCount] = useState(0);

  useEventListener<TheridionEventPayload>("theridion://event", () => {
    countRef.current += 1;
    setCount(countRef.current);
  });

  return { count };
}
