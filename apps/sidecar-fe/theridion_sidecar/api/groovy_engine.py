"""Groovy engine: stub endpoint for JVM-based Groovy scripting."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/scripts", tags=["groovy"])


class GroovyStubOutput(BaseModel):
    status: str = "not_available"
    message: str = "Groovy requires JVM"


@router.post("/groovy", response_model=GroovyStubOutput)
async def groovy_execute() -> GroovyStubOutput:
    return GroovyStubOutput()
