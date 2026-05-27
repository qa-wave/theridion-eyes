"""Flow graph visualization — topological sort with cycle detection."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/flows", tags=["flows"])


class FlowNode(BaseModel):
    name: str
    depends_on: list[str] = Field(default_factory=list)


class FlowGraphRequest(BaseModel):
    nodes: list[FlowNode] = Field(..., min_length=1)


class VisualNode(BaseModel):
    name: str
    level: int
    dependencies: list[str]


class FlowGraphResult(BaseModel):
    nodes: list[VisualNode]
    order: list[str]
    has_cycle: bool


def _topo_sort(nodes: list[FlowNode]) -> tuple[list[str], bool, dict[str, int]]:
    """Kahn's algorithm. Returns (order, has_cycle, levels)."""
    graph: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {}
    all_names = {n.name for n in nodes}

    for n in nodes:
        in_degree.setdefault(n.name, 0)
        for dep in n.depends_on:
            if dep in all_names:
                graph[dep].append(n.name)
                in_degree[n.name] = in_degree.get(n.name, 0) + 1

    queue = [n for n in all_names if in_degree.get(n, 0) == 0]
    queue.sort()
    order: list[str] = []
    levels: dict[str, int] = {}
    for n in queue:
        levels[n] = 0

    while queue:
        node = queue.pop(0)
        order.append(node)
        for neighbor in sorted(graph[node]):
            in_degree[neighbor] -= 1
            levels[neighbor] = max(levels.get(neighbor, 0), levels[node] + 1)
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    has_cycle = len(order) < len(all_names)
    return order, has_cycle, levels


@router.post("/visualize", response_model=FlowGraphResult)
async def flow_visualize(req: FlowGraphRequest) -> FlowGraphResult:
    order, has_cycle, levels = _topo_sort(req.nodes)

    visual_nodes = [
        VisualNode(
            name=n.name,
            level=levels.get(n.name, 0),
            dependencies=n.depends_on,
        )
        for n in req.nodes
    ]

    return FlowGraphResult(nodes=visual_nodes, order=order, has_cycle=has_cycle)
