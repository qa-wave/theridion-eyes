"""Tests for release and product operations endpoints."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient


def test_feature_registry_and_readiness(client: TestClient) -> None:
    features = client.get("/api/product/features")
    assert features.status_code == 200
    payload = features.json()
    assert len(payload["features"]) == 20
    assert payload["totals"]["stable"] >= 1
    assert any(f["id"] == "release-readiness" for f in payload["features"])

    readiness = client.get("/api/product/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["summary"]["pass"] >= 1


def test_sample_workspace_and_collection_health(client: TestClient) -> None:
    sample = client.post("/api/product/sample-workspace")
    assert sample.status_code == 201
    created = sample.json()
    assert created["request_count"] == 4

    health = client.get(f"/api/product/collections/{created['collection_id']}/health")
    assert health.status_code == 200
    payload = health.json()
    assert payload["collection_name"] == "Theridion Sample Workspace"
    assert payload["assertion_coverage_pct"] == 100.0
    assert payload["variable_count"] == 2


def test_redaction_preview(client: TestClient) -> None:
    response = client.post(
        "/api/product/redaction/preview",
        json={"value": "Authorization: Bearer abc.def\npassword=secret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "[REDACTED]" in payload["redacted"]
    assert "secret" not in payload["redacted"]
    assert payload["replacements"] == 2


def test_ci_artifact_pack(client: TestClient) -> None:
    response = client.post(
        "/api/product/ci-artifact-pack",
        json={
            "report": {
                "collection_id": "c1",
                "collection_name": "CI token=collection-secret",
                "results": [
                    {
                        "request_id": "r1",
                        "request_name": "Health token=request-secret",
                        "method": "GET",
                        "url": "https://example.com/health",
                        "status": 200,
                        "elapsed_ms": 12,
                        "error": "Authorization: Bearer abc.def",
                    }
                ],
                "total_requests": 1,
                "successful_requests": 0,
                "failed_requests": 1,
                "total_assertions": 0,
                "passed_assertions": 0,
                "failed_assertions": 0,
                "total_elapsed_ms": 12,
            }
        },
    )
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert {"summary.json", "report.json", "report.md", "trace.html", "junit.xml"} <= set(
            zf.namelist()
        )
        for name in ("summary.json", "report.json", "report.md", "trace.html", "junit.xml"):
            text = zf.read(name).decode()
            assert "collection-secret" not in text
            assert "request-secret" not in text
            assert "abc.def" not in text
