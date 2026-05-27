"""Tests for Spin contract testing — Pact V2 verification and recording."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import httpx
import pytest
import respx

from theridion_sidecar.spin.contract import (
    ContractRecorder,
    _compare_bodies,
    _compare_headers,
    verify_contract,
    verify_interaction,
)
from theridion_sidecar.spin.models import (
    PactContract,
    PactInteraction,
    PactInteractionRequest,
    PactInteractionResponse,
)


# ── Body comparison ───────────────────────────────────────────────────────────

def test_compare_bodies_exact_match():
    assert _compare_bodies({"id": 1}, {"id": 1, "extra": "ok"}) is True


def test_compare_bodies_missing_key():
    assert _compare_bodies({"id": 1, "name": "x"}, {"id": 1}) is False


def test_compare_bodies_nested():
    expected = {"order": {"status": "pending"}}
    actual = {"order": {"status": "pending", "id": 99}}
    assert _compare_bodies(expected, actual) is True


def test_compare_bodies_none_expected():
    assert _compare_bodies(None, {"anything": "goes"}) is True


def test_compare_bodies_list_subset():
    assert _compare_bodies([{"id": 1}], [{"id": 1, "x": "y"}, {"id": 2}]) is True


def test_compare_bodies_list_too_short():
    assert _compare_bodies([{"id": 1}, {"id": 2}], [{"id": 1}]) is False


# ── Header comparison ─────────────────────────────────────────────────────────

def test_compare_headers_pass():
    assert _compare_headers(
        {"Content-Type": "application/json"},
        {"content-type": "application/json; charset=utf-8"},
    ) is True


def test_compare_headers_missing():
    assert _compare_headers(
        {"X-Custom": "value"},
        {"content-type": "application/json"},
    ) is False


def test_compare_headers_empty_expected():
    assert _compare_headers({}, {"content-type": "application/json"}) is True


# ── Interaction verification ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_interaction_pass():
    interaction = PactInteraction(
        description="Get users",
        request=PactInteractionRequest(method="GET", path="/users"),
        response=PactInteractionResponse(
            status=200,
            body={"users": []},
        ),
    )

    with respx.mock:
        respx.get("http://provider.local/users").mock(
            return_value=httpx.Response(200, json={"users": [], "total": 0})
        )
        result = await verify_interaction(interaction, "http://provider.local")

    assert result["passed"] is True
    assert result["failures"] == []


@pytest.mark.asyncio
async def test_verify_interaction_wrong_status():
    interaction = PactInteraction(
        description="Create order",
        request=PactInteractionRequest(method="POST", path="/orders"),
        response=PactInteractionResponse(status=201),
    )

    with respx.mock:
        respx.post("http://provider.local/orders").mock(
            return_value=httpx.Response(400, json={"error": "bad request"})
        )
        result = await verify_interaction(interaction, "http://provider.local")

    assert result["passed"] is False
    assert any("Status mismatch" in f for f in result["failures"])


@pytest.mark.asyncio
async def test_verify_interaction_body_mismatch():
    interaction = PactInteraction(
        description="Get user",
        request=PactInteractionRequest(method="GET", path="/users/1"),
        response=PactInteractionResponse(
            status=200,
            body={"name": "Alice"},
        ),
    )

    with respx.mock:
        respx.get("http://provider.local/users/1").mock(
            return_value=httpx.Response(200, json={"name": "Bob"})
        )
        result = await verify_interaction(interaction, "http://provider.local")

    assert result["passed"] is False


# ── Contract file verification ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_contract_file_not_found():
    result = await verify_contract("/nonexistent/contract.json", "http://provider.local")
    assert result.status == "error"
    assert "not found" in (result.error or "")


@pytest.mark.asyncio
async def test_verify_contract_all_pass(tmp_path: Path):
    contract = PactContract(
        consumer={"name": "Consumer"},
        provider={"name": "Provider"},
        interactions=[
            PactInteraction(
                description="Get health",
                request=PactInteractionRequest(method="GET", path="/health"),
                response=PactInteractionResponse(status=200, body={"ok": True}),
            )
        ],
    )
    contract_file = tmp_path / "test.contract.json"
    contract_file.write_text(contract.model_dump_json(), encoding="utf-8")

    with respx.mock:
        respx.get("http://provider.local/health").mock(
            return_value=httpx.Response(200, json={"ok": True, "version": "1.0"})
        )
        result = await verify_contract(str(contract_file), "http://provider.local")

    assert result.status == "passed"
    assert result.total_interactions == 1
    assert result.passed == 1
    assert result.failed == 0


@pytest.mark.asyncio
async def test_verify_contract_partial_fail(tmp_path: Path):
    contract = PactContract(
        consumer={"name": "Consumer"},
        provider={"name": "Provider"},
        interactions=[
            PactInteraction(
                description="Pass",
                request=PactInteractionRequest(method="GET", path="/ok"),
                response=PactInteractionResponse(status=200),
            ),
            PactInteraction(
                description="Fail",
                request=PactInteractionRequest(method="GET", path="/fail"),
                response=PactInteractionResponse(status=200),
            ),
        ],
    )
    contract_file = tmp_path / "partial.contract.json"
    contract_file.write_text(contract.model_dump_json(), encoding="utf-8")

    with respx.mock:
        respx.get("http://provider.local/ok").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.get("http://provider.local/fail").mock(
            return_value=httpx.Response(404, json={})
        )
        result = await verify_contract(str(contract_file), "http://provider.local")

    assert result.status == "failed"
    assert result.failed == 1
    assert result.passed == 1


# ── Contract recording ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recorder_records_interaction(tmp_path: Path):
    recorder = ContractRecorder(
        consumer="TestConsumer",
        provider="TestProvider",
        base_url="http://provider.local",
    )

    with respx.mock:
        respx.get("http://provider.local/users").mock(
            return_value=httpx.Response(200, json={"users": [{"id": 1}]})
        )
        interaction = await recorder.record(
            method="GET",
            path="/users",
            description="List users",
        )

    assert interaction.request.method == "GET"
    assert interaction.response.status == 200
    assert len(recorder.interactions) == 1


@pytest.mark.asyncio
async def test_recorder_saves_pact_file(tmp_path: Path):
    recorder = ContractRecorder(
        consumer="MyConsumer",
        provider="MyProvider",
        base_url="http://provider.local",
    )

    with respx.mock:
        respx.post("http://provider.local/orders").mock(
            return_value=httpx.Response(201, json={"id": "ORD-001"})
        )
        await recorder.record(
            method="POST",
            path="/orders",
            request_body={"item": "widget"},
            description="Create order",
            provider_state="order service is up",
        )

    out_path = tmp_path / "my_contract.json"
    saved = recorder.save(out_path)
    assert saved.exists()

    data = json.loads(saved.read_text(encoding="utf-8"))
    assert data["consumer"]["name"] == "MyConsumer"
    assert data["provider"]["name"] == "MyProvider"
    assert len(data["interactions"]) == 1
    assert data["interactions"][0]["description"] == "Create order"
    assert "pactSpecification" in data.get("metadata", {})


@pytest.mark.asyncio
async def test_recorder_clear():
    recorder = ContractRecorder("A", "B", "http://x.local")

    with respx.mock:
        respx.get("http://x.local/ping").mock(return_value=httpx.Response(200))
        await recorder.record("GET", "/ping")

    assert len(recorder.interactions) == 1
    recorder.clear()
    assert len(recorder.interactions) == 0
