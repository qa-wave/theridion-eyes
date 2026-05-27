"""Visualizer: render data into HTML templates."""

from __future__ import annotations

import json

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/visualize", tags=["visualizer"])


class VisualizeInput(BaseModel):
    template: str
    data: dict | list | str | None = None


class VisualizeOutput(BaseModel):
    html: str


@router.post("/render", response_model=VisualizeOutput)
async def render(body: VisualizeInput) -> VisualizeOutput:
    data_json = json.dumps(body.data) if body.data is not None else "null"
    html = body.template.replace("{{data}}", data_json)
    html = html.replace("{{DATA}}", data_json)
    return VisualizeOutput(html=html)
