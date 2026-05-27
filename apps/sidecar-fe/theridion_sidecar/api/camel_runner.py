"""Camel runtime detection and test runner API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..camel.runner import CamelRunReport, run_camel_test
from ..camel.runtime import RuntimeStatus, detect_runtime

router = APIRouter(prefix="/api/camel", tags=["camel"])


@router.get("/runtime", response_model=RuntimeStatus)
def get_runtime() -> RuntimeStatus:
    """Return Java and Maven availability status on the host system."""
    return detect_runtime()


class RunInput(BaseModel):
    files: dict[str, str]  # relative_path -> file content (from generator)
    use_mvnw: bool = True  # default: use mvnw wrapper if present in files


@router.post("/run", response_model=CamelRunReport)
async def run(body: RunInput) -> CamelRunReport:
    """Execute Maven tests from generated project files.

    Writes files to a persistent work directory, runs mvn/mvnw test,
    parses surefire XML reports and returns structured results.
    """
    if not body.files:
        raise HTTPException(status_code=400, detail="no files provided")
    return await run_camel_test(body.files, use_mvnw=body.use_mvnw)
