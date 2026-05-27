"""Request dependency resolver — analyze {{var}} references and build execution order."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import storage

router = APIRouter(prefix="/api/test", tags=["dependency"])

VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


class DependencyInfo(BaseModel):
    request_id: str
    name: str
    depends_on: list[str] = Field(default_factory=list)
    provides: list[str] = Field(default_factory=list)
    consumes: list[str] = Field(default_factory=list)


class CycleInfo(BaseModel):
    variable: str
    involved: list[str] = Field(default_factory=list)


class DependencyResult(BaseModel):
    order: list[DependencyInfo] = Field(default_factory=list)
    cycles: list[CycleInfo] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class ResolveInput(BaseModel):
    collection_id: str


def _flatten_requests(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if item.get("is_folder"):
            out.extend(_flatten_requests(item.get("items", [])))
        else:
            out.append(item)
    return out


def _extract_vars(text: str) -> set[str]:
    return set(VAR_PATTERN.findall(text))


def _extract_all_vars(item: dict[str, Any]) -> set[str]:
    """Extract all {{var}} references from a request item."""
    vars_found: set[str] = set()
    for field in ("url", "body"):
        val = item.get(field, "")
        if isinstance(val, str):
            vars_found |= _extract_vars(val)
    headers = item.get("headers", {})
    if isinstance(headers, str):
        vars_found |= _extract_vars(headers)
    elif isinstance(headers, dict):
        for v in headers.values():
            if isinstance(v, str):
                vars_found |= _extract_vars(v)
    return vars_found


def _guess_provides(item: dict[str, Any]) -> set[str]:
    """Guess which variables a request could provide based on naming conventions."""
    name = item.get("name", "").lower()
    method = item.get("method", "GET").upper()
    provides: set[str] = set()

    # POST/PUT create requests often produce IDs
    if method in ("POST", "PUT"):
        # Extract meaningful words from the name
        words = re.findall(r"\w+", name)
        for word in words:
            if word not in ("create", "add", "new", "post", "put", "update", "api", "request"):
                provides.add(f"{word}_id")
                provides.add(f"{word}_token")

    return provides


def _topological_sort(
    nodes: dict[str, set[str]],
    provides_map: dict[str, set[str]],
) -> tuple[list[str], list[CycleInfo]]:
    """Topological sort with cycle detection."""
    # Build adjacency: for each node, find which other nodes provide its deps
    var_to_provider: dict[str, str] = {}
    for node_id, provides in provides_map.items():
        for var in provides:
            var_to_provider[var] = node_id

    graph: dict[str, set[str]] = defaultdict(set)
    for node_id, deps in nodes.items():
        for var in deps:
            provider = var_to_provider.get(var)
            if provider and provider != node_id:
                graph[node_id].add(provider)

    # Kahn's algorithm
    in_degree: dict[str, int] = defaultdict(int)
    all_nodes = set(nodes.keys())
    for node_id in all_nodes:
        if node_id not in in_degree:
            in_degree[node_id] = 0
        for dep in graph.get(node_id, set()):
            in_degree[node_id] += 1

    queue = [n for n in all_nodes if in_degree[n] == 0]
    order: list[str] = []
    while queue:
        queue.sort()
        node = queue.pop(0)
        order.append(node)
        # Find nodes that depend on this one
        for other in all_nodes:
            if node in graph.get(other, set()):
                in_degree[other] -= 1
                if in_degree[other] == 0:
                    queue.append(other)

    cycles: list[CycleInfo] = []
    if len(order) < len(all_nodes):
        remaining = all_nodes - set(order)
        cycles.append(CycleInfo(
            variable="circular",
            involved=sorted(remaining),
        ))
        # Add remaining in arbitrary order
        order.extend(sorted(remaining))

    return order, cycles


@router.post("/resolve-dependencies", response_model=DependencyResult)
def resolve_dependencies(body: ResolveInput) -> DependencyResult:
    coll = storage.get(body.collection_id)
    if coll is None:
        return DependencyResult()

    items = _flatten_requests([it.model_dump() for it in coll.items])

    # Phase 1: extract what each request consumes and could provide
    request_info: dict[str, dict[str, Any]] = {}
    all_consumed: dict[str, set[str]] = {}
    all_provided: dict[str, set[str]] = {}

    for item in items:
        req_id = item.get("id", "")
        if not req_id:
            continue
        consumed = _extract_all_vars(item)
        provided = _guess_provides(item)
        request_info[req_id] = item
        all_consumed[req_id] = consumed
        all_provided[req_id] = provided

    # Phase 2: topological sort
    order_ids, cycles = _topological_sort(all_consumed, all_provided)

    # Phase 3: build result
    all_vars_provided = set()
    for provides in all_provided.values():
        all_vars_provided |= provides

    unresolved_vars: set[str] = set()
    for consumed in all_consumed.values():
        for var in consumed:
            if var not in all_vars_provided:
                unresolved_vars.add(var)

    # Build var_to_provider map for depends_on
    var_to_provider: dict[str, str] = {}
    for req_id, provides in all_provided.items():
        for var in provides:
            var_to_provider[var] = req_id

    order: list[DependencyInfo] = []
    for req_id in order_ids:
        item = request_info.get(req_id, {})
        consumed = all_consumed.get(req_id, set())
        provided = all_provided.get(req_id, set())
        deps = []
        for var in consumed:
            provider = var_to_provider.get(var)
            if provider and provider != req_id and provider not in deps:
                deps.append(provider)

        order.append(DependencyInfo(
            request_id=req_id,
            name=item.get("name", ""),
            depends_on=deps,
            provides=sorted(provided),
            consumes=sorted(consumed),
        ))

    return DependencyResult(
        order=order,
        cycles=cycles,
        unresolved=sorted(unresolved_vars),
    )
