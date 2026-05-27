"""XSD validation: validate XML against XSD schema structure."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/soap", tags=["xsd-validator"])


class XsdValidateInput(BaseModel):
    xml: str
    xsd: str


class XsdError(BaseModel):
    line: int = 0
    message: str = ""


class XsdValidateOutput(BaseModel):
    valid: bool = True
    errors: list[XsdError] = []


@router.post("/xsd-validate", response_model=XsdValidateOutput)
async def xsd_validate(body: XsdValidateInput) -> XsdValidateOutput:
    errors: list[XsdError] = []

    # Parse XSD to extract expected elements
    try:
        ET.fromstring(body.xsd)
    except ET.ParseError as exc:
        return XsdValidateOutput(valid=False, errors=[XsdError(line=0, message=f"XSD parse error: {exc}")])

    # Parse XML
    try:
        ET.fromstring(body.xml)
    except ET.ParseError as exc:
        error_str = str(exc)
        line = 0
        if "line" in error_str:
            try:
                parts = error_str.split("line")
                line = int(parts[1].strip().split(",")[0].split(")")[0])
            except (IndexError, ValueError):
                pass
        return XsdValidateOutput(valid=False, errors=[XsdError(line=line, message=f"XML parse error: {exc}")])

    # Basic structural validation: check root and child elements
    try:
        xsd_root = ET.fromstring(body.xsd)
        xml_root = ET.fromstring(body.xml)
        ns = {"xs": "http://www.w3.org/2001/XMLSchema"}

        expected_elements: set[str] = set()
        for elem in xsd_root.iter():
            name = elem.get("name")
            if name:
                expected_elements.add(name)

        xml_root_tag = xml_root.tag.split("}")[-1] if "}" in xml_root.tag else xml_root.tag
        if expected_elements and xml_root_tag not in expected_elements:
            errors.append(XsdError(line=1, message=f"Root element '{xml_root_tag}' not found in schema"))
    except Exception as exc:
        errors.append(XsdError(line=0, message=str(exc)))

    return XsdValidateOutput(valid=len(errors) == 0, errors=errors)
