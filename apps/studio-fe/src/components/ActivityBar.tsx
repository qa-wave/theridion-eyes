import { Activity, MonitorPlay, Server, Zap } from "lucide-react";
import { Tooltip } from "./Tooltip";

export type AppMode = "silk" | "monitors" | "hubOverview";

// Per-mode accent colors. FE uses violet master accent.
const MODE_ACCENT: Partial<Record<AppMode, string>> = {
  silk: "#8b5cf6",     // violet-500 — Theridion FE master accent
  monitors: "#8b5cf6", // same accent
};

interface Props {
  mode: AppMode;
  onModeChange: (mode: AppMode) => void;
}

const modes: { id: AppMode; icon: typeof Zap; label: string }[] = [
  { id: "silk", icon: MonitorPlay, label: "Silk (Frontend tests)" },
  { id: "monitors", icon: Activity, label: "Test monitors" },
  { id: "hubOverview", icon: Server, label: "Hub Overview" },
];

export function ActivityBar({ mode, onModeChange }: Props) {
  return (
    <nav
      role="navigation"
      aria-label="Module switcher"
      className="flex h-full w-12 flex-col items-center border-r border-white/[0.06] bg-neutral-950 py-2 gap-1"
    >
      {modes.map((m) => {
        const active = mode === m.id;
        const Icon = m.icon;
        return (
          <Tooltip key={m.id} content={m.label} side="right">
            <button
              onClick={() => onModeChange(m.id)}
              aria-label={m.label}
              aria-current={active ? "page" : undefined}
              className={`group relative flex h-10 w-10 items-center justify-center transition-colors ${
                active
                  ? "bg-white/[0.06]"
                  : "border-l-2 border-transparent hover:bg-white/[0.04]"
              }`}
              style={active ? {
                borderLeft: `2px solid ${MODE_ACCENT[m.id] ?? "#8b5cf6"}`,
              } : undefined}
            >
              {/* Subtle glow behind icon on hover */}
              <span className="pointer-events-none absolute inset-0 rounded-lg opacity-0 transition-opacity duration-200 group-hover:opacity-100 bg-[radial-gradient(circle,rgb(var(--accent-500)/0.12)_0%,transparent_70%)]" />
              <Icon
                size={18}
                className={`relative z-10 ${active ? "text-neutral-100" : "text-neutral-500"}`}
                style={active && MODE_ACCENT[m.id] ? { color: MODE_ACCENT[m.id] } : undefined}
              />
            </button>
          </Tooltip>
        );
      })}
    </nav>
  );
}
