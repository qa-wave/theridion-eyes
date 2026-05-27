"""Bru format: convert collections to/from .bru plain-text format."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/format", tags=["bru-format"])


class ToBruInput(BaseModel):
    collection: dict


class ToBruOutput(BaseModel):
    content: str


class FromBruInput(BaseModel):
    content: str


class FromBruOutput(BaseModel):
    collection: dict


def _item_to_bru(item: dict) -> str:
    if item.get("is_folder"):
        lines = [f"folder {item.get('name', 'Untitled')} {{"]
        for child in item.get("items", []):
            lines.append("  " + _item_to_bru(child).replace("\n", "\n  "))
        lines.append("}")
        return "\n".join(lines)

    lines = [f"meta {{", f"  name: {item.get('name', '')}", f"}}"]
    method = item.get("method", "GET")
    url = item.get("url", "")
    lines.append(f"\n{method.lower()} {{")
    lines.append(f"  url: {url}")
    lines.append("}")
    if item.get("headers"):
        lines.append("\nheaders {")
        for k, v in item["headers"].items():
            lines.append(f"  {k}: {v}")
        lines.append("}")
    if item.get("body"):
        lines.append(f"\nbody:json {{\n  {item['body']}\n}}")
    return "\n".join(lines)


@router.post("/to-bru", response_model=ToBruOutput)
async def to_bru(body: ToBruInput) -> ToBruOutput:
    items = body.collection.get("items", [])
    parts = [_item_to_bru(item) for item in items]
    return ToBruOutput(content="\n\n---\n\n".join(parts))


@router.post("/from-bru", response_model=FromBruOutput)
async def from_bru(body: FromBruInput) -> FromBruOutput:
    # Basic parsing of .bru format
    items: list[dict] = []
    sections = body.content.split("---")

    for section in sections:
        section = section.strip()
        if not section:
            continue
        item: dict = {"is_folder": False}
        name_match = re.search(r"name:\s*(.+)", section)
        if name_match:
            item["name"] = name_match.group(1).strip()
        url_match = re.search(r"url:\s*(.+)", section)
        if url_match:
            item["url"] = url_match.group(1).strip()
        for method in ("get", "post", "put", "delete", "patch"):
            if re.search(rf"^{method}\s*\{{", section, re.MULTILINE):
                item["method"] = method.upper()
                break
        if "method" not in item:
            item["method"] = "GET"
        items.append(item)

    return FromBruOutput(collection={"name": "Imported", "items": items})
