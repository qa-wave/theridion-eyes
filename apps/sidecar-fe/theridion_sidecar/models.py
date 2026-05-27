"""Domain models shared across endpoints and storage.

The collection tree is a discriminated union of folders and requests
through a single `CollectionItem` model with `is_folder`. Older files
predating folders deserialize cleanly because `is_folder` defaults to
False and `items` defaults to an empty list.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .assertions import Assertion

HttpMethod = Literal[
    "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"
]

AuthType = Literal["none", "bearer", "basic", "apikey"]

# Silk (frontend testing) item kind — stored alongside regular requests in a
# collection so failed API requests can point to a Playwright spec that
# reproduces the failure.
CollectionItemKind = Literal["request", "playwright_spec"]


class AuthConfig(BaseModel):
    """Authentication configuration attached to a request."""

    type: AuthType = "none"
    # Bearer
    token: str | None = None
    # Basic
    username: str | None = None
    password: str | None = None
    # API Key
    key: str | None = None
    value: str | None = None
    add_to: Literal["header", "query"] = "header"


class RequestExample(BaseModel):
    """A named request variant saved under a collection item."""

    id: str
    name: str
    method: HttpMethod = "GET"
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    auth: AuthConfig | None = None
    notes: str | None = None


class RequestCapture(BaseModel):
    """A value produced by a request and exposed as a runtime variable."""

    name: str
    source: Literal["body", "header", "status"] = "body"
    path: str = ""


class CollectionItem(BaseModel):
    """Either a folder (is_folder=True, has child items) or a request/spec.

    ``kind`` discriminates between a regular HTTP request (``"request"``,
    default for backwards compat) and a Playwright spec entry
    (``"playwright_spec"``).  Older files that have no ``kind`` field
    deserialize as ``"request"`` because of the default.
    """

    id: str
    name: str
    is_folder: bool = False
    # Discriminated kind — "request" is the legacy default.
    kind: CollectionItemKind = "request"
    # Request-specific fields (populated when is_folder=False and kind="request").
    method: HttpMethod | None = None
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    auth: AuthConfig | None = None
    assertions: list[Assertion] = Field(default_factory=list)
    pre_request_script: str | None = None
    post_response_script: str | None = None
    notes: str | None = None
    examples: list[RequestExample] = Field(default_factory=list)
    captures: list[RequestCapture] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # Silk / playwright_spec fields (populated when kind="playwright_spec").
    spec_path: str | None = None
    # Folder-specific field (populated when is_folder=True).
    items: list[CollectionItem] = Field(default_factory=list)


CollectionItem.model_rebuild()


# Back-compat alias used by the older /requests endpoint contract.
SavedRequest = CollectionItem


class CollectionVariable(BaseModel):
    """A variable scoped to a collection."""

    name: str
    value: str
    enabled: bool = True


class Collection(BaseModel):
    id: str
    name: str
    version: int = 1
    items: list[CollectionItem] = Field(default_factory=list)
    variables: list[CollectionVariable] = Field(default_factory=list)


class CollectionSummary(BaseModel):
    """Lightweight projection used by the list endpoint."""
    id: str
    name: str
    request_count: int


class CreateCollectionInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class CreateFolderInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    parent_folder_id: str | None = None


class SaveRequestInput(BaseModel):
    id: str | None = None
    name: str = Field(..., min_length=1, max_length=200)
    method: HttpMethod = "GET"
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    auth: AuthConfig | None = None
    assertions: list[Assertion] = Field(default_factory=list)
    pre_request_script: str | None = None
    post_response_script: str | None = None
    notes: str | None = None
    examples: list[RequestExample] = Field(default_factory=list)
    captures: list[RequestCapture] = Field(default_factory=list)
    parent_folder_id: str | None = None
