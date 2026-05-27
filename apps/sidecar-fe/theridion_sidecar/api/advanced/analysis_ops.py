"""Dependency graph, variable inspector, and git-aware review endpoints."""

from __future__ import annotations

import json
import re
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ... import environments, storage
from ... import globals as global_store
from ...models import CollectionItem

router = APIRouter()

VAR_PATTERN = re.compile(r"\{\{\s*(\$?[A-Za-z_][A-Za-z0-9_-]*)\s*\}\}")


# ---- Variable resolution inspector ---------------------------------------


class VariableInspectInput(BaseModel):
    text: str
    environment_id: str | None = None
    collection_id: str | None = None
    runtime: dict[str, str] = Field(default_factory=dict)


class VariableResolution(BaseModel):
    name: str
    source: Literal["runtime", "environment", "collection", "global", "builtin", "unresolved"]
    value: str | None = None
    resolved: bool


class VariableInspectOutput(BaseModel):
    resolved_text: str
    variables: list[VariableResolution]


def _builtin_preview(name: str) -> str | None:
    if name == "$timestamp":
        return str(int(datetime.now(tz=UTC).timestamp() * 1000))
    if name == "$isoDate":
        return datetime.now(tz=UTC).isoformat()
    if name == "$uuid":
        return str(uuid.uuid4())
    if name == "$randomInt":
        return "0..1000000"
    return None


@router.post("/variables/inspect", response_model=VariableInspectOutput)
def inspect_variables(body: VariableInspectInput) -> VariableInspectOutput:
    env = environments.get(body.environment_id) if body.environment_id else None
    if body.environment_id and env is None:
        raise HTTPException(status_code=404, detail="environment not found")
    coll = storage.get(body.collection_id) if body.collection_id else None
    if body.collection_id and coll is None:
        raise HTTPException(status_code=404, detail="collection not found")

    globals_lookup = global_store.as_dict()
    collection_lookup = {
        v.name: v.value for v in (coll.variables if coll else []) if v.enabled
    }
    env_lookup = {v.name: v.value for v in (env.variables if env else []) if v.enabled}
    resolutions: list[VariableResolution] = []

    def resolve(name: str) -> str:
        if name in body.runtime:
            value = body.runtime[name]
            resolutions.append(
                VariableResolution(
                    name=name, source="runtime", value=value, resolved=True
                )
            )
            return value
        if name in env_lookup:
            value = env_lookup[name]
            resolutions.append(
                VariableResolution(
                    name=name, source="environment", value=value, resolved=True
                )
            )
            return value
        if name in collection_lookup:
            value = collection_lookup[name]
            resolutions.append(
                VariableResolution(
                    name=name, source="collection", value=value, resolved=True
                )
            )
            return value
        if name in globals_lookup:
            value = globals_lookup[name]
            resolutions.append(
                VariableResolution(
                    name=name, source="global", value=value, resolved=True
                )
            )
            return value
        builtin = _builtin_preview(name)
        if builtin is not None:
            resolutions.append(
                VariableResolution(
                    name=name, source="builtin", value=builtin, resolved=True
                )
            )
            return builtin
        resolutions.append(VariableResolution(name=name, source="unresolved", resolved=False))
        return f"{{{{{name}}}}}"

    resolved_text = VAR_PATTERN.sub(lambda match: resolve(match.group(1)), body.text)
    return VariableInspectOutput(resolved_text=resolved_text, variables=resolutions)


# ---- Dependency graph -----------------------------------------------------


def _flatten_requests(items: list[CollectionItem]) -> list[CollectionItem]:
    out: list[CollectionItem] = []
    for item in items:
        if item.is_folder:
            out.extend(_flatten_requests(item.items))
        else:
            out.append(item)
    return out


class DependencyNode(BaseModel):
    id: str
    name: str
    produces: list[str] = Field(default_factory=list)
    consumes: list[str] = Field(default_factory=list)


class DependencyEdge(BaseModel):
    from_id: str
    to_id: str
    variable: str


class DependencyGraphOutput(BaseModel):
    nodes: list[DependencyNode]
    edges: list[DependencyEdge]
    unresolved_variables: list[str] = Field(default_factory=list)


def _request_text_fields(req: CollectionItem) -> list[str]:
    parts = [req.url or "", req.body or ""]
    parts.extend(req.headers.values())
    if req.auth:
        parts.extend(
            [
                req.auth.token or "",
                req.auth.username or "",
                req.auth.password or "",
                req.auth.key or "",
                req.auth.value or "",
            ]
        )
    return parts


