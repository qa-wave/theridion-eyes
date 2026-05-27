import { useEffect, useState } from "react";
import { CheckCircle2, Info, XCircle } from "lucide-react";

export interface Toast {
  id: string;
  type: "success" | "error" | "info";
  message: string;
}

interface Props {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}

const ICON = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
} as const;

const TONE = {
  success: "border-emerald-600/30 bg-emerald-950/80 text-emerald-300",
  error: "border-rose-600/30 bg-rose-950/80 text-rose-300",
  info: "border-cobweb-600/30 bg-neutral-800/95 text-cobweb-300",
} as const;

const PROGRESS_COLOR = {
  success: "bg-emerald-500",
  error: "bg-rose-500",
  info: "bg-cyan-500",
} as const;

const ICON_COLOR = {
  success: "text-emerald-400",
  error: "text-rose-400",
  info: "text-cobweb-400",
} as const;

export function ToastContainer({ toasts, onDismiss }: Props) {
  // Only show the 3 most recent toasts.
  const visible = toasts.slice(-3);

  return (
    <div aria-live="polite" aria-atomic="false" className="pointer-events-none fixed bottom-14 left-1/2 z-[70] flex -translate-x-1/2 flex-col items-center gap-2">
      {visible.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: string) => void }) {
  const [exiting, setExiting] = useState(false);
  const Icon = ICON[toast.type];

  useEffect(() => {
    const fadeTimer = setTimeout(() => setExiting(true), 1800);
    const removeTimer = setTimeout(() => onDismiss(toast.id), 2000);
    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(removeTimer);
    };
  }, [toast.id, onDismiss]);

  return (
    <div
      className={`pointer-events-auto overflow-hidden rounded-lg border text-xs font-medium shadow-xl backdrop-blur ${
        TONE[toast.type]
      } ${exiting ? "toast-exit" : "toast-enter"}`}
    >
      <div className="flex items-center gap-2 px-4 py-2">
        <Icon className={`h-3.5 w-3.5 shrink-0 ${ICON_COLOR[toast.type]}`} />
        {toast.message}
      </div>
      <div
        className={`h-[2px] ${PROGRESS_COLOR[toast.type]}`}
        style={{ animation: "toast-progress 2s linear forwards" }}
      />
    </div>
  );
}
