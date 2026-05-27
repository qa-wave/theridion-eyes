"""Spin contract testing — Pact V2 format provider verification and recording."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from .models import (
    ContractVerifyResult,
    PactContract,
    PactInteraction,
    PactInteractionRequest,
    PactInteractionResponse,
)


# ── Provider verification ────────────────────────────────────────────────────

def _compare_bodies(expected: Any, actual: Any) -> bool:
    """Compare bodies with relaxed matching: expected keys must be present in actual."""
    if expected is None:
        return True
    if isinstance(expected, dict) and isinstance(actual, dict):
        for k, v in expected.items():
            if k not in actual:
                return False
            if not _compare_bodies(v, actual[k]):
                return False
        return True
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) == 0:
            return True
        if len(actual) < len(expected):
            return False
        for exp_item, act_item in zip(expected, actual):
            if not _compare_bodies(exp_item, act_item):
                return False
        return True
    return str(expected) == str(actual)


def _compare_headers(expected: dict[str, str], actual: dict[str, str]) -> bool:
    """Check that all expected headers are present with matching values (case-insensitive keys)."""
    actual_lower = {k.lower(): v for k, v in actual.items()}
    for name, value in expected.items():
        actual_val = actual_lower.get(name.lower())
        if actual_val is None:
            return False
        # Allow content-type with charset suffix: "application/json" matches "application/json; charset=utf-8"
        if value.lower() not in actual_val.lower():
            return False
    return True


async def verify_interaction(
    interaction: PactInteraction,
    provider_url: str,
    provider_state_handler_url: str | None = None,
) -> dict[str, Any]:
    """Replay a single Pact interaction against the real provider and check the response."""
    req = interaction.request
    expected_resp = interaction.response

    # Trigger provider state if handler URL provided
    if provider_state_handler_url and interaction.provider_state:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    provider_state_handler_url,
                    json={"state": interaction.provider_state},
                )
        except Exception:
            pass  # Best-effort

    # Build URL
    url = provider_url.rstrip("/") + req.path
    if req.query:
        url = f"{url}?{req.query}"

    t0 = time.monotonic()
    result: dict[str, Any] = {
        "description": interaction.description,
        "provider_state": interaction.provider_state,
        "passed": False,
        "failures": [],
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            kwargs: dict[str, Any] = {"headers": req.headers}
            if req.body is not None:
                if isinstance(req.body, (dict, list)):
                    kwargs["json"] = req.body
                else:
                    kwargs["content"] = str(req.body).encode()
            resp = await client.request(req.method, url, **kwargs)

        result["duration_ms"] = (time.monotonic() - t0) * 1000
        result["actual_status"] = resp.status_code

        try:
            actual_body = resp.json()
        except Exception:
            actual_body = resp.text
        actual_headers = dict(resp.headers)

        failures: list[str] = []

        # Status check
        if resp.status_code != expected_resp.status:
            failures.append(
                f"Status mismatch: expected {expected_resp.status}, got {resp.status_code}"
            )

        # Headers check
        if expected_resp.headers and not _compare_headers(expected_resp.headers, actual_headers):
            failures.append(f"Header mismatch: expected {expected_resp.headers}")

        # Body check
        if expected_resp.body is not None and not _compare_bodies(expected_resp.body, actual_body):
            failures.append(f"Body mismatch: expected {expected_resp.body!r}, got {actual_body!r}")

        result["passed"] = len(failures) == 0
        result["failures"] = failures

    except Exception as exc:
        result["error"] = str(exc)
        result["failures"] = [str(exc)]

    return result


async def verify_contract(
    contract_path: str | Path,
    provider_url: str,
    provider_state_handler_url: str | None = None,
) -> ContractVerifyResult:
    """Verify all interactions in a Pact contract file against the real provider."""
    p = Path(contract_path)
    if not p.exists():
        return ContractVerifyResult(
            contract_file=str(contract_path),
            provider_url=provider_url,
            total_interactions=0,
            passed=0,
            failed=0,
            results=[],
            status="error",
            error=f"Contract file not found: {contract_path}",
        )

    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        contract = PactContract.model_validate(data)
    except Exception as exc:
        return ContractVerifyResult(
            contract_file=str(contract_path),
            provider_url=provider_url,
            total_interactions=0,
            passed=0,
            failed=0,
            results=[],
            status="error",
            error=f"Failed to parse contract: {exc}",
        )

    results: list[dict[str, Any]] = []
    for interaction in contract.interactions:
        r = await verify_interaction(
            interaction,
            provider_url,
            provider_state_handler_url=provider_state_handler_url,
        )
        results.append(r)

    passed = sum(1 for r in results if r.get("passed"))
    failed = len(results) - passed

    return ContractVerifyResult(
        contract_file=str(contract_path),
        provider_url=provider_url,
        total_interactions=len(results),
        passed=passed,
        failed=failed,
        results=results,
        status="passed" if failed == 0 else "failed",
    )


# ── Consumer recording ───────────────────────────────────────────────────────

class ContractRecorder:
    """Captures HTTP interactions for writing to a Pact V2 .contract.json file.

    Usage:
        recorder = ContractRecorder(consumer="MyApp", provider="OrderService")
        await recorder.record(method="POST", path="/orders", ...)
        recorder.save("/path/to/output.contract.json")
    """

    def __init__(
        self,
        consumer: str,
        provider: str,
        base_url: str,
    ) -> None:
        self.consumer = consumer
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self._interactions: list[PactInteraction] = []

    async def record(
        self,
        method: str,
        path: str,
        request_headers: dict[str, str] | None = None,
        request_body: Any = None,
        query: str | None = None,
        provider_state: str | None = None,
        description: str | None = None,
    ) -> PactInteraction:
        """Execute the real HTTP request and capture both request and response."""
        url = self.base_url + path
        if query:
            url = f"{url}?{query}"

        async with httpx.AsyncClient(timeout=30) as client:
            kwargs: dict[str, Any] = {"headers": request_headers or {}}
            if request_body is not None:
                if isinstance(request_body, (dict, list)):
                    kwargs["json"] = request_body
                else:
                    kwargs["content"] = str(request_body).encode()
            resp = await client.request(method, url, **kwargs)

        try:
            resp_body = resp.json()
        except Exception:
            resp_body = resp.text

        # Keep only the most relevant response headers
        resp_headers = {
            k: v
            for k, v in resp.headers.items()
            if k.lower() in {"content-type", "content-length", "location"}
        }

        interaction = PactInteraction(
            description=description or f"{method} {path}",
            provider_state=provider_state,
            request=PactInteractionRequest(
                method=method,
                path=path,
                query=query,
                headers=request_headers or {},
                body=request_body,
            ),
            response=PactInteractionResponse(
                status=resp.status_code,
                headers=resp_headers,
                body=resp_body,
            ),
        )
        self._interactions.append(interaction)
        return interaction

    def save(self, output_path: str | Path) -> Path:
        """Write recorded interactions to a Pact V2 JSON file."""
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        contract = PactContract(
            consumer={"name": self.consumer},
            provider={"name": self.provider},
            interactions=self._interactions,
            metadata={
                "pactSpecification": {"version": "2.0.0"},
                "pactSpecificationVersion": "2.0.0",
                "theridion": {"recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")},
            },
        )
        tmp = p.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(contract.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(p)
        return p

    @property
    def interactions(self) -> list[PactInteraction]:
        return list(self._interactions)

    def clear(self) -> None:
        self._interactions.clear()
