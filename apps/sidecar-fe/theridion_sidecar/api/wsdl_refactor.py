"""WSDL diff: compare two WSDL documents for breaking changes."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/soap", tags=["wsdl-diff"])


class WsdlDiffInput(BaseModel):
    old_wsdl_url: str
    new_wsdl_url: str


class WsdlDiffOutput(BaseModel):
    added_operations: list[str] = []
    removed_operations: list[str] = []
    changed_types: list[str] = []
    breaking: bool = False


def _extract_operations(xml_text: str) -> set[str]:
    ops: set[str] = set()
    try:
        root = ET.fromstring(xml_text)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "operation":
                name = elem.get("name")
                if name:
                    ops.add(name)
    except ET.ParseError:
        pass
    return ops


def _extract_types(xml_text: str) -> set[str]:
    types: set[str] = set()
    try:
        root = ET.fromstring(xml_text)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag in ("element", "complexType", "simpleType"):
                name = elem.get("name")
                if name:
                    types.add(name)
    except ET.ParseError:
        pass
    return types


@router.post("/wsdl-diff", response_model=WsdlDiffOutput)
async def wsdl_diff(body: WsdlDiffInput) -> WsdlDiffOutput:
    async with httpx.AsyncClient(timeout=30) as client:
        old_resp = await client.get(body.old_wsdl_url)
        new_resp = await client.get(body.new_wsdl_url)

    old_ops = _extract_operations(old_resp.text)
    new_ops = _extract_operations(new_resp.text)

    old_types = _extract_types(old_resp.text)
    new_types = _extract_types(new_resp.text)

    added = sorted(new_ops - old_ops)
    removed = sorted(old_ops - new_ops)
    changed = sorted((old_types - new_types) | (new_types - old_types))

    return WsdlDiffOutput(
        added_operations=added,
        removed_operations=removed,
        changed_types=changed,
        breaking=len(removed) > 0 or len(changed) > 0,
    )
