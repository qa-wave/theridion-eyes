"""WSDL mock generator: generate mock responses for WSDL operations."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/soap", tags=["wsdl-mock-gen"])


class MockOperation(BaseModel):
    name: str
    mock_response_xml: str


class WsdlMockGenInput(BaseModel):
    wsdl_url: str


class WsdlMockGenOutput(BaseModel):
    operations: list[MockOperation] = []
    error: str | None = None


@router.post("/generate-mock", response_model=WsdlMockGenOutput)
async def generate_mock(body: WsdlMockGenInput) -> WsdlMockGenOutput:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(body.wsdl_url)
        root = ET.fromstring(resp.text)

        ops: list[MockOperation] = []
        seen: set[str] = set()
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "operation":
                name = elem.get("name")
                if name and name not in seen:
                    seen.add(name)
                    mock_xml = (
                        '<?xml version="1.0" encoding="UTF-8"?>'
                        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
                        "<soap:Body>"
                        f"<{name}Response>"
                        f"<result>mock-value</{name}Response>"
                        f"</{name}Response>"
                        "</soap:Body></soap:Envelope>"
                    )
                    ops.append(MockOperation(name=name, mock_response_xml=mock_xml))

        return WsdlMockGenOutput(operations=ops)
    except Exception as exc:
        return WsdlMockGenOutput(error=str(exc))
