"""Request console: in-memory log of recent requests/responses."""

from __future__ import annotations

from collections import deque

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/console", tags=["console"])

_MAX_ENTRIES = 200


class ConsoleEntry(BaseModel):
    timestamp: str = ""
    method: str = ""
    url: str = ""
    status: int = 0
    elapsed_ms: float = 0
    request_headers: dict[str, str] = {}
    response_headers: dict[str, str] = {}
    request_body: str | None = None
    response_body: str | None = None


class ConsoleLogInput(BaseModel):
    entries: list[ConsoleEntry]


class ConsoleLogOutput(BaseModel):
    stored: int = 0


class ConsoleEntriesOutput(BaseModel):
    entries: list[ConsoleEntry] = []
    total: int = 0


_store: deque[ConsoleEntry] = deque(maxlen=_MAX_ENTRIES)


@router.post("/log", response_model=ConsoleLogOutput)
async def log_entries(body: ConsoleLogInput) -> ConsoleLogOutput:
    for e in body.entries:
        _store.append(e)
    return ConsoleLogOutput(stored=len(body.entries))


@router.get("/entries", response_model=ConsoleEntriesOutput)
async def get_entries() -> ConsoleEntriesOutput:
    entries = list(_store)
    return ConsoleEntriesOutput(entries=entries, total=len(entries))
