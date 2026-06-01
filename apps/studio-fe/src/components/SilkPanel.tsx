/**
 * SilkPanel — Frontend testing module (Playwright runner panel v2).
 *
 * Layout:
 *   Left sidebar   — run history list (persistent + in-session)
 *   Center         — trace viewer: timeline, browser tabs, stderr
 *   Right sidebar  — spec source / network / screenshots / a11y / console
 *
 * New in v2:
 *   - Run history (loaded from sidecar DB on mount)
 *   - Record new spec (Playwright codegen integration)
 *   - Multi-browser tab switcher
 *   - A11y violations tab with impact badges
 *   - Approve baseline button in screenshot diff view
 *   - Network mocks section in run form
 *
 * Browser-demo mode:
 *   When running outside Tauri (window.__TAURI_INTERNALS__ absent) OR when
 *   the sidecar fetch fails, DEMO_REPORTS provides pre-bundled rich detail
 *   data so Timeline/Network/Screenshots/A11y tabs are all populated.
 *   The first DEMO_HISTORY run is auto-selected on load so the page is
 *   never empty.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Download,
  ExternalLink,
  FileCode,
  Globe,
  History,
  Image,
  MonitorPlay,
  Play,
  Plus,
  RefreshCw,
  Square,
  Terminal,
  Video,
  XCircle,
} from "lucide-react";
import { EmptyState } from "./EmptyState";
import { NewTestDialog } from "./NewTestDialog";
import { sidecar } from "../lib/sidecar";
import { getSidecarBaseUrl, getSidecarToken, isTauri } from "../lib/sidecar/client";
import { useT } from "../lib/i18n/context";
import type {
  SilkA11yViolation,
  SilkBrowserRunResult,
  SilkFramework,
  SilkNetworkEntry,
  SilkRunHistoryEntry,
  SilkRunOutput,
} from "../lib/sidecar/silk";

// ---------------------------------------------------------------------------
// Demo / seed data — shown when sidecar is unreachable on first launch
// ---------------------------------------------------------------------------

const _M = 60_000;
const _H = 3_600_000;
const _D = 86_400_000;

const DEMO_HISTORY: SilkRunHistoryEntry[] = [
  // ── Today ──────────────────────────────────────────────────────────────────
  {
    id: "demo-run-018",
    spec_path: "tests/auth/login.spec.ts",
    status: "passed",
    duration_ms: 6840,
    started_at: new Date(Date.now() - 12 * _M).toISOString(),
    browsers: ["chromium"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 0,
    stderr_tail: "",
  },
  {
    id: "demo-run-017",
    spec_path: "tests/a11y/homepage-axe.spec.ts",
    status: "passed",
    duration_ms: 9420,
    started_at: new Date(Date.now() - 28 * _M).toISOString(),
    browsers: ["chromium", "firefox"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 2,
    stderr_tail: "",
  },
  {
    id: "demo-run-016",
    spec_path: "tests/checkout/payment-flow.spec.ts",
    status: "failed",
    duration_ms: 18650,
    started_at: new Date(Date.now() - 55 * _M).toISOString(),
    browsers: ["chromium"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 0,
    stderr_tail:
      "  1 failed\n  ● Payment flow › completes Stripe 3DS checkout\n\n" +
      "    TimeoutError: waiting for selector '.stripe-success-banner' failed\n" +
      "    Expected: visible\n    Received: hidden after 15000ms",
  },
  // ── Yesterday ──────────────────────────────────────────────────────────────
  {
    id: "demo-run-015",
    spec_path: "tests/profile/settings.spec.ts",
    status: "passed",
    duration_ms: 11240,
    started_at: new Date(Date.now() - 1 * _D - 2 * _H).toISOString(),
    browsers: ["chromium", "webkit"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 0,
    stderr_tail: "",
  },
  {
    id: "demo-run-014",
    spec_path: "tests/dashboard/overview.spec.ts",
    status: "passed",
    duration_ms: 14380,
    started_at: new Date(Date.now() - 1 * _D - 5 * _H).toISOString(),
    browsers: ["chromium", "firefox"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 0,
    stderr_tail: "",
  },
  {
    id: "demo-run-013",
    spec_path: "tests/auth/logout.spec.ts",
    status: "passed",
    duration_ms: 5840,
    started_at: new Date(Date.now() - 1 * _D - 8 * _H).toISOString(),
    browsers: ["chromium", "firefox"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 0,
    stderr_tail: "",
  },
  // ── 2 days ago ─────────────────────────────────────────────────────────────
  {
    id: "demo-run-012",
    spec_path: "tests/checkout/payment-flow.spec.ts",
    status: "passed",
    duration_ms: 38720,
    started_at: new Date(Date.now() - 2 * _D - 1 * _H).toISOString(),
    browsers: ["chromium", "firefox", "webkit"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 0,
    stderr_tail: "",
  },
  {
    id: "demo-run-011",
    spec_path: "tests/auth/login.spec.ts",
    status: "passed",
    duration_ms: 6520,
    started_at: new Date(Date.now() - 2 * _D - 6 * _H).toISOString(),
    browsers: ["chromium"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 0,
    stderr_tail: "",
  },
  // ── 3–4 days ago ───────────────────────────────────────────────────────────
  {
    id: "demo-run-010",
    spec_path: "tests/a11y/homepage-axe.spec.ts",
    status: "passed",
    duration_ms: 8900,
    started_at: new Date(Date.now() - 3 * _D - 3 * _H).toISOString(),
    browsers: ["chromium", "firefox"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 4,
    stderr_tail: "",
  },
  {
    id: "demo-run-009",
    spec_path: "tests/dashboard/overview.spec.ts",
    status: "error",
    duration_ms: 4200,
    started_at: new Date(Date.now() - 3 * _D - 7 * _H).toISOString(),
    browsers: ["chromium"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 0,
    stderr_tail:
      "Error: net::ERR_CONNECTION_REFUSED at https://app.acmecorp.io/dashboard\n" +
      "    at navigateTo (playwright-core/lib/page.ts:98)",
  },
  {
    id: "demo-run-008",
    spec_path: "tests/profile/settings.spec.ts",
    status: "passed",
    duration_ms: 10980,
    started_at: new Date(Date.now() - 4 * _D - 2 * _H).toISOString(),
    browsers: ["chromium"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 0,
    stderr_tail: "",
  },
  // ── 5–7 days ago ───────────────────────────────────────────────────────────
  {
    id: "demo-run-007",
    spec_path: "tests/checkout/payment-flow.spec.ts",
    status: "failed",
    duration_ms: 22100,
    started_at: new Date(Date.now() - 5 * _D - 4 * _H).toISOString(),
    browsers: ["chromium", "firefox"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 0,
    stderr_tail:
      "  1 failed\n  ● Payment flow › applies promo code SAVE20 successfully\n\n" +
      "    Error: expect(received).toContainText('−20%')\n" +
      "    Expected text: '−20%'\n    Received text: 'Promo code invalid'",
  },
  {
    id: "demo-run-006",
    spec_path: "tests/auth/login.spec.ts",
    status: "passed",
    duration_ms: 7120,
    started_at: new Date(Date.now() - 5 * _D - 9 * _H).toISOString(),
    browsers: ["chromium", "firefox"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 0,
    stderr_tail: "",
  },
  {
    id: "demo-run-005",
    spec_path: "tests/dashboard/overview.spec.ts",
    status: "passed",
    duration_ms: 13640,
    started_at: new Date(Date.now() - 6 * _D - 1 * _H).toISOString(),
    browsers: ["chromium", "firefox", "webkit"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 0,
    stderr_tail: "",
  },
  {
    id: "demo-run-004",
    spec_path: "tests/auth/logout.spec.ts",
    status: "passed",
    duration_ms: 5280,
    started_at: new Date(Date.now() - 7 * _D - 2 * _H).toISOString(),
    browsers: ["chromium"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 0,
    stderr_tail: "",
  },
  // ── 10–14 days ago ─────────────────────────────────────────────────────────
  {
    id: "demo-run-003",
    spec_path: "tests/a11y/homepage-axe.spec.ts",
    status: "passed",
    duration_ms: 7620,
    started_at: new Date(Date.now() - 10 * _D - 3 * _H).toISOString(),
    browsers: ["chromium"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 1,
    stderr_tail: "",
  },
  {
    id: "demo-run-002",
    spec_path: "tests/checkout/payment-flow.spec.ts",
    status: "passed",
    duration_ms: 35480,
    started_at: new Date(Date.now() - 12 * _D - 5 * _H).toISOString(),
    browsers: ["chromium", "firefox", "webkit"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 0,
    stderr_tail: "",
  },
  {
    id: "demo-run-001",
    spec_path: "tests/auth/login.spec.ts",
    status: "passed",
    duration_ms: 5940,
    started_at: new Date(Date.now() - 14 * _D).toISOString(),
    browsers: ["chromium"],
    trace_path: null,
    screenshot_paths: [],
    a11y_violations_count: 0,
    stderr_tail: "",
  },
];

// ---------------------------------------------------------------------------
// Browser-demo mode detection
// ---------------------------------------------------------------------------

/** True when running outside Tauri without a reachable sidecar. */
let _isBrowserDemo: boolean | null = null;

