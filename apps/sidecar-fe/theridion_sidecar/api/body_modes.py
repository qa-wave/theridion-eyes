"""Body modes: encode form fields."""

from __future__ import annotations

import urllib.parse

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/requests", tags=["body-modes"])


class FormField(BaseModel):
    key: str
    value: str
    type: str = "text"  # "text" | "file"


class EncodeFormInput(BaseModel):
    fields: list[FormField]


class EncodeFormOutput(BaseModel):
    encoded_body: str
    content_type: str


@router.post("/encode-form", response_model=EncodeFormOutput)
async def encode_form(body: EncodeFormInput) -> EncodeFormOutput:
    pairs = [(f.key, f.value) for f in body.fields if f.type == "text"]
    encoded = urllib.parse.urlencode(pairs)
    return EncodeFormOutput(
        encoded_body=encoded,
        content_type="application/x-www-form-urlencoded",
    )
