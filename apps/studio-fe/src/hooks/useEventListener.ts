/**
 * useEventListener — subscribe to a Tauri event channel.
 *
 * Wraps Tauri's `listen()` API and cleans up the listener on unmount.
 * Falls back gracefully when running outside of a Tauri WebView (e.g. in
 * Playwright / vitest / browser dev mode).
 *
 * Usage:
 *   useEventListener<TheridionEventPayload>("theridion://event", (payload) => {
 *     console.log(payload.event_type);
 *   });
 */

import { useEffect, useRef } from "react";

// Minimal Tauri event typings — we avoid importing the full SDK bundle so
// the hook can be unit-tested without the native bridge.
type UnlistenFn = () => void;

export function useEventListener<T>(
  event: string,
  handler: (payload: T) => void
): void {
  // Keep a stable reference to handler so the effect doesn't re-run on every
  // render when the caller passes an inline callback.
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    let cancelled = false;
    let unlisten: UnlistenFn | null = null;

    async function subscribe() {
      try {
        // Dynamic import — works inside Tauri, fails gracefully outside.
        const tauriEvent = await import("@tauri-apps/api/event");
        if (cancelled) return;
        unlisten = await tauriEvent.listen<T>(event, (e) => {
          handlerRef.current(e.payload);
        });
      } catch {
        // Not running inside Tauri (browser dev / tests) — no-op.
      }
    }

    void subscribe();

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [event]);
}