function getBrowserDemoMode(): boolean {
  if (_isBrowserDemo !== null) return _isBrowserDemo;
  // Tauri is always real.
  if (isTauri()) {
    _isBrowserDemo = false;
    return false;
  }
  // Plain browser — default to demo mode; will be flipped to false on first
  // successful sidecar health response.
  _isBrowserDemo = true;
  return true;
}

/** Called when the sidecar responds successfully — disable demo mode for this session. */
function disableBrowserDemo() {
  _isBrowserDemo = false;
}

// ---------------------------------------------------------------------------
// Demo screenshot thumbnails (inline SVG data-URIs, no file deps)
// ---------------------------------------------------------------------------

// Three small placeholder screenshots encoded as SVG data-URIs.
// They mimic browser screenshots with a dark header bar + content region.

function _svgThumb(
  title: string,
  bg: string,
  accentLine: string,
): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="240" viewBox="0 0 400 240">
  <rect width="400" height="240" fill="#0f1014"/>
  <rect x="0" y="0" width="400" height="28" fill="#1a1c22"/>
  <circle cx="16" cy="14" r="5" fill="#ff5f57"/>
  <circle cx="32" cy="14" r="5" fill="#febc2e"/>
  <circle cx="48" cy="14" r="5" fill="#28c840"/>
  <rect x="70" y="7" width="260" height="14" rx="7" fill="#26282e"/>
  <text x="200" y="19" font-family="monospace" font-size="9" fill="#666" text-anchor="middle">app.acmecorp.io</text>
  <rect x="12" y="40" width="376" height="${bg}" fill="#141418"/>
  <rect x="12" y="42" width="376" height="3" fill="${accentLine}" opacity="0.7"/>
  <rect x="20" y="55" width="120" height="8" rx="4" fill="#1e2028"/>
  <rect x="20" y="71" width="80" height="6" rx="3" fill="#1a1c22"/>
  <rect x="20" y="85" width="200" height="6" rx="3" fill="#1a1c22"/>
  <rect x="20" y="99" width="160" height="6" rx="3" fill="#1a1c22"/>
  <rect x="20" y="117" width="360" height="80" rx="6" fill="#1c1e24"/>
  <rect x="32" y="129" width="80" height="6" rx="3" fill="#22262f"/>
  <rect x="32" y="143" width="200" height="4" rx="2" fill="#22262f"/>
  <rect x="32" y="155" width="140" height="4" rx="2" fill="#22262f"/>
  <rect x="32" y="167" width="180" height="4" rx="2" fill="#22262f"/>
  <text x="200" y="218" font-family="monospace" font-size="8" fill="#3a3e48" text-anchor="middle">${title}</text>
</svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

const DEMO_SCREENSHOTS = {
  login_success: _svgThumb("login-success.png", "168", "#22d3ee"),
  login_form:    _svgThumb("login-form.png", "168", "#06b6d4"),
  payment_error: _svgThumb("stripe-3ds-failure.png", "168", "#f87171"),
  payment_form:  _svgThumb("payment-form.png", "168", "#22d3ee"),
  dashboard:     _svgThumb("dashboard-overview.png", "168", "#34d399"),
  a11y_report:   _svgThumb("a11y-homepage.png", "168", "#fbbf24"),
};

// ---------------------------------------------------------------------------
// Demo reports map — keyed by DEMO_HISTORY run ids
// ---------------------------------------------------------------------------

/** Minimal Playwright JSON report shape for demo purposes. */
interface DemoReport {
  json_report: Record<string, unknown>;
  network_entries: SilkNetworkEntry[];
  screenshot_data_uris: string[]; // data-URIs for browser rendering
  a11y_violations: SilkA11yViolation[];
  stderr_tail: string;
}

function _makeSuite(
  suiteName: string,
  specs: Array<{
    title: string;
    ok: boolean;
    duration: number;
    error?: string;
  }>,
): Record<string, unknown> {
  return {
    title: suiteName,
    specs: specs.map((s) => ({
      title: s.title,
      ok: s.ok,
      tests: [
        {
          status: s.ok ? "passed" : "failed",
          results: [
            {
              duration: s.duration,
              error: s.error ? { message: s.error } : undefined,
            },
          ],
        },
      ],
    })),
    suites: [],
  };
}

function _makeNet(method: string, url: string, status: number): SilkNetworkEntry {
  return {
    request: { method, url },
    response: { status, content: { mimeType: "application/json" } },
  };
}

const DEMO_REPORTS: Record<string, DemoReport> = {
  // ── demo-run-018 (login, passed, today) ────────────────────────────────────
  "demo-run-018": {
    json_report: {
      suites: [
        _makeSuite("Authentication", [
          { title: "renders login form", ok: true, duration: 420 },
          { title: "shows validation errors on empty submit", ok: true, duration: 310 },
          { title: "rejects invalid credentials", ok: true, duration: 1840 },
          { title: "logs in with valid credentials", ok: true, duration: 2190 },
          { title: "redirects to dashboard after login", ok: true, duration: 880 },
          { title: "persists session across reload", ok: true, duration: 1200 },
        ]),
      ],
    },
    network_entries: [
      _makeNet("GET",  "https://app.acmecorp.io/login",           200),
      _makeNet("POST", "https://api.acmecorp.io/auth/session",     401),
      _makeNet("POST", "https://api.acmecorp.io/auth/session",     200),
      _makeNet("GET",  "https://api.acmecorp.io/users/me",         200),
      _makeNet("GET",  "https://app.acmecorp.io/dashboard",        200),
    ],
    screenshot_data_uris: [DEMO_SCREENSHOTS.login_form, DEMO_SCREENSHOTS.login_success],
    a11y_violations: [],
    stderr_tail: "",
  },

  // ── demo-run-017 (a11y/homepage, passed, 2 violations) ─────────────────────
  "demo-run-017": {
    json_report: {
      suites: [
        _makeSuite("Accessibility — homepage", [
          { title: "page loads without console errors", ok: true, duration: 520 },
          { title: "axe-core: zero critical violations", ok: true, duration: 3840 },
          { title: "colour contrast ≥ 4.5:1 on hero text", ok: true, duration: 1200 },
          { title: "all images have alt attributes", ok: true, duration: 640 },
          { title: "keyboard navigation: skip-link works", ok: true, duration: 1080 },
          { title: "screen reader landmark regions present", ok: true, duration: 2140 },
        ]),
      ],
    },
    network_entries: [
      _makeNet("GET",  "https://app.acmecorp.io/",                200),
      _makeNet("GET",  "https://cdn.acmecorp.io/assets/hero.jpg", 200),
      _makeNet("GET",  "https://api.acmecorp.io/features",        200),
    ],
    screenshot_data_uris: [DEMO_SCREENSHOTS.a11y_report],
    a11y_violations: [
      {
        rule: "color-contrast",
        impact: "serious",
        description: "Elements must have sufficient colour contrast",
        nodes: [
          "footer > .legal-links > a",
          "nav.secondary > ul > li.inactive > a",
        ],
      },
      {
        rule: "aria-required-attr",
        impact: "critical",
        description: "Required ARIA attributes must be provided",
        nodes: ["button[role='tab']:nth-child(3)"],
      },
    ],
    stderr_tail: "",
  },

  // ── demo-run-016 (payment-flow, FAILED — Stripe 3DS) ──────────────────────
  "demo-run-016": {
    json_report: {
      suites: [
        _makeSuite("Payment flow", [
          { title: "adds item to cart",                      ok: true,  duration: 1420 },
          { title: "navigates to checkout",                  ok: true,  duration: 880  },
          { title: "fills shipping address",                 ok: true,  duration: 1650 },
          { title: "selects credit card payment",            ok: true,  duration: 540  },
          {
            title: "completes Stripe 3DS checkout",
            ok: false,
            duration: 15000,
            error:
              "TimeoutError: waiting for selector '.stripe-success-banner' failed\n" +
              "Expected: visible\nReceived: hidden after 15000ms\n\n" +
              "  at Object.<anonymous> (tests/checkout/payment-flow.spec.ts:87:5)\n" +
              "    Stripe 3DS iframe did not complete within timeout. " +
              "The mock 3DS challenge may not be resolving correctly in CI.",
          },
          { title: "verifies order confirmation email",      ok: true,  duration: 1260 },
          { title: "checks order appears in account history", ok: true,  duration: 980  },
        ]),
      ],
    },
    network_entries: [
      _makeNet("GET",  "https://app.acmecorp.io/cart",                   200),
      _makeNet("POST", "https://api.acmecorp.io/cart/items",              201),
      _makeNet("GET",  "https://app.acmecorp.io/checkout",               200),
      _makeNet("POST", "https://api.acmecorp.io/orders",                 201),
      _makeNet("POST", "https://api.stripe.com/v1/payment_intents",      200),
      _makeNet("GET",  "https://js.stripe.com/v3/controller/3ds/",       200),
      _makeNet("POST", "https://api.stripe.com/v1/payment_intents/confirm", 402),
    ],
    screenshot_data_uris: [DEMO_SCREENSHOTS.payment_form, DEMO_SCREENSHOTS.payment_error],
    a11y_violations: [],
    stderr_tail:
      "  1 failed\n  ● Payment flow › completes Stripe 3DS checkout\n\n" +
      "    TimeoutError: waiting for selector '.stripe-success-banner' failed\n" +
      "    Expected: visible\n    Received: hidden after 15000ms",
  },

  // ── demo-run-015 (profile/settings, passed) ────────────────────────────────
  "demo-run-015": {
    json_report: {
      suites: [
        _makeSuite("Profile settings", [
          { title: "renders settings page",                  ok: true, duration: 620  },
          { title: "updates display name",                   ok: true, duration: 2100 },
          { title: "changes email with confirmation flow",   ok: true, duration: 4200 },
          { title: "toggles notification preferences",       ok: true, duration: 1350 },
          { title: "uploads profile avatar",                 ok: true, duration: 1980 },
          { title: "deletes account with confirmation",      ok: true, duration: 990  },
        ]),
      ],
    },
    network_entries: [
      _makeNet("GET",  "https://api.acmecorp.io/users/me",              200),
      _makeNet("PATCH","https://api.acmecorp.io/users/me",              200),
      _makeNet("POST", "https://api.acmecorp.io/users/me/avatar",       201),
      _makeNet("POST", "https://api.acmecorp.io/users/me/email-change", 200),
    ],
    screenshot_data_uris: [DEMO_SCREENSHOTS.dashboard],
    a11y_violations: [],
    stderr_tail: "",
  },

  // ── demo-run-014 (dashboard/overview, passed) ──────────────────────────────
  "demo-run-014": {
    json_report: {
      suites: [
        _makeSuite("Dashboard overview", [
          { title: "loads dashboard within 3 seconds",       ok: true, duration: 2180 },
          { title: "renders metric cards with data",         ok: true, duration: 1420 },
          { title: "date range picker updates charts",       ok: true, duration: 3100 },
          { title: "export CSV contains correct columns",    ok: true, duration: 2640 },
          { title: "responsive layout on tablet viewport",   ok: true, duration: 1840 },
          { title: "notification badge shows unread count",  ok: true, duration: 1200 },
        ]),
      ],
    },
    network_entries: [
      _makeNet("GET", "https://api.acmecorp.io/metrics?range=7d",     200),
      _makeNet("GET", "https://api.acmecorp.io/metrics?range=30d",    200),
      _makeNet("GET", "https://api.acmecorp.io/notifications",        200),
      _makeNet("GET", "https://api.acmecorp.io/export/csv?range=7d",  200),
    ],
    screenshot_data_uris: [DEMO_SCREENSHOTS.dashboard],
    a11y_violations: [],
    stderr_tail: "",
  },
};

