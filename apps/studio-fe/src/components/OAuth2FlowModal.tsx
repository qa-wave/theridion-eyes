import { useEffect, useRef, useState } from "react";
import {
  KeyRound, Loader2, X, ExternalLink, RefreshCw, Check, Copy,
  AlertTriangle, Server, User,
} from "lucide-react";
import {
  sidecar,
  type OAuth2AuthorizeUrlOutput,
  type OAuth2TokenOutput,
  type OAuth2ClientCredentialsOutput,
} from "../lib/sidecar";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type FlowType = "code_pkce" | "client_credentials" | "password";
type Step = "configure" | "waiting" | "result";

interface Props {
  open: boolean;
  onClose: () => void;
  onUseToken?: (token: string) => void;
  /** Initial flow type when modal opens */
  initialFlow?: FlowType;
}

interface ProviderPreset {
  label: string;
  auth_url: string;
  token_url: string;
  scope: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    label: "GitHub",
    auth_url: "https://github.com/login/oauth/authorize",
    token_url: "https://github.com/login/oauth/access_token",
    scope: "read:user repo",
  },
  {
    label: "Google",
    auth_url: "https://accounts.google.com/o/oauth2/v2/auth",
    token_url: "https://oauth2.googleapis.com/token",
    scope: "openid email profile",
  },
  {
    label: "Auth0",
    auth_url: "https://YOUR_DOMAIN.auth0.com/authorize",
    token_url: "https://YOUR_DOMAIN.auth0.com/oauth/token",
    scope: "openid profile email",
  },
  {
    label: "Okta",
    auth_url: "https://YOUR_DOMAIN.okta.com/oauth2/default/v1/authorize",
    token_url: "https://YOUR_DOMAIN.okta.com/oauth2/default/v1/token",
    scope: "openid profile email",
  },
];

