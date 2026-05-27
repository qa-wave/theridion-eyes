"""Product operations endpoints.

This module keeps release-readiness, feature governance, onboarding, and CI
packaging concerns in one place. The goal is to make Theridion's broad feature
surface visible and governable without adding more ad-hoc routers.
"""

from __future__ import annotations

import json
import os
import platform
import re
import sys
import uuid
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import __version__, storage
from ..assertions import Assertion
from ..models import AuthConfig, Collection, CollectionItem, CollectionVariable
from .reports import ReportInput, _generate_report_html

router = APIRouter(prefix="/api/product", tags=["product"])


FeatureStatus = Literal["stable", "beta", "experimental", "hidden", "archived"]
FeatureArea = Literal[
    "release",
    "core",
    "protocol",
    "testing",
    "security",
    "ai",
    "ci",
    "governance",
    "ecosystem",
]


class FeatureEntry(BaseModel):
    id: str
    label: str
    area: FeatureArea
    status: FeatureStatus
    ui: bool
    tests: bool
    docs: bool
    summary: str
    next_step: str


class FeatureRegistryOutput(BaseModel):
    generated_at: str
    totals: dict[str, int]
    features: list[FeatureEntry]


class ReadinessCheck(BaseModel):
    id: str
    label: str
    status: Literal["pass", "warn", "fail"]
    detail: str


class ReadinessOutput(BaseModel):
    version: str
    platform: str
    python: str
    storage_home: str
    checks: list[ReadinessCheck]
    summary: dict[str, int]


class HealthIssue(BaseModel):
    severity: Literal["info", "warn", "fail"]
    path: str
    message: str


class CollectionHealthOutput(BaseModel):
    collection_id: str
    collection_name: str
    request_count: int
    folder_count: int
    assertion_coverage_pct: float
    auth_coverage_pct: float
    variable_count: int
    issues: list[HealthIssue]


class SampleWorkspaceOutput(BaseModel):
    collection_id: str
    collection_name: str
    request_count: int
    message: str


class RedactionPreviewInput(BaseModel):
    value: str


class RedactionPreviewOutput(BaseModel):
    redacted: str
    replacements: int


class CiArtifactInput(BaseModel):
    report: ReportInput
    include_html: bool = True
    include_junit: bool = True
    include_json: bool = True
    include_markdown: bool = True
    redact: bool = True


SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(api[-_ ]?key['\"]?\s*[:=]\s*['\"]?)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(token['\"]?\s*[:=]\s*['\"]?)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(password['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+"),
    re.compile(r"(?i)(set-cookie:\s*)[^\n\r]+"),
]


