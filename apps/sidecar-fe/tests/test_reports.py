"""Tests for report generation endpoints (HTML, JUnit XML, JSON, Markdown)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest
from httpx import ASGITransport, AsyncClient

from theridion_sidecar.main import app

BASE = "http://test"


def _sample_input(
    *,
    with_assertions: bool = True,
    mixed: bool = False,
) -> dict:
    """Build a ReportInput-like dict matching RunCollectionOutput shape."""
    results = [
        {
            "request_id": "r1",
            "request_name": "Get Users",
            "method": "GET",
            "url": "https://api.example.com/users",
            "status": 200,
            "elapsed_ms": 120.5,
            "error": None,
            "assertion_results": (
                [
                    {"assertion": {"type": "status", "expected": "200"}, "passed": True, "message": "Status is 200"},
                    {"assertion": {"type": "body_contains", "expected": "users"}, "passed": True, "message": "Body contains 'users'"},
                ]
                if with_assertions
                else []
            ),
            "assertions_passed": 2 if with_assertions else 0,
            "assertions_failed": 0,
        },
    ]

    if mixed:
        results.append(
            {
                "request_id": "r2",
                "request_name": "Delete Admin",
                "method": "DELETE",
                "url": "https://api.example.com/admin",
                "status": 403,
                "elapsed_ms": 45.2,
                "error": None,
                "assertion_results": [
                    {"assertion": {"type": "status", "expected": "200"}, "passed": False, "message": "Expected status 200, got 403"},
                ],
                "assertions_passed": 0,
                "assertions_failed": 1,
            },
        )
        results.append(
            {
                "request_id": "r3",
                "request_name": "Broken Request",
                "method": "POST",
                "url": "https://api.example.com/broken",
                "status": None,
                "elapsed_ms": 5000,
                "error": "transport error: connection refused",
                "assertion_results": [],
                "assertions_passed": 0,
                "assertions_failed": 0,
            },
        )

    total = len(results)
    successful = sum(1 for r in results if r["error"] is None and r["status"] is not None and r["status"] < 400)
    failed = total - successful
    a_passed = sum(r["assertions_passed"] for r in results)
    a_failed = sum(r["assertions_failed"] for r in results)

    return {
        "collection_id": "coll-1",
        "collection_name": "Test Collection",
        "results": results,
        "total_requests": total,
        "successful_requests": successful,
        "failed_requests": failed,
        "total_assertions": a_passed + a_failed,
        "passed_assertions": a_passed,
        "failed_assertions": a_failed,
        "total_elapsed_ms": sum(r["elapsed_ms"] for r in results),
    }


def _empty_input() -> dict:
    return {
        "collection_id": "",
        "collection_name": "Empty",
        "results": [],
        "total_requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "total_assertions": 0,
        "passed_assertions": 0,
        "failed_assertions": 0,
        "total_elapsed_ms": 0,
    }


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)  # type: ignore[arg-type]


# ---- HTML report -----------------------------------------------------------


@pytest.mark.anyio
async def test_html_report_basic_structure(transport: ASGITransport) -> None:
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        resp = await client.post("/api/reports/generate/html", json=_sample_input())
    assert resp.status_code == 200
    html = resp.json()["html"]
    assert "<!DOCTYPE html>" in html
    assert "Test Collection" in html
    assert "Get Users" in html
    assert "200" in html
    # Check pie chart SVG is present
    assert "<svg" in html
    assert "pass rate" in html


@pytest.mark.anyio
async def test_html_report_empty(transport: ASGITransport) -> None:
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        resp = await client.post("/api/reports/generate/html", json=_empty_input())
    assert resp.status_code == 200
    html = resp.json()["html"]
    assert "<!DOCTYPE html>" in html
    assert "No data" in html


@pytest.mark.anyio
async def test_html_report_mixed(transport: ASGITransport) -> None:
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        resp = await client.post("/api/reports/generate/html", json=_sample_input(mixed=True))
    assert resp.status_code == 200
    html = resp.json()["html"]
    assert "Delete Admin" in html
    assert "Broken Request" in html
    assert "connection refused" in html


# ---- JUnit XML report ------------------------------------------------------


@pytest.mark.anyio
async def test_junit_xml_validity(transport: ASGITransport) -> None:
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        resp = await client.post("/api/reports/generate/junit", json=_sample_input())
    assert resp.status_code == 200
    xml_str = resp.json()["xml"]
    root = ET.fromstring(xml_str)
    assert root.tag == "testsuites"
    suite = root.find("testsuite")
    assert suite is not None
    assert suite.get("name") == "Test Collection"
    testcases = suite.findall("testcase")
    # 2 assertions = 2 testcases
    assert len(testcases) == 2
    assert all(tc.get("classname") == "Test Collection" for tc in testcases)
    # No failures in this case
    for tc in testcases:
        assert tc.find("failure") is None


@pytest.mark.anyio
async def test_junit_xml_with_failures(transport: ASGITransport) -> None:
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        resp = await client.post("/api/reports/generate/junit", json=_sample_input(mixed=True))
    assert resp.status_code == 200
    xml_str = resp.json()["xml"]
    root = ET.fromstring(xml_str)
    suite = root.find("testsuite")
    assert suite is not None
    # r1 has 2 assertion TCs, r2 has 1 assertion TC, r3 has 1 request TC (error)
    testcases = suite.findall("testcase")
    assert len(testcases) == 4
    failures = [tc for tc in testcases if tc.find("failure") is not None]
    errors = [tc for tc in testcases if tc.find("error") is not None]
    assert len(failures) == 1
    assert len(errors) == 1


@pytest.mark.anyio
async def test_junit_xml_empty(transport: ASGITransport) -> None:
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        resp = await client.post("/api/reports/generate/junit", json=_empty_input())
    assert resp.status_code == 200
    xml_str = resp.json()["xml"]
    root = ET.fromstring(xml_str)
    suite = root.find("testsuite")
    assert suite is not None
    assert suite.get("tests") == "0"
    assert len(suite.findall("testcase")) == 0


# ---- JSON report -----------------------------------------------------------


@pytest.mark.anyio
async def test_json_report_structure(transport: ASGITransport) -> None:
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        resp = await client.post("/api/reports/generate/json", json=_sample_input())
    assert resp.status_code == 200
    report = resp.json()["report"]
    assert "meta" in report
    assert report["meta"]["tool"] == "Theridion"
    assert "collection" in report
    assert report["collection"]["name"] == "Test Collection"
    assert "summary" in report
    assert report["summary"]["total_requests"] == 1
    assert report["summary"]["successful_requests"] == 1
    assert "results" in report
    assert len(report["results"]) == 1


@pytest.mark.anyio
async def test_json_report_empty(transport: ASGITransport) -> None:
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        resp = await client.post("/api/reports/generate/json", json=_empty_input())
    assert resp.status_code == 200
    report = resp.json()["report"]
    assert report["summary"]["total_requests"] == 0
    assert len(report["results"]) == 0


# ---- Markdown report -------------------------------------------------------


@pytest.mark.anyio
async def test_markdown_report_format(transport: ASGITransport) -> None:
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        resp = await client.post("/api/reports/generate/markdown", json=_sample_input())
    assert resp.status_code == 200
    md = resp.json()["markdown"]
    assert "# Theridion Report: Test Collection" in md
    assert "## Summary" in md
    assert "## Results" in md
    assert "| GET | Get Users |" in md
    assert "Generated by Theridion" in md


@pytest.mark.anyio
async def test_markdown_report_with_failures(transport: ASGITransport) -> None:
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        resp = await client.post("/api/reports/generate/markdown", json=_sample_input(mixed=True))
    assert resp.status_code == 200
    md = resp.json()["markdown"]
    assert "## Failed Assertions" in md
    assert "Delete Admin" in md
    assert "Expected status 200, got 403" in md


@pytest.mark.anyio
async def test_markdown_report_empty(transport: ASGITransport) -> None:
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        resp = await client.post("/api/reports/generate/markdown", json=_empty_input())
    assert resp.status_code == 200
    md = resp.json()["markdown"]
    assert "# Theridion Report: Empty" in md
    assert "Total Requests | 0" in md
