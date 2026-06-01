"""Dev-mode seed data for Theridion Eyes sidecar.

Seeds the local storage on first run so the History panel and trace tabs are
populated without executing any real tests.  Idempotent: if silk_runs already
has rows, or collections already exist, nothing is written.

Call ``maybe_seed()`` from the FastAPI lifespan after the DB schema is
initialised.  The seed is gated to the real home directory (``~/.theridion``);
when tests override ``THERIDION_HOME`` via env-var the fake tmp_path is always
empty so this code is never reached (``maybe_seed()`` returns immediately when
the DB already has rows or when it detects a non-default home).

v2 additions (marker ``.seed_v2``):
- Environments (Production, Staging, Local-dev) with realistic variables
- Global variables (globals.json)
- Request history entries (history.jsonl)
- Screenshot PNGs seeded into silk/runs/<id>/screenshots/ (linked in runs)
- Visual-regression baseline PNGs + .approved.json metadata
"""

from __future__ import annotations

import json
import logging
import sqlite3
import struct
import uuid
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SEED_MARKER = ".silk_seed_v1"  # Written to silk dir after first seed run.
_SEED_MARKER_V2 = ".seed_v2"    # Written to home dir after v2 seed run.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _silk_db_path() -> Path:
    """Return the silk/history.db path, *without* triggering module import loops."""
    from . import storage as _storage
    d = _storage.home_dir() / "silk"
    d.mkdir(parents=True, exist_ok=True)
    return d / "history.db"


def _silk_dir() -> Path:
    from . import storage as _storage
    d = _storage.home_dir() / "silk"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _has_existing_runs() -> bool:
    db = _silk_db_path()
    if not db.exists():
        return False
    try:
        with sqlite3.connect(str(db)) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM silk_runs"
            ).fetchone()
            return bool(row and row[0] > 0)
    except sqlite3.OperationalError:
        # Table does not exist yet — DB is blank.
        return False


def _ts(days_ago: float, hour: int = 10, minute: int = 0) -> str:
    """Return an ISO-8601 UTC timestamp n days in the past."""
    base = datetime.now(tz=timezone.utc).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    return (base - timedelta(days=days_ago)).isoformat()


# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------

# Stable UUIDs so idempotency is trivially checkable.
_RUN_IDS = [
    "a1b2c3d4-0001-0001-0001-000000000001",
    "a1b2c3d4-0001-0001-0001-000000000002",
    "a1b2c3d4-0001-0001-0001-000000000003",
    "a1b2c3d4-0001-0001-0001-000000000004",
    "a1b2c3d4-0001-0001-0001-000000000005",
    "a1b2c3d4-0001-0001-0001-000000000006",
    "a1b2c3d4-0001-0001-0001-000000000007",
    "a1b2c3d4-0001-0001-0001-000000000008",
    "a1b2c3d4-0001-0001-0001-000000000009",
    "a1b2c3d4-0001-0001-0001-000000000010",
]

_SPECS = [
    "tests/auth/login.spec.ts",
    "tests/auth/logout.spec.ts",
    "tests/dashboard/overview.spec.ts",
    "tests/dashboard/overview.spec.ts",
    "tests/checkout/payment-flow.spec.ts",
    "tests/checkout/payment-flow.spec.ts",
    "tests/profile/settings.spec.ts",
    "tests/a11y/homepage-axe.spec.ts",
    "tests/a11y/homepage-axe.spec.ts",
    "tests/auth/login.spec.ts",
]


def _make_json_report(
    spec_title: str,
    test_cases: list[dict],
    browser: str = "chromium",
) -> dict:
    """Build a minimal Playwright JSON report compatible with StepTimeline."""
    specs = []
    for tc in test_cases:
        specs.append({
            "title": tc["title"],
            "ok": tc.get("ok", True),
            "tests": [
                {
                    "status": "passed" if tc.get("ok", True) else "failed",
                    "results": [
                        {
                            "duration": tc.get("duration", 500),
                            **({"error": {"message": tc["error"]}} if not tc.get("ok", True) else {}),
                            "attachments": tc.get("attachments", []),
                        }
                    ],
                }
            ],
        })
    return {
        "stats": {
            "expected": sum(1 for t in test_cases if t.get("ok", True)),
            "unexpected": sum(1 for t in test_cases if not t.get("ok", True)),
            "skipped": sum(1 for t in test_cases if t.get("skipped", False)),
            "duration": sum(t.get("duration", 500) for t in test_cases),
        },
        "suites": [
            {
                "title": spec_title,
                "specs": specs,
                "suites": [],
            }
        ],
    }


def _axe_attachment(violations: list[dict]) -> dict:
    """Build an axe-results.json attachment payload."""
    return {
        "name": "axe-results.json",
        "contentType": "application/json",
        "body": json.dumps({"violations": violations}),
    }


def _network_attachment(entries: list[dict]) -> dict:
    """Build a network.json HAR-style attachment payload."""
    return {
        "name": "network.json",
        "contentType": "application/json",
        "body": json.dumps({"log": {"entries": entries}}),
    }


# ---------------------------------------------------------------------------
# The actual seed rows
# ---------------------------------------------------------------------------