FEATURES: list[FeatureEntry] = [
    FeatureEntry(
        id="release-readiness",
        label="Release readiness dashboard",
        area="release",
        status="stable",
        ui=True,
        tests=True,
        docs=False,
        summary="Single operational view for bundle, storage, platform, and release gates.",
        next_step="Keep adding checks as release gates become explicit.",
    ),
    FeatureEntry(
        id="feature-registry",
        label="Feature registry",
        area="governance",
        status="stable",
        ui=True,
        tests=True,
        docs=False,
        summary=(
            "Central manifest for stable, beta, experimental, hidden, "
            "and archived capabilities."
        ),
        next_step="Use it to drive command palette visibility and docs generation.",
    ),
    FeatureEntry(
        id="experimental-toggle",
        label="Experimental feature governance",
        area="governance",
        status="beta",
        ui=True,
        tests=True,
        docs=False,
        summary="Experimental and niche capabilities are labeled instead of looking stable.",
        next_step="Persist per-workspace feature visibility preferences.",
    ),
    FeatureEntry(
        id="cold-start-profile",
        label="Cold start profiling",
        area="release",
        status="beta",
        ui=True,
        tests=True,
        docs=False,
        summary="Readiness checks expose bundle presence and runtime hints.",
        next_step="Add import timing instrumentation around heavy protocol modules.",
    ),
    FeatureEntry(
        id="sample-workspace",
        label="First-run sample workspace",
        area="core",
        status="stable",
        ui=True,
        tests=True,
        docs=False,
        summary=(
            "Creates a local demo collection with REST, SOAP, GraphQL, "
            "assertions, and CI examples."
        ),
        next_step="Open the generated requests automatically after creation.",
    ),
    FeatureEntry(
        id="migration-guidance",
        label="Guided migration report",
        area="ecosystem",
        status="beta",
        ui=False,
        tests=False,
        docs=False,
        summary="Universal import already exists; this defines the report shape users need.",
        next_step="Return warnings from every importer in a shared format.",
    ),
    FeatureEntry(
        id="collection-health",
        label="Collection health check",
        area="testing",
        status="stable",
        ui=True,
        tests=True,
        docs=False,
        summary="Static lint for URLs, assertions, variables, duplicate names, and secret leaks.",
        next_step="Add quick fixes for common findings.",
    ),
    FeatureEntry(
        id="variable-inspector",
        label="Variable resolution inspector",
        area="core",
        status="stable",
        ui=True,
        tests=True,
        docs=True,
        summary="Existing variable inspector is part of the governed release surface.",
        next_step="Embed resolution hints directly in URL/body editors.",
    ),
    FeatureEntry(
        id="execution-timeline",
        label="Unified execution timeline",
        area="testing",
        status="beta",
        ui=True,
        tests=True,
        docs=False,
        summary="Timing, network, retry, cookie, and redirect data are tracked as one surface.",
        next_step="Persist timeline events into trace artifacts.",
    ),
    FeatureEntry(
        id="trace-viewer",
        label="In-app trace viewer",
        area="testing",
        status="beta",
        ui=True,
        tests=True,
        docs=False,
        summary="HTML trace generation exists and is exposed as a release differentiator.",
        next_step="Add historical trace library inside the app.",
    ),
    FeatureEntry(
        id="soap-workbench",
        label="SOAP contract workbench",
        area="protocol",
        status="beta",
        ui=True,
        tests=True,
        docs=True,
        summary="SOAP, XSD, WSDL diff, WS-Security, MTOM, and coverage are one workbench.",
        next_step="Build a single SOAP workbench screen instead of isolated modals.",
    ),
    FeatureEntry(
        id="cert-manager",
        label="WS-Security certificate manager",
        area="security",
        status="beta",
        ui=True,
        tests=True,
        docs=False,
        summary="Certificate APIs are tracked as release-critical SOAP infrastructure.",
        next_step="Add expiry alerts and signing diagnostics.",
    ),
    FeatureEntry(
        id="contract-drift",
        label="OpenAPI contract drift watcher",
        area="testing",
        status="beta",
        ui=True,
        tests=True,
        docs=False,
        summary="Contract guard and OpenAPI sync are promoted as one drift workflow.",
        next_step="Schedule drift checks for monitored collections.",
    ),
    FeatureEntry(
        id="assertion-maintenance",
        label="Assertion maintenance queue",
        area="ai",
        status="beta",
        ui=True,
        tests=True,
        docs=False,
        summary="Self-healing assertions are tracked as a queueable maintenance workflow.",
        next_step="Add accept/reject state and audit history.",
    ),
    FeatureEntry(
        id="secrets-policy",
        label="Secrets policy and redaction preview",
        area="security",
        status="stable",
        ui=True,
        tests=True,
        docs=False,
        summary=(
            "Preview redaction before data lands in reports, logs, "
            "clipboard, or CI artifacts."
        ),
        next_step="Make redaction policy configurable per workspace.",
    ),
    FeatureEntry(
        id="ci-artifact-pack",
        label="CI artifact pack",
        area="ci",
        status="stable",
        ui=False,
        tests=True,
        docs=False,
        summary="Generates redacted HTML, JSON, Markdown, and JUnit artifacts in one ZIP.",
        next_step="Wire this into the CLI runner output path.",
    ),
    FeatureEntry(
        id="github-action",
        label="Official GitHub Action contract",
        area="ci",
        status="experimental",
        ui=False,
        tests=False,
        docs=False,
        summary="Defines artifact outputs required by a marketplace action.",
        next_step="Add action.yml and release packaging.",
    ),
    FeatureEntry(
        id="plugin-boundary",
        label="Plugin boundary for niche protocols",
        area="ecosystem",
        status="experimental",
        ui=True,
        tests=False,
        docs=False,
        summary="Kafka, JMS, JDBC, MQTT, AMF, and similar protocols are plugin candidates.",
        next_step="Move plugin candidates behind lazy imports.",
    ),
    FeatureEntry(
        id="workflow-usability-audit",
        label="Workflow usability audit",
        area="governance",
        status="beta",
        ui=True,
        tests=False,
        docs=False,
        summary=(
            "Release center tracks import, request, auth, assertion, "
            "and CI workflow friction."
        ),
        next_step="Attach measured step counts from E2E flows.",
    ),
    FeatureEntry(
        id="release-narrative",
        label="Public release narrative",
        area="release",
        status="beta",
        ui=True,
        tests=False,
        docs=True,
        summary="Release surface is framed around local-first testing, WS-Security, and traces.",
        next_step="Generate release notes from the feature registry.",
    ),
]


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _walk(
    items: list[CollectionItem],
    prefix: str = "",
) -> Iterator[tuple[CollectionItem, str]]:
    for item in items:
        path = f"{prefix}/{item.name}" if prefix else item.name
        yield item, path
        if item.is_folder:
            yield from _walk(item.items, path)


