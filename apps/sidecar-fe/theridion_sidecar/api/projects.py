"""CRUD endpoints for git-native YAML projects."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from theridion_sidecar import yaml_storage
from theridion_sidecar.yaml_storage import (
    Project,
    ProjectSummary,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class ExportOutput(BaseModel):
    project_name: str


@router.get("", response_model=list[ProjectSummary])
async def list_projects() -> list[ProjectSummary]:
    """List all YAML projects."""
    return yaml_storage.list_projects()


@router.post("", response_model=Project, status_code=201)
async def create_project(body: CreateProjectInput) -> Project:
    """Create a new empty YAML project."""
    try:
        return yaml_storage.create_project(body.name)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{name}", response_model=Project)
async def get_project(name: str) -> Project:
    """Get a project with all its collections and environments."""
    proj = yaml_storage.get_project(name)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"project {name!r} not found")
    return proj


@router.post(
    "/{name}/export-from-collection/{collection_id}",
    response_model=ExportOutput,
)
async def export_from_collection(name: str, collection_id: str) -> ExportOutput:
    """Convert an existing JSON collection to a YAML project.

    The *name* path parameter is currently unused — the project name is
    derived from the collection. This keeps the URL RESTful while
    allowing automatic naming.
    """
    try:
        project_name = yaml_storage.export_collection_to_yaml(collection_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ExportOutput(project_name=project_name)


@router.delete("/{name}", status_code=204)
async def delete_project(name: str) -> None:
    """Delete a YAML project entirely."""
    if not yaml_storage.delete_project(name):
        raise HTTPException(status_code=404, detail=f"project {name!r} not found")
