"""JUnit reporter: generate JUnit XML from test results."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/reports", tags=["junit-reporter"])


class TestResultInput(BaseModel):
    name: str
    status: str  # "passed" | "failed" | "error"
    elapsed_ms: float = 0
    error: str | None = None
    assertions: int = 0


class JunitInput(BaseModel):
    results: list[TestResultInput]


class JunitOutput(BaseModel):
    xml: str


@router.post("/junit", response_model=JunitOutput)
async def generate_junit(body: JunitInput) -> JunitOutput:
    testsuite = ET.Element("testsuite")
    testsuite.set("name", "Theridion")
    testsuite.set("tests", str(len(body.results)))

    failures = sum(1 for r in body.results if r.status == "failed")
    errors = sum(1 for r in body.results if r.status == "error")
    testsuite.set("failures", str(failures))
    testsuite.set("errors", str(errors))
    total_time = sum(r.elapsed_ms for r in body.results) / 1000
    testsuite.set("time", f"{total_time:.3f}")

    for r in body.results:
        tc = ET.SubElement(testsuite, "testcase")
        tc.set("name", r.name)
        tc.set("time", f"{r.elapsed_ms / 1000:.3f}")
        if r.status == "failed":
            failure = ET.SubElement(tc, "failure")
            failure.set("message", r.error or "Test failed")
            failure.text = r.error or ""
        elif r.status == "error":
            error = ET.SubElement(tc, "error")
            error.set("message", r.error or "Test error")
            error.text = r.error or ""

    xml_str = ET.tostring(testsuite, encoding="unicode", xml_declaration=True)
    return JunitOutput(xml=xml_str)