def _duplicate_name_issues(items: list[CollectionItem], prefix: str = "") -> list[HealthIssue]:
    seen: dict[str, int] = {}
    issues: list[HealthIssue] = []
    for item in items:
        seen[item.name] = seen.get(item.name, 0) + 1
        if item.is_folder:
            child_prefix = f"{prefix}/{item.name}" if prefix else item.name
            issues.extend(_duplicate_name_issues(item.items, child_prefix))
    for name, count in seen.items():
        if count > 1:
            issues.append(
                HealthIssue(
                    severity="warn",
                    path=prefix or "/",
                    message=f"duplicate item name: {name}",
                )
            )
    return issues


def _redact(value: str) -> tuple[str, int]:
    count = 0
    redacted = value
    for pattern in SENSITIVE_PATTERNS:
        redacted, n = pattern.subn(lambda m: f"{m.group(1)}[REDACTED]", redacted)
        count += n
    return redacted, count


@router.get("/features", response_model=FeatureRegistryOutput)
def feature_registry() -> FeatureRegistryOutput:
    totals: dict[str, int] = {}
    for feature in FEATURES:
        totals[feature.status] = totals.get(feature.status, 0) + 1
    return FeatureRegistryOutput(generated_at=_now(), totals=totals, features=FEATURES)


@router.get("/readiness", response_model=ReadinessOutput)
def readiness() -> ReadinessOutput:
    root = storage.home_dir()
    root.mkdir(parents=True, exist_ok=True)
    binary_dir = Path(__file__).parents[3] / "desktop" / "src-tauri" / "binaries"
    checks = [
        ReadinessCheck(
            id="storage-home",
            label="Storage home writable",
            status="pass" if os.access(root, os.W_OK) else "fail",
            detail=str(root),
        ),
        ReadinessCheck(
            id="collections",
            label="Collections readable",
            status="pass",
            detail=f"{len(storage.list_summaries())} collections",
        ),
        ReadinessCheck(
            id="python",
            label="Python runtime",
            status="pass",
            detail=sys.version.split()[0],
        ),
        ReadinessCheck(
            id="bundle-dir",
            label="Bundled sidecar directory",
            status="pass" if binary_dir.exists() else "warn",
            detail=str(binary_dir),
        ),
        ReadinessCheck(
            id="feature-governance",
            label="Feature registry available",
            status="pass",
            detail=f"{len(FEATURES)} governed features",
        ),
    ]
    summary = {"pass": 0, "warn": 0, "fail": 0}
    for check in checks:
        summary[check.status] += 1
    return ReadinessOutput(
        version=__version__,
        platform=f"{platform.system()} {platform.machine()}",
        python=sys.version.split()[0],
        storage_home=str(root),
        checks=checks,
        summary=summary,
    )


@router.get("/collections/{collection_id}/health", response_model=CollectionHealthOutput)
def collection_health(collection_id: str) -> CollectionHealthOutput:
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")

    issues: list[HealthIssue] = []
    request_count = 0
    folder_count = 0
    with_assertions = 0
    with_auth = 0
    variable_count = len(coll.variables)
    issues.extend(_duplicate_name_issues(coll.items))

    for entry, path in _walk(coll.items):
        if entry.is_folder:
            folder_count += 1
            continue
        request_count += 1
        if entry.assertions:
            with_assertions += 1
        else:
            issues.append(
                HealthIssue(
                    severity="warn",
                    path=path,
                    message="request has no assertions",
                )
            )
        if entry.auth and entry.auth.type != "none":
            with_auth += 1
        if not entry.url:
            issues.append(HealthIssue(severity="fail", path=path, message="request URL is empty"))
        haystack = "\n".join([entry.url or "", json.dumps(entry.headers or {}), entry.body or ""])
        _, replacements = _redact(haystack)
        if replacements:
            issues.append(
                HealthIssue(
                    severity="fail",
                    path=path,
                    message="possible secret stored in request data",
                )
            )
        for var_name in re.findall(r"{{\s*([A-Za-z_][\w.-]*)\s*}}", haystack):
            if not any(v.name == var_name and v.enabled for v in coll.variables):
                issues.append(
                    HealthIssue(
                        severity="info",
                        path=path,
                        message=(
                            f"variable '{var_name}' is not defined at collection scope"
                        ),
                    )
                )

    return CollectionHealthOutput(
        collection_id=coll.id,
        collection_name=coll.name,
        request_count=request_count,
        folder_count=folder_count,
        assertion_coverage_pct=(
            round((with_assertions / request_count) * 100, 1)
            if request_count
            else 100.0
        ),
        auth_coverage_pct=round((with_auth / request_count) * 100, 1) if request_count else 0.0,
        variable_count=variable_count,
        issues=issues,
    )


