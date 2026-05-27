"""Visual dependency graph — analyze {{var}} references and captures to build a directed graph."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import storage

router = APIRouter(prefix="/api/graph", tags=["graph"])

VAR_PATTERN = re.compile(r"\{\{(\$?\w+)\}\}")

# Built-in template functions that are NOT user variables
BUILTIN_VARS = {"$timestamp", "$uuid", "$isoDate", "$randomInt"}


class GraphNode(BaseModel):
    id: str
    name: str
    method: str = "GET"
    url: str = ""
    produces: list[str] = Field(default_factory=list)
    consumes: list[str] = Field(default_factory=list)
    folder: str | None = None


class GraphEdge(BaseModel):
    from_id: str
    to_id: str
    variable: str


class GraphGroup(BaseModel):
    name: str
    node_ids: list[str] = Field(default_factory=list)


class GraphResult(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    groups: list[GraphGroup] = Field(default_factory=list)
    execution_order: list[str] = Field(default_factory=list)
    has_cycle: bool = False
    cycle_members: list[str] = Field(default_factory=list)


class CollectionGraphInput(BaseModel):
    collection_id: str


def _extract_vars(text: str) -> set[str]:
    """Extract all {{var}} references, excluding builtins."""
    return {v for v in VAR_PATTERN.findall(text) if v not in BUILTIN_VARS}


def _extract_all_consumed(item: dict[str, Any]) -> set[str]:
    """Extract all {{var}} references from a request item fields."""
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


def _extract_produces(item: dict[str, Any]) -> set[str]:
    """Get variables produced by captures defined on this request."""
    captures = item.get("captures", [])
    produced: set[str] = set()
    for cap in captures:
        name = cap.get("name", "") if isinstance(cap, dict) else ""
        if name:
            produced.add(name)
    return produced


def _flatten_with_folder(
    items: list[dict[str, Any]], folder_name: str | None = None,
) -> list[tuple[dict[str, Any], str | None]]:
    """Flatten items tree, returning (item, folder_name) tuples."""
    out: list[tuple[dict[str, Any], str | None]] = []
    for item in items:
        if item.get("is_folder"):
            fname = item.get("name", "Folder")
            out.extend(_flatten_with_folder(item.get("items", []), fname))
        else:
            out.append((item, folder_name))
    return out


def _topological_sort(
    node_ids: list[str],
    edges: list[GraphEdge],
) -> tuple[list[str], bool, list[str]]:
    """Kahn's algorithm. Returns (order, has_cycle, cycle_members)."""
    graph: dict[str, set[str]] = defaultdict(set)
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}

    for edge in edges:
        if edge.to_id in in_degree and edge.from_id in in_degree:
            graph[edge.from_id].add(edge.to_id)
            in_degree[edge.to_id] = in_degree.get(edge.to_id, 0) + 1

    queue = sorted([n for n in node_ids if in_degree[n] == 0])
    order: list[str] = []

    while queue:
        node = queue.pop(0)
        order.append(node)
        for neighbor in sorted(graph.get(node, set())):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    has_cycle = len(order) < len(node_ids)
    cycle_members = sorted(set(node_ids) - set(order)) if has_cycle else []

    # Append cycle members at end so we still have a full list
    if has_cycle:
        order.extend(cycle_members)

    return order, has_cycle, cycle_members


@router.post("/collection", response_model=GraphResult)
def build_collection_graph(body: CollectionGraphInput) -> GraphResult:
    """Build a dependency graph for all requests in a collection."""
    try:
        coll = storage.get(body.collection_id)
    except (ValueError, OSError):
        return GraphResult()
    if coll is None:
        return GraphResult()

    items_with_folder = _flatten_with_folder(
        [it.model_dump() for it in coll.items]
    )

    # Build nodes
    nodes: list[GraphNode] = []
    node_ids: list[str] = []
    produces_map: dict[str, set[str]] = {}
    consumes_map: dict[str, set[str]] = {}
    folder_map: dict[str, str | None] = {}

    for item, folder in items_with_folder:
        req_id = item.get("id", "")
        if not req_id:
            continue
        produced = _extract_produces(item)
        consumed = _extract_all_consumed(item)
        produces_map[req_id] = produced
        consumes_map[req_id] = consumed
        folder_map[req_id] = folder
        node_ids.append(req_id)
        nodes.append(GraphNode(
            id=req_id,
            name=item.get("name", ""),
            method=item.get("method", "GET") or "GET",
            url=item.get("url", "") or "",
            produces=sorted(produced),
            consumes=sorted(consumed),
            folder=folder,
        ))

    # Build edges: variable_name -> producer_id
    var_to_producer: dict[str, str] = {}
    for req_id, produced in produces_map.items():
        for var in produced:
            var_to_producer[var] = req_id

    edges: list[GraphEdge] = []
    for req_id, consumed in consumes_map.items():
        for var in consumed:
            producer = var_to_producer.get(var)
            if producer and producer != req_id:
                edges.append(GraphEdge(
                    from_id=producer,
                    to_id=req_id,
                    variable=var,
                ))

    # Build groups from folders
    groups_dict: dict[str, list[str]] = defaultdict(list)
    for req_id, folder in folder_map.items():
        if folder:
            groups_dict[folder].append(req_id)
    groups = [
        GraphGroup(name=name, node_ids=ids)
        for name, ids in sorted(groups_dict.items())
    ]

    # Topological sort
    execution_order, has_cycle, cycle_members = _topological_sort(node_ids, edges)

    return GraphResult(
        nodes=nodes,
        edges=edges,
        groups=groups,
        execution_order=execution_order,
        has_cycle=has_cycle,
        cycle_members=cycle_members,
    )
