import { useEffect, type RefObject } from "react";

/**
 * Trap keyboard focus within a container element. When active, Tab and
 * Shift+Tab cycle through focusable children, preventing focus from
 * escaping the modal.
 */
export function useFocusTrap(ref: RefObject<HTMLElement | null>, active: boolean) {
  useEffect(() => {
    if (!active || !ref.current) return;
    const el = ref.current;
    const focusable = el.querySelectorAll<HTMLElement>(
      'button, input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    function handler(e: KeyboardEvent) {
      if (e.key !== "Tab") return;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    }

    el.addEventListener("keydown", handler);
    first?.focus();
    return () => el.removeEventListener("keydown", handler);
  }, [active, ref]);
}
