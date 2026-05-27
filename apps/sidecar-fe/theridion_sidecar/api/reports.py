"""Report generation: HTML, JUnit XML, JSON, and Markdown from collection runner results.

Accepts the same result shape produced by the collection runner
(POST /api/runner/{id}/run) and generates self-contained reports
suitable for CI/CD pipelines, PR comments, and archival.
"""

from __future__ import annotations

import html
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/reports", tags=["reports"])


# ---- Input models ----------------------------------------------------------


class AssertionResultInput(BaseModel):
    assertion: dict[str, Any] = Field(default_factory=dict)
    passed: bool = True
    message: str = ""


class RequestResultInput(BaseModel):
    request_id: str = ""
    request_name: str = ""
    method: str = "GET"
    url: str = ""
    status: int | None = None
    elapsed_ms: float = 0
    error: str | None = None
    assertion_results: list[AssertionResultInput] = Field(default_factory=list)
    assertions_passed: int = 0
    assertions_failed: int = 0


class ReportInput(BaseModel):
    """Mirrors RunCollectionOutput from the collection runner."""

    collection_id: str = ""
    collection_name: str = "Unnamed Collection"
    results: list[RequestResultInput] = Field(default_factory=list)
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_assertions: int = 0
    passed_assertions: int = 0
    failed_assertions: int = 0
    total_elapsed_ms: float = 0


# ---- HTML report -----------------------------------------------------------


class HtmlReportOutput(BaseModel):
    html: str


