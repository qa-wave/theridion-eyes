"""MCP server: expose Theridion capabilities as MCP-compatible tools.

Provides a manifest of available tools with JSON schemas and a real
invoke endpoint that dispatches to the underlying sidecar logic.
"""

from __future__ import annotations

import json
import traceback
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .. import environments, storage
from ..assertions import Assertion, ResponseData, evaluate_all
from ..healing import heal

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class McpTool(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = {}


class McpManifest(BaseModel):
    name: str = "theridion"
    version: str = "0.1.0"
    tools: list[McpTool] = []


class McpInvokeInput(BaseModel):
    tool: str
    arguments: dict[str, Any] = {}


class McpInvokeOutput(BaseModel):
    result: dict[str, Any] = {}
    error: str | None = None


_TOOLS = [
    McpTool(
        name="execute_request",
        description=(
            "Execute an HTTP request and return the response. "
            "Supports GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
                    "default": "GET",
                },
                "url": {"type": "string", "description": "The request URL"},
                "headers": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "default": {},
                },
                "query": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "default": {},
                },
                "body": {"type": ["string", "null"], "default": None},
                "timeout_seconds": {"type": "number", "default": 30},
                "follow_redirects": {"type": "boolean", "default": True},
                "environment_id": {"type": ["string", "null"], "default": None},
                "collection_id": {"type": ["string", "null"], "default": None},
            },
            "required": ["url"],
        },
    ),
    McpTool(
        name="list_collections",
        description="List all saved API collections with their request counts",
        input_schema={"type": "object", "properties": {}},
    ),
    McpTool(
        name="get_collection",
        description="Get full details of a collection including all requests and folders",
        input_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Collection UUID"},
            },
            "required": ["id"],
        },
    ),
    McpTool(
        name="run_collection",
        description=(
            "Run all requests in a collection sequentially and return "
            "results with assertion outcomes"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "collection_id": {"type": "string", "description": "Collection UUID"},
                "environment_id": {
                    "type": ["string", "null"],
                    "description": "Optional environment UUID for variable substitution",
                    "default": None,
                },
            },
            "required": ["collection_id"],
        },
    ),
    McpTool(
        name="evaluate_assertions",
        description="Evaluate a list of assertions against response data",
        input_schema={
            "type": "object",
            "properties": {
                "assertions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "status", "response_time", "json_path",
                                    "header_exists", "header_equals",
                                    "body_contains", "body_regex",
                                ],
                            },
                            "expected": {"type": "string", "default": ""},
                            "path": {"type": "string", "default": ""},
                            "operator": {"type": "string", "default": "eq"},
                        },
                        "required": ["type"],
                    },
                },
                "response": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "integer"},
                        "headers": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                        },
                        "body": {"type": "string"},
                        "elapsed_ms": {"type": "number"},
                    },
                    "required": ["status"],
                },
            },
            "required": ["assertions", "response"],
        },
    ),
    McpTool(
        name="list_environments",
        description="List all saved environments with their variable counts",
        input_schema={"type": "object", "properties": {}},
    ),
    McpTool(
        name="create_request",
        description="Save a new request to an existing collection",
        input_schema={
            "type": "object",
            "properties": {
                "collection_id": {"type": "string", "description": "Collection UUID"},
                "name": {"type": "string", "description": "Human-readable request name"},
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
                },
                "url": {"type": "string", "description": "Full URL for the request"},
                "headers": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "default": {},
                },
                "body": {"type": ["string", "null"], "default": None},
            },
            "required": ["collection_id", "name", "method", "url"],
        },
    ),
    McpTool(
        name="inspect_api",
        description=(
            "Discover and inspect an API by checking for OpenAPI/Swagger "
            "specs and probing common endpoints"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "base_url": {
                    "type": "string",
                    "description": "Base URL of the API to inspect",
                },
            },
            "required": ["base_url"],
        },
    ),
    McpTool(
        name="generate_assertions",
        description=(
            "Suggest test assertions for an API response. Returns a list "
            "of assertion objects that can be added to a request."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "response_status": {"type": "integer", "description": "HTTP status code"},
                "response_body": {"type": "string", "description": "Response body text"},
                "response_headers": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "default": {},
                },
            },
            "required": ["response_status", "response_body"],
        },
    ),
    McpTool(
        name="heal_assertion",
        description=(
            "When an assertion fails, suggest a fix based on the actual "
            "response. Uses fuzzy matching to find renamed/moved fields."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "assertion_type": {"type": "string", "description": "Assertion type (e.g. json_path)"},
                "assertion_path": {"type": "string", "description": "The path that failed"},
                "assertion_expected": {"type": "string", "description": "Expected value"},
                "response_body": {"type": "string", "description": "Actual response body"},
            },
            "required": ["assertion_type", "assertion_path", "assertion_expected", "response_body"],
        },
    ),
    McpTool(
        name="compare_responses",
        description=(
            "Compare two API response bodies and return the differences. "
            "Useful for regression testing."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "response_a": {"type": "string", "description": "First response body (JSON)"},
                "response_b": {"type": "string", "description": "Second response body (JSON)"},
            },
            "required": ["response_a", "response_b"],
        },
    ),
]


@router.get("/manifest", response_model=McpManifest)
async def get_manifest() -> McpManifest:
    return McpManifest(tools=_TOOLS)