def _vars_in_request(req: CollectionItem) -> set[str]:
    found: set[str] = set()
    for text in _request_text_fields(req):
        found.update(match.group(1) for match in VAR_PATTERN.finditer(text))
    return found


@router.get("/collections/{collection_id}/dependency-graph", response_model=DependencyGraphOutput)
def dependency_graph(collection_id: str) -> DependencyGraphOutput:
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")
    requests = _flatten_requests(coll.items)
    producers: dict[str, str] = {}
    nodes: list[DependencyNode] = []
    for req in requests:
        produced = [capture.name for capture in req.captures]
        for name in produced:
            producers[name] = req.id
        nodes.append(
            DependencyNode(
                id=req.id,
                name=req.name,
                produces=produced,
                consumes=sorted(_vars_in_request(req)),
            )
        )
    edges: list[DependencyEdge] = []
    unresolved: set[str] = set()
    for node in nodes:
        for var in node.consumes:
            producer_id = producers.get(var)
            if producer_id and producer_id != node.id:
                edges.append(DependencyEdge(from_id=producer_id, to_id=node.id, variable=var))
            elif not var.startswith("$"):
                unresolved.add(var)
    return DependencyGraphOutput(nodes=nodes, edges=edges, unresolved_variables=sorted(unresolved))


# ---- Git-aware review mode ------------------------------------------------


class GitReviewInput(BaseModel):
    repo_path: str = "."


class GitReviewChange(BaseModel):
    file: str
    summary: str
    details: list[str] = Field(default_factory=list)


class GitReviewOutput(BaseModel):
    changes: list[GitReviewChange]


def _git(repo_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_path), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _load_json_maybe(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _requests_by_id(collection: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not collection:
        return out

    def walk(items: Any) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("is_folder"):
                walk(item.get("items"))
            elif isinstance(item.get("id"), str):
                out[str(item["id"])] = item

    walk(collection.get("items"))
    return out


@router.post("/git/review", response_model=GitReviewOutput)
def git_review(body: GitReviewInput) -> GitReviewOutput:
    repo = Path(body.repo_path).expanduser().resolve()
    if not (repo / ".git").exists():
        raise HTTPException(status_code=400, detail="repo_path is not a git repository")
    root_proc = _git(repo, ["rev-parse", "--show-toplevel"])
    if root_proc.returncode != 0:
        raise HTTPException(status_code=400, detail=root_proc.stderr.strip() or "git failed")
    root = Path(root_proc.stdout.strip())
    changed_proc = _git(root, ["diff", "--name-only"])
    if changed_proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=changed_proc.stderr.strip() or "git diff failed",
        )
    changes: list[GitReviewChange] = []
    for rel in [line for line in changed_proc.stdout.splitlines() if line.endswith(".json")]:
        path = root / rel
        if not path.exists():
            changes.append(GitReviewChange(file=rel, summary="Deleted JSON file"))
            continue
        current = _load_json_maybe(path.read_text(encoding="utf-8"))
        if not current or "items" not in current:
            continue
        head_proc = _git(root, ["show", f"HEAD:{rel}"])
        previous = _load_json_maybe(head_proc.stdout) if head_proc.returncode == 0 else None
        old_requests = _requests_by_id(previous)
        new_requests = _requests_by_id(current)
        details: list[str] = []
        for request_id in sorted(new_requests.keys() - old_requests.keys()):
            details.append(f"Added request: {new_requests[request_id].get('name', request_id)}")
        for request_id in sorted(old_requests.keys() - new_requests.keys()):
            details.append(f"Removed request: {old_requests[request_id].get('name', request_id)}")
        for request_id in sorted(new_requests.keys() & old_requests.keys()):
            old = old_requests[request_id]
            new = new_requests[request_id]
            for field in (
                "name",
                "method",
                "url",
                "headers",
                "body",
                "auth",
                "assertions",
                "captures",
            ):
                if old.get(field) != new.get(field):
                    details.append(
                        f"Changed {field} on {new.get('name') or old.get('name') or request_id}"
                    )
        if previous and previous.get("name") != current.get("name"):
            details.insert(
                0,
                f"Renamed collection: {previous.get('name')} -> {current.get('name')}",
            )
        summary = f"{len(details)} collection-level change{'s' if len(details) != 1 else ''}"
        changes.append(GitReviewChange(file=rel, summary=summary, details=details))
    return GitReviewOutput(changes=changes)
