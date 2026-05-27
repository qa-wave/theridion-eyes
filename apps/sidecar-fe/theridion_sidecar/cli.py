"""CLI entry point — `theridion test <collection> [--env <env>] [--report <path>]`.

Runs all requests in a collection file, evaluates assertions, prints
results to stdout, and optionally generates an HTML trace report.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from .assertions import Assertion, AssertionResult, ResponseData, evaluate_all
from .models import Collection, CollectionItem


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="theridion",
        description="Theridion API test runner",
    )
    sub = parser.add_subparsers(dest="command")

    test_cmd = sub.add_parser("test", help="Run a collection")
    test_cmd.add_argument("collection", help="Path to collection JSON file")
    test_cmd.add_argument("--env", help="Path to environment JSON file")
    test_cmd.add_argument("--report", help="Path to output HTML report")
    test_cmd.add_argument("--timeout", type=float, default=30, help="Request timeout in seconds")

    args = parser.parse_args()
    if args.command == "test":
        sys.exit(asyncio.run(run_tests(args)))
    else:
        parser.print_help()
        sys.exit(1)


async def run_tests(args: argparse.Namespace) -> int:
    # Load collection.
    coll_path = Path(args.collection)
    if not coll_path.exists():
        print(f"Error: {coll_path} not found", file=sys.stderr)
        return 1
    coll = Collection(**json.loads(coll_path.read_text()))

    # Load environment.
    env_vars: dict[str, str] = {}
    if args.env:
        env_path = Path(args.env)
        if env_path.exists():
            env_data = json.loads(env_path.read_text())
            for v in env_data.get("variables", []):
                if v.get("enabled", True):
                    env_vars[v["name"]] = v["value"]

    # Flatten requests.
    requests = _collect_requests(coll.items)
    results: list[dict[str, Any]] = []
    total_pass = 0
    total_fail = 0
    total_error = 0
    started = time.perf_counter()

    print(f"\n  Theridion Test Runner")
    print(f"  Collection: {coll.name} ({len(requests)} requests)\n")

    for req in requests:
        if not req.url:
            print(f"  \u2717 {req.name} — no URL")
            total_error += 1
            results.append({"name": req.name, "status": None, "error": "No URL", "assertions": []})
            continue

        url = _substitute(req.url, env_vars)
        headers = {k: _substitute(v, env_vars) for k, v in req.headers.items()}
        body = _substitute(req.body, env_vars) if req.body else None

        req_started = time.perf_counter()
        try:
            async with httpx.AsyncClient(http2=True, timeout=args.timeout, follow_redirects=True) as client:
                response = await client.request(
                    method=req.method or "GET",
                    url=url,
                    headers=headers,
                    content=body.encode() if body else None,
                )
            elapsed = (time.perf_counter() - req_started) * 1000

            # Evaluate assertions.
            a_results: list[dict[str, Any]] = []
            if req.assertions:
                resp_data = ResponseData(
                    status=response.status_code,
                    headers=dict(response.headers),
                    body=response.text,
                    elapsed_ms=elapsed,
                )
                for ar in evaluate_all(req.assertions, resp_data):
                    a_results.append({"passed": ar.passed, "message": ar.message})
                    if ar.passed:
                        total_pass += 1
                    else:
                        total_fail += 1

            status_icon = "\u2713" if response.status_code < 400 else "\u2717"
            print(f"  {status_icon} {req.name} [{response.status_code}] {elapsed:.0f}ms", end="")
            if a_results:
                ap = sum(1 for a in a_results if a["passed"])
                af = len(a_results) - ap
                print(f" ({ap} passed, {af} failed)", end="")
            print()

            results.append({
                "name": req.name,
                "method": req.method or "GET",
                "url": url,
                "status": response.status_code,
                "elapsed_ms": round(elapsed, 2),
                "assertions": a_results,
            })
        except Exception as e:
            elapsed = (time.perf_counter() - req_started) * 1000
            print(f"  \u2717 {req.name} — {e}")
            total_error += 1
            results.append({"name": req.name, "status": None, "error": str(e), "assertions": [], "elapsed_ms": round(elapsed, 2)})

    total_elapsed = (time.perf_counter() - started) * 1000
    print(f"\n  {len(requests)} requests, {total_pass} assertions passed, {total_fail} failed, {total_error} errors")
    print(f"  Total time: {total_elapsed:.0f}ms\n")

    # Generate HTML report if requested.
    if args.report:
        report_path = Path(args.report)
        html = _generate_html_report(coll.name, results, total_elapsed)
        report_path.write_text(html, encoding="utf-8")
        print(f"  Report: {report_path.resolve()}\n")

    return 1 if (total_fail > 0 or total_error > 0) else 0


def _collect_requests(items: list[CollectionItem]) -> list[CollectionItem]:
    out: list[CollectionItem] = []
    for it in items:
        if it.is_folder:
            out.extend(_collect_requests(it.items))
        else:
            out.append(it)
    return out


def _substitute(text: str | None, vars: dict[str, str]) -> str:
    if not text:
        return ""
    import re
    def repl(m: re.Match[str]) -> str:
        return vars.get(m.group(1), m.group(0))
    return re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}", repl, text)


def _generate_html_report(name: str, results: list[dict[str, Any]], total_ms: float) -> str:
    rows = ""
    for r in results:
        status = r.get("status", "ERR")
        color = "#10b981" if isinstance(status, int) and status < 400 else "#ef4444"
        assertions_html = ""
        for a in r.get("assertions", []):
            icon = "\u2713" if a["passed"] else "\u2717"
            ac = "#10b981" if a["passed"] else "#ef4444"
            assertions_html += f'<div style="color:{ac};font-size:12px;padding:2px 0">{icon} {a["message"]}</div>'
        rows += f"""
        <tr>
          <td style="padding:10px;border-bottom:1px solid #222">{r.get("method","")}</td>
          <td style="padding:10px;border-bottom:1px solid #222;font-family:monospace;font-size:12px">{r.get("name","")}</td>
          <td style="padding:10px;border-bottom:1px solid #222;color:{color};font-weight:bold">{status}</td>
          <td style="padding:10px;border-bottom:1px solid #222">{r.get("elapsed_ms",0):.0f} ms</td>
          <td style="padding:10px;border-bottom:1px solid #222">{assertions_html or "—"}</td>
        </tr>"""

    total = len(results)
    passed = sum(1 for r in results if isinstance(r.get("status"), int) and r["status"] < 400)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Theridion Test Report — {name}</title>
<style>
  body {{ background:#0a0a0a; color:#e5e5e5; font-family:Inter,system-ui,sans-serif; margin:0; padding:40px; }}
  h1 {{ font-size:24px; font-weight:600; margin:0 0 8px; }}
  .meta {{ color:#737373; font-size:14px; margin-bottom:32px; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ text-align:left; padding:10px; border-bottom:2px solid #333; color:#737373; font-size:11px; text-transform:uppercase; letter-spacing:0.1em; }}
  .summary {{ display:flex; gap:24px; margin-bottom:24px; }}
  .stat {{ background:#111; border:1px solid #222; border-radius:8px; padding:16px 24px; }}
  .stat-value {{ font-size:28px; font-weight:700; }}
  .stat-label {{ font-size:11px; color:#737373; text-transform:uppercase; letter-spacing:0.1em; margin-top:4px; }}
</style>
</head>
<body>
<h1>Theridion Test Report</h1>
<div class="meta">{name} &middot; {total_ms:.0f}ms total</div>
<div class="summary">
  <div class="stat"><div class="stat-value">{total}</div><div class="stat-label">Requests</div></div>
  <div class="stat"><div class="stat-value" style="color:#10b981">{passed}</div><div class="stat-label">Passed</div></div>
  <div class="stat"><div class="stat-value" style="color:#ef4444">{total - passed}</div><div class="stat-label">Failed</div></div>
</div>
<table>
<thead><tr><th>Method</th><th>Name</th><th>Status</th><th>Time</th><th>Assertions</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</body>
</html>"""
