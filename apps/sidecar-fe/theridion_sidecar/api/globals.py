"""Global variables CRUD API."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import globals as global_store

router = APIRouter(prefix="/api/globals", tags=["globals"])


class GlobalVarsInput(BaseModel):
    variables: list[global_store.GlobalVariable] = Field(default_factory=list)


@router.get("", response_model=global_store.GlobalsStore)
def get_globals() -> global_store.GlobalsStore:
    return global_store.load()


@router.put("", response_model=global_store.GlobalsStore)
def replace_globals(body: GlobalVarsInput) -> global_store.GlobalsStore:
    store = global_store.GlobalsStore(variables=body.variables)
    global_store.save(store)
    return store
