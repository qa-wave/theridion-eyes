"""YAML collections: convert collections to/from YAML format."""

from __future__ import annotations

import json

import yaml
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/format", tags=["yaml-collections"])


class ToYamlInput(BaseModel):
    collection: dict


class ToYamlOutput(BaseModel):
    content: str


class FromYamlInput(BaseModel):
    content: str


class FromYamlOutput(BaseModel):
    collection: dict


@router.post("/to-yaml", response_model=ToYamlOutput)
async def to_yaml(body: ToYamlInput) -> ToYamlOutput:
    content = yaml.dump(body.collection, default_flow_style=False, allow_unicode=True)
    return ToYamlOutput(content=content)


@router.post("/from-yaml", response_model=FromYamlOutput)
async def from_yaml(body: FromYamlInput) -> FromYamlOutput:
    data = yaml.safe_load(body.content)
    if not isinstance(data, dict):
        data = {"name": "Imported", "items": []}
    return FromYamlOutput(collection=data)
