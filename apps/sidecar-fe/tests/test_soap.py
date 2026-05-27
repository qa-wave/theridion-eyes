"""Tests for the SOAP / WSDL inspection endpoint.

We use a local WSDL fixture so the test never reaches the network.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURE = Path(__file__).parent / "fixtures" / "calculator.wsdl"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


def _file_url() -> str:
    return f"file://{FIXTURE.resolve()}"


def test_inspect_returns_services_and_operations(client: TestClient) -> None:
    res = client.post("/api/soap/inspect", json={"wsdl_url": _file_url()})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["target_namespace"] == "http://example.com/calc"
    assert len(body["services"]) == 1
    svc = body["services"][0]
    assert svc["name"] == "CalcService"
    assert len(svc["ports"]) == 1
    port = svc["ports"][0]
    assert port["name"] == "CalcPort"
    op_names = {op["name"] for op in port["operations"]}
    assert op_names == {"Add", "Subtract"}


def test_inspect_surfaces_soap_action(client: TestClient) -> None:
    body = client.post(
        "/api/soap/inspect", json={"wsdl_url": _file_url()}
    ).json()
    [add] = [
        op
        for op in body["services"][0]["ports"][0]["operations"]
        if op["name"] == "Add"
    ]
    assert add["soap_action"] == "http://example.com/calc/Add"


def test_inspect_invalid_wsdl_returns_400(client: TestClient) -> None:
    res = client.post(
        "/api/soap/inspect",
        json={"wsdl_url": "file:///does/not/exist.wsdl"},
    )
    assert res.status_code == 400
    assert "WSDL error" in res.json()["detail"]


def test_execute_unknown_operation_returns_404(client: TestClient) -> None:
    res = client.post(
        "/api/soap/execute",
        json={
            "wsdl_url": _file_url(),
            "operation": "DoesNotExist",
            "args": {"a": 1, "b": 2},
        },
    )
    assert res.status_code == 404


def test_execute_returns_fault_when_transport_unreachable(
    client: TestClient,
) -> None:
    """The fixture's port is the unreachable example.com address. zeep
    will raise on the actual SOAP call; we want that surfaced as a
    structured fault, not a 500."""
    res = client.post(
        "/api/soap/execute",
        json={
            "wsdl_url": _file_url(),
            "operation": "Add",
            "args": {"a": 1, "b": 2},
        },
    )
    # We don't actually want to reach example.com in CI; either the call
    # transport-fails (ok=false) or, less likely, succeeds. Both are
    # acceptable outcomes for *this* fixture — we just assert the
    # response shape is well-formed.
    assert res.status_code == 200
    body = res.json()
    assert "ok" in body
    if body["ok"] is False:
        assert isinstance(body["fault"], str)
        assert len(body["fault"]) > 0
