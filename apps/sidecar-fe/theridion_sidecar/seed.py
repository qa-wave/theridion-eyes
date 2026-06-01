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
            "skipped": 0,
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

    # Run 10 — today (just now): login.spec.ts, chromium, passed
    run10 = {
        "id": _RUN_IDS[9],
        "spec_path": "tests/auth/login.spec.ts",
        "exit_code": 0,
        "duration_ms": 3240,
        "started_at": _ts(0.02, hour=9, minute=15),
        "browsers": ["chromium"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": "",
        "json_report": _make_json_report(
            "Login spec",
            [
                {"title": "displays login form", "ok": True, "duration": 480},
                {"title": "logs in with valid credentials", "ok": True, "duration": 1200},
                {"title": "shows error on invalid password", "ok": True, "duration": 860},
                {"title": "redirects to dashboard after login", "ok": True, "duration": 700},
            ],
        ),
    }

    # Run 9 — today: homepage a11y, chromium+firefox, passed with 2 a11y violations
    axe_violations = [
        {
            "id": "color-contrast",
            "impact": "serious",
            "description": "Elements must have sufficient color contrast",
            "nodes": [{"target": [".hero-subtitle"]}],
        },
        {
            "id": "image-alt",
            "impact": "critical",
            "description": "Images must have alternative text",
            "nodes": [{"target": ["img.logo"]}],
        },
    ]
    run9 = {
        "id": _RUN_IDS[8],
        "spec_path": "tests/a11y/homepage-axe.spec.ts",
        "exit_code": 0,
        "duration_ms": 5180,
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
                    "title": "homepage passes axe audit",
                    "ok": True,
                    "duration": 2100,
                    "attachments": [_axe_attachment(axe_violations)],
                },
                {"title": "nav links are keyboard-accessible", "ok": True, "duration": 880},
            ],
        ),
    }

    # Run 8 — yesterday: payment flow, chromium, FAILED (1 test failed)
    run8 = {
        "id": _RUN_IDS[7],
        "spec_path": "tests/checkout/payment-flow.spec.ts",
        "exit_code": 1,
        "duration_ms": 8650,
        "started_at": _ts(1.0, hour=16, minute=5),
        "browsers": ["chromium"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": (
            "  1 failed\n"
            "  ● checkout › payment-flow › completes Stripe checkout\n"
            "\n"
            "    TimeoutError: waiting for selector '.stripe-success' failed\n"
            "    at Object.waitForSelector (playwright-core/lib/client/page.ts:123)\n"
            "    Expected: visible\n"
            "    Received: hidden after 10000ms"
        ),
        "json_report": _make_json_report(
            "Payment flow",
            [
                {"title": "loads checkout page", "ok": True, "duration": 920},
                {"title": "fills in card details", "ok": True, "duration": 1380},
                {
                    "title": "completes Stripe checkout",
                    "ok": False,
                    "duration": 10000,
                    "error": "TimeoutError: waiting for selector '.stripe-success' failed: timeout 10000ms exceeded",
                },
                {"title": "shows order confirmation", "ok": True, "duration": 350},
            ],
        ),
    }

    # Run 7 — yesterday: profile settings, chromium, passed
    run7 = {
        "id": _RUN_IDS[6],
        "spec_path": "tests/profile/settings.spec.ts",
        "exit_code": 0,
        "duration_ms": 4120,
        "started_at": _ts(1.0, hour=14, minute=22),
        "browsers": ["chromium"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": "",
        "json_report": _make_json_report(
            "Profile settings",
            [
                {"title": "renders settings page", "ok": True, "duration": 610},
                {"title": "updates display name", "ok": True, "duration": 1050},
                {"title": "changes email address", "ok": True, "duration": 980},
                {"title": "saves notification preferences", "ok": True, "duration": 780},
            ],
        ),
    }

    # Run 6 — 2 days ago: payment flow, chromium+firefox+webkit, passed (after fix)
    run6 = {
        "id": _RUN_IDS[5],
        "spec_path": "tests/checkout/payment-flow.spec.ts",
        "exit_code": 0,
        "duration_ms": 22410,
        "started_at": _ts(2.0, hour=11, minute=30),
        "browsers": ["chromium", "firefox", "webkit"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": "",
        "json_report": _make_json_report(
            "Payment flow (all browsers)",
            [
                {"title": "loads checkout page", "ok": True, "duration": 880},
                {"title": "fills in card details", "ok": True, "duration": 1220},
                {"title": "completes Stripe checkout", "ok": True, "duration": 2950},
                {"title": "shows order confirmation", "ok": True, "duration": 410},
            ],
        ),
    }

    # Run 5 — 3 days ago: dashboard, chromium+firefox, passed
    network_entries = [
        {"request": {"method": "GET", "url": "https://app.example.com/api/metrics"},
         "response": {"status": 200, "content": {"mimeType": "application/json"}}},
        {"request": {"method": "GET", "url": "https://app.example.com/api/notifications"},
         "response": {"status": 200, "content": {"mimeType": "application/json"}}},
        {"request": {"method": "POST", "url": "https://app.example.com/api/analytics/pageview"},
         "response": {"status": 204, "content": {"mimeType": "text/plain"}}},
    ]
    run5 = {
        "id": _RUN_IDS[4],
        "spec_path": "tests/dashboard/overview.spec.ts",
        "exit_code": 0,
        "duration_ms": 6730,
        "started_at": _ts(3.0, hour=10, minute=0),
        "browsers": ["chromium", "firefox"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": "",
        "json_report": _make_json_report(
            "Dashboard overview",
            [
                {"title": "loads dashboard for authenticated user", "ok": True, "duration": 1100,
                 "attachments": [_network_attachment(network_entries)]},
                {"title": "displays metric cards", "ok": True, "duration": 640},
                {"title": "chart renders with data", "ok": True, "duration": 820},
                {"title": "notifications bell shows count", "ok": True, "duration": 390},
            ],
        ),
    }

    # Run 4 — 5 days ago: logout, chromium, passed
    run4 = {
        "id": _RUN_IDS[3],
        "spec_path": "tests/auth/logout.spec.ts",
        "exit_code": 0,
        "duration_ms": 2180,
        "started_at": _ts(5.0, hour=15, minute=48),
        "browsers": ["chromium"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": "",
        "json_report": _make_json_report(
            "Logout flow",
            [
                {"title": "clicking logout clears session", "ok": True, "duration": 850},
                {"title": "redirects to login page", "ok": True, "duration": 620},
                {"title": "protected pages require re-login", "ok": True, "duration": 710},
            ],
        ),
    }

    # Run 3 — 7 days ago: dashboard, chromium, FAILED (2 tests)
    run3 = {
        "id": _RUN_IDS[2],
        "spec_path": "tests/dashboard/overview.spec.ts",
        "exit_code": 1,
        "duration_ms": 9200,
        "started_at": _ts(7.0, hour=9, minute=5),
        "browsers": ["chromium"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": (
            "  2 failed\n"
            "  ● dashboard › chart renders with data\n"
            "    Error: expect(received).toBeVisible()\n"
            "    Expected: visible\n"
            "    Received: <div class='chart-container' style='display: none'>\n"
            "\n"
            "  ● dashboard › notifications bell shows count\n"
            "    Error: expected '0' to equal '3'"
        ),
        "json_report": _make_json_report(
            "Dashboard overview",
            [
                {"title": "loads dashboard for authenticated user", "ok": True, "duration": 980},
                {"title": "displays metric cards", "ok": True, "duration": 590},
                {
                    "title": "chart renders with data",
                    "ok": False,
                    "duration": 5000,
                    "error": "Error: expect(received).toBeVisible() — element not visible",
                },
                {
                    "title": "notifications bell shows count",
                    "ok": False,
                    "duration": 1200,
                    "error": "Error: expected '0' to equal '3'",
                },
            ],
        ),
    }

    # Run 2 — 10 days ago: a11y homepage, chromium, passed, 1 violation
    axe_violations_v2 = [
        {
            "id": "aria-required-attr",
            "impact": "critical",
            "description": "Required ARIA attributes must be provided",
            "nodes": [{"target": ["[role=progressbar]"]}],
        },
    ]
    run2 = {
        "id": _RUN_IDS[1],
        "spec_path": "tests/a11y/homepage-axe.spec.ts",
        "exit_code": 0,
        "duration_ms": 3870,
        "started_at": _ts(10.0, hour=11, minute=20),
        "browsers": ["chromium"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 1,
        "stderr_tail": "",
        "json_report": _make_json_report(
            "Homepage accessibility audit",
            [
                {
                    "title": "homepage passes axe audit",
                    "ok": True,
                    "duration": 1800,
                    "attachments": [_axe_attachment(axe_violations_v2)],
                },
            ],
        ),
    }

    # Run 1 — 14 days ago: login, chromium, passed (baseline run)
    run1 = {
        "id": _RUN_IDS[0],
        "spec_path": "tests/auth/login.spec.ts",
        "exit_code": 0,
        "duration_ms": 3050,
        "started_at": _ts(14.0, hour=10, minute=0),
        "browsers": ["chromium"],
        "trace_path": None,
        "screenshot_paths": [],
        "a11y_violations_count": 0,
        "stderr_tail": "",
        "json_report": _make_json_report(
            "Login spec",
            [
                {"title": "displays login form", "ok": True, "duration": 420},
                {"title": "logs in with valid credentials", "ok": True, "duration": 1100},
                {"title": "shows error on invalid password", "ok": True, "duration": 790},
                {"title": "redirects to dashboard after login", "ok": True, "duration": 740},
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

test.describe('Login flow', () => {
  test('displays login form', async ({ page }) => {
    await page.goto('https://app.example.com/login');
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
    await expect(page.getByLabel('Email')).toBeVisible();
    await expect(page.getByLabel('Password')).toBeVisible();
  });

  test('logs in with valid credentials', async ({ page }) => {
    await page.goto('https://app.example.com/login');
    await page.getByLabel('Email').fill('alice@example.com');
    await page.getByLabel('Password').fill('correct-password');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\\/dashboard/);
  });

  test('shows error on invalid password', async ({ page }) => {
    await page.goto('https://app.example.com/login');
    await page.getByLabel('Email').fill('alice@example.com');
    await page.getByLabel('Password').fill('wrong-password');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByTestId('error-banner')).toHaveText(/invalid credentials/i);
  });

  test('redirects to dashboard after login', async ({ page }) => {
    await page.goto('https://app.example.com/login?returnTo=/dashboard/analytics');
    await page.getByLabel('Email').fill('alice@example.com');
    await page.getByLabel('Password').fill('correct-password');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\\/dashboard\\/analytics/);
  });
});
""",
    "tests/auth/logout.spec.ts": """\
import { test, expect } from '@playwright/test';

test.describe('Logout flow', () => {
  test('clicking logout clears session', async ({ page }) => {
    await page.goto('https://app.example.com/dashboard');
    await page.getByRole('button', { name: 'Account menu' }).click();
    await page.getByRole('menuitem', { name: 'Sign out' }).click();
    await expect(page).toHaveURL(/\\/login/);
  });

  test('redirects to login page', async ({ page }) => {
    await page.goto('https://app.example.com/login');
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  });

  test('protected pages require re-login', async ({ page }) => {
    await page.goto('https://app.example.com/dashboard');
    await expect(page).toHaveURL(/\\/login/);
  });
});
""",
    "tests/dashboard/overview.spec.ts": """\
import { test, expect } from '@playwright/test';

test.describe('Dashboard overview', () => {
  test('loads dashboard for authenticated user', async ({ page }) => {
    await page.goto('https://app.example.com/dashboard');
    await expect(page.getByTestId('dashboard-root')).toBeVisible();
  });

  test('displays metric cards', async ({ page }) => {
    await page.goto('https://app.example.com/dashboard');
    await expect(page.getByTestId('metric-total-users')).toBeVisible();
    await expect(page.getByTestId('metric-revenue')).toBeVisible();
    await expect(page.getByTestId('metric-conversions')).toBeVisible();
  });

  test('chart renders with data', async ({ page }) => {
    await page.goto('https://app.example.com/dashboard');
    await expect(page.getByTestId('revenue-chart')).toBeVisible();
    const bars = page.locator('[data-testid="chart-bar"]');
    await expect(bars).toHaveCount(7);
  });

  test('notifications bell shows count', async ({ page }) => {
    await page.goto('https://app.example.com/dashboard');
    const badge = page.getByTestId('notification-badge');
    await expect(badge).toHaveText('3');
  });
});
""",
    "tests/checkout/payment-flow.spec.ts": """\
import { test, expect } from '@playwright/test';

test.describe('Payment flow', () => {
  test('loads checkout page', async ({ page }) => {
    await page.goto('https://app.example.com/checkout');
    await expect(page.getByRole('heading', { name: 'Checkout' })).toBeVisible();
    await expect(page.getByTestId('order-summary')).toBeVisible();
  });

  test('fills in card details', async ({ page }) => {
    await page.goto('https://app.example.com/checkout');
    const stripe = page.frameLocator('iframe[name="stripe-card"]');
    await stripe.getByPlaceholder('Card number').fill('4242 4242 4242 4242');
    await stripe.getByPlaceholder('MM / YY').fill('12 / 28');
    await stripe.getByPlaceholder('CVC').fill('123');
  });

  test('completes Stripe checkout', async ({ page }) => {
    await page.goto('https://app.example.com/checkout?demo=1');
    await page.getByRole('button', { name: 'Pay now' }).click();
    await expect(page.locator('.stripe-success')).toBeVisible({ timeout: 10_000 });
  });

  test('shows order confirmation', async ({ page }) => {
    await page.goto('https://app.example.com/checkout/confirmation');
    await expect(page.getByTestId('order-id')).toBeVisible();
    await expect(page.getByRole('heading', { name: /order confirmed/i })).toBeVisible();
  });
});
""",
    "tests/profile/settings.spec.ts": """\
import { test, expect } from '@playwright/test';

test.describe('Profile settings', () => {
  test('renders settings page', async ({ page }) => {
    await page.goto('https://app.example.com/settings');
    await expect(page.getByRole('heading', { name: 'Account settings' })).toBeVisible();
  });

  test('updates display name', async ({ page }) => {
    await page.goto('https://app.example.com/settings');
    await page.getByLabel('Display name').fill('Alice Doe');
    await page.getByRole('button', { name: 'Save changes' }).click();
    await expect(page.getByTestId('toast-success')).toHaveText(/saved/i);
  });

  test('changes email address', async ({ page }) => {
    await page.goto('https://app.example.com/settings');
    await page.getByLabel('Email').fill('alice.new@example.com');
    await page.getByRole('button', { name: 'Save changes' }).click();
    await expect(page.getByTestId('toast-success')).toBeVisible();
  });

  test('saves notification preferences', async ({ page }) => {
    await page.goto('https://app.example.com/settings/notifications');
    await page.getByLabel('Email digest').check();
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByTestId('toast-success')).toBeVisible();
  });
});
""",
    "tests/a11y/homepage-axe.spec.ts": """\
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Homepage accessibility audit', () => {
  test('homepage passes axe audit', async ({ page }) => {
    await page.goto('https://app.example.com');
    const results = await new AxeBuilder({ page }).analyze();
    // Report violations as a JSON attachment for Silk's a11y tab.
    await test.info().attach('axe-results.json', {
      contentType: 'application/json',
      body: JSON.stringify({ violations: results.violations }),
    });
    // Check that no critical violations are present.
    const critical = results.violations.filter((v) => v.impact === 'critical');
    expect(critical).toHaveLength(0);
  });

  test('nav links are keyboard-accessible', async ({ page }) => {
    await page.goto('https://app.example.com');
    await page.keyboard.press('Tab');
    const focused = page.locator(':focus');
    await expect(focused).toHaveAttribute('href');
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
                {"name": "BASE_URL",      "value": "https://app.example.com",         "enabled": True},
                {"name": "API_URL",       "value": "https://api.example.com/v1",       "enabled": True},
                {"name": "AUTH_TOKEN",    "value": "prod-token-abc123",                "enabled": True},
                {"name": "TIMEOUT_MS",    "value": "10000",                            "enabled": True},
                {"name": "DEBUG",         "value": "false",                            "enabled": True},
            ],
        },
        {
            "id": _ENV_IDS["staging"],
            "name": "Staging",
            "variables": [
                {"name": "BASE_URL",      "value": "https://staging.example.com",      "enabled": True},
                {"name": "API_URL",       "value": "https://api.staging.example.com/v1","enabled": True},
                {"name": "AUTH_TOKEN",    "value": "staging-token-xyz789",             "enabled": True},
                {"name": "TIMEOUT_MS",    "value": "15000",                            "enabled": True},
                {"name": "DEBUG",         "value": "true",                             "enabled": True},
                {"name": "FEATURE_FLAG",  "value": "checkout-v2",                     "enabled": True},
            ],
        },
        {
            "id": _ENV_IDS["local"],
            "name": "Local-dev",
            "variables": [
                {"name": "BASE_URL",      "value": "http://localhost:3000",            "enabled": True},
                {"name": "API_URL",       "value": "http://localhost:4000/v1",         "enabled": True},
                {"name": "AUTH_TOKEN",    "value": "dev-token-local",                  "enabled": True},
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
            {"name": "COMPANY_NAME",  "value": "Example Corp",             "enabled": True},
            {"name": "SUPPORT_EMAIL", "value": "support@example.com",      "enabled": True},
            {"name": "APP_VERSION",   "value": "2.4.1",                    "enabled": True},
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
            "url": "https://api.example.com/v1/users/me",
            "status": 200,
            "elapsed_ms": 134.5,
            "timestamp": _ts_epoch(0.01, hour=9, minute=22),
            "request_body": None,
            "response_body": '{"id":"usr_01","email":"alice@example.com","name":"Alice Doe","role":"admin"}',
            "request_headers": {"Authorization": "Bearer prod-token-abc123", "Accept": "application/json"},
            "response_headers": {"Content-Type": "application/json", "X-Request-Id": "req-001"},
        },
        {
            "id": _HISTORY_IDS[1],
            "method": "POST",
            "url": "https://api.example.com/v1/auth/login",
            "status": 200,
            "elapsed_ms": 287.3,
            "timestamp": _ts_epoch(0.02, hour=9, minute=15),
            "request_body": '{"email":"alice@example.com","password":"•••••••••"}',
            "response_body": '{"access_token":"eyJhbGciOiJIUzI1NiJ9.example","expires_in":3600}',
            "request_headers": {"Content-Type": "application/json"},
            "response_headers": {"Content-Type": "application/json", "Set-Cookie": "session=abc; HttpOnly"},
        },
        {
            "id": _HISTORY_IDS[2],
            "method": "GET",
            "url": "https://api.example.com/v1/dashboard/metrics",
            "status": 200,
            "elapsed_ms": 412.8,
            "timestamp": _ts_epoch(0.5, hour=14, minute=5),
            "request_body": None,
            "response_body": '{"total_users":12480,"revenue_usd":84320.50,"conversion_rate":0.034}',
            "request_headers": {"Authorization": "Bearer prod-token-abc123"},
            "response_headers": {"Content-Type": "application/json", "Cache-Control": "max-age=60"},
        },
        {
            "id": _HISTORY_IDS[3],
            "method": "POST",
            "url": "https://api.example.com/v1/checkout/sessions",
            "status": 201,
            "elapsed_ms": 623.1,
            "timestamp": _ts_epoch(1.0, hour=11, minute=30),
            "request_body": '{"items":[{"sku":"PRO-12M","qty":1}],"currency":"USD"}',
            "response_body": '{"session_id":"cs_test_abc123","url":"https://checkout.stripe.com/pay/cs_test_abc123","expires_at":1735000000}',
            "request_headers": {"Content-Type": "application/json", "Authorization": "Bearer prod-token-abc123"},
            "response_headers": {"Content-Type": "application/json", "Location": "/checkout/cs_test_abc123"},
        },
        {
            "id": _HISTORY_IDS[4],
            "method": "GET",
            "url": "https://api.example.com/v1/users?page=1&limit=20",
            "status": 200,
            "elapsed_ms": 198.4,
            "timestamp": _ts_epoch(1.5, hour=16, minute=0),
            "request_body": None,
            "response_body": '{"data":[{"id":"usr_01","email":"alice@example.com"},{"id":"usr_02","email":"bob@example.com"}],"total":2,"page":1}',
            "request_headers": {"Authorization": "Bearer prod-token-abc123"},
            "response_headers": {"Content-Type": "application/json"},
        },
        {
            "id": _HISTORY_IDS[5],
            "method": "PATCH",
            "url": "https://api.example.com/v1/users/usr_01/settings",
            "status": 422,
            "elapsed_ms": 89.7,
            "timestamp": _ts_epoch(2.0, hour=10, minute=45),
            "request_body": '{"notification_email":"invalid-email"}',
            "response_body": '{"detail":"Validation failed","errors":[{"field":"notification_email","msg":"Not a valid email address"}]}',
            "request_headers": {"Content-Type": "application/json", "Authorization": "Bearer prod-token-abc123"},
            "response_headers": {"Content-Type": "application/json"},
        },
        {
            "id": _HISTORY_IDS[6],
            "method": "DELETE",
            "url": "https://api.example.com/v1/sessions/sess_xyz",
            "status": 204,
            "elapsed_ms": 67.2,
            "timestamp": _ts_epoch(3.0, hour=17, minute=55),
            "request_body": None,
            "response_body": None,
            "request_headers": {"Authorization": "Bearer prod-token-abc123"},
            "response_headers": {},
        },
        {
            "id": _HISTORY_IDS[7],
            "method": "GET",
            "url": "https://api.example.com/v1/notifications?unread=true",
            "status": 200,
            "elapsed_ms": 156.9,
            "timestamp": _ts_epoch(5.0, hour=9, minute=8),
            "request_body": None,
            "response_body": '{"notifications":[{"id":"n1","title":"Deployment succeeded","read":false},{"id":"n2","title":"New user signup","read":false}],"total":2}',
            "request_headers": {"Authorization": "Bearer prod-token-abc123"},
            "response_headers": {"Content-Type": "application/json"},
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
        "run_id":   _RUN_IDS[8],   # run9 — a11y
        "filename": "homepage-screenshot.png",
        "color":    (99, 102, 241),   # indigo — homepage colour
    },
    {
        "run_id":   _RUN_IDS[4],   # run5 — dashboard
        "filename": "dashboard-screenshot.png",
        "color":    (16, 185, 129),   # emerald — dashboard
    },
    {
        "run_id":   _RUN_IDS[9],   # run10 — login
        "filename": "login-form-screenshot.png",
        "color":    (59, 130, 246),   # blue — login
    },
]

# Visual-regression baseline definitions — one per test_id × browser × viewport.
_BASELINE_DEFS = [
    {
        "test_id": "homepage passes axe audit",
        "browser": "chromium",
        "viewport": "1280x720",
        "color": (99, 102, 241),
        "approved_by": "alice@example.com",
        "diff_ratio": 0.0,
        "approved_at_offset": 0.5,   # days ago
    },
    {
        "test_id": "homepage passes axe audit",
        "browser": "firefox",
        "viewport": "1280x720",
        "color": (139, 92, 246),
        "approved_by": "alice@example.com",
        "diff_ratio": 0.0,
        "approved_at_offset": 0.5,
    },
    {
        "test_id": "loads checkout page",
        "browser": "chromium",
        "viewport": "1280x720",
        "color": (245, 158, 11),
        "approved_by": "bob@example.com",
        "diff_ratio": 0.002,
        "approved_at_offset": 2.0,
    },
    {
        "test_id": "loads dashboard for authenticated user",
        "browser": "chromium",
        "viewport": "1440x900",
        "color": (16, 185, 129),
        "approved_by": "alice@example.com",
        "diff_ratio": 0.0,
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