const FLOW_TYPES: { value: FlowType; label: string; icon: React.ReactNode; description: string }[] = [
  {
    value: "code_pkce",
    label: "Authorization Code + PKCE",
    icon: <ExternalLink className="h-3.5 w-3.5" />,
    description: "Interactive browser login. Recommended for user-facing apps.",
  },
  {
    value: "client_credentials",
    label: "Client Credentials",
    icon: <Server className="h-3.5 w-3.5" />,
    description: "Server-to-server. No user interaction. Best for APIs and daemons.",
  },
  {
    value: "password",
    label: "Resource Owner Password",
    icon: <User className="h-3.5 w-3.5" />,
    description: "Legacy only. Deprecated in OAuth 2.1.",
  },
];

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function OAuth2FlowModal({ open, onClose, onUseToken, initialFlow = "code_pkce" }: Props) {
  const [flowType, setFlowType] = useState<FlowType>(initialFlow);
  const [step, setStep] = useState<Step>("configure");

  // Authorization Code + PKCE fields
  const [authUrl, setAuthUrl] = useState("");
  const [tokenUrl, setTokenUrl] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [scope, setScope] = useState("");
  const [redirectUri, setRedirectUri] = useState("http://localhost:9876/oauth2/callback");
  const [usePkce, setUsePkce] = useState(true);

  // Client Credentials extra fields
  const [ccTokenUrl, setCcTokenUrl] = useState("");
  const [ccClientId, setCcClientId] = useState("");
  const [ccClientSecret, setCcClientSecret] = useState("");
  const [ccScope, setCcScope] = useState("");
  const [ccAudience, setCcAudience] = useState("");
  const [ccUseBasicAuth, setCcUseBasicAuth] = useState(false);

  // Password grant fields
  const [pwTokenUrl, setPwTokenUrl] = useState("");
  const [pwClientId, setPwClientId] = useState("");
  const [pwClientSecret, setPwClientSecret] = useState("");
  const [pwScope, setPwScope] = useState("");
  const [pwUsername, setPwUsername] = useState("");
  const [pwPassword, setPwPassword] = useState("");

  // Shared result state
  const [, setAuthorizeResult] = useState<OAuth2AuthorizeUrlOutput | null>(null);
  const [tokenResult, setTokenResult] = useState<OAuth2TokenOutput | OAuth2ClientCredentialsOutput | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  if (!open) return null;

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function reset() {
    setStep("configure");
    setAuthorizeResult(null);
    setTokenResult(null);
    setError(null);
    setBusy(false);
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function applyPreset(preset: ProviderPreset) {
    setAuthUrl(preset.auth_url);
    setTokenUrl(preset.token_url);
    setScope(preset.scope);
  }

  function copyToken() {
    if (tokenResult?.access_token) {
      navigator.clipboard.writeText(tokenResult.access_token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  function handleUseToken() {
    if (tokenResult?.access_token && onUseToken) {
      onUseToken(tokenResult.access_token);
      onClose();
    }
  }

  async function handleCancel() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    try {
      await sidecar.oauth2StopCallback();
    } catch {
      // ignore
    }
    reset();
  }

  // ---------------------------------------------------------------------------
  // Authorization Code + PKCE flow
  // ---------------------------------------------------------------------------

  async function startPkceFlow() {
    if (!authUrl.trim() || !tokenUrl.trim() || !clientId.trim()) return;
    setBusy(true);
    setError(null);

    try {
      await sidecar.oauth2StartCallback(9876, 300);

      const result = await sidecar.oauth2AuthorizeUrl({
        auth_url: authUrl,
        client_id: clientId,
        redirect_uri: redirectUri,
        scope,
        use_pkce: usePkce,
      });
      setAuthorizeResult(result);
      window.open(result.url, "_blank");
      setStep("waiting");
      setBusy(false);

      pollRef.current = setInterval(async () => {
        try {
          const poll = await sidecar.oauth2PollResult();
          if (poll.status === "received" && poll.code) {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            await exchangeCode(poll.code, result.code_verifier);
          } else if (poll.status === "expired" || poll.status === "not_running") {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setError("Authorization timed out or callback server stopped.");
            setStep("configure");
          } else if (poll.error) {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setError(`Authorization error: ${poll.error}`);
            setStep("configure");
          }
        } catch {
          // Ignore transient poll errors
        }
      }, 1000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  async function exchangeCode(code: string, codeVerifier: string | null) {
    setBusy(true);
    setError(null);
    try {
      const result = await sidecar.oauth2Token({
        token_url: tokenUrl,
        client_id: clientId,
        client_secret: clientSecret || undefined,
        code,
        redirect_uri: redirectUri,
        code_verifier: codeVerifier || undefined,
      });
      setTokenResult(result);
      setStep("result");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setStep("configure");
    } finally {
      setBusy(false);
    }
  }

  async function handlePkceRefresh() {
    const tr = tokenResult as OAuth2TokenOutput | null;
    if (!tr?.refresh_token) return;
    setBusy(true);
    setError(null);
    try {
      const result = await sidecar.oauth2Refresh({
        token_url: tokenUrl,
        refresh_token: tr.refresh_token,
        client_id: clientId,
        client_secret: clientSecret || undefined,
      });
      setTokenResult(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Client Credentials flow
  // ---------------------------------------------------------------------------

  async function startClientCredentialsFlow() {
    if (!ccTokenUrl.trim() || !ccClientId.trim() || !ccClientSecret.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const extraParams: Record<string, string> = {};
      if (ccAudience.trim()) extraParams["audience"] = ccAudience.trim();

      const result = await sidecar.oauth2ClientCredentials({
        token_url: ccTokenUrl,
        client_id: ccClientId,
        client_secret: ccClientSecret,
        scope: ccScope || undefined,
        extra_params: Object.keys(extraParams).length ? extraParams : undefined,
        use_basic_auth: ccUseBasicAuth,
      });
      setTokenResult(result);
      setStep("result");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Resource Owner Password flow (deprecated)
  // ---------------------------------------------------------------------------

  async function startPasswordFlow() {
    if (!pwTokenUrl.trim() || !pwClientId.trim() || !pwUsername.trim() || !pwPassword.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await sidecar.oauth2Password({
        token_url: pwTokenUrl,
        username: pwUsername,
        password: pwPassword,
        client_id: pwClientId,
        client_secret: pwClientSecret || undefined,
        scope: pwScope || undefined,
      });
      setTokenResult(result);
      setStep("result");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const currentFlow = FLOW_TYPES.find((f) => f.value === flowType)!;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[680px] w-[660px] max-h-[95vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">

        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <KeyRound className="h-4 w-4 text-cobweb-400" /> OAuth2 Authorization
          </div>
          <button
            type="button"
            onClick={() => { handleCancel(); onClose(); }}
            className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Flow type selector (only visible in configure step) */}
        {step === "configure" && (
          <div className="border-b border-glass px-4 py-3">
            <p className="mb-2 text-[11px] uppercase tracking-wider text-neutral-500">Flow Type</p>
            <div className="flex gap-2">
              {FLOW_TYPES.map((f) => (
                <button
                  key={f.value}
                  type="button"
                  onClick={() => { setFlowType(f.value); reset(); setStep("configure"); }}
                  className={[
                    "flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs transition",
                    flowType === f.value
                      ? "border-cobweb-500/50 bg-cobweb-600/20 text-cobweb-300"
                      : "border-glass bg-neutral-900/50 text-neutral-400 hover:border-neutral-600 hover:text-neutral-200",
                  ].join(" ")}
                >
                  {f.icon}
                  {f.label}
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-[11px] text-neutral-500">{currentFlow.description}</p>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">
            {error}
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-4 space-y-4">

          {/* ================================================================
              Authorization Code + PKCE — Configure
              ================================================================ */}
          {step === "configure" && flowType === "code_pkce" && (
            <>
              <div>
                <p className="mb-2 text-[11px] uppercase tracking-wider text-neutral-500">
                  Provider Templates
                </p>
                <div className="flex flex-wrap gap-2">
                  {PROVIDER_PRESETS.map((p) => (
                    <button
                      key={p.label}
                      type="button"
                      onClick={() => applyPreset(p)}
                      className="rounded-md border border-glass bg-neutral-900/50 px-2.5 py-1 text-xs text-neutral-300 transition hover:border-cobweb-500/40 hover:text-cobweb-300"
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-3">
                <Field label="Authorization URL" value={authUrl} onChange={setAuthUrl} placeholder="https://provider.com/oauth2/authorize" />
                <Field label="Token URL" value={tokenUrl} onChange={setTokenUrl} placeholder="https://provider.com/oauth2/token" />
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Client ID" value={clientId} onChange={setClientId} placeholder="your-client-id" />
                  <Field label="Client Secret (optional)" value={clientSecret} onChange={setClientSecret} placeholder="your-client-secret" type="password" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Scope" value={scope} onChange={setScope} placeholder="openid email profile" />
                  <Field label="Redirect URI" value={redirectUri} onChange={setRedirectUri} placeholder="http://localhost:9876/oauth2/callback" />
                </div>
                <label className="flex items-center gap-2 text-xs text-neutral-400 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={usePkce}
                    onChange={(e) => setUsePkce(e.target.checked)}
                    className="rounded border-neutral-600 bg-neutral-800 text-cobweb-500 focus:ring-cobweb-500/30"
                  />
                  Use PKCE (S256) — recommended for public clients
                </label>
              </div>

              <button
                type="button"
                onClick={startPkceFlow}
                disabled={busy || !authUrl.trim() || !tokenUrl.trim() || !clientId.trim()}
                className="mt-2 inline-flex items-center gap-2 rounded-md bg-cobweb-600/20 px-4 py-2 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-50"
              >
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ExternalLink className="h-3.5 w-3.5" />}
                Authorize in Browser
              </button>
            </>
          )}

          {/* ================================================================
              Client Credentials — Configure
              ================================================================ */}
          {step === "configure" && flowType === "client_credentials" && (
            <div className="space-y-3">
              <Field label="Token URL" value={ccTokenUrl} onChange={setCcTokenUrl} placeholder="https://provider.com/oauth2/token" />
              <div className="grid grid-cols-2 gap-3">
                <Field label="Client ID" value={ccClientId} onChange={setCcClientId} placeholder="your-client-id" />
                <Field label="Client Secret" value={ccClientSecret} onChange={setCcClientSecret} placeholder="your-client-secret" type="password" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Scope (optional)" value={ccScope} onChange={setCcScope} placeholder="api:read api:write" />
                <Field label="Audience (optional)" value={ccAudience} onChange={setCcAudience} placeholder="https://api.example.com" />
              </div>
              <label className="flex items-center gap-2 text-xs text-neutral-400 cursor-pointer">
                <input
                  type="checkbox"
                  checked={ccUseBasicAuth}
                  onChange={(e) => setCcUseBasicAuth(e.target.checked)}
                  className="rounded border-neutral-600 bg-neutral-800 text-cobweb-500 focus:ring-cobweb-500/30"
                />
                Send credentials as HTTP Basic Auth (RFC 6749 §2.3.1 recommended)
              </label>

              <button
                type="button"
                onClick={startClientCredentialsFlow}
                disabled={busy || !ccTokenUrl.trim() || !ccClientId.trim() || !ccClientSecret.trim()}
                className="inline-flex items-center gap-2 rounded-md bg-cobweb-600/20 px-4 py-2 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-50"
              >
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Server className="h-3.5 w-3.5" />}
                Get Token
              </button>
            </div>
          )}

          {/* ================================================================
              Resource Owner Password — Configure (with deprecation warning)
              ================================================================ */}
          {step === "configure" && flowType === "password" && (
            <div className="space-y-3">
              {/* Deprecation warning */}
              <div className="flex items-start gap-2 rounded-md border border-amber-700/30 bg-amber-950/20 px-3 py-2.5 text-xs text-amber-400">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                <div>
                  <strong>Deprecated by OAuth 2.1</strong> — The Resource Owner Password grant has been
                  removed in OAuth 2.1. It exposes user credentials directly to the client. Use
                  Authorization Code + PKCE for new integrations. This flow is provided only for
                  compatibility with legacy authorization servers.
                </div>
              </div>

              <Field label="Token URL" value={pwTokenUrl} onChange={setPwTokenUrl} placeholder="https://legacy.example.com/oauth/token" />
              <div className="grid grid-cols-2 gap-3">
                <Field label="Client ID" value={pwClientId} onChange={setPwClientId} placeholder="your-client-id" />
                <Field label="Client Secret (optional)" value={pwClientSecret} onChange={setPwClientSecret} placeholder="your-client-secret" type="password" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Username" value={pwUsername} onChange={setPwUsername} placeholder="user@example.com" />
                <Field label="Password" value={pwPassword} onChange={setPwPassword} placeholder="" type="password" />
              </div>
              <Field label="Scope (optional)" value={pwScope} onChange={setPwScope} placeholder="openid email" />

              <button
                type="button"
                onClick={startPasswordFlow}
                disabled={busy || !pwTokenUrl.trim() || !pwClientId.trim() || !pwUsername.trim() || !pwPassword.trim()}
                className="inline-flex items-center gap-2 rounded-md bg-amber-600/20 px-4 py-2 text-xs font-medium text-amber-400 transition hover:bg-amber-600/30 disabled:opacity-50"
              >
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <User className="h-3.5 w-3.5" />}
                Get Token (legacy)
              </button>
            </div>
          )}

          {/* ================================================================
              Waiting for browser callback (PKCE only)
              ================================================================ */}
          {step === "waiting" && (
            <div className="flex flex-col items-center justify-center py-12 space-y-4">
              <Loader2 className="h-8 w-8 animate-spin text-cobweb-400" />
              <p className="text-sm text-neutral-300">Waiting for authorization...</p>
              <p className="text-xs text-neutral-500">
                Complete the login in your browser. The callback will be captured automatically.
              </p>
              <button
                type="button"
                onClick={handleCancel}
                className="mt-4 rounded-md border border-glass px-3 py-1.5 text-xs text-neutral-400 transition hover:border-neutral-600 hover:text-neutral-200"
              >
                Cancel
              </button>
            </div>
          )}

          {/* ================================================================
              Token result (all flows)
              ================================================================ */}
          {step === "result" && tokenResult && (
            <div className="space-y-4">
              <div>
                <p className="mb-1 text-[11px] uppercase tracking-wider text-neutral-500">Access Token</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded-md border border-glass bg-neutral-900/50 px-3 py-2 font-mono text-xs text-emerald-400 break-all max-h-20 overflow-y-auto">
                    {tokenResult.access_token}
                  </code>
                  <button
                    type="button"
                    onClick={copyToken}
                    className="rounded-md p-1.5 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"
                    title="Copy token"
                  >
                    {copied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3 text-xs">
                <div>
                  <p className="text-[10px] uppercase text-neutral-500">Token Type</p>
                  <p className="text-neutral-300">{tokenResult.token_type}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase text-neutral-500">Expires In</p>
                  <p className="text-neutral-300">{tokenResult.expires_in ? `${tokenResult.expires_in}s` : "N/A"}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase text-neutral-500">Scope</p>
                  <p className="text-neutral-300">{tokenResult.scope || "N/A"}</p>
                </div>
              </div>

              {"refresh_token" in tokenResult && tokenResult.refresh_token && (
                <div>
                  <p className="mb-1 text-[11px] uppercase tracking-wider text-neutral-500">Refresh Token</p>
                  <code className="block rounded-md border border-glass bg-neutral-900/50 px-3 py-2 font-mono text-xs text-neutral-400 break-all max-h-16 overflow-y-auto">
                    {tokenResult.refresh_token}
                  </code>
                </div>
              )}

              <div className="flex items-center gap-2 pt-2">
                {onUseToken && (
                  <button
                    type="button"
                    onClick={handleUseToken}
                    className="inline-flex items-center gap-2 rounded-md bg-emerald-600/20 px-3 py-1.5 text-xs font-medium text-emerald-400 transition hover:bg-emerald-600/30"
                  >
                    <Check className="h-3.5 w-3.5" />
                    Use as Bearer Token
                  </button>
                )}
                {"refresh_token" in tokenResult && tokenResult.refresh_token && flowType === "code_pkce" && (
                  <button
                    type="button"
                    onClick={handlePkceRefresh}
                    disabled={busy}
                    className="inline-flex items-center gap-2 rounded-md bg-cobweb-600/20 px-3 py-1.5 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-50"
                  >
                    {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                    Refresh Token
                  </button>
                )}
                {/* Client Credentials: re-fetch button */}
                {flowType === "client_credentials" && (
                  <button
                    type="button"
                    onClick={startClientCredentialsFlow}
                    disabled={busy}
                    className="inline-flex items-center gap-2 rounded-md bg-cobweb-600/20 px-3 py-1.5 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-50"
                  >
                    {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                    Fetch New Token
                  </button>
                )}
                <button
                  type="button"
                  onClick={reset}
                  className="rounded-md border border-glass px-3 py-1.5 text-xs text-neutral-400 transition hover:border-neutral-600 hover:text-neutral-200"
                >
                  Start Over
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal helper component
// ---------------------------------------------------------------------------

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div>
      <p className="mb-1 text-[11px] uppercase tracking-wider text-neutral-500">{label}</p>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
        spellCheck={false}
      />
    </div>
  );
}