def _generate_report_html(data: ReportInput) -> str:
    """Return a self-contained HTML report with summary, per-request details,
    charts (SVG pie + bar), filtering, and dark theme."""

    timestamp = datetime.now(tz=UTC).isoformat(timespec="seconds")
    total = data.total_requests or len(data.results)
    passed = data.successful_requests
    failed = data.failed_requests
    skipped = total - passed - failed
    duration_s = data.total_elapsed_ms / 1000

    # Build JSON payload for JS
    results_json = json.dumps(
        [r.model_dump(mode="json") for r in data.results],
        ensure_ascii=False,
    )

    # SVG pie chart (pass/fail)
    pie_svg = _pie_chart_svg(passed, failed, skipped)

    # Per-request rows HTML
    rows_html = ""
    for r in data.results:
        status_cls = "pass" if r.error is None and r.status is not None and r.status < 400 else "fail"
        status_display = str(r.status) if r.status is not None else "ERR"
        assertions_html = ""
        if r.assertion_results:
            assertions_html = '<ul class="assertions">'
            for a in r.assertion_results:
                a_cls = "pass" if a.passed else "fail"
                assertions_html += f'<li class="{a_cls}">{html.escape(a.message)}</li>'
            assertions_html += "</ul>"

        rows_html += f"""
        <tr class="req-row" data-status="{status_cls}" data-name="{html.escape(r.request_name.lower())}">
          <td><span class="method">{html.escape(r.method)}</span></td>
          <td class="name-cell">{html.escape(r.request_name)}</td>
          <td>{html.escape(r.url)}</td>
          <td class="status-{status_cls}">{status_display}</td>
          <td>{r.elapsed_ms:.0f}ms</td>
          <td>{r.assertions_passed}/{r.assertions_passed + r.assertions_failed}</td>
          <td>{html.escape(r.error or "")}</td>
        </tr>
        """
        if assertions_html:
            rows_html += f'<tr class="req-row assertion-detail" data-status="{status_cls}" data-name="{html.escape(r.request_name.lower())}"><td colspan="7">{assertions_html}</td></tr>'

    # Response time bar data
    bar_data_json = json.dumps(
        [
            {"name": r.request_name[:30], "ms": r.elapsed_ms}
            for r in data.results
        ],
        ensure_ascii=False,
    )

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Theridion Report — {html.escape(data.collection_name)}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
background:#0a0a0a;color:#e5e5e5;padding:1.5rem;line-height:1.5}}
h1{{font-size:1.5rem;font-weight:700;margin-bottom:.25rem}}
.subtitle{{color:#737373;font-size:.875rem;margin-bottom:1.5rem}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem;margin-bottom:1.5rem}}
.stat{{background:#171717;border-radius:8px;padding:1rem;text-align:center}}
.stat .value{{font-size:1.75rem;font-weight:700}}
.stat .label{{font-size:.75rem;color:#737373;text-transform:uppercase;letter-spacing:.05em}}
.stat.pass .value{{color:#6ee7b7}}
.stat.fail .value{{color:#fca5a5}}
.stat.time .value{{color:#93c5fd}}
.stat.total .value{{color:#e5e5e5}}
.charts{{display:flex;gap:1.5rem;margin-bottom:1.5rem;flex-wrap:wrap}}
.chart-box{{background:#171717;border-radius:8px;padding:1rem;flex:1;min-width:280px}}
.chart-box h3{{font-size:.875rem;color:#a3a3a3;margin-bottom:.75rem}}
.filters{{display:flex;gap:.75rem;margin-bottom:1rem;align-items:center;flex-wrap:wrap}}
.filters input{{background:#171717;border:1px solid #262626;border-radius:6px;padding:.375rem .75rem;
color:#e5e5e5;font-size:.8125rem;min-width:200px}}
.filters button{{background:#171717;border:1px solid #262626;border-radius:6px;padding:.375rem .75rem;
color:#a3a3a3;font-size:.8125rem;cursor:pointer;transition:all .15s}}
.filters button:hover,.filters button.active{{background:#262626;color:#e5e5e5;border-color:#404040}}
table{{width:100%;border-collapse:collapse;font-size:.8125rem}}
thead{{background:#171717;position:sticky;top:0}}
th{{padding:.5rem .75rem;text-align:left;font-weight:600;color:#a3a3a3;border-bottom:1px solid #262626}}
td{{padding:.5rem .75rem;border-bottom:1px solid #1a1a1a}}
.method{{font-weight:700;font-size:.75rem;padding:2px 6px;border-radius:3px;background:#262626}}
.name-cell{{font-weight:500}}
.status-pass{{color:#6ee7b7;font-weight:700}}
.status-fail{{color:#fca5a5;font-weight:700}}
.assertions{{list-style:none;padding:.25rem 0}}
.assertions li{{padding:2px 0;font-size:.75rem}}
.assertions li.pass::before{{content:"\\2713 ";color:#6ee7b7}}
.assertions li.fail::before{{content:"\\2717 ";color:#f87171}}
.assertion-detail td{{background:#111;padding:.25rem .75rem}}
.bar-chart{{display:flex;flex-direction:column;gap:3px;max-height:300px;overflow-y:auto}}
.bar-row{{display:flex;align-items:center;gap:.5rem}}
.bar-label{{min-width:120px;max-width:160px;font-size:.6875rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.bar-track{{flex:1;height:16px;background:#262626;border-radius:3px;position:relative}}
.bar-fill{{height:100%;border-radius:3px;background:#059669;min-width:2px;display:flex;align-items:center;padding-left:4px;font-size:.625rem;color:#fff;white-space:nowrap}}
.hidden{{display:none}}
footer{{margin-top:2rem;padding-top:1rem;border-top:1px solid #262626;font-size:.75rem;color:#525252;text-align:center}}
@media(max-width:640px){{.summary{{grid-template-columns:1fr 1fr}}.charts{{flex-direction:column}}}}
</style>
</head>
<body>
<h1>Theridion Report — {html.escape(data.collection_name)}</h1>
<p class="subtitle">Generated {timestamp} | Total duration {duration_s:.2f}s</p>

<div class="summary">
  <div class="stat total"><div class="value">{total}</div><div class="label">Total</div></div>
  <div class="stat pass"><div class="value">{passed}</div><div class="label">Passed</div></div>
  <div class="stat fail"><div class="value">{failed}</div><div class="label">Failed</div></div>
  <div class="stat time"><div class="value">{duration_s:.2f}s</div><div class="label">Duration</div></div>
</div>

<div class="charts">
  <div class="chart-box">
    <h3>Pass / Fail</h3>
    {pie_svg}
  </div>
  <div class="chart-box">
    <h3>Response Time (ms)</h3>
    <div id="bar-chart" class="bar-chart"></div>
  </div>
</div>

<div class="filters">
  <input type="text" id="search" placeholder="Filter by name..." />
  <button type="button" class="filter-btn active" data-filter="all">All</button>
  <button type="button" class="filter-btn" data-filter="pass">Passed</button>
  <button type="button" class="filter-btn" data-filter="fail">Failed</button>
</div>

<table>
  <thead>
    <tr><th>Method</th><th>Name</th><th>URL</th><th>Status</th><th>Time</th><th>Assertions</th><th>Error</th></tr>
  </thead>
  <tbody id="results-body">
    {rows_html}
  </tbody>
</table>

<footer>Theridion API Testing Platform</footer>

<script>
(function(){{
  var barData = {bar_data_json};
  var maxMs = Math.max.apply(null, barData.map(function(d){{ return d.ms; }})) || 1;
  var barHtml = "";
  barData.forEach(function(d){{
    var pct = Math.max(d.ms / maxMs * 100, 1);
    barHtml += '<div class="bar-row"><div class="bar-label">' + d.name + '</div>';
    barHtml += '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%">' + d.ms.toFixed(0) + 'ms</div></div></div>';
  }});
  document.getElementById("bar-chart").innerHTML = barHtml;

  var searchEl = document.getElementById("search");
  var rows = document.querySelectorAll(".req-row");
  var activeFilter = "all";

  function applyFilter() {{
    var q = searchEl.value.toLowerCase();
    rows.forEach(function(row) {{
      var name = row.getAttribute("data-name") || "";
      var status = row.getAttribute("data-status") || "";
      var nameMatch = !q || name.indexOf(q) >= 0;
      var statusMatch = activeFilter === "all" || status === activeFilter;
      row.classList.toggle("hidden", !(nameMatch && statusMatch));
    }});
  }}

  searchEl.addEventListener("input", applyFilter);
  document.querySelectorAll(".filter-btn").forEach(function(btn) {{
    btn.addEventListener("click", function() {{
      document.querySelectorAll(".filter-btn").forEach(function(b){{ b.classList.remove("active"); }});
      btn.classList.add("active");
      activeFilter = btn.getAttribute("data-filter");
      applyFilter();
    }});
  }});
}})();
</script>
</body>
</html>
"""


def _pie_chart_svg(passed: int, failed: int, skipped: int) -> str:
    """Generate a simple SVG donut chart for pass/fail/skipped."""
    total = passed + failed + skipped
    if total == 0:
        return '<svg viewBox="0 0 120 120" width="120" height="120"><circle cx="60" cy="60" r="50" fill="#262626"/><text x="60" y="65" text-anchor="middle" fill="#737373" font-size="12">No data</text></svg>'

    segments = []
    colors = [("#059669", passed), ("#dc2626", failed), ("#525252", skipped)]
    offset = 0
    circumference = 2 * 3.14159 * 40

    for color, count in colors:
        if count == 0:
            continue
        pct = count / total
        dash = pct * circumference
        gap = circumference - dash
        segments.append(
            f'<circle cx="60" cy="60" r="40" fill="none" stroke="{color}" stroke-width="18" '
            f'stroke-dasharray="{dash:.2f} {gap:.2f}" stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 60 60)"/>'
        )
        offset += dash

    joined = "\n".join(segments)
    pass_pct = round(passed / total * 100) if total else 0
    return f"""\
<svg viewBox="0 0 120 120" width="140" height="140">
{joined}
<text x="60" y="58" text-anchor="middle" fill="#e5e5e5" font-size="16" font-weight="700">{pass_pct}%</text>
<text x="60" y="72" text-anchor="middle" fill="#737373" font-size="9">pass rate</text>
</svg>"""


@router.post("/generate/html", response_model=HtmlReportOutput)
async def generate_html_report(body: ReportInput) -> HtmlReportOutput:
    return HtmlReportOutput(html=_generate_report_html(body))


# ---- JUnit XML report ------------------------------------------------------


class JunitReportOutput(BaseModel):
    xml: str


def _generate_junit_xml(data: ReportInput) -> str:
    """Generate JUnit XML compatible with Jenkins, GitHub Actions, GitLab CI."""
    testsuites = ET.Element("testsuites")
    testsuite = ET.SubElement(testsuites, "testsuite")
    testsuite.set("name", data.collection_name)
    testsuite.set("tests", str(data.total_requests or len(data.results)))
    testsuite.set("failures", str(data.failed_assertions))
    testsuite.set("errors", str(data.failed_requests))
    testsuite.set("time", f"{data.total_elapsed_ms / 1000:.3f}")
    testsuite.set("timestamp", datetime.now(tz=UTC).isoformat(timespec="seconds"))

    for r in data.results:
        if r.assertion_results:
            # One testcase per assertion
            for a in r.assertion_results:
                tc = ET.SubElement(testsuite, "testcase")
                tc.set("name", f"{r.request_name} :: {a.message}")
                tc.set("classname", data.collection_name)
                tc.set("time", f"{r.elapsed_ms / 1000:.3f}")
                if not a.passed:
                    failure = ET.SubElement(tc, "failure")
                    failure.set("message", a.message)
                    failure.set("type", a.assertion.get("type", "assertion"))
                    failure.text = f"Request: {r.method} {r.url}\nStatus: {r.status}\n{a.message}"
        else:
            # No assertions — one testcase per request
            tc = ET.SubElement(testsuite, "testcase")
            tc.set("name", r.request_name)
            tc.set("classname", data.collection_name)
            tc.set("time", f"{r.elapsed_ms / 1000:.3f}")
            if r.error:
                error_el = ET.SubElement(tc, "error")
                error_el.set("message", r.error)
                error_el.set("type", "TransportError")
                error_el.text = f"Request: {r.method} {r.url}\n{r.error}"
            elif r.status is not None and r.status >= 400:
                failure = ET.SubElement(tc, "failure")
                failure.set("message", f"HTTP {r.status}")
                failure.set("type", "HttpError")
                failure.text = f"Request: {r.method} {r.url}\nHTTP status {r.status}"

    return ET.tostring(testsuites, encoding="unicode", xml_declaration=True)


@router.post("/generate/junit", response_model=JunitReportOutput)
async def generate_junit_report(body: ReportInput) -> JunitReportOutput:
    return JunitReportOutput(xml=_generate_junit_xml(body))


# ---- JSON report -----------------------------------------------------------


class JsonReportOutput(BaseModel):
    report: dict[str, Any]


def _generate_json_report(data: ReportInput) -> dict[str, Any]:
    """Structured JSON export for programmatic consumption."""
    return {
        "meta": {
            "tool": "Theridion",
            "version": "1.0",
            "generated_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        },
        "collection": {
            "id": data.collection_id,
            "name": data.collection_name,
        },
        "summary": {
            "total_requests": data.total_requests or len(data.results),
            "successful_requests": data.successful_requests,
            "failed_requests": data.failed_requests,
            "total_assertions": data.total_assertions,
            "passed_assertions": data.passed_assertions,
            "failed_assertions": data.failed_assertions,
            "total_elapsed_ms": data.total_elapsed_ms,
        },
        "results": [r.model_dump(mode="json") for r in data.results],
    }


@router.post("/generate/json", response_model=JsonReportOutput)
async def generate_json_report(body: ReportInput) -> JsonReportOutput:
    return JsonReportOutput(report=_generate_json_report(body))


# ---- Markdown report -------------------------------------------------------


class MarkdownReportOutput(BaseModel):
    markdown: str


def _generate_markdown(data: ReportInput) -> str:
    """Markdown table suitable for PR comments and documentation."""
    timestamp = datetime.now(tz=UTC).isoformat(timespec="seconds")
    total = data.total_requests or len(data.results)
    lines = [
        f"# Theridion Report: {data.collection_name}",
        "",
        f"Generated: {timestamp}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Requests | {total} |",
        f"| Passed | {data.successful_requests} |",
        f"| Failed | {data.failed_requests} |",
        f"| Total Assertions | {data.total_assertions} |",
        f"| Passed Assertions | {data.passed_assertions} |",
        f"| Failed Assertions | {data.failed_assertions} |",
        f"| Duration | {data.total_elapsed_ms:.0f}ms |",
        "",
        "## Results",
        "",
        "| Method | Name | Status | Time | Assertions | Error |",
        "|--------|------|--------|------|------------|-------|",
    ]

    for r in data.results:
        status = str(r.status) if r.status is not None else "ERR"
        icon = "x" if (r.error or (r.status is not None and r.status >= 400)) else "check"
        a_summary = f"{r.assertions_passed}/{r.assertions_passed + r.assertions_failed}" if r.assertion_results else "-"
        error = r.error or ""
        # Escape pipe chars in error messages for Markdown tables
        error = error.replace("|", "\\|")[:80]
        lines.append(
            f"| {r.method} | {r.request_name} | :{icon}: {status} | {r.elapsed_ms:.0f}ms | {a_summary} | {error} |"
        )

    if data.results:
        # Add assertion details for failures
        failed_assertions = [
            (r, a)
            for r in data.results
            for a in r.assertion_results
            if not a.passed
        ]
        if failed_assertions:
            lines.append("")
            lines.append("## Failed Assertions")
            lines.append("")
            for r, a in failed_assertions:
                lines.append(f"- **{r.request_name}**: {a.message}")

    lines.append("")
    lines.append("---")
    lines.append("*Generated by Theridion API Testing Platform*")
    lines.append("")
    return "\n".join(lines)


@router.post("/generate/markdown", response_model=MarkdownReportOutput)
async def generate_markdown_report(body: ReportInput) -> MarkdownReportOutput:
    return MarkdownReportOutput(markdown=_generate_markdown(body))
