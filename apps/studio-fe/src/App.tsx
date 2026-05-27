import { useState } from "react";
import { Activity } from "lucide-react";
import { ActivityBar, type AppMode } from "./components/ActivityBar";
import { SilkPanel } from "./components/SilkPanel";
import { HubOverviewPanel } from "./components/HubOverviewPanel";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { EmptyState } from "./components/EmptyState";

export default function App() {
  const [mode, setMode] = useState<AppMode>("silk");
  const [toast, setToast] = useState<{ type: "success" | "error" | "info"; message: string } | null>(null);

  const handleToast = (type: "success" | "error" | "info", message: string) => {
    setToast({ type, message });
    window.setTimeout(() => setToast(null), 4000);
  };

  return (
    <ErrorBoundary>
      <div className="flex h-screen w-screen flex-col bg-neutral-950 text-neutral-200">
        <div className="flex flex-1 overflow-hidden">
          <ActivityBar mode={mode} onModeChange={setMode} />
          <main className="flex-1 overflow-hidden">
            {mode === "silk" && <SilkPanel onToast={handleToast} />}
            {mode === "monitors" && (
              <EmptyState
                icon={Activity}
                title="Test monitors"
                description="Scheduled Playwright run monitoring (synthetic FE checks). Vytvoř monitor v Silk panelu přes 'Schedule run' tlačítko."
              />
            )}
            {mode === "hubOverview" && <HubOverviewPanel />}
          </main>
        </div>
        <footer className="flex h-7 items-center justify-between border-t border-white/[0.06] bg-neutral-950 px-3 text-[11px] text-neutral-500">
          <span>Theridion FE v0.0.1</span>
          <span>{mode}</span>
        </footer>
        {toast && (
          <div
            role="status"
            aria-live="polite"
            className={`pointer-events-none fixed bottom-12 left-1/2 -translate-x-1/2 rounded-md px-4 py-2 text-sm shadow-lg ${
              toast.type === "success" ? "bg-emerald-600 text-white" :
              toast.type === "error" ? "bg-rose-600 text-white" :
              "bg-violet-600 text-white"
            }`}
          >
            {toast.message}
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}