def _build_seed_runs() -> list[dict]:
    """Return ordered list of run dicts (newest first matches DB ordering)."""

    # ---------------------------------------------------------------------------
    # Rich network entries used across multiple runs
    # ---------------------------------------------------------------------------
    _net_dashboard = [
        {"request": {"method": "GET",  "url": "https://app.acmecorp.io/api/v2/metrics?range=7d",   "headers": {"Authorization": "Bearer tok-prod"}}, "response": {"status": 200, "bodySize": 2840, "timings": {"wait": 42, "receive": 18}, "content": {"mimeType": "application/json"}}},
        {"request": {"method": "GET",  "url": "https://app.acmecorp.io/api/v2/users/active",       "headers": {"Authorization": "Bearer tok-prod"}}, "response": {"status": 200, "bodySize": 1120, "timings": {"wait": 31, "receive": 9},  "content": {"mimeType": "application/json"}}},
        {"request": {"method": "GET",  "url": "https://app.acmecorp.io/api/v2/notifications?unread=1", "headers": {"Authorization": "Bearer tok-prod"}}, "response": {"status": 200, "bodySize": 580, "timings": {"wait": 22, "receive": 6}, "content": {"mimeType": "application/json"}}},
        {"request": {"method": "POST", "url": "https://analytics.acmecorp.io/collect",             "headers": {"Content-Type": "application/json"}},  "response": {"status": 204, "bodySize": 0,    "timings": {"wait": 8,  "receive": 2},  "content": {"mimeType": "text/plain"}}},
        {"request": {"method": "GET",  "url": "https://cdn.acmecorp.io/assets/dashboard.css",      "headers": {}},                                    "response": {"status": 200, "bodySize": 48200,"timings": {"wait": 5,  "receive": 12}, "content": {"mimeType": "text/css"}}},
        {"request": {"method": "GET",  "url": "https://cdn.acmecorp.io/assets/charts.bundle.js",   "headers": {}},                                    "response": {"status": 200, "bodySize": 186000,"timings": {"wait": 8,  "receive": 62}, "content": {"mimeType": "application/javascript"}}},
        {"request": {"method": "GET",  "url": "https://app.acmecorp.io/api/v2/feature-flags",      "headers": {"Authorization": "Bearer tok-prod"}}, "response": {"status": 200, "bodySize": 320,  "timings": {"wait": 15, "receive": 4},  "content": {"mimeType": "application/json"}}},
        {"request": {"method": "GET",  "url": "https://app.acmecorp.io/api/v2/revenue/chart?period=30d","headers": {"Authorization": "Bearer tok-prod"}}, "response": {"status": 200, "bodySize": 4200, "timings": {"wait": 68, "receive": 22}, "content": {"mimeType": "application/json"}}},
    ]
    _net_checkout = [
        {"request": {"method": "GET",  "url": "https://app.acmecorp.io/api/v2/cart",               "headers": {"Authorization": "Bearer tok-prod"}}, "response": {"status": 200, "bodySize": 860,  "timings": {"wait": 38, "receive": 11}, "content": {"mimeType": "application/json"}}},
        {"request": {"method": "POST", "url": "https://api.stripe.com/v1/payment_intents",         "headers": {"Content-Type": "application/x-www-form-urlencoded"}}, "response": {"status": 200, "bodySize": 1680, "timings": {"wait": 210, "receive": 45}, "content": {"mimeType": "application/json"}}},
        {"request": {"method": "GET",  "url": "https://app.acmecorp.io/api/v2/orders/latest",      "headers": {"Authorization": "Bearer tok-prod"}}, "response": {"status": 200, "bodySize": 720,  "timings": {"wait": 29, "receive": 8},  "content": {"mimeType": "application/json"}}},
        {"request": {"method": "POST", "url": "https://app.acmecorp.io/api/v2/analytics/funnel",   "headers": {"Content-Type": "application/json"}},  "response": {"status": 201, "bodySize": 0,    "timings": {"wait": 12, "receive": 3},  "content": {"mimeType": "text/plain"}}},
        {"request": {"method": "GET",  "url": "https://js.stripe.com/v3/",                         "headers": {}},                                    "response": {"status": 200, "bodySize": 95000,"timings": {"wait": 15, "receive": 38}, "content": {"mimeType": "application/javascript"}}},
        {"request": {"method": "POST", "url": "https://app.acmecorp.io/api/v2/checkout/validate",  "headers": {"Content-Type": "application/json"}},  "response": {"status": 200, "bodySize": 140,  "timings": {"wait": 55, "receive": 4},  "content": {"mimeType": "application/json"}}},
    ]
    _net_auth = [
        {"request": {"method": "POST", "url": "https://app.acmecorp.io/api/v2/auth/login",         "headers": {"Content-Type": "application/json"}},  "response": {"status": 200, "bodySize": 480,  "timings": {"wait": 112, "receive": 8}, "content": {"mimeType": "application/json"}}},
        {"request": {"method": "GET",  "url": "https://app.acmecorp.io/api/v2/auth/session",       "headers": {"Authorization": "Bearer tok-prod"}}, "response": {"status": 200, "bodySize": 260,  "timings": {"wait": 18, "receive": 5},  "content": {"mimeType": "application/json"}}},
        {"request": {"method": "GET",  "url": "https://app.acmecorp.io/api/v2/users/me",           "headers": {"Authorization": "Bearer tok-prod"}}, "response": {"status": 200, "bodySize": 380,  "timings": {"wait": 21, "receive": 6},  "content": {"mimeType": "application/json"}}},
        {"request": {"method": "POST", "url": "https://analytics.acmecorp.io/collect",             "headers": {"Content-Type": "application/json"}},  "response": {"status": 204, "bodySize": 0,    "timings": {"wait": 7,  "receive": 2},  "content": {"mimeType": "text/plain"}}},
        {"request": {"method": "GET",  "url": "https://app.acmecorp.io/api/v2/feature-flags",      "headers": {"Authorization": "Bearer tok-prod"}}, "response": {"status": 200, "bodySize": 320,  "timings": {"wait": 14, "receive": 4},  "content": {"mimeType": "application/json"}}},
    ]

    # ---------------------------------------------------------------------------
    # Rich a11y violation sets
    # ---------------------------------------------------------------------------
    _axe_homepage_v1 = [
        {"id": "color-contrast",      "impact": "serious",  "description": "Elements must have sufficient color contrast (4.5:1 for normal text)", "nodes": [{"target": [".hero-subtitle"]}, {"target": [".nav-link--active"]}]},
        {"id": "image-alt",           "impact": "critical", "description": "Images must have alternative text", "nodes": [{"target": ["img.partner-logo-3"]}, {"target": ["img.hero-bg"]}]},
        {"id": "link-name",           "impact": "serious",  "description": "Links must have discernible text", "nodes": [{"target": ["a.icon-only-link"]}]},
        {"id": "aria-required-attr",  "impact": "critical", "description": "Required ARIA attributes must be provided", "nodes": [{"target": ["[role=progressbar]"]}]},
    ]
    _axe_homepage_v2 = [
        {"id": "color-contrast",      "impact": "serious",  "description": "Elements must have sufficient color contrast", "nodes": [{"target": [".hero-subtitle"]}]},
        {"id": "image-alt",           "impact": "critical", "description": "Images must have alternative text", "nodes": [{"target": ["img.logo"]}]},
    ]
    _axe_homepage_resolved = [
        {"id": "aria-required-attr",  "impact": "critical", "description": "Required ARIA attributes must be provided", "nodes": [{"target": ["[role=progressbar]"]}]},
    ]

    # ---------------------------------------------------------------------------
    # Run 10 — today (CI/PR #847): full login suite, chromium, all 7 tests passed
    # ---------------------------------------------------------------------------
    run10 = {
        "id": _RUN_IDS[9],
        "spec_path": "tests/auth/login.spec.ts",
        "exit_code": 0,
        "duration_ms": 6840,
        "started_at": _ts(0.02, hour=9, minute=15),
        "browsers": ["chromium"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": "",
        "json_report": _make_json_report(
            "Login flow",
            [
                {"title": "renders login page with all form fields",          "ok": True, "duration": 480,
                 "attachments": [_network_attachment(_net_auth)]},
                {"title": "logs in with valid credentials → dashboard",       "ok": True, "duration": 1340},
                {"title": "shows inline error on wrong password",             "ok": True, "duration": 890},
                {"title": "shows inline error on unregistered email",         "ok": True, "duration": 720},
                {"title": "redirects to returnTo path after login",           "ok": True, "duration": 940},
                {"title": "rate-limits after 5 failed attempts",              "ok": True, "duration": 1120},
                {"title": "remember-me checkbox persists session 30 days",    "ok": True, "duration": 1350},
            ],
        ),
    }

    # ---------------------------------------------------------------------------
    # Run 9 — today: homepage a11y full audit, chromium+firefox, 2 violations fixed vs baseline
    # ---------------------------------------------------------------------------
    run9 = {
        "id": _RUN_IDS[8],
        "spec_path": "tests/a11y/homepage-axe.spec.ts",
        "exit_code": 0,
        "duration_ms": 9420,
        "started_at": _ts(0.1, hour=8, minute=42),
        "browsers": ["chromium", "firefox"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 2,
        "stderr_tail": "",
        "json_report": _make_json_report(
            "Homepage accessibility audit",
            [
                {
                    "title": "homepage passes axe audit (WCAG 2.1 AA)",
                    "ok": True,
                    "duration": 2840,
                    "attachments": [_axe_attachment(_axe_homepage_v2)],
                },
                {"title": "nav links are keyboard-accessible (Tab order)",          "ok": True, "duration": 960},
                {"title": "skip-to-content link appears on first Tab press",        "ok": True, "duration": 780},
                {"title": "hero CTA is reachable and activatable via keyboard",     "ok": True, "duration": 640},
                {"title": "footer links have sufficient target size (≥44×44px)",    "ok": True, "duration": 520},
                {"title": "modal traps focus and dismisses with Escape",            "ok": True, "duration": 1180},
                {"title": "colour-scheme toggle preserves contrast ratios",         "ok": True, "duration": 900},
            ],
        ),
    }

    # ---------------------------------------------------------------------------
    # Run 8 — yesterday (PR #841 regression): payment flow, chromium, 1 test FAILED
    # ---------------------------------------------------------------------------
    run8 = {
        "id": _RUN_IDS[7],
        "spec_path": "tests/checkout/payment-flow.spec.ts",
        "exit_code": 1,
        "duration_ms": 18650,
        "started_at": _ts(1.0, hour=16, minute=5),
        "browsers": ["chromium"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": (
            "  1 failed\n"
            "  ● Payment flow › completes Stripe 3DS checkout\n"
            "\n"
            "    TimeoutError: waiting for selector '.stripe-success-banner' failed\n"
            "    at Object.waitForSelector (playwright-core/lib/client/page.ts:123)\n"
            "    Expected: visible\n"
            "    Received: hidden after 15000ms\n"
            "\n"
            "  Note: Stripe test-mode 3DS challenge iframe was not dismissed correctly."
        ),
        "json_report": _make_json_report(
            "Payment flow",
            [
                {"title": "loads checkout page with order summary",             "ok": True, "duration": 1020,
                 "attachments": [_network_attachment(_net_checkout)]},
                {"title": "applies promo code SAVE20 successfully",             "ok": True, "duration": 1480},
                {"title": "fills card details in Stripe iframe",                "ok": True, "duration": 2200},
                {"title": "completes Stripe 3DS checkout",                      "ok": False, "duration": 15000,
                 "error": "TimeoutError: waiting for selector '.stripe-success-banner' failed: timeout 15000ms exceeded"},
                {"title": "shows order confirmation with order ID",             "ok": True, "duration": 480},
                {"title": "sends order confirmation email (webhook verified)",  "ok": True, "duration": 2870},
            ],
        ),
    }

    # ---------------------------------------------------------------------------
    # Run 7 — yesterday: profile settings suite, chromium+webkit, all passed
    # ---------------------------------------------------------------------------
    run7 = {
        "id": _RUN_IDS[6],
        "spec_path": "tests/profile/settings.spec.ts",
        "exit_code": 0,
        "duration_ms": 11240,
        "started_at": _ts(1.0, hour=14, minute=22),
        "browsers": ["chromium", "webkit"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": "",
        "json_report": _make_json_report(
            "Profile settings",
            [
                {"title": "renders account settings page",                     "ok": True, "duration": 680},
                {"title": "updates display name and persists across reload",    "ok": True, "duration": 1180},
                {"title": "changes email → receives verification link",        "ok": True, "duration": 2100},
                {"title": "uploads avatar (JPEG, < 2 MB)",                     "ok": True, "duration": 1560},
                {"title": "enables 2FA → shows QR code",                       "ok": True, "duration": 1350},
                {"title": "saves notification preferences (email + push)",      "ok": True, "duration": 920},
                {"title": "deletes account flow shows confirmation dialog",     "ok": True, "duration": 1040},
                {"title": "connected OAuth providers list is populated",        "ok": True, "duration": 780},
            ],
        ),
    }

    # ---------------------------------------------------------------------------
    # Run 6 — 2 days ago: payment flow, chromium+firefox+webkit, full pass (post-fix)
    # ---------------------------------------------------------------------------
    run6 = {
        "id": _RUN_IDS[5],
        "spec_path": "tests/checkout/payment-flow.spec.ts",
        "exit_code": 0,
        "duration_ms": 38720,
        "started_at": _ts(2.0, hour=11, minute=30),
        "browsers": ["chromium", "firefox", "webkit"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": "",
        "json_report": _make_json_report(
            "Payment flow (all browsers — release/2.8.0)",
            [
                {"title": "loads checkout page with order summary",             "ok": True, "duration": 980,
                 "attachments": [_network_attachment(_net_checkout)]},
                {"title": "applies promo code SAVE20 successfully",             "ok": True, "duration": 1320},
                {"title": "fills card details in Stripe iframe",                "ok": True, "duration": 2180},
                {"title": "completes Stripe 3DS checkout",                      "ok": True, "duration": 4250},
                {"title": "shows order confirmation with order ID",             "ok": True, "duration": 510},
                {"title": "sends order confirmation email (webhook verified)",  "ok": True, "duration": 2640},
            ],
        ),
    }

    # ---------------------------------------------------------------------------
    # Run 5 — 3 days ago: dashboard full suite, chromium+firefox, all 8 passed
    # ---------------------------------------------------------------------------
    run5 = {
        "id": _RUN_IDS[4],
        "spec_path": "tests/dashboard/overview.spec.ts",
        "exit_code": 0,
        "duration_ms": 14380,
        "started_at": _ts(3.0, hour=10, minute=0),
        "browsers": ["chromium", "firefox"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": "",
        "json_report": _make_json_report(
            "Dashboard overview",
            [
                {"title": "loads dashboard for authenticated user",             "ok": True, "duration": 1260,
                 "attachments": [_network_attachment(_net_dashboard)]},
                {"title": "displays all 4 KPI metric cards",                   "ok": True, "duration": 740},
                {"title": "revenue chart renders with 30-day data",             "ok": True, "duration": 1080},
                {"title": "notifications bell shows unread count badge",        "ok": True, "duration": 420},
                {"title": "date range picker updates chart on change",          "ok": True, "duration": 1640},
                {"title": "export CSV button triggers download",                "ok": True, "duration": 1180},
                {"title": "team activity feed lists last 10 events",            "ok": True, "duration": 860},
                {"title": "quick-action buttons are keyboard accessible",       "ok": True, "duration": 560},
            ],
        ),
    }

    # ---------------------------------------------------------------------------
    # Run 4 — 5 days ago: logout suite, chromium+firefox, all passed
    # ---------------------------------------------------------------------------
    run4 = {
        "id": _RUN_IDS[3],
        "spec_path": "tests/auth/logout.spec.ts",
        "exit_code": 0,
        "duration_ms": 5840,
        "started_at": _ts(5.0, hour=15, minute=48),
        "browsers": ["chromium", "firefox"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": "",
        "json_report": _make_json_report(
            "Logout flow",
            [
                {"title": "clicking logout clears session cookies",             "ok": True, "duration": 890,
                 "attachments": [_network_attachment(_net_auth)]},
                {"title": "redirects to /login after sign-out",                "ok": True, "duration": 640},
                {"title": "protected routes require re-authentication",         "ok": True, "duration": 760},
                {"title": "refresh token is revoked on logout",                 "ok": True, "duration": 920},
                {"title": "SSO session terminated via back-channel",            "ok": True, "duration": 1380},
            ],
        ),
    }

    # ---------------------------------------------------------------------------
    # Run 3 — 7 days ago: dashboard, chromium, FAILED — 2 tests (pre-fix regression)
    # ---------------------------------------------------------------------------
    run3 = {
        "id": _RUN_IDS[2],
        "spec_path": "tests/dashboard/overview.spec.ts",
        "exit_code": 1,
        "duration_ms": 15800,
        "started_at": _ts(7.0, hour=9, minute=5),
        "browsers": ["chromium"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": (
            "  2 failed\n"
            "  ● Dashboard overview › revenue chart renders with 30-day data\n"
            "    Error: expect(received).toBeVisible()\n"
            "    Expected: visible\n"
            "    Received: <div class='recharts-responsive-container' style='display: none'>\n"
            "\n"
            "  ● Dashboard overview › notifications bell shows unread count badge\n"
            "    Error: expected text content '0' to equal '4'\n"
            "    Received: '0'\n"
            "    Expected: '4'"
        ),
        "json_report": _make_json_report(
            "Dashboard overview",
            [
                {"title": "loads dashboard for authenticated user",             "ok": True, "duration": 1100,
                 "attachments": [_network_attachment(_net_dashboard)]},
                {"title": "displays all 4 KPI metric cards",                   "ok": True, "duration": 680},
                {
                    "title": "revenue chart renders with 30-day data",
                    "ok": False,
                    "duration": 8000,
                    "error": "Error: expect(received).toBeVisible() — recharts-responsive-container not visible",
                },
                {
                    "title": "notifications bell shows unread count badge",
                    "ok": False,
                    "duration": 1200,
                    "error": "Error: expected text content '0' to equal '4'",
                },
                {"title": "date range picker updates chart on change",          "ok": True, "duration": 1640},
                {"title": "export CSV button triggers download",                "ok": True, "duration": 1180},
            ],
        ),
    }

    # ---------------------------------------------------------------------------
    # Run 2 — 10 days ago: full a11y homepage audit, chromium, 4 violations (pre-fix)
    # ---------------------------------------------------------------------------
    run2 = {
        "id": _RUN_IDS[1],
        "spec_path": "tests/a11y/homepage-axe.spec.ts",
        "exit_code": 0,
        "duration_ms": 7620,
        "started_at": _ts(10.0, hour=11, minute=20),
        "browsers": ["chromium"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 4,
        "stderr_tail": "",
        "json_report": _make_json_report(
            "Homepage accessibility audit",
            [
                {
                    "title": "homepage passes axe audit (WCAG 2.1 AA)",
                    "ok": True,
                    "duration": 3240,
                    "attachments": [_axe_attachment(_axe_homepage_v1)],
                },
                {"title": "nav links are keyboard-accessible (Tab order)",          "ok": True, "duration": 1040},
                {"title": "skip-to-content link appears on first Tab press",        "ok": True, "duration": 820},
                {"title": "hero CTA is reachable and activatable via keyboard",     "ok": True, "duration": 680},
            ],
        ),
    }

    # ---------------------------------------------------------------------------
    # Run 1 — 14 days ago: login, chromium, passed (baseline — branch main)
    # ---------------------------------------------------------------------------
    run1 = {
        "id": _RUN_IDS[0],
        "spec_path": "tests/auth/login.spec.ts",
        "exit_code": 0,
        "duration_ms": 5940,
        "started_at": _ts(14.0, hour=10, minute=0),
        "browsers": ["chromium"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": "",
        "json_report": _make_json_report(
            "Login flow",
            [
                {"title": "renders login page with all form fields",          "ok": True, "duration": 460,
                 "attachments": [_network_attachment(_net_auth)]},
                {"title": "logs in with valid credentials → dashboard",       "ok": True, "duration": 1280},
                {"title": "shows inline error on wrong password",             "ok": True, "duration": 840},
                {"title": "shows inline error on unregistered email",         "ok": True, "duration": 700},
                {"title": "redirects to returnTo path after login",           "ok": True, "duration": 860},
                {"title": "rate-limits after 5 failed attempts",              "ok": True, "duration": 1100},
            ],
        ),
    }

    # Return newest-first so INSERT order produces correct DESC ordering.
    return [run10, run9, run8, run7, run6, run5, run4, run3, run2, run1]


# ---------------------------------------------------------------------------
# Seed: spec files
# ---------------------------------------------------------------------------

_SPEC_SOURCES: dict[str, str] = {
    "tests/auth/login.spec.ts": """\
import { test, expect } from '@playwright/test';
import { captureNetworkHAR } from '../helpers/network';

test.describe('Login flow', () => {
  test.use({ baseURL: process.env.BASE_URL ?? 'https://app.acmecorp.io' });

  test('renders login page with all form fields', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByRole('heading', { name: 'Sign in to Acme' })).toBeVisible();
    await expect(page.getByLabel('Email address')).toBeVisible();
    await expect(page.getByLabel('Password')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeEnabled();
    await expect(page.getByTestId('oauth-google-btn')).toBeVisible();
  });

  test('logs in with valid credentials → dashboard', async ({ page }) => {
    await captureNetworkHAR(page, 'network.json');
    await page.goto('/login');
    await page.getByLabel('Email address').fill(process.env.TEST_USER ?? 'alice@acmecorp.io');
    await page.getByLabel('Password').fill(process.env.TEST_PASS ?? 's3cur3P@ss!');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\\/dashboard/);
    await expect(page.getByTestId('user-avatar')).toBeVisible();
  });

  test('shows inline error on wrong password', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('Email address').fill('alice@acmecorp.io');
    await page.getByLabel('Password').fill('wr0ng-p@ss');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByTestId('error-banner')).toHaveText(/invalid credentials/i);
    await expect(page).toHaveURL(/\\/login/);
  });

  test('shows inline error on unregistered email', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('Email address').fill('nobody@example.com');
    await page.getByLabel('Password').fill('s3cur3P@ss!');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByTestId('error-banner')).toHaveText(/no account found/i);
  });

  test('redirects to returnTo path after login', async ({ page }) => {
    await page.goto('/login?returnTo=/dashboard/analytics');
    await page.getByLabel('Email address').fill('alice@acmecorp.io');
    await page.getByLabel('Password').fill('s3cur3P@ss!');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\\/dashboard\\/analytics/);
  });

  test('rate-limits after 5 failed attempts', async ({ page }) => {
    await page.goto('/login');
    for (let i = 0; i < 5; i++) {
      await page.getByLabel('Email address').fill('alice@acmecorp.io');
      await page.getByLabel('Password').fill('bad-pass');
      await page.getByRole('button', { name: 'Sign in' }).click();
    }
    await expect(page.getByTestId('rate-limit-notice')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeDisabled();
  });

  test('remember-me checkbox persists session 30 days', async ({ page, context }) => {
    await page.goto('/login');
    await page.getByLabel('Email address').fill('alice@acmecorp.io');
    await page.getByLabel('Password').fill('s3cur3P@ss!');
    await page.getByLabel('Keep me signed in').check();
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\\/dashboard/);
    const cookies = await context.cookies();
    const session = cookies.find((c) => c.name === 'sid');
    expect(session?.expires).toBeGreaterThan(Date.now() / 1000 + 29 * 86_400);
  });
});
""",
    "tests/auth/logout.spec.ts": """\
import { test, expect } from '@playwright/test';
import { captureNetworkHAR } from '../helpers/network';

test.describe('Logout flow', () => {
  test.use({ baseURL: process.env.BASE_URL ?? 'https://app.acmecorp.io' });

  test('clicking logout clears session cookies', async ({ page, context }) => {
    await captureNetworkHAR(page, 'network.json');
    await page.goto('/dashboard');
    await page.getByRole('button', { name: 'Account menu' }).click();
    await page.getByRole('menuitem', { name: 'Sign out' }).click();
    await expect(page).toHaveURL(/\\/login/);
    const cookies = await context.cookies();
    expect(cookies.find((c) => c.name === 'sid')).toBeUndefined();
  });

  test('redirects to /login after sign-out', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByRole('heading', { name: 'Sign in to Acme' })).toBeVisible();
  });

  test('protected routes require re-authentication', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\\/login/);
    await page.goto('/settings');
    await expect(page).toHaveURL(/\\/login/);
  });

  test('refresh token is revoked on logout', async ({ page }) => {
    await page.goto('/dashboard');
    await page.getByRole('button', { name: 'Account menu' }).click();
    await page.getByRole('menuitem', { name: 'Sign out' }).click();
    // Attempt to use the refresh endpoint — should return 401.
    const res = await page.request.post('/api/v2/auth/refresh');
    expect(res.status()).toBe(401);
  });

  test('SSO session terminated via back-channel', async ({ page }) => {
    await page.goto('/dashboard');
    await page.getByRole('button', { name: 'Account menu' }).click();
    await page.getByRole('menuitem', { name: 'Sign out' }).click();
    await expect(page).toHaveURL(/\\/login/);
    await expect(page.getByTestId('logout-success-banner')).toBeVisible();
  });
});
""",
    "tests/dashboard/overview.spec.ts": """\
import { test, expect } from '@playwright/test';
import { captureNetworkHAR } from '../helpers/network';

test.describe('Dashboard overview', () => {
  test.use({ baseURL: process.env.BASE_URL ?? 'https://app.acmecorp.io' });

  test('loads dashboard for authenticated user', async ({ page }) => {
    await captureNetworkHAR(page, 'network.json');
    await page.goto('/dashboard');
    await expect(page.getByTestId('dashboard-root')).toBeVisible();
    await expect(page.getByTestId('sidebar-nav')).toBeVisible();
  });

  test('displays all 4 KPI metric cards', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.getByTestId('metric-total-users')).toBeVisible();
    await expect(page.getByTestId('metric-revenue')).toBeVisible();
    await expect(page.getByTestId('metric-conversions')).toBeVisible();
    await expect(page.getByTestId('metric-churn-rate')).toBeVisible();
  });

  test('revenue chart renders with 30-day data', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.getByTestId('revenue-chart')).toBeVisible();
    const points = page.locator('[data-testid="chart-point"]');
    await expect(points).toHaveCount(30);
  });

  test('notifications bell shows unread count badge', async ({ page }) => {
    await page.goto('/dashboard');
    const badge = page.getByTestId('notification-badge');
    await expect(badge).toBeVisible();
    const count = parseInt(await badge.textContent() ?? '0', 10);
    expect(count).toBeGreaterThan(0);
  });

  test('date range picker updates chart on change', async ({ page }) => {
    await page.goto('/dashboard');
    await page.getByTestId('date-range-picker').click();
    await page.getByRole('option', { name: 'Last 90 days' }).click();
    const points = page.locator('[data-testid="chart-point"]');
    await expect(points).toHaveCount(90);
  });

  test('export CSV button triggers download', async ({ page }) => {
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Export CSV' }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/\\.csv$/);
  });

  test('team activity feed lists last 10 events', async ({ page }) => {
    await page.goto('/dashboard');
    const feed = page.getByTestId('activity-feed');
    await expect(feed).toBeVisible();
    const items = feed.locator('[data-testid="feed-item"]');
    await expect(items).toHaveCount(10);
  });

  test('quick-action buttons are keyboard accessible', async ({ page }) => {
    await page.goto('/dashboard');
    await page.keyboard.press('Tab');
    const focused = page.locator(':focus');
    await expect(focused).toHaveAttribute('data-testid');
  });
});
""",
    "tests/checkout/payment-flow.spec.ts": """\
import { test, expect } from '@playwright/test';
import { captureNetworkHAR } from '../helpers/network';

test.describe('Payment flow', () => {
  test.use({ baseURL: process.env.BASE_URL ?? 'https://app.acmecorp.io' });

  test('loads checkout page with order summary', async ({ page }) => {
    await captureNetworkHAR(page, 'network.json');
    await page.goto('/checkout?item=PRO-12M');
    await expect(page.getByRole('heading', { name: 'Checkout' })).toBeVisible();
    await expect(page.getByTestId('order-summary')).toBeVisible();
    await expect(page.getByTestId('line-item-PRO-12M')).toBeVisible();
  });

  test('applies promo code SAVE20 successfully', async ({ page }) => {
    await page.goto('/checkout?item=PRO-12M');
    await page.getByTestId('promo-code-input').fill('SAVE20');
    await page.getByRole('button', { name: 'Apply' }).click();
    await expect(page.getByTestId('discount-line')).toContainText('−20%');
    await expect(page.getByTestId('total-price')).toBeVisible();
  });

  test('fills card details in Stripe iframe', async ({ page }) => {
    await page.goto('/checkout?item=PRO-12M');
    const stripe = page.frameLocator('iframe[name="stripe-card-element"]');
    await stripe.getByPlaceholder('1234 1234 1234 1234').fill('4242 4242 4242 4242');
    await stripe.getByPlaceholder('MM / YY').fill('12 / 28');
    await stripe.getByPlaceholder('CVC').fill('123');
    await expect(page.getByRole('button', { name: 'Pay now' })).toBeEnabled();
  });

  test('completes Stripe 3DS checkout', async ({ page }) => {
    await page.goto('/checkout?item=PRO-12M&demo=1');
    const stripe = page.frameLocator('iframe[name="stripe-card-element"]');
    await stripe.getByPlaceholder('1234 1234 1234 1234').fill('4000 0025 0000 3155');
    await stripe.getByPlaceholder('MM / YY').fill('12 / 28');
    await stripe.getByPlaceholder('CVC').fill('123');
    await page.getByRole('button', { name: 'Pay now' }).click();
    // Dismiss 3DS challenge
    const challengeFrame = page.frameLocator('iframe[name="stripe-3ds-challenge"]');
    await challengeFrame.getByRole('button', { name: 'Complete' }).click();
    await expect(page.getByTestId('stripe-success-banner')).toBeVisible({ timeout: 15_000 });
  });

  test('shows order confirmation with order ID', async ({ page }) => {
    await page.goto('/checkout/confirmation?order=ORD-20240601-4821');
    await expect(page.getByTestId('order-id')).toHaveText(/ORD-\\d+/);
    await expect(page.getByRole('heading', { name: /order confirmed/i })).toBeVisible();
  });

  test('sends order confirmation email (webhook verified)', async ({ page }) => {
    // Triggers webhook via test helper endpoint.
    const res = await page.request.post('/api/v2/test/trigger-order-email?order=ORD-20240601-4821');
    expect(res.status()).toBe(200);
    const body = await res.json() as { delivered: boolean };
    expect(body.delivered).toBe(true);
  });
});
""",
    "tests/profile/settings.spec.ts": """\
import { test, expect } from '@playwright/test';

test.describe('Profile settings', () => {
  test.use({ baseURL: process.env.BASE_URL ?? 'https://app.acmecorp.io' });

  test('renders account settings page', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Account settings' })).toBeVisible();
    await expect(page.getByTestId('tab-profile')).toBeVisible();
    await expect(page.getByTestId('tab-security')).toBeVisible();
    await expect(page.getByTestId('tab-notifications')).toBeVisible();
  });

  test('updates display name and persists across reload', async ({ page }) => {
    await page.goto('/settings');
    await page.getByLabel('Display name').fill('Alice Mercer');
    await page.getByRole('button', { name: 'Save changes' }).click();
    await expect(page.getByTestId('toast-success')).toHaveText(/saved/i);
    await page.reload();
    await expect(page.getByLabel('Display name')).toHaveValue('Alice Mercer');
  });

  test('changes email → receives verification link', async ({ page }) => {
    await page.goto('/settings');
    await page.getByLabel('Email address').fill('alice.new@acmecorp.io');
    await page.getByRole('button', { name: 'Save changes' }).click();
    await expect(page.getByTestId('email-verify-notice')).toBeVisible();
    await expect(page.getByTestId('email-verify-notice')).toContainText(/verification link sent/i);
  });

  test('uploads avatar (JPEG, < 2 MB)', async ({ page }) => {
    await page.goto('/settings');
    await page.getByTestId('avatar-upload-btn').click();
    await page.getByLabel('Choose file').setInputFiles('tests/fixtures/avatar-512.jpg');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByTestId('avatar-img')).toHaveAttribute('src', /\\/uploads\\//);
  });

  test('enables 2FA → shows QR code', async ({ page }) => {
    await page.goto('/settings/security');
    await page.getByRole('button', { name: 'Enable two-factor auth' }).click();
    await expect(page.getByTestId('2fa-qr-code')).toBeVisible();
    await expect(page.getByTestId('2fa-backup-codes')).toBeVisible();
  });

  test('saves notification preferences (email + push)', async ({ page }) => {
    await page.goto('/settings/notifications');
    await page.getByLabel('Weekly email digest').check();
    await page.getByLabel('Push: new team member').check();
    await page.getByRole('button', { name: 'Save preferences' }).click();
    await expect(page.getByTestId('toast-success')).toBeVisible();
  });

  test('deletes account flow shows confirmation dialog', async ({ page }) => {
    await page.goto('/settings/danger-zone');
    await page.getByRole('button', { name: 'Delete my account' }).click();
    await expect(page.getByRole('dialog', { name: 'Delete account?' })).toBeVisible();
    await expect(page.getByTestId('confirm-delete-input')).toBeVisible();
  });

  test('connected OAuth providers list is populated', async ({ page }) => {
    await page.goto('/settings/security');
    const providers = page.locator('[data-testid="oauth-provider-row"]');
    await expect(providers).toHaveCount(2);
  });
});
""",
    "tests/a11y/homepage-axe.spec.ts": """\
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Homepage accessibility audit', () => {
  test.use({ baseURL: process.env.BASE_URL ?? 'https://app.acmecorp.io' });

  test('homepage passes axe audit (WCAG 2.1 AA)', async ({ page }) => {
    await page.goto('/');
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    // Attach violations JSON for Silk's a11y tab.
    await test.info().attach('axe-results.json', {
      contentType: 'application/json',
      body: JSON.stringify({ violations: results.violations }),
    });
    const critical = results.violations.filter((v) => v.impact === 'critical');
    expect(critical, `Critical violations: ${JSON.stringify(critical)}`).toHaveLength(0);
  });

  test('nav links are keyboard-accessible (Tab order)', async ({ page }) => {
    await page.goto('/');
    await page.keyboard.press('Tab');
    const focused = page.locator(':focus');
    await expect(focused).toHaveAttribute('href');
    const href = await focused.getAttribute('href');
    expect(href).not.toBeNull();
  });

  test('skip-to-content link appears on first Tab press', async ({ page }) => {
    await page.goto('/');
    await page.keyboard.press('Tab');
    await expect(page.getByTestId('skip-to-content')).toBeFocused();
  });

  test('hero CTA is reachable and activatable via keyboard', async ({ page }) => {
    await page.goto('/');
    // Tab through until hero CTA is focused.
    for (let i = 0; i < 10; i++) {
      const focused = page.locator(':focus');
      const testId = await focused.getAttribute('data-testid');
      if (testId === 'hero-cta') break;
      await page.keyboard.press('Tab');
    }
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\\/(signup|register)/);
  });

  test('footer links have sufficient target size (≥44×44px)', async ({ page }) => {
    await page.goto('/');
    const footerLinks = page.locator('footer a');
    const count = await footerLinks.count();
    for (let i = 0; i < count; i++) {
      const box = await footerLinks.nth(i).boundingBox();
      if (box) {
        expect(box.width * box.height).toBeGreaterThanOrEqual(44 * 8);
      }
    }
  });

  test('modal traps focus and dismisses with Escape', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('signup-modal-trigger').click();
    const modal = page.getByRole('dialog');
    await expect(modal).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(modal).not.toBeVisible();
  });

  test('colour-scheme toggle preserves contrast ratios', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('theme-toggle').click();
    const results = await new AxeBuilder({ page })
      .withRules(['color-contrast'])
      .analyze();
    expect(results.violations).toHaveLength(0);
  });
});
""",
}


# ---------------------------------------------------------------------------
# Seed: collections (spec entries)
# ---------------------------------------------------------------------------

def _build_seed_collections() -> list[dict]:
    """Return a list of Collection JSON dicts to persist as files."""
    _coll_id = "b2c3d4e5-0001-0001-0001-000000000001"

    items = []
    for i, (spec_path, _) in enumerate(_SPEC_SOURCES.items()):
        # Create a playwright_spec entry for each spec file.
        items.append({
            "id": f"item-{i + 1:04d}-0001-0001-0001-000000000001",
            "name": spec_path.split("/")[-1],
            "is_folder": False,
            "kind": "playwright_spec",
            "spec_path": f"~/.theridion/silk/specs/{spec_path}",
            "method": None,
            "url": None,
            "headers": {},
            "body": None,
            "auth": None,
            "assertions": [],
            "pre_request_script": None,
            "post_response_script": None,
            "notes": None,
            "examples": [],
            "captures": [],
            "tags": ["e2e"],
            "items": [],
        })

    return [
        {
            "id": _coll_id,
            "name": "Example App — E2E Tests",
            "version": 1,
            "items": items,
            "variables": [
                {"name": "BASE_URL", "value": "https://app.example.com", "enabled": True},
                {"name": "TEST_USER", "value": "alice@example.com", "enabled": True},
            ],
        }
    ]


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def _write_silk_runs(runs: list[dict]) -> None:
    """Insert seed runs directly into SQLite (bypasses save_run to control started_at)."""
    from . import silk_storage as _ss

    # Ensure schema exists.
    conn = _ss._connect()
    conn.close()

    db = _silk_db_path()
    with sqlite3.connect(str(db)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        for run in runs:
            report_json = json.dumps(run["json_report"]) if run.get("json_report") else None
            screenshots_json = json.dumps(run.get("screenshot_paths") or [])
            browsers_json = json.dumps(run.get("browsers") or ["chromium"])

            if run["exit_code"] == 0:
                status = "passed"
            elif run["exit_code"] == 1:
                status = "failed"
            else:
                status = "error"

            conn.execute(
                """
                INSERT OR IGNORE INTO silk_runs
                  (id, spec_path, status, duration_ms, started_at, browsers,
                   trace_path, screenshot_paths, a11y_violations_count,
                   stderr_tail, json_report)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run["id"],
                    run["spec_path"],
                    status,
                    run["duration_ms"],
                    run["started_at"],
                    browsers_json,
                    run.get("trace_path"),
                    screenshots_json,
                    run.get("a11y_violations_count", 0),
                    run.get("stderr_tail", ""),
                    report_json,
                ),
            )


def _write_spec_files(specs_dir: Path) -> None:
    """Write example spec files into ~/.theridion/silk/specs/."""
    for rel_path, source in _SPEC_SOURCES.items():
        dest = specs_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_text(source, encoding="utf-8")


def _write_collections(collections: list[dict]) -> None:
    """Write collection JSON files (only if the collection file does not exist)."""
    from . import storage as _storage
    import os
    import tempfile

    coll_dir = _storage.collections_dir()
    for coll in collections:
        dest = coll_dir / f"{coll['id']}.json"
        if dest.exists():
            continue
        # Atomic write.
        fd, tmp = tempfile.mkstemp(prefix=coll["id"] + ".", suffix=".json.tmp",
                                   dir=str(coll_dir))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(coll, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, dest)
        except Exception:
            try:
                Path(tmp).unlink(missing_ok=True)
            except OSError:
                pass
            raise


# ---------------------------------------------------------------------------
# v2 seed data: environments
# ---------------------------------------------------------------------------

_ENV_IDS = {
    "production":  "c3d4e5f6-0001-0001-0001-000000000001",
    "staging":     "c3d4e5f6-0001-0001-0001-000000000002",
    "local":       "c3d4e5f6-0001-0001-0001-000000000003",
}


def _build_seed_environments() -> list[dict]:
    return [
        {
            "id": _ENV_IDS["production"],
            "name": "Production",
            "variables": [
                {"name": "BASE_URL",      "value": "https://app.acmecorp.io",          "enabled": True},
                {"name": "API_URL",       "value": "https://api.acmecorp.io/v2",       "enabled": True},
                {"name": "AUTH_TOKEN",    "value": "prod-token-eyJhbGciOiJSUzI1Ni",   "enabled": True},
                {"name": "TIMEOUT_MS",    "value": "10000",                            "enabled": True},
                {"name": "DEBUG",         "value": "false",                            "enabled": True},
            ],
        },
        {
            "id": _ENV_IDS["staging"],
            "name": "Staging",
            "variables": [
                {"name": "BASE_URL",      "value": "https://staging.acmecorp.io",      "enabled": True},
                {"name": "API_URL",       "value": "https://api.staging.acmecorp.io/v2","enabled": True},
                {"name": "AUTH_TOKEN",    "value": "stg-token-eyJhbGciOiJSUzI1Ni",    "enabled": True},
                {"name": "TIMEOUT_MS",    "value": "15000",                            "enabled": True},
                {"name": "DEBUG",         "value": "true",                             "enabled": True},
                {"name": "FEATURE_FLAGS", "value": "checkout-v3,ai-recommendations",  "enabled": True},
            ],
        },
        {
            "id": _ENV_IDS["local"],
            "name": "Local-dev",
            "variables": [
                {"name": "BASE_URL",      "value": "http://localhost:3000",            "enabled": True},
                {"name": "API_URL",       "value": "http://localhost:4000/v2",         "enabled": True},
                {"name": "AUTH_TOKEN",    "value": "dev-token-insecure-local-only",    "enabled": True},
                {"name": "TIMEOUT_MS",    "value": "30000",                            "enabled": True},
                {"name": "DEBUG",         "value": "true",                             "enabled": True},
                {"name": "MOCK_STRIPE",   "value": "true",                             "enabled": True},
            ],
        },
    ]


def _write_environments(envs: list[dict]) -> None:
    """Write environment JSON files idempotently."""
    from . import environments as _envs
    import os
    import tempfile

    envs_dir = _envs.envs_dir()
    for env in envs:
        dest = envs_dir / f"{env['id']}.json"
        if dest.exists():
            continue
        fd, tmp = tempfile.mkstemp(
            prefix=env["id"] + ".", suffix=".json.tmp", dir=str(envs_dir)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(env, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, dest)
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise


# ---------------------------------------------------------------------------
# v2 seed data: global variables
# ---------------------------------------------------------------------------


def _build_seed_globals() -> dict:
    return {
        "variables": [
            {"name": "COMPANY_NAME",  "value": "Acme Corp",                "enabled": True},
            {"name": "SUPPORT_EMAIL", "value": "support@acmecorp.io",      "enabled": True},
            {"name": "APP_VERSION",   "value": "2.8.0",                    "enabled": True},
            {"name": "DEFAULT_LANG",  "value": "en",                       "enabled": True},
        ]
    }


def _write_globals(data: dict) -> None:
    """Write globals.json idempotently."""
    from . import storage as _storage
    import os
    import tempfile

    dest = _storage.home_dir() / "globals.json"
    if dest.exists():
        return
    fd, tmp = tempfile.mkstemp(prefix="globals.", suffix=".json.tmp",
                               dir=str(_storage.home_dir()))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# v2 seed data: request history (history.jsonl)
# ---------------------------------------------------------------------------

_HISTORY_IDS = [
    "d4e5f6a7-0001-0001-0001-000000000001",
    "d4e5f6a7-0001-0001-0001-000000000002",
    "d4e5f6a7-0001-0001-0001-000000000003",
    "d4e5f6a7-0001-0001-0001-000000000004",
    "d4e5f6a7-0001-0001-0001-000000000005",
    "d4e5f6a7-0001-0001-0001-000000000006",
    "d4e5f6a7-0001-0001-0001-000000000007",
    "d4e5f6a7-0001-0001-0001-000000000008",
]


def _ts_epoch(days_ago: float, hour: int = 12, minute: int = 0) -> float:
    """Return a Unix epoch float for a timestamp n days in the past."""
    base = datetime.now(tz=timezone.utc).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    return (base - timedelta(days=days_ago)).timestamp()


def _build_seed_history() -> list[dict]:
    return [
        {
            "id": _HISTORY_IDS[0],
            "method": "GET",
            "url": "https://api.acmecorp.io/v2/users/me",
            "status": 200,
            "elapsed_ms": 87.4,
            "timestamp": _ts_epoch(0.01, hour=9, minute=22),
            "request_body": None,
            "response_body": (
                '{"id":"usr_a1b2","email":"alice.mercer@acmecorp.io","name":"Alice Mercer",'
                '"role":"admin","avatar_url":"https://cdn.acmecorp.io/avatars/alice.jpg",'
                '"plan":"enterprise","mfa_enabled":true,"created_at":"2023-04-01T00:00:00Z"}'
            ),
            "request_headers": {
                "Authorization": "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9",
                "Accept": "application/json",
                "X-Client-Version": "2.8.0",
            },
            "response_headers": {
                "Content-Type": "application/json; charset=utf-8",
                "X-Request-Id": "req-a1b2-0001",
                "X-RateLimit-Remaining": "498",
                "Cache-Control": "private, max-age=30",
            },
        },
        {
            "id": _HISTORY_IDS[1],
            "method": "POST",
            "url": "https://api.acmecorp.io/v2/auth/login",
            "status": 200,
            "elapsed_ms": 312.8,
            "timestamp": _ts_epoch(0.02, hour=9, minute=15),
            "request_body": '{"email":"alice.mercer@acmecorp.io","password":"•••••••••••","remember_me":true}',
            "response_body": (
                '{"access_token":"eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.demo-payload.sig",'
                '"refresh_token":"rt_1a2b3c4d5e6f","expires_in":3600,"token_type":"Bearer",'
                '"user":{"id":"usr_a1b2","email":"alice.mercer@acmecorp.io","name":"Alice Mercer"}}'
            ),
            "request_headers": {
                "Content-Type": "application/json",
                "X-Client-Version": "2.8.0",
            },
            "response_headers": {
                "Content-Type": "application/json; charset=utf-8",
                "Set-Cookie": "sid=s1a2b3c4; Path=/; HttpOnly; Secure; SameSite=Strict",
                "X-Request-Id": "req-a1b2-0002",
            },
        },
        {
            "id": _HISTORY_IDS[2],
            "method": "GET",
            "url": "https://api.acmecorp.io/v2/dashboard/metrics?range=30d",
            "status": 200,
            "elapsed_ms": 438.2,
            "timestamp": _ts_epoch(0.5, hour=14, minute=5),
            "request_body": None,
            "response_body": (
                '{"period":"30d","total_users":28_640,"active_users":19_820,'
                '"revenue_usd":247_890.50,"mrr_usd":84_320.00,"arr_usd":1_011_840.00,'
                '"conversion_rate":0.038,"churn_rate":0.012,"nps_score":71,'
                '"top_plans":[{"name":"Pro","count":1840},{"name":"Enterprise","count":320}]}'
            ),
            "request_headers": {
                "Authorization": "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9",
            },
            "response_headers": {
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "private, max-age=60",
                "X-Request-Id": "req-a1b2-0003",
            },
        },
        {
            "id": _HISTORY_IDS[3],
            "method": "POST",
            "url": "https://api.acmecorp.io/v2/checkout/sessions",
            "status": 201,
            "elapsed_ms": 584.6,
            "timestamp": _ts_epoch(1.0, hour=11, minute=30),
            "request_body": (
                '{"items":[{"sku":"ENTERPRISE-12M","qty":1,"unit_price_usd":2999.00}],'
                '"currency":"USD","promo_code":"SAVE20","customer_id":"cus_a1b2c3"}'
            ),
            "response_body": (
                '{"session_id":"cs_live_a1b2c3d4e5","checkout_url":"https://checkout.stripe.com/pay/cs_live_a1b2c3d4e5",'
                '"amount_usd":2399.20,"discount_applied":599.80,"expires_at":1769385600}'
            ),
            "request_headers": {
                "Content-Type": "application/json",
                "Authorization": "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9",
                "Idempotency-Key": "idem-a1b2-checkout-001",
            },
            "response_headers": {
                "Content-Type": "application/json; charset=utf-8",
                "Location": "/checkout/cs_live_a1b2c3d4e5",
                "X-Request-Id": "req-a1b2-0004",
            },
        },
        {
            "id": _HISTORY_IDS[4],
            "method": "GET",
            "url": "https://api.acmecorp.io/v2/users?page=1&limit=25&sort=created_at:desc",
            "status": 200,
            "elapsed_ms": 221.7,
            "timestamp": _ts_epoch(1.5, hour=16, minute=0),
            "request_body": None,
            "response_body": (
                '{"data":['
                '{"id":"usr_a1b2","email":"alice.mercer@acmecorp.io","plan":"enterprise","created_at":"2023-04-01T00:00:00Z"},'
                '{"id":"usr_c3d4","email":"bob.zhang@acmecorp.io","plan":"pro","created_at":"2023-06-15T00:00:00Z"},'
                '{"id":"usr_e5f6","email":"carol.hayes@acmecorp.io","plan":"pro","created_at":"2023-07-20T00:00:00Z"},'
                '{"id":"usr_g7h8","email":"dan.okoro@acmecorp.io","plan":"starter","created_at":"2024-01-10T00:00:00Z"}'
                '],"total":28640,"page":1,"per_page":25,"pages":1146}'
            ),
            "request_headers": {
                "Authorization": "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9",
            },
            "response_headers": {
                "Content-Type": "application/json; charset=utf-8",
                "X-Total-Count": "28640",
                "X-Request-Id": "req-a1b2-0005",
            },
        },
        {
            "id": _HISTORY_IDS[5],
            "method": "PATCH",
            "url": "https://api.acmecorp.io/v2/users/usr_a1b2/settings",
            "status": 422,
            "elapsed_ms": 94.3,
            "timestamp": _ts_epoch(2.0, hour=10, minute=45),
            "request_body": '{"notification_email":"not-a-valid@@email","digest_frequency":"hourly"}',
            "response_body": (
                '{"error":"VALIDATION_FAILED","message":"Request body failed schema validation",'
                '"details":['
                '{"field":"notification_email","code":"INVALID_EMAIL","message":"Must be a valid RFC-5322 email address"},'
                '{"field":"digest_frequency","code":"INVALID_ENUM","message":"Allowed values: daily, weekly, never"}'
                ']}'
            ),
            "request_headers": {
                "Content-Type": "application/json",
                "Authorization": "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9",
            },
            "response_headers": {
                "Content-Type": "application/json; charset=utf-8",
                "X-Request-Id": "req-a1b2-0006",
            },
        },
        {
            "id": _HISTORY_IDS[6],
            "method": "DELETE",
            "url": "https://api.acmecorp.io/v2/sessions/sess_x9y8z7w6",
            "status": 204,
            "elapsed_ms": 58.1,
            "timestamp": _ts_epoch(3.0, hour=17, minute=55),
            "request_body": None,
            "response_body": None,
            "request_headers": {
                "Authorization": "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9",
                "X-Client-Version": "2.8.0",
            },
            "response_headers": {
                "X-Request-Id": "req-a1b2-0007",
            },
        },
        {
            "id": _HISTORY_IDS[7],
            "method": "GET",
            "url": "https://api.acmecorp.io/v2/notifications?unread=true&limit=10",
            "status": 200,
            "elapsed_ms": 143.6,
            "timestamp": _ts_epoch(5.0, hour=9, minute=8),
            "request_body": None,
            "response_body": (
                '{"notifications":['
                '{"id":"ntf_001","type":"deploy_success","title":"Deployment to production succeeded","body":"v2.8.0 deployed in 2m 14s","read":false,"created_at":"2026-06-01T07:04:00Z"},'
                '{"id":"ntf_002","type":"new_signup","title":"New enterprise sign-up","body":"TechNova GmbH joined the Enterprise plan","read":false,"created_at":"2026-05-31T14:22:00Z"},'
                '{"id":"ntf_003","type":"alert","title":"P95 latency spike — /api/v2/metrics","body":"P95 rose to 840ms (+340ms vs baseline) for 4 minutes","read":false,"created_at":"2026-05-31T11:05:00Z"},'
                '{"id":"ntf_004","type":"payment","title":"Payment received — $2,399.20","body":"Invoice INV-2024-0841 paid by TechNova GmbH","read":false,"created_at":"2026-05-30T16:48:00Z"}'
                '],"total_unread":4,"total":22}'
            ),
            "request_headers": {
                "Authorization": "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9",
            },
            "response_headers": {
                "Content-Type": "application/json; charset=utf-8",
                "X-Request-Id": "req-a1b2-0008",
            },
        },
    ]


def _write_history(entries: list[dict]) -> None:
    """Write history.jsonl idempotently (only if file does not exist)."""
    from . import storage as _storage
    import os
    import tempfile

    dest = _storage.home_dir() / "history.jsonl"
    if dest.exists():
        return
    fd, tmp = tempfile.mkstemp(prefix="history.", suffix=".jsonl.tmp",
                               dir=str(_storage.home_dir()))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# v2 seed data: screenshot PNGs and visual baseline PNGs
# ---------------------------------------------------------------------------

def _make_minimal_png(width: int = 4, height: int = 4,
                       color: tuple[int, int, int] = (34, 197, 94)) -> bytes:
    """Generate a minimal valid PNG from scratch (no Pillow needed).

    Returns raw PNG bytes for a solid-colour RGB image of the given size.
    Uses raw deflate via zlib so it works in pure Python with no deps.
    """
    r, g, b = color

    # PNG signature
    sig = b"\x89PNG\r\n\x1a\n"

    def _chunk(tag: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        body = tag + data
        crc = struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        return length + body + crc

    # IHDR: width, height, bit-depth=8, color-type=2 (RGB), compress=0, filter=0, interlace=0
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)

    # IDAT: raw image rows, each prefixed with filter byte 0 (None)
    raw_rows = b""
    for _ in range(height):
        row = bytes([r, g, b] * width)
        raw_rows += b"\x00" + row
    compressed = zlib.compress(raw_rows, level=9)
    idat = _chunk(b"IDAT", compressed)

    # IEND
    iend = _chunk(b"IEND", b"")

    return sig + ihdr + idat + iend


# Stable screenshot IDs that are cross-referenced back to silk run IDs.
# run9  (a11y) → screenshot of homepage
# run5  (dashboard) → screenshot of dashboard
# run10 (login) → screenshot of login form
_SCREENSHOT_DEFS = [
    {
        "run_id":   _RUN_IDS[8],   # run9 — a11y / homepage
        "filename": "homepage-axe-audit-chromium.png",
        "color":    (99, 102, 241),   # indigo — homepage hero colour
    },
    {
        "run_id":   _RUN_IDS[4],   # run5 — dashboard overview
        "filename": "dashboard-overview-chromium.png",
        "color":    (16, 185, 129),   # emerald — dashboard KPI cards
    },
    {
        "run_id":   _RUN_IDS[9],   # run10 — login flow
        "filename": "login-form-filled-chromium.png",
        "color":    (59, 130, 246),   # blue — login form
    },
]

# Visual-regression baseline definitions — one per test_id × browser × viewport.
_BASELINE_DEFS = [
    {
        "test_id":           "homepage passes axe audit (WCAG 2.1 AA)",
        "browser":           "chromium",
        "viewport":          "1440x900",
        "color":             (99, 102, 241),
        "approved_by":       "alice.mercer@acmecorp.io",
        "diff_ratio":        0.0,
        "approved_at_offset": 0.5,   # days ago
    },
    {
        "test_id":           "homepage passes axe audit (WCAG 2.1 AA)",
        "browser":           "firefox",
        "viewport":          "1440x900",
        "color":             (139, 92, 246),
        "approved_by":       "alice.mercer@acmecorp.io",
        "diff_ratio":        0.0,
        "approved_at_offset": 0.5,
    },
    {
        "test_id":           "loads checkout page with order summary",
        "browser":           "chromium",
        "viewport":          "1440x900",
        "color":             (245, 158, 11),
        "approved_by":       "bob.zhang@acmecorp.io",
        "diff_ratio":        0.0015,
        "approved_at_offset": 2.0,
    },
    {
        "test_id":           "loads dashboard for authenticated user",
        "browser":           "chromium",
        "viewport":          "1920x1080",
        "color":             (16, 185, 129),
        "approved_by":       "alice.mercer@acmecorp.io",
        "diff_ratio":        0.0,
        "approved_at_offset": 1.0,
    },
]


def _baseline_filename(test_id: str, browser: str, viewport: str) -> str:
    safe_id = test_id.replace("/", "_").replace(" ", "_")
    safe_viewport = viewport.replace("x", "_")
    return f"{safe_id}-{browser}-{safe_viewport}.png"


def _write_screenshots(silk_dir: Path) -> None:
    """Write demo screenshot PNGs into run sub-directories."""
    for defn in _SCREENSHOT_DEFS:
        run_dir = silk_dir / "runs" / defn["run_id"] / "screenshots"
        run_dir.mkdir(parents=True, exist_ok=True)
        dest = run_dir / defn["filename"]
        if not dest.exists():
            dest.write_bytes(_make_minimal_png(color=defn["color"]))


def _write_baselines(silk_dir: Path) -> None:
    """Write demo baseline PNGs and .approved.json metadata."""
    baselines_dir = silk_dir / "baselines"
    baselines_dir.mkdir(parents=True, exist_ok=True)
    for defn in _BASELINE_DEFS:
        fname = _baseline_filename(defn["test_id"], defn["browser"], defn["viewport"])
        png_dest = baselines_dir / fname
        meta_dest = baselines_dir / f"{fname}.approved.json"
        approved_at = (
            datetime.now(tz=timezone.utc) - timedelta(days=defn["approved_at_offset"])
        ).isoformat()

        if not png_dest.exists():
            png_dest.write_bytes(_make_minimal_png(color=defn["color"]))

        if not meta_dest.exists():
            meta = {
                "test_id": defn["test_id"],
                "browser": defn["browser"],
                "viewport": defn["viewport"],
                "approved": True,
                "approved_by": defn["approved_by"],
                "approved_at": approved_at,
                "diff_ratio": defn["diff_ratio"],
                "candidate_path": str(png_dest),
            }
            meta_dest.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _patch_silk_runs_with_screenshots(silk_dir: Path) -> None:
    """Back-fill screenshot_paths in the already-inserted silk_runs rows."""
    db = silk_dir / "history.db"
    if not db.exists():
        return
    with sqlite3.connect(str(db)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        for defn in _SCREENSHOT_DEFS:
            run_id = defn["run_id"]
            screenshot_path = str(
                silk_dir / "runs" / run_id / "screenshots" / defn["filename"]
            )
            # Only update if screenshots_paths is currently '[]' (empty).
            conn.execute(
                """
                UPDATE silk_runs
                SET screenshot_paths = ?
                WHERE id = ? AND (screenshot_paths = '[]' OR screenshot_paths IS NULL)
                """,
                (json.dumps([screenshot_path]), run_id),
            )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def maybe_seed() -> None:
    """Seed local storage when empty.  Safe to call on every startup.

    Skips seeding when:
    - The silk DB already contains runs (idempotent guard).
    - The silk-seed marker file is present (belt-and-suspenders).

    After the v1 silk-run seed, also runs seed_all() for v2 data
    (environments, globals, history, screenshots, baselines).
    """
    silk_dir = _silk_dir()
    marker = silk_dir / _SEED_MARKER

    if not marker.exists():
        if _has_existing_runs():
            # DB already populated — write marker so we skip faster next time.
            marker.touch()
        else:
            logger.info("theridion-eyes: seeding demo history data...")
            try:
                runs = _build_seed_runs()
                _write_silk_runs(runs)

                specs_dir = silk_dir / "specs"
                _write_spec_files(specs_dir)

                collections = _build_seed_collections()
                _write_collections(collections)

                marker.touch()
                logger.info(
                    "theridion-eyes: seed complete (%d runs, %d specs, %d collections).",
                    len(runs), len(_SPEC_SOURCES), len(collections),
                )
            except Exception as exc:
                # Seed failures must never crash the sidecar.
                logger.warning("theridion-eyes: seed failed (non-fatal): %s", exc, exc_info=True)

    # Always attempt v2 seed (idempotent — guarded by its own marker).
    seed_all()


def seed_all() -> None:
    """Seed all non-silk-run data (environments, globals, history, baselines).

    Idempotent: guarded by ``_SEED_MARKER_V2`` written to the home dir.
    Safe to call on every startup — will no-op when already seeded.
    """
    from . import storage as _storage
    home = _storage.home_dir()
    marker_v2 = home / _SEED_MARKER_V2

    if marker_v2.exists():
        return  # Already seeded.

    logger.info("theridion-eyes: running v2 seed (envs, globals, history, baselines)...")
    try:
        # Environments
        envs = _build_seed_environments()
        _write_environments(envs)

        # Global variables
        _write_globals(_build_seed_globals())

        # Request history
        _write_history(_build_seed_history())

        # Screenshots — write PNGs and back-fill silk_runs rows
        silk_dir = _silk_dir()
        _write_screenshots(silk_dir)
        _patch_silk_runs_with_screenshots(silk_dir)

        # Visual regression baselines
        _write_baselines(silk_dir)

        marker_v2.touch()
        logger.info(
            "theridion-eyes: v2 seed complete (%d envs, history, %d baselines).",
            len(envs), len(_BASELINE_DEFS),
        )
    except Exception as exc:
        logger.warning("theridion-eyes: v2 seed failed (non-fatal): %s", exc, exc_info=True)
