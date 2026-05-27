"""CRUD endpoints for request environments."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import environments
from ..environments import Environment, EnvironmentSummary, EnvVariable

router = APIRouter(prefix="/api/environments", tags=["environments"])


class CreateEnvironmentInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class RenameEnvironmentInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class ReplaceVariablesInput(BaseModel):
    variables: list[EnvVariable]


# ---- Diff models -----------------------------------------------------------


class DiffInput(BaseModel):
    left_id: str
    right_id: str


class DiffVarPair(BaseModel):
    name: str
    value: str


class DiffVarDifferent(BaseModel):
    name: str
    left_value: str
    right_value: str


class DiffOutput(BaseModel):
    only_left: list[DiffVarPair] = Field(default_factory=list)
    only_right: list[DiffVarPair] = Field(default_factory=list)
    different: list[DiffVarDifferent] = Field(default_factory=list)
    same: list[DiffVarPair] = Field(default_factory=list)


# ---- Clone model -----------------------------------------------------------


class CloneInput(BaseModel):
    new_name: str = Field(..., min_length=1, max_length=200)


@router.get("", response_model=list[EnvironmentSummary])
def list_environments() -> list[EnvironmentSummary]:
    return environments.list_summaries()


@router.post("", response_model=Environment, status_code=201)
def create_environment(body: CreateEnvironmentInput) -> Environment:
    return environments.create(body.name)


@router.get("/{env_id}", response_model=Environment)
def get_environment(env_id: str) -> Environment:
    env = environments.get(env_id)
    if env is None:
        raise HTTPException(status_code=404, detail="environment not found")
    return env


@router.patch("/{env_id}", response_model=Environment)
def rename_environment(env_id: str, body: RenameEnvironmentInput) -> Environment:
    try:
        return environments.rename(env_id, body.name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/{env_id}/variables", response_model=Environment)
def replace_variables(env_id: str, body: ReplaceVariablesInput) -> Environment:
    try:
        return environments.replace_variables(env_id, body.variables)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{env_id}", status_code=204)
def delete_environment(env_id: str) -> None:
    if not environments.delete(env_id):
        raise HTTPException(status_code=404, detail="environment not found")


@router.post("/diff", response_model=DiffOutput)
def diff_environments(body: DiffInput) -> DiffOutput:
    """Compare two environments side-by-side.

    Returns four buckets: variables only in the left env, only in the
    right env, present in both but with different values, and identical.
    """
    left = environments.get(body.left_id)
    right = environments.get(body.right_id)
    if not left:
        raise HTTPException(status_code=404, detail=f"Left environment {body.left_id} not found")
    if not right:
        raise HTTPException(status_code=404, detail=f"Right environment {body.right_id} not found")

    left_vars = {v.name: v.value for v in left.variables if v.enabled}
    right_vars = {v.name: v.value for v in right.variables if v.enabled}
    all_names = sorted(set(left_vars) | set(right_vars))

    only_left: list[DiffVarPair] = []
    only_right: list[DiffVarPair] = []
    different: list[DiffVarDifferent] = []
    same: list[DiffVarPair] = []

    for name in all_names:
        in_left = name in left_vars
        in_right = name in right_vars
        if in_left and in_right:
            if left_vars[name] == right_vars[name]:
                same.append(DiffVarPair(name=name, value=left_vars[name]))
            else:
                different.append(DiffVarDifferent(
                    name=name,
                    left_value=left_vars[name],
                    right_value=right_vars[name],
                ))
        elif in_left:
            only_left.append(DiffVarPair(name=name, value=left_vars[name]))
        else:
            only_right.append(DiffVarPair(name=name, value=right_vars[name]))

    return DiffOutput(
        only_left=only_left,
        only_right=only_right,
        different=different,
        same=same,
    )


@router.post("/{env_id}/clone", response_model=EnvironmentSummary, status_code=201)
def clone_environment(env_id: str, body: CloneInput) -> EnvironmentSummary:
    """Duplicate an environment with a new name, copying all variables."""
    source = environments.get(env_id)
    if not source:
        raise HTTPException(status_code=404, detail="environment not found")

    new_env = environments.create(body.new_name)
    # Copy all variables from source
    environments.replace_variables(new_env.id, list(source.variables))

    return EnvironmentSummary(
        id=new_env.id,
        name=new_env.name,
        variable_count=len(source.variables),
    )
