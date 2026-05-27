"""CLI reporters: generate reports in multiple formats."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/reports", tags=["cli-reporters"])


class ReportResult(BaseModel):
    name: str
    status: str
    elapsed_ms: float = 0
    error: str | None = None
    assertions: int = 0


class ReportInput(BaseModel):
    results: list[ReportResult]
    format: str = "html"  # "html" | "json" | "junit" | "markdown"


class ReportOutput(BaseModel):
    content: str
    content_type: str


@router.post("/generate", response_model=ReportOutput)
async def generate_report(body: ReportInput) -> ReportOutput:
    if body.format == "json":
        content = json.dumps([r.model_dump() for r in body.results], indent=2)
        return ReportOutput(content=content, content_type="application/json")

    elif body.format == "junit":
        testsuite = ET.Element("testsuite", name="Theridion", tests=str(len(body.results)))
        for r in body.results:
            tc = ET.SubElement(testsuite, "testcase", name=r.name, time=f"{r.elapsed_ms / 1000:.3f}")
            if r.status == "failed":
                ET.SubElement(tc, "failure", message=r.error or "")
        content = ET.tostring(testsuite, encoding="unicode", xml_declaration=True)
        return ReportOutput(content=content, content_type="application/xml")

    elif body.format == "markdown":
        lines = ["# Test Report\n", "| Name | Status | Time (ms) | Error |", "|---|---|---|---|"]
        for r in body.results:
            err = r.error or ""
            lines.append(f"| {r.name} | {r.status} | {r.elapsed_ms:.0f} | {err} |")
        passed = sum(1 for r in body.results if r.status == "passed")
        lines.append(f"\n**{passed}/{len(body.results)} passed**")
        return ReportOutput(content="\n".join(lines), content_type="text/markdown")

    else:  # html
        rows = ""
        for r in body.results:
            color = "#4ade80" if r.status == "passed" else "#f87171"
            rows += f"<tr><td>{r.name}</td><td style='color:{color}'>{r.status}</td><td>{r.elapsed_ms:.0f}ms</td></tr>"
        content = (
            "<html><body><h1>Test Report</h1>"
            f"<table border='1'><tr><th>Name</th><th>Status</th><th>Time</th></tr>{rows}</table>"
            "</body></html>"
        )
        return ReportOutput(content=content, content_type="text/html")