// Populate remaining history entries with minimal but non-empty demo reports
// so every run click shows something useful.
for (const entry of DEMO_HISTORY) {
  if (!DEMO_REPORTS[entry.id]) {
    const specName = entry.spec_path.split("/").pop()?.replace(".spec.ts", "") ?? entry.id;
    DEMO_REPORTS[entry.id] = {
      json_report: {
        suites: [
          _makeSuite(specName, [
            { title: "setup and navigate",          ok: true,  duration: 480  },
            { title: "primary user flow",           ok: entry.status === "passed", duration: 1840,
              error: entry.status !== "passed" ? "Expected condition was not met within timeout." : undefined },
            { title: "assert page state",           ok: entry.status !== "error", duration: 920  },
            { title: "cleanup session",             ok: true,  duration: 240  },
          ]),
        ],
      },
      network_entries: [
        _makeNet("GET",  `https://app.acmecorp.io/${specName}`, 200),
        _makeNet("GET",  "https://api.acmecorp.io/health",       200),
      ],
      screenshot_data_uris: entry.status === "failed"
        ? [DEMO_SCREENSHOTS.payment_error]
        : [DEMO_SCREENSHOTS.dashboard],
      a11y_violations: entry.a11y_violations_count > 0
        ? [
            {
              rule: "color-contrast",
              impact: "moderate",
              description: "Elements must have sufficient colour contrast",
              nodes: [".footer-link", ".secondary-nav-item"],
            },
          ]
        : [],
      stderr_tail: entry.stderr_tail,
    };
  }
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SessionRun {
  run: SilkRunOutput;
  specLabel: string;
  startedAt: number;
  traceUrl?: string;
}

type ActiveTab = "timeline" | "network" | "screenshots" | "a11y" | "console";

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

function StatusIcon({
  status,
  size = 12,
}: {
  status: "passed" | "failed" | "error" | "running";
  size?: number;
}) {
  if (status === "passed")
    return <CheckCircle2 size={size} className="text-emerald-400 shrink-0" />;
  if (status === "failed")
    return <XCircle size={size} className="text-red-400 shrink-0" />;
  if (status === "error")
    return <AlertCircle size={size} className="text-amber-400 shrink-0" />;
  return <RefreshCw size={size} className="text-neutral-400 animate-spin shrink-0" />;
}

function ImpactBadge({ impact }: { impact: string }) {
  const colors: Record<string, string> = {
    critical: "bg-red-900/60 text-red-300 border-red-800",
    serious: "bg-orange-900/60 text-orange-300 border-orange-800",
    moderate: "bg-amber-900/60 text-amber-300 border-amber-800",
    minor: "bg-neutral-800 text-neutral-400 border-neutral-700",
  };
  const cls = colors[impact] ?? colors.minor;
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[9px] font-medium uppercase ${cls}`}>
      {impact}
    </span>
  );
}

function durationLabel(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ---------------------------------------------------------------------------
// Attachment parsers (mirror Python _parse_network_entries / _parse_screenshot_paths)
// ---------------------------------------------------------------------------

function extractNetworkEntries(report: Record<string, unknown> | null): SilkNetworkEntry[] {
  if (!report) return [];
  const entries: SilkNetworkEntry[] = [];

  function walkSuites(suites: unknown[]): void {
    for (const suite of suites) {
      if (typeof suite !== "object" || !suite) continue;
      const s = suite as Record<string, unknown>;
      for (const spec of (s.specs as unknown[] | undefined) ?? []) {
        if (typeof spec !== "object" || !spec) continue;
        for (const test of ((spec as Record<string, unknown>).tests as unknown[] | undefined) ?? []) {
          if (typeof test !== "object" || !test) continue;
          for (const result of ((test as Record<string, unknown>).results as unknown[] | undefined) ?? []) {
            if (typeof result !== "object" || !result) continue;
            for (const att of ((result as Record<string, unknown>).attachments as unknown[] | undefined) ?? []) {
              if (typeof att !== "object" || !att) continue;
              const a = att as Record<string, unknown>;
              if (a.name !== "network.json" && a.name !== "har.json") continue;
              const body = a.body as string | undefined;
              if (!body) continue;
              try {
                const data = JSON.parse(body) as Record<string, unknown>;
                const ents = (data.log as Record<string, unknown> | undefined)?.entries as SilkNetworkEntry[] | undefined;
                if (Array.isArray(ents)) entries.push(...ents);
              } catch {
                // ignore malformed
              }
            }
          }
        }
      }
      walkSuites((s.suites as unknown[] | undefined) ?? []);
    }
  }

  walkSuites((report.suites as unknown[] | undefined) ?? []);
  return entries;
}

function extractScreenshotPaths(report: Record<string, unknown> | null): string[] {
  if (!report) return [];
  const paths: string[] = [];

  function walkSuites(suites: unknown[]): void {
    for (const suite of suites) {
      if (typeof suite !== "object" || !suite) continue;
      const s = suite as Record<string, unknown>;
      for (const spec of (s.specs as unknown[] | undefined) ?? []) {
        if (typeof spec !== "object" || !spec) continue;
        for (const test of ((spec as Record<string, unknown>).tests as unknown[] | undefined) ?? []) {
          if (typeof test !== "object" || !test) continue;
          for (const result of ((test as Record<string, unknown>).results as unknown[] | undefined) ?? []) {
            if (typeof result !== "object" || !result) continue;
            for (const att of ((result as Record<string, unknown>).attachments as unknown[] | undefined) ?? []) {
              if (typeof att !== "object" || !att) continue;
              const a = att as Record<string, unknown>;
              const ct = String(a.contentType ?? "");
              const name = String(a.name ?? "");
              const path = String(a.path ?? "");
              if (path && (ct.startsWith("image/") || name.toLowerCase().includes("screenshot") || path.endsWith(".png"))) {
                paths.push(path);
              }
            }
          }
        }
      }
      walkSuites((s.suites as unknown[] | undefined) ?? []);
    }
  }

  walkSuites((report.suites as unknown[] | undefined) ?? []);
  return paths;
}

function timeAgo(isoOrMs: string | number): string {
  const ms = typeof isoOrMs === "number" ? isoOrMs : Date.parse(isoOrMs);
  const diff = Date.now() - ms;
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return new Date(ms).toLocaleDateString();
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Browser tab switcher for per_browser_results. */
function BrowserTabBar({
  browsers,
  active,
  onSelect,
  results,
}: {
  browsers: string[];
  active: string;
  onSelect: (b: string) => void;
  results: Record<string, SilkBrowserRunResult>;
}) {
  if (browsers.length <= 1) return null;
  return (
    <div className="flex gap-1 border-b border-neutral-800 px-3 py-1.5">
      {browsers.map((b) => {
        const r = results[b];
        const ok = r?.exit_code === 0;
        return (
          <button
            key={b}
            onClick={() => onSelect(b)}
            className={`flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors ${
              active === b
                ? "bg-neutral-800 text-neutral-100"
                : "text-neutral-500 hover:text-neutral-300 hover:bg-neutral-900"
            }`}
          >
            {ok ? (
              <CheckCircle2 size={10} className="text-emerald-400" />
            ) : (
              <XCircle size={10} className="text-red-400" />
            )}
            {b}
          </button>
        );
      })}
    </div>
  );
}

/** Step timeline extracted from Playwright JSON report. */
interface PlaywrightSuite {
  title: string;
  specs?: PlaywrightSpec[];
  suites?: PlaywrightSuite[];
}
interface PlaywrightSpec {
  title: string;
  ok: boolean;
  tests?: Array<{
    status: string;
    results?: Array<{ duration: number; error?: { message: string } }>;
  }>;
}

function flattenSpecs(suite: PlaywrightSuite): PlaywrightSpec[] {
  const out: PlaywrightSpec[] = [];
  (suite.specs ?? []).forEach((s) => out.push(s));
  (suite.suites ?? []).forEach((s) => out.push(...flattenSpecs(s)));
  return out;
}

function StepTimeline({ report }: { report: Record<string, unknown> | null }) {
  const t = useT();
  if (!report)
    return (
      <div className="flex items-center justify-center h-full text-xs text-neutral-600">
        {t("silk.timeline.noReport")}
      </div>
    );

  const suites = (report.suites as PlaywrightSuite[] | undefined) ?? [];
  const allSpecs = suites.flatMap(flattenSpecs);

  if (allSpecs.length === 0)
    return (
      <div className="flex items-center justify-center h-full text-xs text-neutral-600">
        {t("silk.timeline.noSteps")}
      </div>
    );

  return (
    <div className="flex flex-col gap-1 overflow-y-auto p-2">
      {/* Suite label shown as a header strip with cyan accent left-border */}
      {suites.map((suite, si) => (
        <div key={si}>
          {suite.title && (
            <div className="flex items-center gap-2 px-1 py-1 mb-0.5 border-l-2 border-cobweb-500">
              <span className="text-[10px] uppercase tracking-wider text-cobweb-400 font-semibold">
                {suite.title}
              </span>
            </div>
          )}
          {flattenSpecs(suite).map((spec, i) => {
            const result = spec.tests?.[0]?.results?.[0];
            const duration = result?.duration ?? 0;
            const errorMsg = result?.error?.message;
            return (
              <div
                key={i}
                className={`flex items-start gap-2 rounded p-2 text-xs ${
                  spec.ok
                    ? "bg-emerald-950/30 border border-emerald-900/40"
                    : "bg-red-950/40 border border-red-900/40"
                }`}
              >
                {spec.ok ? (
                  <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-400" />
                ) : (
                  <XCircle size={12} className="mt-0.5 shrink-0 text-red-400" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-neutral-200 font-medium truncate">{spec.title}</div>
                  {errorMsg && (
                    <div className="mt-0.5 text-red-400 text-[10px] line-clamp-3 font-mono">
                      {errorMsg}
                    </div>
                  )}
                </div>
                <div className="shrink-0 flex items-center gap-1 text-cobweb-600">
                  <Clock size={10} />
                  <span className="font-mono">{duration}ms</span>
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

/** A11y violations list. */
function A11yPanel({ violations }: { violations: SilkA11yViolation[] }) {
  const t = useT();
  if (violations.length === 0)
    return (
      <div className="flex items-center justify-center h-32 text-xs text-emerald-500 gap-1.5">
        <CheckCircle2 size={14} />
        {t("silk.a11y.noViolations")}
      </div>
    );

  return (
    <div className="flex flex-col gap-2 overflow-y-auto p-2">
      {violations.map((v, i) => (
        <div key={i} className="rounded border border-neutral-800 bg-neutral-900 p-2.5">
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="text-xs font-medium text-neutral-200 font-mono">{v.rule}</span>
            <ImpactBadge impact={v.impact} />
          </div>
          <p className="text-[10px] text-neutral-400 mb-1.5">{v.description}</p>
          {v.nodes.length > 0 && (
            <details className="text-[10px]">
              <summary className="cursor-pointer text-neutral-500 hover:text-neutral-400">
                {t("silk.a11y.affectedElements", { n: v.nodes.length })}
              </summary>
              <ul className="mt-1 space-y-0.5 font-mono">
                {v.nodes.map((n, ni) => (
                  <li key={ni} className="text-neutral-500 truncate">{n}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Install dialog
// ---------------------------------------------------------------------------

function InstallDialog({
  onDone,
  onCancel,
}: {
  onDone: () => void;
  onCancel: () => void;
}) {
  const t = useT();
  const [log, setLog] = useState<string[]>([t("silk.install.log.start")]);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    sidecar
      .silkInstallBrowsersSync()
      .then((res) => {
        if (cancelled) return;
        if (res.ok) {
          setLog((prev) => [...prev, `Done. Path: ${res.browser_path ?? "unknown"}`]);
          setDone(true);
          setTimeout(onDone, 1200);
        } else {
          setError(res.message);
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [onDone]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [log]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-[520px] rounded-lg border border-neutral-800 bg-neutral-925 shadow-2xl p-5 flex flex-col gap-4">
        <div className="flex items-center gap-2 text-neutral-100">
          <Download size={18} className="text-emerald-400" />
          <h2 className="font-semibold text-sm">{t("silk.install.title")}</h2>
        </div>
        <div
          ref={logRef}
          className="h-48 overflow-y-auto rounded bg-neutral-950 p-3 font-mono text-xs text-neutral-400 select-text"
        >
          {log.map((line, i) => <div key={i}>{line}</div>)}
          {error && <div className="text-red-400 mt-1">{t("silk.install.error", { msg: error })}</div>}
          {done && <div className="text-emerald-400 mt-1">{t("silk.install.chromiumReady")}</div>}
        </div>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded px-3 py-1.5 text-xs bg-neutral-800 hover:bg-neutral-700 text-neutral-300 transition-colors"
          >
            {done || error ? t("silk.install.close") : t("silk.install.cancel")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Record dialog
// ---------------------------------------------------------------------------

/**
 * SSE streaming via fetch — works under Tauri where EventSource cannot send
 * the X-Theridion-Token auth header.  We open a streaming fetch, read lines,
 * and accumulate them in state.  The abort controller lets us cancel early
 * when the user hits "Stop recording" or "Cancel".
 */
async function* _fetchSSELines(
  url: string,
  token: string | null,
  signal: AbortSignal,
): AsyncGenerator<string> {
  const headers: Record<string, string> = {};
  if (token) headers["X-Theridion-Token"] = token;
  const res = await fetch(url, { headers, signal });
  if (!res.ok || !res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n");
    buf = parts.pop() ?? "";
    for (const part of parts) {
      const trimmed = part.trim();
      if (trimmed.startsWith("data:")) {
        yield trimmed.slice(5).trim();
      }
    }
  }
}

function RecordDialog({
  onCapture,
  onRunNow,
  onCancel,
}: {
  /** Called when recording stops and user wants to just keep the spec text. */
  onCapture: (specCode: string, specPath: string | null) => void;
  /** Called when user wants to save + immediately run the recorded spec. */
  onRunNow: (sessionId: string, framework: string) => void;
  onCancel: () => void;
}) {
  const t = useT();
  const [url, setUrl] = useState("http://localhost:3000");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [liveLines, setLiveLines] = useState<string[]>([]);
  const [stopping, setStopping] = useState(false);
  const [capturedSpec, setCapturedSpec] = useState<{ code: string; path: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  // Framework selection
  const [frameworks, setFrameworks] = useState<SilkFramework[]>([]);
  const [loadingFrameworks, setLoadingFrameworks] = useState(true);
  const [selectedFrameworkId, setSelectedFrameworkId] = useState<string>("playwright-ts");

  useEffect(() => {
    sidecar
      .silkFrameworks()
      .then(({ frameworks: fws }) => {
        setFrameworks(fws);
        // Pick first recordable framework as default (prefer playwright-ts)
        const defaultFw =
          fws.find((f) => f.id === "playwright-ts") ??
          fws.find((f) => f.recordable) ??
          fws[0];
        if (defaultFw) setSelectedFrameworkId(defaultFw.id);
      })
      .catch(() => {
        // Non-blocking — fall back to playwright-ts
      })
      .finally(() => setLoadingFrameworks(false));
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [liveLines]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const selectedFramework = frameworks.find((f) => f.id === selectedFrameworkId) ?? null;
  const canRecord = selectedFramework === null || selectedFramework.recordable;

  /** Start codegen and immediately open the fetch-based SSE stream. */
  const handleStart = async () => {
    setError(null);
    try {
      const res = await sidecar.silkRecordStart({ url, framework: selectedFrameworkId });
      setSessionId(res.session_id);
      setLiveLines([res.message]);

      // Open SSE stream with fetch (compatible with Tauri auth headers).
      const [base, token] = await Promise.all([getSidecarBaseUrl(), getSidecarToken()]);
      const streamUrl = `${base}/api/silk/record/stream/${encodeURIComponent(res.session_id)}`;
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      void (async () => {
        try {
          for await (const line of _fetchSSELines(streamUrl, token, ctrl.signal)) {
            if (line === "DONE") break;
            setLiveLines((prev) => [...prev, line]);
          }
        } catch {
          // AbortError when user clicks cancel — expected.
        }
      })();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleStop = async () => {
    if (!sessionId) return;
    setStopping(true);
    abortRef.current?.abort();
    try {
      const res = await sidecar.silkRecordStop(sessionId);
      setCapturedSpec({ code: res.spec_text, path: res.spec_path });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setStopping(false);
    }
  };

  const handleKeep = () => {
    if (capturedSpec) {
      onCapture(capturedSpec.code, capturedSpec.path);
    }
  };

  const handleRunNow = () => {
    if (sessionId) {
      onRunNow(sessionId, selectedFrameworkId);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-[600px] rounded-lg border border-neutral-800 bg-neutral-925 shadow-2xl p-5 flex flex-col gap-4">
        <div className="flex items-center gap-2 text-neutral-100">
          <Video size={16} className="text-emerald-400" />
          <h2 className="font-semibold text-sm">{t("silk.record.title")}</h2>
        </div>

        {/* ── Phase 1: setup ── */}
        {!sessionId && !capturedSpec && (
          <>
            {/* Framework selector */}
            <div className="flex flex-col gap-1">
              <label className="text-xs text-neutral-500">{t("silk.record.framework.label")}</label>
              {loadingFrameworks ? (
                <div className="flex items-center gap-1.5 text-xs text-neutral-500 h-7">
                  <RefreshCw size={11} className="animate-spin" />
                  {t("silk.record.framework.loading")}
                </div>
              ) : (
                <select
                  value={selectedFrameworkId}
                  onChange={(e) => setSelectedFrameworkId(e.target.value)}
                  className="rounded bg-neutral-950 border border-neutral-800 px-3 py-1.5 text-xs text-neutral-200 focus:outline-none focus:border-emerald-600 transition-colors"
                >
                  {frameworks.length === 0 ? (
                    <option value="playwright-ts">Playwright (TypeScript)</option>
                  ) : (
                    frameworks.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.label}
                      </option>
                    ))
                  )}
                </select>
              )}
              {canRecord && selectedFramework?.recordable_via_transpile && (
                <p className="text-[10px] text-neutral-400 mt-0.5">
                  {t("silk.record.framework.transpileNote", { label: selectedFramework.label })}
                </p>
              )}
              {!canRecord && selectedFramework && (
                <p className="text-[10px] text-amber-400 mt-0.5">
                  {t("silk.record.framework.noRecord", { label: selectedFramework.label })}
                </p>
              )}
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-neutral-500">{t("silk.record.targetUrl.label")}</label>
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="rounded bg-neutral-950 border border-neutral-800 px-3 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-600"
                spellCheck={false}
              />
            </div>
            {error && <div className="text-xs text-red-400">{error}</div>}
            <div className="flex justify-end gap-2">
              <button onClick={onCancel} className="rounded px-3 py-1.5 text-xs bg-neutral-800 hover:bg-neutral-700 text-neutral-300">
                {t("silk.record.cancel")}
              </button>
              <button
                onClick={() => void handleStart()}
                disabled={!url.trim() || !canRecord}
                className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed text-white"
                title={!canRecord && selectedFramework ? t("silk.record.framework.noRecord", { label: selectedFramework.label }) : undefined}
              >
                <Play size={11} />
                {t("silk.record.startRecording")}
              </button>
            </div>
          </>
        )}

        {/* ── Phase 2: recording in progress ── */}
        {sessionId && !capturedSpec && (
          <>
            <div className="text-xs text-neutral-400">
              {t("silk.record.inProgress")}
            </div>
            <div
              ref={logRef}
              className="h-36 overflow-y-auto rounded bg-neutral-950 p-3 font-mono text-xs text-neutral-400 select-text"
            >
              {liveLines.map((l, i) => <div key={i}>{l}</div>)}
              <div className="animate-pulse text-emerald-500 mt-1">{t("silk.record.recording")}</div>
            </div>
            {error && <div className="text-xs text-red-400">{error}</div>}
            <div className="flex justify-end gap-2">
              <button onClick={onCancel} className="rounded px-3 py-1.5 text-xs bg-neutral-800 hover:bg-neutral-700 text-neutral-300">
                {t("silk.record.cancel")}
              </button>
              <button
                onClick={() => void handleStop()}
                disabled={stopping}
                className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium bg-red-700 hover:bg-red-600 disabled:opacity-40 text-white"
              >
                {stopping ? <RefreshCw size={11} className="animate-spin" /> : <Square size={11} />}
                {t("silk.record.stopRecording")}
              </button>
            </div>
          </>
        )}

        {/* ── Phase 3: spec captured — offer Run Now or Keep ── */}
        {capturedSpec && (
          <>
            <div className="text-xs text-neutral-400">
              {t("silk.record.captured")}
            </div>
            <div className="h-24 overflow-y-auto rounded bg-neutral-950 p-3 font-mono text-[10px] text-neutral-400 select-text">
              {capturedSpec.code.split("\n").slice(0, 12).join("\n")}
              {capturedSpec.code.split("\n").length > 12 && "\n…"}
            </div>
            {error && <div className="text-xs text-red-400">{error}</div>}
            <div className="flex justify-end gap-2">
              <button onClick={onCancel} className="rounded px-3 py-1.5 text-xs bg-neutral-800 hover:bg-neutral-700 text-neutral-300">
                {t("silk.record.discard")}
              </button>
              <button
                onClick={handleKeep}
                className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs bg-neutral-700 hover:bg-neutral-600 text-neutral-200"
              >
                <FileCode size={11} />
                {t("silk.record.keep")}
              </button>
              <button
                onClick={handleRunNow}
                className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium bg-emerald-700 hover:bg-emerald-600 text-white"
              >
                <Play size={11} />
                {t("silk.record.runNow")}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Run form (with mocks + browser selection)
// ---------------------------------------------------------------------------

function RunForm({
  onRun,
  running,
}: {
  onRun: (specPath: string, workspaceDir: string, browsers: string[]) => void;
  running: boolean;
}) {
  const t = useT();
  const [specPath, setSpecPath] = useState("");
  const [workspaceDir, setWorkspaceDir] = useState("");
  const [browsers, setBrowsers] = useState<string[]>(["chromium"]);

  const toggleBrowser = (b: string) => {
    setBrowsers((prev) =>
      prev.includes(b) ? (prev.length > 1 ? prev.filter((x) => x !== b) : prev) : [...prev, b],
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (specPath.trim()) onRun(specPath.trim(), workspaceDir.trim(), browsers);
  };

  const BROWSERS = ["chromium", "firefox", "webkit"];

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 rounded-lg border border-neutral-800 bg-neutral-900 p-4"
    >
      <h3 className="text-xs font-semibold text-neutral-300 uppercase tracking-wider">
        {t("silk.runForm.title")}
      </h3>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-neutral-500">{t("silk.runForm.specPath.label")}</label>
        <input
          value={specPath}
          onChange={(e) => setSpecPath(e.target.value)}
          placeholder={t("silk.runForm.specPath.placeholder")}
          className="rounded bg-neutral-950 border border-neutral-800 px-3 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-600 transition-colors"
          spellCheck={false}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-neutral-500">{t("silk.runForm.workspaceDir.label")}</label>
        <input
          value={workspaceDir}
          onChange={(e) => setWorkspaceDir(e.target.value)}
          placeholder={t("silk.runForm.workspaceDir.placeholder")}
          className="rounded bg-neutral-950 border border-neutral-800 px-3 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-600 transition-colors"
          spellCheck={false}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-neutral-500">{t("silk.runForm.browsers.label")}</label>
        <div className="flex gap-1.5">
          {BROWSERS.map((b) => (
            <button
              key={b}
              type="button"
              onClick={() => toggleBrowser(b)}
              className={`rounded border px-2 py-1 text-xs font-medium transition-colors ${
                browsers.includes(b)
                  ? "border-emerald-700 bg-emerald-950/50 text-emerald-300"
                  : "border-neutral-700 bg-neutral-800 text-neutral-500 hover:text-neutral-300"
              }`}
            >
              {b}
            </button>
          ))}
        </div>
      </div>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={running || !specPath.trim()}
          className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors"
        >
          {running ? <RefreshCw size={12} className="animate-spin" /> : <Play size={12} />}
          {running ? t("silk.runForm.running") : t("silk.runForm.run")}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Main SilkPanel
// ---------------------------------------------------------------------------

interface SilkPanelProps {
  onToast?: (type: "success" | "error" | "info", message: string) => void;
}

export function SilkPanel({ onToast }: SilkPanelProps) {
  const t = useT();
  const [browsersInstalled, setBrowsersInstalled] = useState<boolean | null>(null);
  const [showInstallDialog, setShowInstallDialog] = useState(false);
  const [showRecordDialog, setShowRecordDialog] = useState(false);
  const [showNewTestDialog, setShowNewTestDialog] = useState(false);
  const [sessionRuns, setSessionRuns] = useState<SessionRun[]>([]);
  const [historyRuns, setHistoryRuns] = useState<SilkRunHistoryEntry[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [checkingBrowsers, setCheckingBrowsers] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [activeTab, setActiveTab] = useState<ActiveTab>("timeline");
  const [activeBrowser, setActiveBrowser] = useState("chromium");
  // True while running in a plain browser without a live sidecar.
  const [demoMode, setDemoMode] = useState<boolean>(getBrowserDemoMode);

  // Check browser presence on mount.
  const checkBrowsers = useCallback(async () => {
    setCheckingBrowsers(true);
    try {
      const res = await sidecar.silkCheckBrowsers();
      setBrowsersInstalled(res.installed);
      // Sidecar responded — we are NOT in browser-demo mode.
      disableBrowserDemo();
      setDemoMode(false);
    } catch {
      setBrowsersInstalled(false);
    } finally {
      setCheckingBrowsers(false);
    }
  }, []);

  // Load run history on mount. Falls back to demo data when sidecar is offline.
  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const runs = await sidecar.silkListRuns(50);
      if (runs.length > 0) {
        // Real sidecar data — disable demo mode.
        disableBrowserDemo();
        setDemoMode(false);
        setHistoryRuns(runs);
      } else {
        setHistoryRuns(DEMO_HISTORY);
      }
    } catch {
      // Sidecar unavailable — populate with demo data so the UI is never blank.
      setHistoryRuns(DEMO_HISTORY);
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    void checkBrowsers();
    void loadHistory();
  }, [checkBrowsers, loadHistory]);

  // Browser-demo auto-select: once history is populated and we are in demo mode,
  // pre-select the first (most-recent) run so the panel is never empty on load.
  useEffect(() => {
    if (demoMode && historyRuns.length > 0 && selectedRunId === null) {
      setSelectedRunId(historyRuns[0].id);
    }
  }, [demoMode, historyRuns, selectedRunId]);

  const handleInstallDone = useCallback(() => {
    setShowInstallDialog(false);
    void checkBrowsers();
    onToast?.("success", "Playwright Chromium installed.");
  }, [checkBrowsers, onToast]);

  const handleRun = useCallback(
    async (specPath: string, workspaceDir: string, browsers: string[]) => {
      if (!browsersInstalled) {
        setShowInstallDialog(true);
        return;
      }
      setRunning(true);
      try {
        const result = await sidecar.silkRun({
          spec_path: specPath,
          workspace_dir: workspaceDir || undefined,
          browsers: browsers as ("chromium" | "firefox" | "webkit")[],
        });
        const traceUrl = result.trace_path
          ? await sidecar.silkTraceUrl(result.run_id)
          : undefined;
        const entry: SessionRun = {
          run: result,
          specLabel: specPath.split("/").pop() ?? specPath,
          startedAt: Date.now(),
          traceUrl,
        };
        setSessionRuns((prev) => [entry, ...prev]);
        setSelectedRunId(result.run_id);
        setActiveBrowser(browsers[0] ?? "chromium");
        setActiveTab("timeline");

        if (result.failed > 0 || result.exit_code !== 0) {
          onToast?.("error", `Silk: ${result.failed} failed`);
        } else {
          onToast?.("success", `Silk: ${result.passed} passed`);
        }

        // Refresh history after run.
        void loadHistory();
      } catch (e: unknown) {
        onToast?.(
          "error",
          `Silk run error: ${e instanceof Error ? e.message : String(e)}`,
        );
      } finally {
        setRunning(false);
      }
    },
    [browsersInstalled, onToast, loadHistory],
  );

  const handleCaptureSpec = useCallback(
    (specCode: string, _specPath: string | null) => {
      setShowRecordDialog(false);
      if (specCode.trim()) {
        onToast?.("success", "Spec recorded — paste code into your spec file.");
      }
    },
    [onToast],
  );

  /**
   * "Run Now" bridge: stop the codegen session, save the spec, and immediately
   * run it.  This wires the record->run loop so a recorded spec is never discarded.
   */
  const handleRecordRunNow = useCallback(
    async (sessionId: string, framework: string) => {
      setShowRecordDialog(false);
      if (!browsersInstalled) {
        setShowInstallDialog(true);
        return;
      }
      setRunning(true);
      try {
        const result = await sidecar.silkRecordSaveAndRun({
          session_id: sessionId,
          framework,
          filename: "recorded",
          browsers: ["chromium"],
        });
        const traceUrl = result.run.trace_path
          ? await sidecar.silkTraceUrl(result.run.run_id)
          : undefined;
        const entry: SessionRun = {
          run: result.run,
          specLabel: result.spec_path.split("/").pop() ?? result.spec_path,
          startedAt: Date.now(),
          traceUrl,
        };
        setSessionRuns((prev) => [entry, ...prev]);
        setSelectedRunId(result.run.run_id);
        setActiveBrowser("chromium");
        setActiveTab("timeline");

        if (result.run.failed > 0 || result.run.exit_code !== 0) {
          onToast?.("error", `Silk: ${result.run.failed} failed`);
        } else {
          onToast?.("success", `Silk: ${result.run.passed} passed`);
        }

        void loadHistory();
      } catch (e: unknown) {
        onToast?.(
          "error",
          `Record+run error: ${e instanceof Error ? e.message : String(e)}`,
        );
      } finally {
        setRunning(false);
      }
    },
    [browsersInstalled, onToast, loadHistory],
  );

  const handleNewTestSaved = useCallback(
    (specPath: string) => {
      onToast?.("success", `Test uložen: ${specPath}`);
      // Keep dialog open so user can see the saved path (dialog closes itself via "Zavřít")
    },
    [onToast],
  );

  // Find selected run across session + history.
  const selectedSession = sessionRuns.find((r) => r.run.run_id === selectedRunId);
  const selectedRun = selectedSession?.run ?? null;
  const browsers = selectedRun
    ? Object.keys(selectedRun.per_browser_results)
    : [];
  const browserResult: SilkBrowserRunResult | null =
    selectedRun?.per_browser_results?.[activeBrowser] ?? null;

  // In browser-demo mode, augment a history selection with bundled DEMO_REPORTS.
  const demoReport = (demoMode && selectedRunId && !selectedRun)
    ? (DEMO_REPORTS[selectedRunId] ?? null)
    : null;

  // Resolved data for the right-panel tabs — demo data fills in when real run is absent.
  const activeJsonReport: Record<string, unknown> | null =
    browserResult?.json_report ?? selectedRun?.json_report ?? demoReport?.json_report ?? null;
  const activeNetworkEntries: SilkNetworkEntry[] =
    demoReport ? demoReport.network_entries : extractNetworkEntries(activeJsonReport);
  const activeDemoScreenshots: string[] = demoReport?.screenshot_data_uris ?? [];
  const activeRealScreenshots: string[] = demoReport ? [] : extractScreenshotPaths(activeJsonReport);

  // A11y violations — demo or real.
  const a11yViolations: SilkA11yViolation[] =
    demoReport?.a11y_violations ??
    selectedRun?.a11y_violations ??
    browserResult?.a11y_violations ??
    [];

  // Stats for the center panel when showing a history run in demo mode.
  const selectedHistoryRun = historyRuns.find((h) => h.id === selectedRunId) ?? null;
  const demoStderr = demoReport?.stderr_tail ?? selectedHistoryRun?.stderr_tail ?? "";

  // Right-panel tab definitions — use cobweb (cyan) accent on active tab.
  const TABS: { id: ActiveTab; label: string; icon: React.ReactNode }[] = [
    { id: "timeline", label: t("silk.tabs.timeline"), icon: <Play size={11} /> },
    { id: "network", label: t("silk.tabs.network"), icon: <Globe size={11} /> },
    { id: "screenshots", label: t("silk.tabs.screenshots"), icon: <Image size={11} /> },
    {
      id: "a11y",
      label: `A11y${a11yViolations.length > 0 ? ` (${a11yViolations.length})` : ""}`,
      icon: <AlertTriangle size={11} className={a11yViolations.length > 0 ? "text-amber-400" : ""} />,
    },
    { id: "console", label: t("silk.tabs.console"), icon: <Terminal size={11} /> },
  ];

  return (
    <>
      {showInstallDialog && (
        <InstallDialog
          onDone={handleInstallDone}
          onCancel={() => setShowInstallDialog(false)}
        />
      )}
      {showRecordDialog && (
        <RecordDialog
          onCapture={handleCaptureSpec}
          onRunNow={(sessionId, framework) => void handleRecordRunNow(sessionId, framework)}
          onCancel={() => setShowRecordDialog(false)}
        />
      )}
      {showNewTestDialog && (
        <NewTestDialog
          onSaved={handleNewTestSaved}
          onCancel={() => setShowNewTestDialog(false)}
        />
      )}

      <div className="flex h-full flex-col bg-neutral-950 text-neutral-200">
        {/* Toolbar */}
        <div className="flex items-center justify-between border-b border-neutral-800 px-3 py-2 shrink-0">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowRecordDialog(true)}
              disabled={!browsersInstalled}
              className="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs font-medium bg-neutral-800 hover:bg-neutral-700 disabled:opacity-40 text-neutral-200 transition-colors"
              title={browsersInstalled ? t("silk.toolbar.record.title") : t("silk.toolbar.record.titleNoBrowsers")}
            >
              <Video size={12} className="text-red-400" />
              {t("silk.toolbar.record")}
            </button>
            <button
              onClick={() => setShowNewTestDialog(true)}
              className="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs font-medium bg-neutral-800 hover:bg-neutral-700 text-neutral-200 transition-colors"
              title={t("silk.toolbar.newTest.title")}
            >
              <FileCode size={12} className="text-emerald-400" />
              {t("silk.toolbar.newTest")}
            </button>
          </div>

          <div className="flex items-center gap-2">
            {/* Browser status */}
            {browsersInstalled === false && (
              <button
                onClick={() => setShowInstallDialog(true)}
                className="flex items-center gap-1 text-[10px] text-amber-400 hover:text-amber-300"
              >
                <Download size={10} />
                {t("silk.toolbar.installBrowsers")}
              </button>
            )}
            <button
              onClick={() => void checkBrowsers()}
              disabled={checkingBrowsers}
              title={t("silk.toolbar.refreshBrowserCheck")}
              className="text-neutral-500 hover:text-neutral-300 transition-colors"
            >
              <RefreshCw size={12} className={checkingBrowsers ? "animate-spin" : ""} />
            </button>
            <button
              onClick={() => void loadHistory()}
              disabled={loadingHistory}
              title={t("silk.toolbar.refreshHistory")}
              className="text-neutral-500 hover:text-neutral-300 transition-colors"
            >
              <History size={12} className={loadingHistory ? "animate-spin" : ""} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex flex-1 min-h-0">
          {/* Left sidebar — history */}
          <div className="flex w-52 shrink-0 flex-col border-r border-neutral-800 bg-neutral-925">
            <div className="flex items-center justify-between border-b border-neutral-800 px-3 py-2">
              <span className="flex items-center gap-1.5 text-xs font-semibold text-neutral-300">
                <MonitorPlay size={12} className="text-cobweb-500" />
                {t("silk.history.title")}
                {demoMode && (
                  <span className="rounded border border-cobweb-800 bg-cobweb-950/60 px-1 py-px text-[8px] uppercase tracking-wider text-cobweb-400">
                    demo
                  </span>
                )}
              </span>
              <button
                onClick={() => handleRun("", "", ["chromium"])}
                disabled={running}
                className="text-neutral-500 hover:text-cobweb-400 transition-colors"
                title={t("silk.history.newRun.title")}
              >
                <Plus size={12} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto py-1">
              {/* Session runs (in-memory, unsaved) */}
              {sessionRuns.length === 0 && historyRuns.length === 0 && (
                <EmptyState
                  icon={History}
                  title={t("silk.history.empty.title")}
                  description={t("silk.history.empty.description")}
                />
              )}

              {sessionRuns.map((entry) => {
                const status =
                  entry.run.exit_code === 0 ? "passed" :
                  entry.run.failed > 0 ? "failed" : "error";
                return (
                  <button
                    key={entry.run.run_id}
                    onClick={() => {
                      setSelectedRunId(entry.run.run_id);
                      const firstBrowser = Object.keys(entry.run.per_browser_results)[0] ?? "chromium";
                      setActiveBrowser(firstBrowser);
                    }}
                    className={`w-full text-left px-3 py-2 flex flex-col gap-0.5 transition-colors border-l-2 ${
                      selectedRunId === entry.run.run_id
                        ? "bg-neutral-800 border-cobweb-500"
                        : "hover:bg-neutral-900 border-transparent"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <StatusIcon status={status} size={10} />
                      <span className="flex-1 truncate text-xs text-neutral-200 min-w-0">
                        {entry.specLabel}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-[10px] text-neutral-600">
                      <span>{durationLabel(entry.run.duration_ms)}</span>
                      <span>{timeAgo(entry.startedAt)}</span>
                    </div>
                  </button>
                );
              })}

              {historyRuns.length > 0 && (
                <>
                  <div className="px-3 py-1.5 text-[10px] uppercase text-neutral-600 tracking-wider">
                    {t("silk.history.previousRuns")}
                  </div>
                  {historyRuns
                    .filter((h) => !sessionRuns.some((s) => s.run.run_id === h.id))
                    .map((h) => (
                      <button
                        key={h.id}
                        onClick={() => setSelectedRunId(h.id)}
                        className={`w-full text-left px-3 py-2 flex flex-col gap-0.5 transition-colors border-l-2 ${
                          selectedRunId === h.id
                            ? "bg-neutral-800 border-cobweb-500"
                            : "hover:bg-neutral-900 border-transparent"
                        }`}
                      >
                        <div className="flex items-center gap-1">
                          <StatusIcon status={h.status} size={10} />
                          <span className="flex-1 truncate text-xs text-neutral-200 min-w-0">
                            {h.spec_path.split("/").pop()}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-[10px] text-neutral-600">
                          <span>{durationLabel(h.duration_ms)}</span>
                          <span>{timeAgo(h.started_at)}</span>
                          {h.browsers.length > 1 && (
                            <span className="text-neutral-700">{h.browsers.join(", ")}</span>
                          )}
                        </div>
                      </button>
                    ))}
                </>
              )}
            </div>
          </div>

          {/* Center — run form + trace viewer */}
          <div className="flex flex-1 min-w-0 flex-col">
            {/* Run form */}
            <div className="border-b border-neutral-800 p-3">
              <RunForm onRun={handleRun} running={running} />
            </div>

            {/* Browser tab bar */}
            {selectedRun && browsers.length > 1 && (
              <BrowserTabBar
                browsers={browsers}
                active={activeBrowser}
                onSelect={(b) => setActiveBrowser(b)}
                results={selectedRun.per_browser_results}
              />
            )}

            {/* Stats row — real run */}
            {selectedRun && (
              <div className="border-b border-neutral-800 px-4 py-3">
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-xs font-semibold text-neutral-300">
                    Run {selectedRun.run_id.slice(0, 8)}
                  </span>
                  {selectedSession?.traceUrl && (
                    <a
                      href={selectedSession.traceUrl}
                      download={`trace-${selectedRun.run_id}.zip`}
                      className="flex items-center gap-1 text-xs text-cobweb-400 hover:text-cobweb-300 transition-colors"
                    >
                      <Download size={11} />
                      {t("silk.network.downloadTrace")}
                    </a>
                  )}
                </div>
                <div className="grid grid-cols-4 gap-2">
                  {[
                    {
                      label: t("silk.stats.passed"),
                      value: browserResult?.passed ?? selectedRun.passed,
                      color: "text-emerald-400",
                    },
                    {
                      label: t("silk.stats.failed"),
                      value: browserResult?.failed ?? selectedRun.failed,
                      color: "text-red-400",
                    },
                    {
                      label: t("silk.stats.errors"),
                      value: browserResult?.errors ?? selectedRun.errors,
                      color: "text-amber-400",
                    },
                    {
                      label: t("silk.stats.duration"),
                      value: durationLabel(browserResult?.duration_ms ?? selectedRun.duration_ms),
                      color: "text-cobweb-300",
                    },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="rounded bg-neutral-900 p-2 flex flex-col items-center">
                      <span className={`text-base font-bold ${color}`}>{value}</span>
                      <span className="text-[10px] text-neutral-500">{label}</span>
                    </div>
                  ))}
                </div>

                {/* Stderr */}
                {(browserResult?.stderr_tail || selectedRun.stderr_tail) && (
                  <div className="mt-3">
                    <span className="text-[10px] uppercase text-neutral-500 tracking-wider">
                      {t("silk.stats.stderr")}
                    </span>
                    <pre className="mt-1 max-h-28 overflow-y-auto rounded bg-neutral-950 p-2 text-[10px] text-neutral-400 font-mono whitespace-pre-wrap">
                      {browserResult?.stderr_tail ?? selectedRun.stderr_tail}
                    </pre>
                  </div>
                )}
              </div>
            )}

            {/* Stats row — demo / history run (no live SilkRunOutput) */}
            {!selectedRun && selectedHistoryRun && (
              <div className="border-b border-neutral-800 px-4 py-3">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-semibold text-neutral-300">
                    {selectedHistoryRun.spec_path.split("/").pop()}
                  </span>
                  <StatusIcon status={selectedHistoryRun.status} size={10} />
                  {demoMode && (
                    <span className="text-[9px] text-cobweb-500 border border-cobweb-800/50 rounded px-1">
                      demo data
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-4 gap-2">
                  {(() => {
                    const specs = activeJsonReport
                      ? (activeJsonReport.suites as Array<Record<string,unknown>> | undefined ?? [])
                          .flatMap((s) => (s.specs as Array<Record<string,unknown>> | undefined ?? []))
                      : [];
                    const passed = specs.filter((s) => s.ok).length;
                    const failed = specs.filter((s) => !s.ok).length;
                    return [
                      { label: t("silk.stats.passed"), value: passed, color: "text-emerald-400" },
                      { label: t("silk.stats.failed"), value: failed, color: "text-red-400" },
                      { label: t("silk.stats.errors"), value: 0, color: "text-amber-400" },
                      {
                        label: t("silk.stats.duration"),
                        value: durationLabel(selectedHistoryRun.duration_ms),
                        color: "text-cobweb-300",
                      },
                    ];
                  })().map(({ label, value, color }) => (
                    <div key={label} className="rounded bg-neutral-900 p-2 flex flex-col items-center">
                      <span className={`text-base font-bold ${color}`}>{value}</span>
                      <span className="text-[10px] text-neutral-500">{label}</span>
                    </div>
                  ))}
                </div>
                {demoStderr && (
                  <div className="mt-3">
                    <span className="text-[10px] uppercase text-neutral-500 tracking-wider">
                      {t("silk.stats.stderr")}
                    </span>
                    <pre className="mt-1 max-h-28 overflow-y-auto rounded bg-neutral-950 p-2 text-[10px] text-neutral-400 font-mono whitespace-pre-wrap">
                      {demoStderr}
                    </pre>
                  </div>
                )}
              </div>
            )}

            {!selectedRun && !selectedHistoryRun && (
              <div className="flex flex-1 items-center justify-center text-xs text-neutral-600">
                {t("silk.stats.selectRun")}
              </div>
            )}
          </div>

          {/* Right sidebar — tabs */}
          <div className="flex w-72 shrink-0 flex-col border-l border-neutral-800">
            {/* Tab headers — cobweb (cyan) accent on active */}
            <div className="flex border-b border-neutral-800 overflow-x-auto">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-1 px-2.5 py-2 text-[10px] font-medium whitespace-nowrap transition-colors ${
                    activeTab === tab.id
                      ? "border-b-2 border-cobweb-500 text-cobweb-300"
                      : "text-neutral-500 hover:text-neutral-300"
                  }`}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="flex-1 min-h-0 overflow-hidden">
              {activeTab === "timeline" && (
                <StepTimeline report={activeJsonReport} />
              )}

              {activeTab === "a11y" && (
                <A11yPanel violations={a11yViolations} />
              )}

              {activeTab === "console" && (
                <div className="p-2 overflow-y-auto h-full">
                  {(browserResult?.stderr_tail || selectedRun?.stderr_tail || demoStderr) ? (
                    <pre className="text-[10px] font-mono text-neutral-400 whitespace-pre-wrap">
                      {browserResult?.stderr_tail ?? selectedRun?.stderr_tail ?? demoStderr}
                    </pre>
                  ) : (
                    <div className="flex items-center justify-center h-24 text-xs text-neutral-600">
                      {t("silk.console.noOutput")}
                    </div>
                  )}
                </div>
              )}

              {activeTab === "network" && (() => {
                if (activeNetworkEntries.length === 0) {
                  return (
                    <div className="flex items-center justify-center h-full text-xs text-neutral-600 flex-col gap-2">
                      <Globe size={20} className="text-neutral-700" />
                      {activeJsonReport ? t("silk.network.noEntries.noReport") : t("silk.network.noEntries.inTrace")}
                      {selectedSession?.traceUrl && (
                        <a
                          href={selectedSession.traceUrl}
                          download={`trace-${selectedRun?.run_id}.zip`}
                          className="flex items-center gap-1 text-xs text-cobweb-400 hover:text-cobweb-300"
                        >
                          <Download size={11} />
                          {t("silk.network.downloadTrace")}
                        </a>
                      )}
                    </div>
                  );
                }
                return (
                  <div className="flex flex-col overflow-y-auto h-full">
                    <div className="px-3 py-1.5 border-b border-neutral-800 text-[10px] text-neutral-500">
                      {t("silk.network.requestCount", { n: activeNetworkEntries.length })}
                    </div>
                    {activeNetworkEntries.map((entry, i) => {
                      const req = entry.request ?? {};
                      const res = (entry as Record<string, unknown>).response as Record<string, unknown> | undefined;
                      const status = res?.status as number | undefined;
                      const statusColor = !status ? "text-neutral-500"
                        : status < 300 ? "text-cobweb-400"
                        : status < 400 ? "text-amber-400"
                        : "text-red-400";
                      return (
                        <div key={i} className="flex items-center gap-2 px-3 py-1.5 border-b border-neutral-900 text-[10px] hover:bg-neutral-900 min-w-0">
                          <span className="shrink-0 w-8 font-mono text-neutral-400">{req.method ?? "?"}</span>
                          <span className={`shrink-0 w-8 font-mono ${statusColor}`}>{status ?? ""}</span>
                          <span className="flex-1 text-neutral-300 truncate font-mono" title={String(req.url ?? "")}>
                            {String(req.url ?? "")}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                );
              })()}

              {activeTab === "screenshots" && (() => {
                // Demo screenshots (data-URIs) take priority in browser-demo mode.
                if (activeDemoScreenshots.length > 0) {
                  return (
                    <div className="flex flex-col gap-2 overflow-y-auto p-2 h-full">
                      {activeDemoScreenshots.map((src, i) => {
                        const labels = [
                          "screenshot-01.png",
                          "screenshot-02.png",
                          "screenshot-03.png",
                        ];
                        const label = labels[i] ?? `screenshot-${String(i + 1).padStart(2, "0")}.png`;
                        return (
                          <div key={i} className="rounded border border-cobweb-900/40 bg-neutral-900 p-2">
                            <div className="flex items-center gap-2 mb-1.5">
                              <span className="text-[10px] text-cobweb-500 font-mono truncate flex-1">
                                {label}
                              </span>
                            </div>
                            <img
                              src={src}
                              alt={`demo-screenshot-${i}`}
                              className="w-full rounded object-contain max-h-48 bg-neutral-950 border border-neutral-800"
                            />
                          </div>
                        );
                      })}
                    </div>
                  );
                }

                if (activeRealScreenshots.length === 0) {
                  return (
                    <div className="flex items-center justify-center h-full text-xs text-neutral-600 flex-col gap-2">
                      <Image size={20} className="text-neutral-700" />
                      {activeJsonReport ? t("silk.screenshots.none.noReport") : t("silk.screenshots.none.captured")}
                    </div>
                  );
                }
                return (
                  <div className="flex flex-col gap-2 overflow-y-auto p-2 h-full">
                    {activeRealScreenshots.map((p, i) => (
                      <div key={i} className="rounded border border-neutral-800 bg-neutral-900 p-2">
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                          <span className="text-[10px] text-neutral-400 font-mono truncate flex-1" title={p}>
                            {p.split("/").pop() ?? p}
                          </span>
                          <a
                            href={`file://${p}`}
                            target="_blank"
                            rel="noreferrer"
                            title={p}
                            className="shrink-0 text-neutral-500 hover:text-cobweb-400 transition-colors"
                          >
                            <ExternalLink size={11} />
                          </a>
                        </div>
                        <img
                          src={`file://${p}`}
                          alt={`screenshot-${i}`}
                          className="w-full rounded object-contain max-h-48 bg-neutral-950"
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display = "none";
                          }}
                        />
                      </div>
                    ))}
                  </div>
                );
              })()}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