@router.post("/invoke", response_model=McpInvokeOutput)
async def invoke_tool(body: McpInvokeInput) -> McpInvokeOutput:
    tool_names = {t.name for t in _TOOLS}
    if body.tool not in tool_names:
        return McpInvokeOutput(error=f"Unknown tool: {body.tool}")

    try:
        result = await _dispatch(body.tool, body.arguments)
        return McpInvokeOutput(result=result)
    except Exception as exc:
        return McpInvokeOutput(error=f"{type(exc).__name__}: {exc}")


async def _dispatch(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Route tool invocations to actual sidecar logic."""

    if tool == "execute_request":
        return await _execute_request(args)
    elif tool == "list_collections":
        return _list_collections()
    elif tool == "get_collection":
        return _get_collection(args)
    elif tool == "run_collection":
        return await _run_collection(args)
    elif tool == "evaluate_assertions":
        return _evaluate_assertions(args)
    elif tool == "list_environments":
        return _list_environments()
    elif tool == "create_request":
        return _create_request(args)
    elif tool == "inspect_api":
        return await _inspect_api(args)
    elif tool == "generate_assertions":
        return _generate_assertions(args)
    elif tool == "heal_assertion":
        return _heal_assertion(args)
    elif tool == "compare_responses":
        return _compare_responses(args)
    else:
        raise ValueError(f"No dispatch handler for tool: {tool}")


async def _execute_request(args: dict[str, Any]) -> dict[str, Any]:
    from .requests import ExecuteRequest, execute

    req = ExecuteRequest(
        method=args.get("method", "GET"),
        url=args["url"],
        headers=args.get("headers", {}),
        query=args.get("query", {}),
        body=args.get("body"),
        timeout_seconds=args.get("timeout_seconds", 30),
        follow_redirects=args.get("follow_redirects", True),
        environment_id=args.get("environment_id"),
        collection_id=args.get("collection_id"),
    )
    resp = await execute(req)
    return resp.model_dump(mode="json")


def _list_collections() -> dict[str, Any]:
    summaries = storage.list_summaries()
    return {"collections": [s.model_dump(mode="json") for s in summaries]}


def _get_collection(args: dict[str, Any]) -> dict[str, Any]:
    coll_id = args["id"]
    coll = storage.get(coll_id)
    if coll is None:
        raise ValueError(f"Collection {coll_id} not found")
    return coll.model_dump(mode="json")


async def _run_collection(args: dict[str, Any]) -> dict[str, Any]:
    from .runner import RunInput, run_collection

    result = await run_collection(
        collection_id=args["collection_id"],
        body=RunInput(environment_id=args.get("environment_id")),
    )
    return result.model_dump(mode="json")


def _evaluate_assertions(args: dict[str, Any]) -> dict[str, Any]:
    assertions = [Assertion(**a) for a in args["assertions"]]
    resp_data = args["response"]
    response = ResponseData(
        status=resp_data["status"],
        headers=resp_data.get("headers", {}),
        body=resp_data.get("body", ""),
        elapsed_ms=resp_data.get("elapsed_ms", 0),
    )
    results = evaluate_all(assertions, response)
    passed = sum(1 for r in results if r.passed)
    return {
        "results": [r.model_dump(mode="json") for r in results],
        "passed": passed,
        "failed": len(results) - passed,
        "total": len(results),
    }


def _list_environments() -> dict[str, Any]:
    summaries = environments.list_summaries()
    return {"environments": [s.model_dump(mode="json") for s in summaries]}


def _create_request(args: dict[str, Any]) -> dict[str, Any]:
    import uuid as _uuid

    from ..models import CollectionItem

    coll = storage.get(args["collection_id"])
    if coll is None:
        raise ValueError(f"Collection {args['collection_id']} not found")
    item = CollectionItem(
        id=str(_uuid.uuid4()),
        name=args["name"],
        method=args["method"],
        url=args["url"],
        headers=args.get("headers", {}),
        body=args.get("body"),
    )
    updated = storage.add_request(args["collection_id"], item)
    return {"id": item.id, "name": item.name, "collection": updated.name}


async def _inspect_api(args: dict[str, Any]) -> dict[str, Any]:
    from ..mcp_server_v2 import inspect_api as _inspect

    return await _inspect(args["base_url"])


def _generate_assertions(args: dict[str, Any]) -> dict[str, Any]:
    from ..mcp_server_v2 import generate_assertions as _gen

    result = _gen(
        response_status=args["response_status"],
        response_body=args["response_body"],
        response_headers=args.get("response_headers"),
    )
    return {"assertions": result}


def _heal_assertion(args: dict[str, Any]) -> dict[str, Any]:
    assertion = Assertion(
        type=args["assertion_type"],
        path=args["assertion_path"],
        expected=args["assertion_expected"],
        operator="eq",
    )
    output = heal(assertion, args["response_body"])
    return {
        "candidates": [
            {"path": c.suggested_path, "confidence": c.confidence, "reason": c.reason}
            for c in output.candidates
        ],
        "auto_fixable": output.auto_fixable,
    }


def _compare_responses(args: dict[str, Any]) -> dict[str, Any]:
    from ..mcp_server_v2 import compare_responses as _compare

    return _compare(args["response_a"], args["response_b"])
