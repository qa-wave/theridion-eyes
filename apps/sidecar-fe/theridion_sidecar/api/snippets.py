"""Request Snippets Library — curated reusable request templates.

File-based storage in ~/.theridion/snippets/ (one JSON per snippet).
Includes built-in read-only snippets loaded from code.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..storage import home_dir

router = APIRouter(prefix="/api/snippets", tags=["snippets"])


class Snippet(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    category: str = "General"
    description: str = ""
    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    auth: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    builtin: bool = False


class SnippetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: str = "General"
    description: str = ""
    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    auth: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)


class SnippetUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    description: str | None = None
    method: str | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    body: str | None = None
    auth: dict[str, Any] | None = None
    tags: list[str] | None = None


class SnippetList(BaseModel):
    items: list[Snippet] = Field(default_factory=list)


class SnippetImport(BaseModel):
    snippets: list[SnippetCreate]


class SnippetExport(BaseModel):
    snippets: list[Snippet] = Field(default_factory=list)


# ---- Built-in snippets (read-only) ----

BUILTIN_SNIPPETS: list[Snippet] = [
    Snippet(
        id="builtin-health-check",
        name="Health Check",
        category="Common",
        description="Simple GET health endpoint",
        method="GET",
        url="{{base_url}}/health",
        headers={},
        tags=["health", "monitoring"],
        builtin=True,
    ),
    Snippet(
        id="builtin-graphql-introspection",
        name="GraphQL Introspection",
        category="GraphQL",
        description="Full introspection query for a GraphQL API",
        method="POST",
        url="{{base_url}}/graphql",
        headers={"Content-Type": "application/json"},
        body=json.dumps({
            "query": "{ __schema { types { name kind description } } }"
        }),
        tags=["graphql", "introspection"],
        builtin=True,
    ),
    Snippet(
        id="builtin-jwt-decode",
        name="JWT Decode",
        category="Auth",
        description="Decode a JWT token via jwt.io API",
        method="GET",
        url="https://jwt.io/.well-known/jwks.json",
        headers={"Accept": "application/json"},
        tags=["jwt", "auth", "decode"],
        builtin=True,
    ),
    Snippet(
        id="builtin-oauth2-token",
        name="OAuth2 Token Request",
        category="Auth",
        description="Request an OAuth2 access token using client credentials",
        method="POST",
        url="{{auth_url}}/oauth/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body="grant_type=client_credentials&client_id={{client_id}}&client_secret={{client_secret}}",
        tags=["oauth2", "auth", "token"],
        builtin=True,
    ),
    Snippet(
        id="builtin-webhook-test",
        name="Webhook Test",
        category="Common",
        description="Send a test POST payload to a webhook URL",
        method="POST",
        url="{{webhook_url}}",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"event": "test", "timestamp": "{{$timestamp}}"}),
        tags=["webhook", "test"],
        builtin=True,
    ),
]


# ---- File storage helpers ----

def _snippets_dir() -> Path:
    d = home_dir() / "snippets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _snippet_path(snippet_id: str) -> Path:
    return _snippets_dir() / f"{snippet_id}.json"


def _load_snippet(path: Path) -> Snippet | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Snippet(**data)
    except Exception:
        return None


def _save_snippet(snippet: Snippet) -> None:
    path = _snippet_path(snippet.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix="snip.", suffix=".json.tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(snippet.model_dump(mode="json"), f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(Path(tmp), path)
    except Exception:
        try:
            Path(tmp).unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _load_all_user_snippets() -> list[Snippet]:
    snippets: list[Snippet] = []
    d = _snippets_dir()
    if not d.exists():
        return snippets
    for p in d.glob("*.json"):
        s = _load_snippet(p)
        if s:
            snippets.append(s)
    return snippets


def _all_snippets(
    category: str | None = None,
    tag: str | None = None,
    search: str | None = None,
) -> list[Snippet]:
    all_items = BUILTIN_SNIPPETS + _load_all_user_snippets()
    if category:
        all_items = [s for s in all_items if s.category.lower() == category.lower()]
    if tag:
        all_items = [s for s in all_items if tag.lower() in [t.lower() for t in s.tags]]
    if search:
        q = search.lower()
        all_items = [
            s for s in all_items
            if q in s.name.lower()
            or q in s.description.lower()
            or q in s.category.lower()
            or any(q in t.lower() for t in s.tags)
        ]
    all_items.sort(key=lambda s: s.name.lower())
    return all_items


# ---- Endpoints ----

@router.get("/categories", response_model=list[str])
def list_categories() -> list[str]:
    """List all unique categories across built-in and user snippets."""
    all_items = BUILTIN_SNIPPETS + _load_all_user_snippets()
    cats = sorted(set(s.category for s in all_items))
    return cats


@router.get("/export", response_model=SnippetExport)
def export_snippets() -> SnippetExport:
    """Export all user snippets as JSON for sharing."""
    return SnippetExport(snippets=_load_all_user_snippets())


@router.get("", response_model=SnippetList)
def list_snippets(
    category: str | None = Query(None),
    tag: str | None = Query(None),
    search: str | None = Query(None),
) -> SnippetList:
    """List all snippets (built-in + user), with optional filters."""
    return SnippetList(items=_all_snippets(category, tag, search))


@router.get("/{snippet_id}", response_model=Snippet)
def get_snippet(snippet_id: str) -> Snippet:
    """Get a single snippet by ID."""
    # Check builtins first
    for b in BUILTIN_SNIPPETS:
        if b.id == snippet_id:
            return b
    s = _load_snippet(_snippet_path(snippet_id))
    if not s:
        raise HTTPException(status_code=404, detail="Snippet not found")
    return s


@router.post("", response_model=Snippet, status_code=201)
def create_snippet(body: SnippetCreate) -> Snippet:
    """Create a new user snippet."""
    now = time.time()
    snippet = Snippet(
        id=str(uuid.uuid4()),
        name=body.name,
        category=body.category,
        description=body.description,
        method=body.method,
        url=body.url,
        headers=body.headers,
        body=body.body,
        auth=body.auth,
        tags=body.tags,
        created_at=now,
        updated_at=now,
        builtin=False,
    )
    _save_snippet(snippet)
    return snippet


@router.put("/{snippet_id}", response_model=Snippet)
def update_snippet(snippet_id: str, body: SnippetUpdate) -> Snippet:
    """Update an existing user snippet."""
    # Cannot update builtins
    for b in BUILTIN_SNIPPETS:
        if b.id == snippet_id:
            raise HTTPException(status_code=403, detail="Cannot modify built-in snippets")
    s = _load_snippet(_snippet_path(snippet_id))
    if not s:
        raise HTTPException(status_code=404, detail="Snippet not found")
    update_data = body.model_dump(exclude_none=True)
    for key, val in update_data.items():
        setattr(s, key, val)
    s.updated_at = time.time()
    _save_snippet(s)
    return s


@router.delete("/{snippet_id}", status_code=204)
def delete_snippet(snippet_id: str) -> None:
    """Delete a user snippet."""
    for b in BUILTIN_SNIPPETS:
        if b.id == snippet_id:
            raise HTTPException(status_code=403, detail="Cannot delete built-in snippets")
    path = _snippet_path(snippet_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Snippet not found")
    path.unlink()


@router.post("/import", response_model=SnippetList)
def import_snippets(body: SnippetImport) -> SnippetList:
    """Import snippets from JSON. Creates new IDs for each."""
    imported: list[Snippet] = []
    now = time.time()
    for item in body.snippets:
        snippet = Snippet(
            id=str(uuid.uuid4()),
            name=item.name,
            category=item.category,
            description=item.description,
            method=item.method,
            url=item.url,
            headers=item.headers,
            body=item.body,
            auth=item.auth,
            tags=item.tags,
            created_at=now,
            updated_at=now,
            builtin=False,
        )
        _save_snippet(snippet)
        imported.append(snippet)
    return SnippetList(items=imported)
