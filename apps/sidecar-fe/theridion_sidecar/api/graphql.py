"""GraphQL execution and introspection endpoint."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import environments

router = APIRouter(prefix="/api/graphql", tags=["graphql"])

INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      name
      kind
      description
      fields(includeDeprecated: true) {
        name
        description
        args { name type { name kind ofType { name kind } } }
        type { name kind ofType { name kind ofType { name kind } } }
        isDeprecated
        deprecationReason
      }
      inputFields {
        name
        type { name kind ofType { name kind } }
      }
      enumValues(includeDeprecated: true) {
        name
        description
        isDeprecated
      }
    }
  }
}
"""


class GraphQLExecuteInput(BaseModel):
    url: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    variables: dict[str, Any] = Field(default_factory=dict)
    operation_name: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    environment_id: str | None = None


class GraphQLResponse(BaseModel):
    data: Any = None
    errors: list[dict[str, Any]] | None = None
    status: int = 200
    elapsed_ms: float = 0
    raw_body: str = ""


class IntrospectInput(BaseModel):
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    environment_id: str | None = None


class GraphQLType(BaseModel):
    name: str
    kind: str
    description: str | None = None
    fields: list[dict[str, Any]] = Field(default_factory=list)


class IntrospectOutput(BaseModel):
    types: list[GraphQLType] = Field(default_factory=list)
    query_type: str | None = None
    mutation_type: str | None = None
    subscription_type: str | None = None


@router.post("/execute", response_model=GraphQLResponse)
async def execute(body: GraphQLExecuteInput) -> GraphQLResponse:
    env = environments.get(body.environment_id) if body.environment_id else None
    if body.environment_id and env is None:
        raise HTTPException(status_code=404, detail="environment not found")

    resolved_url = environments.substitute(body.url, env)
    resolved_headers = environments.substitute_dict(body.headers, env)
    resolved_query = environments.substitute(body.query, env)

    # Substitute variables values.
    resolved_vars = {}
    for k, v in body.variables.items():
        if isinstance(v, str):
            resolved_vars[k] = environments.substitute(v, env)
        else:
            resolved_vars[k] = v

    payload: dict[str, Any] = {"query": resolved_query}
    if resolved_vars:
        payload["variables"] = resolved_vars
    if body.operation_name:
        payload["operationName"] = body.operation_name

    resolved_headers.setdefault("Content-Type", "application/json")

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(http2=True, timeout=30) as client:
            response = await client.post(
                resolved_url,
                headers=resolved_headers,
                content=json.dumps(payload).encode("utf-8"),
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"transport error: {exc}") from exc

    elapsed_ms = (time.perf_counter() - started) * 1000

    try:
        result = response.json()
    except Exception:
        return GraphQLResponse(
            status=response.status_code,
            elapsed_ms=round(elapsed_ms, 2),
            raw_body=response.text,
            errors=[{"message": "Response is not valid JSON"}],
        )

    return GraphQLResponse(
        data=result.get("data"),
        errors=result.get("errors"),
        status=response.status_code,
        elapsed_ms=round(elapsed_ms, 2),
        raw_body=response.text,
    )


@router.post("/introspect", response_model=IntrospectOutput)
async def introspect(body: IntrospectInput) -> IntrospectOutput:
    env = environments.get(body.environment_id) if body.environment_id else None
    if body.environment_id and env is None:
        raise HTTPException(status_code=404, detail="environment not found")

    resolved_url = environments.substitute(body.url, env)
    resolved_headers = environments.substitute_dict(body.headers, env)
    resolved_headers.setdefault("Content-Type", "application/json")

    try:
        async with httpx.AsyncClient(http2=True, timeout=30) as client:
            response = await client.post(
                resolved_url,
                headers=resolved_headers,
                content=json.dumps({"query": INTROSPECTION_QUERY}).encode("utf-8"),
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"transport error: {exc}") from exc

    try:
        result = response.json()
    except Exception:
        raise HTTPException(status_code=502, detail="introspection response is not JSON")

    schema = result.get("data", {}).get("__schema", {})
    types_raw = schema.get("types", [])
    # Filter out built-in types (starting with __)
    user_types = [
        GraphQLType(
            name=t["name"],
            kind=t["kind"],
            description=t.get("description"),
            fields=t.get("fields") or [],
        )
        for t in types_raw
        if not t["name"].startswith("__")
    ]

    return IntrospectOutput(
        types=user_types,
        query_type=schema.get("queryType", {}).get("name") if schema.get("queryType") else None,
        mutation_type=schema.get("mutationType", {}).get("name") if schema.get("mutationType") else None,
        subscription_type=schema.get("subscriptionType", {}).get("name") if schema.get("subscriptionType") else None,
    )
