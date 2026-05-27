"""SSE (Server-Sent Events) client endpoint.

Connects to a remote SSE stream, collects events for up to 30 seconds
or 100 events, and returns the collected data. Useful for testing
SSE endpoints without keeping a persistent browser connection.
"""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["sse"])


class SSEConnectInput(BaseModel):
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    environment_id: str | None = None
    max_events: int = 100
    timeout_seconds: float = 30.0


class SSEEvent(BaseModel):
    id: str | None = None
    event: str = "message"
    data: str = ""
    timestamp: float = 0.0


class SSEResult(BaseModel):
    url: str
    events: list[SSEEvent]
    total_events: int
    connection_time_ms: float
    error: str | None = None


def _parse_sse_lines(raw: str) -> list[SSEEvent]:
    """Parse SSE text format into structured events."""
    events: list[SSEEvent] = []
    current_id: str | None = None
    current_event = "message"
    current_data_lines: list[str] = []

    for line in raw.split("\n"):
        if line.startswith("id:"):
            current_id = line[3:].strip()
        elif line.startswith("event:"):
            current_event = line[6:].strip()
        elif line.startswith("data:"):
            current_data_lines.append(line[5:].strip())
        elif line.strip() == "" and current_data_lines:
            events.append(
                SSEEvent(
                    id=current_id,
                    event=current_event,
                    data="\n".join(current_data_lines),
                    timestamp=time.time(),
                )
            )
            current_id = None
            current_event = "message"
            current_data_lines = []

    # Flush any remaining data that wasn't terminated by a blank line.
    if current_data_lines:
        events.append(
            SSEEvent(
                id=current_id,
                event=current_event,
                data="\n".join(current_data_lines),
                timestamp=time.time(),
            )
        )

    return events


@router.post("/api/sse/connect")
async def sse_connect(body: SSEConnectInput) -> SSEResult:
    """Connect to an SSE endpoint and collect events."""
    t0 = time.perf_counter()
    collected: list[SSEEvent] = []
    error: str | None = None

    try:
        async with httpx.AsyncClient(timeout=body.timeout_seconds) as client:
            async with client.stream(
                "GET",
                body.url,
                headers={
                    "Accept": "text/event-stream",
                    **body.headers,
                },
            ) as response:
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    # Parse complete events from the buffer.
                    while "\n\n" in buffer:
                        block, buffer = buffer.split("\n\n", 1)
                        events = _parse_sse_lines(block + "\n")
                        collected.extend(events)
                        if len(collected) >= body.max_events:
                            break
                    if len(collected) >= body.max_events:
                        break
                    elapsed = time.perf_counter() - t0
                    if elapsed >= body.timeout_seconds:
                        break

                # Parse any remaining data in the buffer.
                if buffer.strip() and len(collected) < body.max_events:
                    events = _parse_sse_lines(buffer)
                    collected.extend(events)

    except httpx.TimeoutException:
        error = "Connection timed out"
    except httpx.ConnectError as e:
        error = f"Connection failed: {e}"
    except Exception as e:
        error = str(e)

    connection_time_ms = (time.perf_counter() - t0) * 1000

    return SSEResult(
        url=body.url,
        events=collected[: body.max_events],
        total_events=len(collected),
        connection_time_ms=round(connection_time_ms, 2),
        error=error,
    )
