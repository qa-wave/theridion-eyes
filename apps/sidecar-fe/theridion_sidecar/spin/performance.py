"""Spin performance smoke probes — lightweight RPS + percentile checks.

This is intentionally minimal: a 10–100 RPS / 30 s smoke check to validate
that an endpoint can handle load without error spikes. Surge remains the
primary load testing module for sustained load scenarios.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Any

import httpx


class PerfProbeResult:
    def __init__(
        self,
        target_rps: int,
        duration_seconds: int,
        total_requests: int,
        errors: int,
        latencies_ms: list[float],
    ) -> None:
        self.target_rps = target_rps
        self.duration_seconds = duration_seconds
        self.total_requests = total_requests
        self.errors = errors
        self.latencies_ms = sorted(latencies_ms)

    @property
    def actual_rps(self) -> float:
        return self.total_requests / max(self.duration_seconds, 1)

    @property
    def error_rate(self) -> float:
        return self.errors / max(self.total_requests, 1)

    @property
    def p50(self) -> float:
        return self._percentile(0.50)

    @property
    def p95(self) -> float:
        return self._percentile(0.95)

    @property
    def p99(self) -> float:
        return self._percentile(0.99)

    def _percentile(self, q: float) -> float:
        if not self.latencies_ms:
            return 0.0
        idx = int(len(self.latencies_ms) * q)
        idx = min(idx, len(self.latencies_ms) - 1)
        return self.latencies_ms[idx]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_rps": self.target_rps,
            "actual_rps": round(self.actual_rps, 2),
            "duration_seconds": self.duration_seconds,
            "total_requests": self.total_requests,
            "errors": self.errors,
            "error_rate_pct": round(self.error_rate * 100, 2),
            "latency_p50_ms": round(self.p50, 1),
            "latency_p95_ms": round(self.p95, 1),
            "latency_p99_ms": round(self.p99, 1),
            "latency_min_ms": round(min(self.latencies_ms, default=0.0), 1),
            "latency_max_ms": round(max(self.latencies_ms, default=0.0), 1),
        }


async def run_smoke_probe(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: Any = None,
    target_rps: int = 10,
    duration_seconds: int = 10,
    max_concurrency: int = 20,
    expected_status: int = 200,
    p95_threshold_ms: float | None = None,
    error_rate_threshold: float = 0.05,
) -> dict[str, Any]:
    """Run a lightweight performance smoke check.

    Clamps target_rps to [1, 100] and duration to [5, 30] seconds to avoid
    this module competing with Surge for serious load testing.
    """
    target_rps = max(1, min(100, target_rps))
    duration_seconds = max(5, min(30, duration_seconds))

    latencies: list[float] = []
    errors = 0
    total = 0
    semaphore = asyncio.Semaphore(max_concurrency)
    deadline = time.monotonic() + duration_seconds
    interval = 1.0 / target_rps

    async def _single_request() -> None:
        nonlocal errors, total
        t0 = time.monotonic()
        async with semaphore:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    kwargs: dict[str, Any] = {"headers": headers or {}}
                    if body is not None:
                        if isinstance(body, (dict, list)):
                            kwargs["json"] = body
                        else:
                            kwargs["content"] = str(body).encode()
                    resp = await client.request(method, url, **kwargs)
                    if resp.status_code != expected_status:
                        errors += 1
            except Exception:
                errors += 1
            finally:
                latency = (time.monotonic() - t0) * 1000
                latencies.append(latency)
                total += 1

    tasks: list[asyncio.Task[None]] = []
    while time.monotonic() < deadline:
        task = asyncio.create_task(_single_request())
        tasks.append(task)
        # Pace requests to approach target RPS
        await asyncio.sleep(interval)

    # Wait for all in-flight requests
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    result = PerfProbeResult(
        target_rps=target_rps,
        duration_seconds=duration_seconds,
        total_requests=total,
        errors=errors,
        latencies_ms=latencies,
    )
    data = result.to_dict()

    # Assertions
    checks: list[dict[str, Any]] = []
    all_passed = True

    error_ok = result.error_rate <= error_rate_threshold
    checks.append({
        "name": "error_rate",
        "passed": error_ok,
        "expected": f"<= {error_rate_threshold * 100}%",
        "actual": f"{data['error_rate_pct']}%",
    })
    if not error_ok:
        all_passed = False

    if p95_threshold_ms is not None:
        p95_ok = result.p95 <= p95_threshold_ms
        checks.append({
            "name": "p95_latency",
            "passed": p95_ok,
            "expected": f"<= {p95_threshold_ms} ms",
            "actual": f"{data['latency_p95_ms']} ms",
        })
        if not p95_ok:
            all_passed = False

    data["checks"] = checks
    data["passed"] = all_passed
    return data
