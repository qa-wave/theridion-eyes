"""AMF protocol: stub endpoint for Adobe Message Format."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/amf", tags=["amf"])


class AmfStubOutput(BaseModel):
    status: str = "not_available"
    message: str = "AMF protocol support is not yet implemented"


@router.post("/invoke", response_model=AmfStubOutput)
async def amf_invoke() -> AmfStubOutput:
    return AmfStubOutput()
