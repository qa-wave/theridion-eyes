"""Git-native YAML project storage backend.

Directory structure on disk::

    $THERIDION_HOME/projects/{project-name}/
    ├── .theridion.yaml          # project manifest
    ├── environments/
    │   ├── dev.yaml
    │   └── prod.yaml
    └── collections/
        └── {collection-name}/
            ├── .collection.yaml  # name, variables
            ├── {folder-name}/
            │   └── {request}.yaml
            └── {request}.yaml

Request YAML format::

    name: Create User
    method: POST
    url: "{{base_url}}/users"
    headers:
      Content-Type: application/json
    body: |
      {"name": "Alice"}
    auth:
      type: bearer
      token: "{{token}}"
    assertions:
      - type: status
        expected: "201"

This format is designed to be human-readable and git-friendly — each
request is a single YAML file, diffs are clean, and merge conflicts are
easy to resolve by hand.
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import storage
from .models import Collection, CollectionItem


# ---------------------------------------------------------------------------
# Pydantic models for the API layer
# ---------------------------------------------------------------------------

from pydantic import BaseModel, Field


class ProjectSummary(BaseModel):
    """Lightweight projection for listing projects."""

    name: str
    collection_count: int = 0
    environment_count: int = 0
    created_at: str | None = None


class ProjectEnvironment(BaseModel):
    """An environment inside a YAML project."""

    name: str
    variables: dict[str, str] = Field(default_factory=dict)


class ProjectCollection(BaseModel):
    """A collection directory inside a YAML project."""

    name: str
    requests: list[dict[str, Any]] = Field(default_factory=list)
    variables: dict[str, str] = Field(default_factory=dict)


class Project(BaseModel):
    """Full project with all collections and environments."""

    name: str
    created_at: str | None = None
    collections: list[ProjectCollection] = Field(default_factory=list)
    environments: list[ProjectEnvironment] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9 _.-]{0,99}$")


def _sanitize_name(name: str) -> str:
    """Return a filesystem-safe version of *name*.

    Raises ValueError for obviously bad inputs.
    """
    name = name.strip()
    if not name:
        raise ValueError("name must not be empty")
    if not _SAFE_NAME_RE.match(name):
        raise ValueError(
            f"name contains invalid characters: {name!r}. "
            "Use alphanumeric, spaces, dots, hyphens, or underscores."
        )
    return name


def _projects_root() -> Path:
    """Return the base directory for YAML projects."""
    root = storage.home_dir() / "projects"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _project_dir(name: str) -> Path:
    return _projects_root() / _sanitize_name(name)


def _slugify(name: str) -> str:
    """Turn a human name into a filesystem-safe slug."""
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug or "untitled"


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def list_projects() -> list[ProjectSummary]:
    """List all YAML projects under $THERIDION_HOME/projects/."""
    root = _projects_root()
    out: list[ProjectSummary] = []
    for entry in sorted(root.iterdir()):
        manifest = entry / ".theridion.yaml"
        if not manifest.is_file():
            continue
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError):
            continue

        collections_dir = entry / "collections"
        col_count = (
            sum(1 for c in collections_dir.iterdir() if c.is_dir())
            if collections_dir.is_dir()
            else 0
        )
        env_dir = entry / "environments"
        env_count = (
            sum(1 for e in env_dir.glob("*.yaml"))
            if env_dir.is_dir()
            else 0
        )
        out.append(
            ProjectSummary(
                name=data.get("name", entry.name),
                collection_count=col_count,
                environment_count=env_count,
                created_at=data.get("created_at"),
            )
        )
    return out


def get_project(name: str) -> Project | None:
    """Load a full project from disk."""
    pdir = _project_dir(name)
    manifest = pdir / ".theridion.yaml"
    if not manifest.is_file():
        return None

    try:
        meta = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return None

    # Load environments
    environments: list[ProjectEnvironment] = []
    env_dir = pdir / "environments"
    if env_dir.is_dir():
        for ef in sorted(env_dir.glob("*.yaml")):
            try:
                edata = yaml.safe_load(ef.read_text(encoding="utf-8")) or {}
            except (yaml.YAMLError, OSError):
                continue
            environments.append(
                ProjectEnvironment(
                    name=edata.get("name", ef.stem),
                    variables=edata.get("variables", {}),
                )
            )

    # Load collections
    collections: list[ProjectCollection] = []
    col_dir = pdir / "collections"
    if col_dir.is_dir():
        for cdir in sorted(col_dir.iterdir()):
            if not cdir.is_dir():
                continue
            col_meta_path = cdir / ".collection.yaml"
            col_meta: dict[str, Any] = {}
            if col_meta_path.is_file():
                try:
                    col_meta = yaml.safe_load(
                        col_meta_path.read_text(encoding="utf-8")
                    ) or {}
                except (yaml.YAMLError, OSError):
                    pass

            requests = _load_requests_recursive(cdir)
            collections.append(
                ProjectCollection(
                    name=col_meta.get("name", cdir.name),
                    requests=requests,
                    variables=col_meta.get("variables", {}),
                )
            )

    return Project(
        name=meta.get("name", name),
        created_at=meta.get("created_at"),
        collections=collections,
        environments=environments,
    )


def _load_requests_recursive(directory: Path) -> list[dict[str, Any]]:
    """Recursively load request YAML files from a directory tree."""
    out: list[dict[str, Any]] = []
    for entry in sorted(directory.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            # This is a folder — recurse
            children = _load_requests_recursive(entry)
            out.append(
                {
                    "name": entry.name,
                    "is_folder": True,
                    "items": children,
                }
            )
        elif entry.suffix == ".yaml":
            try:
                data = yaml.safe_load(entry.read_text(encoding="utf-8")) or {}
            except (yaml.YAMLError, OSError):
                continue
            # Ensure the name is set
            if "name" not in data:
                data["name"] = entry.stem
            out.append(data)
    return out


def create_project(name: str) -> Project:
    """Create a new empty YAML project."""
    safe_name = _sanitize_name(name)
    pdir = _projects_root() / safe_name
    if pdir.exists():
        raise FileExistsError(f"project {safe_name!r} already exists")

    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "collections").mkdir(exist_ok=True)
    (pdir / "environments").mkdir(exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    manifest = {"name": name, "created_at": now, "version": 1}
    (pdir / ".theridion.yaml").write_text(
        yaml.dump(manifest, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    return Project(name=name, created_at=now, collections=[], environments=[])


def save_request(
    project: str,
    collection: str,
    path: str,
    request_data: dict[str, Any],
) -> None:
    """Save a request YAML file inside a project collection.

    *path* is a slash-separated relative path, e.g.
    ``"users/create-user"`` (no ``.yaml`` extension needed).
    """
    pdir = _project_dir(project)
    if not (pdir / ".theridion.yaml").is_file():
        raise FileNotFoundError(f"project {project!r} not found")

    col_dir = pdir / "collections" / _sanitize_name(collection)
    if not col_dir.is_dir():
        # Auto-create the collection directory + manifest
        col_dir.mkdir(parents=True, exist_ok=True)
        col_manifest = {"name": collection, "variables": {}}
        (col_dir / ".collection.yaml").write_text(
            yaml.dump(col_manifest, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

    # Build the file path
    parts = [p.strip() for p in path.strip("/").split("/") if p.strip()]
    if not parts:
        raise ValueError("path must not be empty")

    # Last segment is the request filename
    filename = parts[-1]
    if not filename.endswith(".yaml"):
        filename += ".yaml"

    target = col_dir
    for folder in parts[:-1]:
        target = target / _sanitize_name(folder)
        target.mkdir(parents=True, exist_ok=True)

    target = target / filename
    target.write_text(
        yaml.dump(request_data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


def delete_request(project: str, collection: str, path: str) -> None:
    """Delete a request YAML file from a project collection."""
    pdir = _project_dir(project)
    if not (pdir / ".theridion.yaml").is_file():
        raise FileNotFoundError(f"project {project!r} not found")

    col_dir = pdir / "collections" / _sanitize_name(collection)
    parts = [p.strip() for p in path.strip("/").split("/") if p.strip()]
    if not parts:
        raise ValueError("path must not be empty")

    filename = parts[-1]
    if not filename.endswith(".yaml"):
        filename += ".yaml"

    target = col_dir
    for folder in parts[:-1]:
        target = target / folder

    target = target / filename
    if not target.is_file():
        raise FileNotFoundError(f"request file not found: {target}")
    target.unlink()


def delete_project(name: str) -> bool:
    """Delete a YAML project entirely."""
    pdir = _project_dir(name)
    if not pdir.is_dir():
        return False
    shutil.rmtree(pdir)
    return True


def export_collection_to_yaml(collection_id: str) -> str:
    """Convert an existing JSON collection to a YAML project.

    Creates a new project named after the collection and writes all
    requests as YAML files. Returns the project name.
    """
    coll = storage.get(collection_id)
    if coll is None:
        raise FileNotFoundError(f"collection {collection_id} not found")

    project_name = coll.name
    # Avoid collision — append suffix if needed
    pdir = _projects_root() / _sanitize_name(project_name)
    suffix = 0
    while pdir.exists():
        suffix += 1
        project_name = f"{coll.name} {suffix}"
        pdir = _projects_root() / _sanitize_name(project_name)

    proj = create_project(project_name)
    _export_items(project_name, coll.name, coll.items, "")
    return project_name


def _export_items(
    project: str,
    collection: str,
    items: list[CollectionItem],
    prefix: str,
) -> None:
    """Recursively export CollectionItems to YAML files."""
    for item in items:
        if item.is_folder:
            _export_items(
                project,
                collection,
                item.items,
                f"{prefix}/{_slugify(item.name)}" if prefix else _slugify(item.name),
            )
        else:
            req_data: dict[str, Any] = {"name": item.name}
            if item.method:
                req_data["method"] = item.method
            if item.url:
                req_data["url"] = item.url
            if item.headers:
                req_data["headers"] = dict(item.headers)
            if item.body:
                req_data["body"] = item.body
            if item.auth:
                req_data["auth"] = item.auth.model_dump(exclude_none=True)
            if item.assertions:
                req_data["assertions"] = [
                    a.model_dump(exclude_none=True) for a in item.assertions
                ]

            slug = _slugify(item.name)
            path = f"{prefix}/{slug}" if prefix else slug
            save_request(project, collection, path, req_data)
