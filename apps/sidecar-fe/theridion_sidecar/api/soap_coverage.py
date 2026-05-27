"""SOAP coverage: check which WSDL operations are covered by a collection."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from theridion_sidecar import storage

router = APIRouter(prefix="/api/soap", tags=["soap-coverage"])


class SoapCoverageInput(BaseModel):
    wsdl_url: str
    collection_id: str


class SoapCoverageOutput(BaseModel):
    total_operations: int = 0
    covered: list[str] = []
    uncovered: list[str] = []
    coverage_pct: float = 0.0


def _extract_operations(xml_text: str) -> list[str]:
    ops: list[str] = []
    try:
        root = ET.fromstring(xml_text)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "operation":
                name = elem.get("name")
                if name and name not in ops:
                    ops.append(name)
    except ET.ParseError:
        pass
    return ops


def _collect_request_names(items: list[dict]) -> set[str]:
    names: set[str] = set()
    for item in items:
        if item.get("is_folder") and item.get("items"):
            names.update(_collect_request_names(item["items"]))
        else:
            name = item.get("name", "")
            names.add(name.lower())
            url = item.get("url", "")
            names.add(url.lower())
    return names


@router.post("/coverage", response_model=SoapCoverageOutput)
async def soap_coverage(body: SoapCoverageInput) -> SoapCoverageOutput:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(body.wsdl_url)
    operations = _extract_operations(resp.text)

    col = storage.load_collection(body.collection_id)
    if col is None:
        return SoapCoverageOutput(total_operations=len(operations), uncovered=operations)

    req_names = _collect_request_names([i.model_dump() for i in col.items])

    covered = [op for op in operations if op.lower() in req_names]
    uncovered = [op for op in operations if op.lower() not in req_names]
    total = len(operations)
    pct = (len(covered) / total * 100) if total > 0 else 0.0

    return SoapCoverageOutput(
        total_operations=total,
        covered=covered,
        uncovered=uncovered,
        coverage_pct=round(pct, 1),
    )
