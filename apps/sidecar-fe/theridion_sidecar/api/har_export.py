"""HAR 1.2 export from network console entries."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/export", tags=["export"])


class NetworkEntryData(BaseModel):
    method: str
    url: str
    status: int
    request_headers: dict[str, str]
    response_headers: dict[str, str]
    request_body: str | None = None
    response_body: str = ""
    elapsed_ms: float = 0
    timestamp: float = 0


class HarExportInput(BaseModel):
    entries: list[NetworkEntryData]


class HarExportOutput(BaseModel):
    har_json: str


def _headers_list(headers: dict[str, str]) -> list[dict[str, str]]:
    return [{"name": k, "value": v} for k, v in headers.items()]


def _to_har_entry(entry: NetworkEntryData) -> dict:
    started = datetime.fromtimestamp(
        entry.timestamp / 1000 if entry.timestamp > 1e12 else entry.timestamp,
        tz=timezone.utc,
    ).isoformat()

    req_body_size = len((entry.request_body or "").encode())
    resp_body_size = len(entry.response_body.encode())

    content_type = entry.response_headers.get(
        "content-type", entry.response_headers.get("Content-Type", "")
    )

    return {
        "startedDateTime": started,
        "time": entry.elapsed_ms,
        "request": {
            "method": entry.method,
            "url": entry.url,
            "httpVersion": "HTTP/1.1",
            "cookies": [],
            "headers": _headers_list(entry.request_headers),
            "queryString": [],
            "postData": {
                "mimeType": entry.request_headers.get(
                    "content-type",
                    entry.request_headers.get("Content-Type", "application/json"),
                ),
                "text": entry.request_body or "",
            }
            if entry.request_body
            else None,
            "headersSize": -1,
            "bodySize": req_body_size,
        },
        "response": {
            "status": entry.status,
            "statusText": "",
            "httpVersion": "HTTP/1.1",
            "cookies": [],
            "headers": _headers_list(entry.response_headers),
            "content": {
                "size": resp_body_size,
                "mimeType": content_type,
                "text": entry.response_body,
            },
            "redirectURL": "",
            "headersSize": -1,
            "bodySize": resp_body_size,
        },
        "cache": {},
        "timings": {
            "send": 0,
            "wait": entry.elapsed_ms,
            "receive": 0,
        },
    }


@router.post("/har", response_model=HarExportOutput)
async def export_har(body: HarExportInput) -> HarExportOutput:
    har = {
        "log": {
            "version": "1.2",
            "creator": {"name": "Theridion", "version": "0.0.1"},
            "entries": [_to_har_entry(e) for e in body.entries],
        }
    }
    return HarExportOutput(har_json=json.dumps(har, indent=2))
