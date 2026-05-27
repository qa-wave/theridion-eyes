import { useRef, useState, useEffect, useCallback } from "react";

interface TooltipProps {
  content: string | React.ReactNode;
  shortcut?: string;
  children: React.ReactNode;
  side?: "top" | "bottom" | "left" | "right";
}

export function Tooltip({ content, shortcut, children, side = "right" }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const triggerRef = useRef<HTMLDivElement>(null);

  const show = useCallback(() => {
    timerRef.current = setTimeout(() => setVisible(true), 300);
  }, []);

  const hide = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setVisible(false);
  }, []);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const positionClasses: Record<string, string> = {
    top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
    bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
    left: "right-full top-1/2 -translate-y-1/2 mr-2",
    right: "left-full top-1/2 -translate-y-1/2 ml-2",
  };

  const arrowClasses: Record<string, string> = {
    top: "top-full left-1/2 -translate-x-1/2 border-t-neutral-800 border-x-transparent border-b-transparent border-4",
    bottom: "bottom-full left-1/2 -translate-x-1/2 border-b-neutral-800 border-x-transparent border-t-transparent border-4",
    left: "left-full top-1/2 -translate-y-1/2 border-l-neutral-800 border-y-transparent border-r-transparent border-4",
    right: "right-full top-1/2 -translate-y-1/2 border-r-neutral-800 border-y-transparent border-l-transparent border-4",
  };

  return (
    <div ref={triggerRef} className="relative inline-flex" onMouseEnter={show} onMouseLeave={hide}>
      {children}
      {visible && (
        <div
          className={`tooltip-enter pointer-events-none absolute z-50 whitespace-nowrap rounded-md border border-glass bg-neutral-800/95 px-2.5 py-1.5 text-xs font-medium text-neutral-100 shadow-lg backdrop-blur ${positionClasses[side]}`}
        >
          <span className={`absolute ${arrowClasses[side]}`} />
          <span className="flex items-center gap-2">
            {content}
            {shortcut && (
              <kbd className="rounded border border-neutral-700 bg-neutral-900/80 px-1 py-0.5 font-mono text-[10px] text-neutral-400">
                {shortcut}
              </kbd>
            )}
          </span>
        </div>
      )}
    </div>
  );
}
