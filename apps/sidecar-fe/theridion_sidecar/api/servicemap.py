"""Service dependency map — auto-discover services from collections,
manage nodes/edges, persist graph layout.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import storage
from ..storage import home_dir

router = APIRouter(prefix="/api/servicemap", tags=["servicemap"])


class ServiceNode(BaseModel):
    id: str
    label: str
    url: str = ""
    x: float = 0
    y: float = 0
    color: str = ""


class ServiceEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str = ""
    request_id: str | None = None
    collection_id: str | None = None


class ServiceGraph(BaseModel):
    nodes: list[ServiceNode] = Field(default_factory=list)
    edges: list[ServiceEdge] = Field(default_factory=list)


def _path() -> Path:
    return home_dir() / "servicemap.json"


def _load() -> ServiceGraph:
    p = _path()
    if not p.exists():
        return ServiceGraph()
    try:
        return ServiceGraph(**json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return ServiceGraph()


def _save(graph: ServiceGraph) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = graph.model_dump(mode="json")
    fd, tmp = tempfile.mkstemp(prefix="smap.", suffix=".json.tmp", dir=str(p.parent))
    tmp_p = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_p, p)
    except Exception:
        try:
            tmp_p.unlink(missing_ok=True)
        except OSError:
            pass
        raise


@router.get("", response_model=ServiceGraph)
def get_graph() -> ServiceGraph:
    return _load()


@router.put("", response_model=ServiceGraph)
def save_graph(body: ServiceGraph) -> ServiceGraph:
    _save(body)
    return body


@router.post("/discover", response_model=ServiceGraph)
def discover_services() -> ServiceGraph:
    """Auto-discover services by scanning all collections for unique base URLs."""
    existing = _load()
    existing_urls = {n.url for n in existing.nodes}

    summaries = storage.list_summaries()
    host_map: dict[str, set[str]] = {}  # host → set of collection_ids

    for s in summaries:
        coll = storage.get(s.id)
        if not coll:
            continue
        for item in _flatten(coll.items):
            if not item.url:
                continue
            try:
                parsed = urlparse(item.url)
                host = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else None
            except Exception:
                host = None
            if host and host not in existing_urls:
                host_map.setdefault(host, set()).add(s.id)

    # Create nodes for new hosts
    colors = ["#06b6d4", "#8b5cf6", "#f59e0b", "#10b981", "#ef4444", "#ec4899", "#6366f1", "#14b8a6"]
    offset = len(existing.nodes)
    for i, (host, coll_ids) in enumerate(sorted(host_map.items())):
        node = ServiceNode(
            id=str(uuid.uuid4()),
            label=urlparse(host).netloc or host,
            url=host,
            x=150 + (i % 4) * 200,
            y=100 + (i // 4) * 150,
            color=colors[(offset + i) % len(colors)],
        )
        existing.nodes.append(node)
        existing_urls.add(host)

    # Auto-create edges between services that share collection
    node_by_url: dict[str, str] = {n.url: n.id for n in existing.nodes}

    _save(existing)
    return existing


class AddNodeInput(BaseModel):
    label: str
    url: str = ""
    x: float = 200
    y: float = 200
    color: str = "#06b6d4"


@router.post("/nodes", response_model=ServiceGraph)
def add_node(body: AddNodeInput) -> ServiceGraph:
    g = _load()
    g.nodes.append(ServiceNode(id=str(uuid.uuid4()), **body.model_dump()))
    _save(g)
    return g


@router.delete("/nodes/{node_id}", response_model=ServiceGraph)
def delete_node(node_id: str) -> ServiceGraph:
    g = _load()
    g.nodes = [n for n in g.nodes if n.id != node_id]
    g.edges = [e for e in g.edges if e.source != node_id and e.target != node_id]
    _save(g)
    return g


class AddEdgeInput(BaseModel):
    source: str
    target: str
    label: str = ""


@router.post("/edges", response_model=ServiceGraph)
def add_edge(body: AddEdgeInput) -> ServiceGraph:
    g = _load()
    g.edges.append(ServiceEdge(id=str(uuid.uuid4()), **body.model_dump()))
    _save(g)
    return g


@router.delete("/edges/{edge_id}", response_model=ServiceGraph)
def delete_edge(edge_id: str) -> ServiceGraph:
    g = _load()
    g.edges = [e for e in g.edges if e.id != edge_id]
    _save(g)
    return g


def _flatten(items: list[Any]) -> list[Any]:
    out = []
    for it in items:
        if it.is_folder:
            out.extend(_flatten(it.items))
        else:
            out.append(it)
    return out
