/**
 * Sidecar HTTP client — base URL resolution + auth token management + generic call helper.
 *
 * Resolution order for the sidecar URL:
 *   1. `VITE_SIDECAR_URL` build-time env override — used by Playwright
 *      tests (which spawn their own sidecar on a non-default port) and
 *      by anyone running the app in a regular browser tab.
 *   2. Tauri command `get_sidecar_port` — when the desktop shell spawned
 *      the bundled sidecar binary, this is the source of truth. We poll
 *      it on first call and also subscribe to the `sidecar://ready`
 *      event so the resolution finishes the moment the binary is up
 *      (cold start of the --onefile bundle is ~8 s).
 *   3. Dev fallback `http://127.0.0.1:8765` — when neither of the above
 *      is available (developer running `pnpm dev` without Tauri and
 *      without VITE_SIDECAR_URL), assume a sidecar started by hand on
 *      the default dev port.
 *
 * Auth token resolution order:
 *   1. `VITE_SIDECAR_TOKEN` build-time env override — used by Playwright tests
 *      (set to the token printed by the test sidecar process).
 *   2. Tauri command `get_sidecar_token` — the token parsed from the ready line.
 *   3. null (no header sent) — dev standalone mode where no token is configured.
 */

const DEV_FALLBACK_URL = "http://127.0.0.1:8765";

interface TauriWindow extends Window {
  __TAURI_INTERNALS__?: unknown;
}

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in (window as TauriWindow);
}

let _urlPromise: Promise<string> | null = null;
let _tokenPromise: Promise<string | null> | null = null;

/** Returns the sidecar's base URL, awaiting Tauri's port handshake when needed. */
export function getSidecarBaseUrl(): Promise<string> {
  if (_urlPromise) return _urlPromise;
  _urlPromise = resolveSidecarBaseUrl();
  return _urlPromise;
}

/** Returns the X-Theridion-Token value, or null when running without auth (dev mode). */
export function getSidecarToken(): Promise<string | null> {
  if (_tokenPromise) return _tokenPromise;
  _tokenPromise = resolveSidecarToken();
  return _tokenPromise;
}

async function resolveSidecarBaseUrl(): Promise<string> {
  const fromEnv = import.meta.env.VITE_SIDECAR_URL as string | undefined;
  if (fromEnv) return fromEnv;

  if (!isTauri()) return DEV_FALLBACK_URL;

  const [{ invoke }, { listen }] = await Promise.all([
    import("@tauri-apps/api/core"),
    import("@tauri-apps/api/event"),
  ]);

  const port = await invoke<number | null>("get_sidecar_port").catch(() => null);
  if (typeof port === "number") return `http://127.0.0.1:${port}`;

  // Wait for the ready event. The sidecar's --onefile cold start can take
  // up to ~10 s; we don't impose a timeout here so the UI's "connecting…"
  // state simply lingers rather than throwing.
  return new Promise<string>((resolve) => {
    void listen<number>("sidecar://ready", (event) => {
      resolve(`http://127.0.0.1:${event.payload}`);
    });
  });
}

async function resolveSidecarToken(): Promise<string | null> {
  // Playwright / CI: token is baked into the build env.
  const fromEnv = import.meta.env.VITE_SIDECAR_TOKEN as string | undefined;
  if (fromEnv) return fromEnv;

  if (!isTauri()) {
    // Standalone dev sidecar launched without THERIDION_TOKEN — no auth header needed.
    return null;
  }

  const { invoke } = await import("@tauri-apps/api/core");
  const token = await invoke<string | null>("get_sidecar_token").catch(() => null);
  return token ?? null;
}

export interface HealthResponse {
  status: string;
  version: string;
  uptime_seconds: number;
}

export async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const [baseUrl, token] = await Promise.all([getSidecarBaseUrl(), getSidecarToken()]);
  const authHeaders: Record<string, string> = token
    ? { "X-Theridion-Token": token }
    : {};
  const res = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...authHeaders,
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail: string;
    try {
      const j = (await res.json()) as { detail?: unknown };
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j);
    } catch {
      detail = await res.text();
    }
    throw new Error(`sidecar ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}