@router.post("/sample-workspace", response_model=SampleWorkspaceOutput, status_code=201)
def create_sample_workspace() -> SampleWorkspaceOutput:
    coll = Collection(
        id=str(uuid.uuid4()),
        name="Theridion Sample Workspace",
        variables=[
            CollectionVariable(name="baseUrl", value="https://api.example.com", enabled=True),
            CollectionVariable(name="token", value="replace-me", enabled=True),
        ],
        items=[
            CollectionItem(
                id=str(uuid.uuid4()),
                name="REST health",
                method="GET",
                url="{{baseUrl}}/health",
                headers={"accept": "application/json"},
                assertions=[Assertion(type="status", expected="200")],
            ),
            CollectionItem(
                id=str(uuid.uuid4()),
                name="Authenticated profile",
                method="GET",
                url="{{baseUrl}}/me",
                auth=AuthConfig(type="bearer", token="{{token}}"),
                assertions=[
                    Assertion(type="json_path", path="$.id", operator="exists")
                ],
            ),
            CollectionItem(
                id=str(uuid.uuid4()),
                name="GraphQL current user",
                method="POST",
                url="{{baseUrl}}/graphql",
                headers={"content-type": "application/json"},
                body='{"query":"query { viewer { id name } }"}',
                assertions=[Assertion(type="body_contains", expected="viewer")],
            ),
            CollectionItem(
                id=str(uuid.uuid4()),
                name="SOAP calculator",
                method="POST",
                url="{{baseUrl}}/soap",
                headers={"content-type": "text/xml"},
                body="<Envelope><Body><!-- WSDL operation sample --></Body></Envelope>",
                assertions=[Assertion(type="status", expected="200")],
            ),
        ],
    )
    storage._atomic_write(coll)  # noqa: SLF001 - product onboarding needs one atomic seed write.
    return SampleWorkspaceOutput(
        collection_id=coll.id,
        collection_name=coll.name,
        request_count=4,
        message="Sample workspace created",
    )


@router.post("/redaction/preview", response_model=RedactionPreviewOutput)
def redaction_preview(body: RedactionPreviewInput) -> RedactionPreviewOutput:
    redacted, replacements = _redact(body.value)
    return RedactionPreviewOutput(redacted=redacted, replacements=replacements)


@router.post("/ci-artifact-pack")
def ci_artifact_pack(body: CiArtifactInput) -> Response:
    report = body.report
    payload = report.model_dump(mode="json")
    json_text = json.dumps(payload, indent=2)
    summary_text = json.dumps(
        {
            "generated_at": _now(),
            "collection": report.collection_name,
            "failed": report.failed_requests,
        },
        indent=2,
    )
    markdown = (
        f"# Theridion CI Report\n\n"
        f"- Collection: {report.collection_name}\n"
        f"- Total requests: {report.total_requests}\n"
        f"- Passed: {report.successful_requests}\n"
        f"- Failed: {report.failed_requests}\n"
        f"- Assertions: {report.passed_assertions}/{report.total_assertions}\n"
    )
    html_text = _generate_report_html(report)
    junit_text = _junit_xml(report)
    if body.redact:
        summary_text, _ = _redact(summary_text)
        json_text, _ = _redact(json_text)
        markdown, _ = _redact(markdown)
        html_text, _ = _redact(html_text)
        junit_text, _ = _redact(junit_text)

    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("summary.json", summary_text)
        if body.include_json:
            zf.writestr("report.json", json_text)
        if body.include_markdown:
            zf.writestr("report.md", markdown)
        if body.include_html:
            zf.writestr("trace.html", html_text)
        if body.include_junit:
            zf.writestr("junit.xml", junit_text)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"content-disposition": 'attachment; filename="theridion-ci-artifacts.zip"'},
    )


def _junit_xml(report: ReportInput) -> str:
    failures = sum(1 for r in report.results if r.error or r.assertions_failed > 0)
    cases = [
        (
            f'<testsuite name="{_xml(report.collection_name)}" '
            f'tests="{len(report.results)}" failures="{failures}">'
        )
    ]
    for result in report.results:
        cases.append(
            (
                f'<testcase classname="{_xml(report.collection_name)}" '
                f'name="{_xml(result.request_name)}" '
                f'time="{result.elapsed_ms / 1000:.3f}">'
            )
        )
        if result.error or result.assertions_failed > 0:
            message = _xml(result.error or "assertion failed")
            cases.append(f'<failure message="{message}"></failure>')
        cases.append("</testcase>")
    cases.append("</testsuite>")
    return "".join(cases)


def _xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
