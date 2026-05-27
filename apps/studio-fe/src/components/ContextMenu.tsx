import { useEffect, useRef } from "react";
import { Edit, ExternalLink, Star, Trash2, Terminal, CopyPlus } from "lucide-react";

export interface ContextMenuAction {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  danger?: boolean;
}

interface Props {
  open: boolean;
  x: number;
  y: number;
  actions: ContextMenuAction[];
  onClose: () => void;
}

export function ContextMenu({ open, x, y, actions, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("mousedown", handleClick);
    window.addEventListener("keydown", handleKey);
    return () => {
      window.removeEventListener("mousedown", handleClick);
      window.removeEventListener("keydown", handleKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  // Clamp position to viewport
  const safeX = Math.min(x, window.innerWidth - 200);
  const safeY = Math.min(y, window.innerHeight - actions.length * 36 - 16);

  return (
    <div
      ref={ref}
      className="fixed z-[60] min-w-[180px] animate-slide-in rounded-lg border border-glass-light bg-neutral-900 py-1 shadow-2xl shadow-black/60"
      style={{ left: safeX, top: safeY }}
    >
      {actions.map((a, idx) => (
        <button
          key={idx}
          type="button"
          onClick={() => {
            a.onClick();
            onClose();
          }}
          className={`flex w-full items-center gap-2 px-3 py-1.5 text-xs transition hover:bg-neutral-800/60 ${
            a.danger ? "text-rose-400 hover:text-rose-300" : "text-neutral-300 hover:text-neutral-100"
          }`}
        >
          <span className="flex-shrink-0">{a.icon}</span>
          {a.label}
        </button>
      ))}
    </div>
  );
}

/** Helper to build standard sidebar context menu actions. */
export function buildSidebarActions(opts: {
  onRename?: () => void;
  onDuplicate?: () => void;
  onDelete?: () => void;
  onToggleFavorite?: () => void;
  isFavorite?: boolean;
  onCopyAsCurl?: () => void;
  onOpenInNewTab?: () => void;
}): ContextMenuAction[] {
  const actions: ContextMenuAction[] = [];
  if (opts.onOpenInNewTab) actions.push({ label: "Open in new tab", icon: <ExternalLink className="h-3.5 w-3.5" />, onClick: opts.onOpenInNewTab });
  if (opts.onRename) actions.push({ label: "Rename", icon: <Edit className="h-3.5 w-3.5" />, onClick: opts.onRename });
  if (opts.onDuplicate) actions.push({ label: "Duplicate", icon: <CopyPlus className="h-3.5 w-3.5" />, onClick: opts.onDuplicate });
  if (opts.onToggleFavorite) {
    actions.push({
      label: opts.isFavorite ? "Remove from Favorites" : "Add to Favorites",
      icon: <Star className={`h-3.5 w-3.5 ${opts.isFavorite ? "fill-amber-500 text-amber-500" : ""}`} />,
      onClick: opts.onToggleFavorite,
    });
  }
  if (opts.onCopyAsCurl) actions.push({ label: "Copy as cURL", icon: <Terminal className="h-3.5 w-3.5" />, onClick: opts.onCopyAsCurl });
  if (opts.onDelete) actions.push({ label: "Delete", icon: <Trash2 className="h-3.5 w-3.5" />, onClick: opts.onDelete, danger: true });
  return actions;
}
