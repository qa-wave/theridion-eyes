"""Self-healing assertion endpoint.

Given a failed assertion and the response data, suggests candidate
fixes so the user can update their assertion to match the actual API
response structure.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..assertions import Assertion
from ..healing import HealCandidate, HealOutput, heal

router = APIRouter(prefix="/api/assertions", tags=["assertions"])


class HealInput(BaseModel):
    assertion: Assertion
    response_body: str
    response_headers: dict[str, str] = {}
    response_status: int = 200


@router.post("/heal", response_model=HealOutput)
def heal_endpoint(body: HealInput) -> HealOutput:
    return heal(
        assertion=body.assertion,
        response_body=body.response_body,
        response_headers=body.response_headers,
        response_status=body.response_status,
    )
