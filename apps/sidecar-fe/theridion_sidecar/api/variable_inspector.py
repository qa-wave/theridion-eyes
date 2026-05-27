"""Variable Inspector — resolve {{var}} references with source tracking.

Endpoint:
- POST /api/variables/resolve — show each variable's resolved value and
  which scope it came from (global, collection, environment, builtin,
  or unresolved).
"""

from __future__ import annotations

import re

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import environments, storage
from .. import globals as global_store
from ..environments import _VAR_PATTERN, _builtin

router = APIRouter(prefix="/api/variables", tags=["variables"])


class ResolvedVariable(BaseModel):
    name: str
    value: str
    source: str  # "global" | "collection" | "environment" | "builtin" | "unresolved"
    overridden_by: str | None = None


class ResolveInput(BaseModel):
    text: str
    environment_id: str | None = None
    collection_id: str | None = None


class ResolveOutput(BaseModel):
    variables: list[ResolvedVariable] = Field(default_factory=list)
    resolved_text: str = ""


@router.post("/resolve", response_model=ResolveOutput)
async def resolve_variables(body: ResolveInput) -> ResolveOutput:
    # Build lookup tables per scope, in resolution order (later wins).
    global_vars = global_store.as_dict()

    coll_vars: dict[str, str] = {}
    if body.collection_id:
        coll = storage.get(body.collection_id)
        if coll and coll.variables:
            coll_vars = {v.name: v.value for v in coll.variables if v.enabled}

    env_vars: dict[str, str] = {}
    env = None
    if body.environment_id:
        env = environments.get(body.environment_id)
        if env:
            env_vars = {v.name: v.value for v in env.variables if v.enabled}

    # Find all {{var}} tokens in text.
    seen: set[str] = set()
    resolved_vars: list[ResolvedVariable] = []

    for m in _VAR_PATTERN.finditer(body.text):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)

        # Check builtin first (they override everything).
        if name.startswith("$"):
            builtin_val = _builtin(name)
            if builtin_val is not None:
                # Determine if any scope also defines this name.
                overridden = None
                if name in env_vars:
                    overridden = "environment"
                elif name in coll_vars:
                    overridden = "collection"
                elif name in global_vars:
                    overridden = "global"
                resolved_vars.append(ResolvedVariable(
                    name=name, value=builtin_val, source="builtin",
                    overridden_by=overridden,
                ))
                continue

        # Resolution order: global < collection < environment.
        # The *last* scope to define the variable is the effective source;
        # lower-priority scopes that also define it are reported as overridden.
        value: str | None = None
        source: str = "unresolved"
        overridden_by: str | None = None

        if name in global_vars:
            value = global_vars[name]
            source = "global"

        if name in coll_vars:
            if value is not None:
                overridden_by = source  # global is overridden
            value = coll_vars[name]
            source = "collection"

        if name in env_vars:
            if value is not None:
                overridden_by = source  # global or collection is overridden
            value = env_vars[name]
            source = "environment"

        resolved_vars.append(ResolvedVariable(
            name=name,
            value=value if value is not None else f"{{{{{name}}}}}",
            source=source,
            overridden_by=overridden_by if source != "unresolved" else None,
        ))

    # Also produce the fully-resolved text.
    resolved_text = environments.substitute(
        body.text, env, collection_vars=coll_vars,
    )

    return ResolveOutput(variables=resolved_vars, resolved_text=resolved_text)
