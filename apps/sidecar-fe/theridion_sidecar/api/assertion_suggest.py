"""Smart assertion auto-suggest based on response heuristics.

Analyzes a response (status, headers, body, timing) and suggests
relevant assertions without requiring an AI model.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from theridion_sidecar.assertions import Assertion

router = APIRouter(prefix="/api/assertions", tags=["assertions"])


class SuggestInput(BaseModel):
    status: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    elapsed_ms: float = 0


class AssertionSuggestion(BaseModel):
    assertion: Assertion
    confidence: float
    reason: str
    category: str


class SuggestOutput(BaseModel):
    suggestions: list[AssertionSuggestion]


# Fields that are commonly important and should be non-null
_IMPORTANT_FIELDS = {"id", "name", "email", "username", "title", "status", "type", "url"}

# Pagination-related keys
_PAGINATION_KEYS = {"page", "total", "limit", "offset", "per_page", "total_pages", "count", "next", "previous", "has_more", "has_next"}

# Auth/token-related keys
_AUTH_KEYS = {"token", "access_token", "refresh_token", "id_token", "jwt", "api_key", "session_id"}


def _suggest_status(status: int) -> list[AssertionSuggestion]:
    return [
        AssertionSuggestion(
            assertion=Assertion(type="status", expected=str(status), path="", operator="eq"),
            confidence=1.0,
            reason=f"Status code is {status}",
            category="status",
        )
    ]


def _suggest_performance(elapsed_ms: float) -> list[AssertionSuggestion]:
    if elapsed_ms <= 0:
        return []
    budget = round(elapsed_ms * 2)
    # Cap at reasonable max
    budget = min(budget, 30000)
    return [
        AssertionSuggestion(
            assertion=Assertion(type="response_time", expected=str(budget), path="", operator="eq"),
            confidence=0.7,
            reason=f"Response took {elapsed_ms:.0f}ms, budget set to 2x ({budget}ms)",
            category="performance",
        )
    ]


def _suggest_content_type(headers: dict[str, str]) -> list[AssertionSuggestion]:
    ct = _get_header(headers, "content-type")
    if not ct:
        return []
    return [
        AssertionSuggestion(
            assertion=Assertion(type="header_equals", expected=ct, path="content-type", operator="eq"),
            confidence=0.85,
            reason=f"Content-Type is '{ct}'",
            category="structure",
        )
    ]


def _suggest_json_structure(data: Any, prefix: str = "") -> list[AssertionSuggestion]:
    """Generate suggestions from JSON structure (top-level only to keep count low)."""
    suggestions: list[AssertionSuggestion] = []

    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"

            # Exists check for top-level keys
            suggestions.append(
                AssertionSuggestion(
                    assertion=Assertion(type="json_path", expected="", path=path, operator="exists"),
                    confidence=0.8,
                    reason=f"Field '{path}' exists in response",
                    category="structure",
                )
            )

            # Type checks
            if isinstance(value, str):
                if key.lower() in _IMPORTANT_FIELDS:
                    suggestions.append(
                        AssertionSuggestion(
                            assertion=Assertion(type="json_path", expected="", path=path, operator="exists"),
                            confidence=0.9,
                            reason=f"Important field '{path}' should not be null",
                            category="content",
                        )
                    )
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                suggestions.append(
                    AssertionSuggestion(
                        assertion=Assertion(type="json_path", expected=str(value), path=path, operator="eq"),
                        confidence=0.6,
                        reason=f"Numeric field '{path}' equals {value}",
                        category="content",
                    )
                )
            elif isinstance(value, list):
                suggestions.append(
                    AssertionSuggestion(
                        assertion=Assertion(type="json_path", expected="0", path=path, operator="gte"),
                        confidence=0.75,
                        reason=f"Array '{path}' has items (length >= 0)",
                        category="structure",
                    )
                )
                if len(value) > 0:
                    suggestions.append(
                        AssertionSuggestion(
                            assertion=Assertion(type="json_path", expected="0", path=f"{path}.length", operator="gt"),
                            confidence=0.7,
                            reason=f"Array '{path}' is not empty ({len(value)} items)",
                            category="content",
                        )
                    )

    elif isinstance(data, list):
        if len(data) > 0:
            suggestions.append(
                AssertionSuggestion(
                    assertion=Assertion(type="body_contains", expected="[", path="", operator="eq"),
                    confidence=0.6,
                    reason="Response is a JSON array",
                    category="structure",
                )
            )
            # Suggest structure of first element
            if isinstance(data[0], dict):
                for key in data[0]:
                    path = f"0.{key}" if not prefix else f"{prefix}.0.{key}"
                    suggestions.append(
                        AssertionSuggestion(
                            assertion=Assertion(type="json_path", expected="", path=path, operator="exists"),
                            confidence=0.7,
                            reason=f"Array element field '{key}' exists",
                            category="structure",
                        )
                    )

    return suggestions


def _suggest_pagination(data: Any) -> list[AssertionSuggestion]:
    """Suggest assertions for pagination fields."""
    if not isinstance(data, dict):
        return []
    suggestions: list[AssertionSuggestion] = []
    found_keys = set(data.keys()) & _PAGINATION_KEYS
    for key in found_keys:
        value = data[key]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            suggestions.append(
                AssertionSuggestion(
                    assertion=Assertion(type="json_path", expected="0", path=key, operator="gte"),
                    confidence=0.8,
                    reason=f"Pagination field '{key}' is non-negative",
                    category="content",
                )
            )
        elif isinstance(value, bool):
            suggestions.append(
                AssertionSuggestion(
                    assertion=Assertion(type="json_path", expected="", path=key, operator="exists"),
                    confidence=0.75,
                    reason=f"Pagination flag '{key}' present",
                    category="structure",
                )
            )
    return suggestions


def _suggest_auth_tokens(data: Any) -> list[AssertionSuggestion]:
    """Suggest assertions for auth/token fields."""
    if not isinstance(data, dict):
        return []
    suggestions: list[AssertionSuggestion] = []
    found_keys = set(data.keys()) & _AUTH_KEYS
    for key in found_keys:
        value = data[key]
        suggestions.append(
            AssertionSuggestion(
                assertion=Assertion(type="json_path", expected="", path=key, operator="exists"),
                confidence=0.95,
                reason=f"Auth field '{key}' must be present",
                category="security",
            )
        )
        if isinstance(value, str) and len(value) > 0:
            suggestions.append(
                AssertionSuggestion(
                    assertion=Assertion(type="json_path", expected="", path=key, operator="exists"),
                    confidence=0.9,
                    reason=f"Token '{key}' should be a non-empty string",
                    category="security",
                )
            )
    return suggestions


def _suggest_error_patterns(status: int, body: str, data: Any) -> list[AssertionSuggestion]:
    """Suggest assertions for error responses."""
    if status < 400:
        return []
    suggestions: list[AssertionSuggestion] = []

    # If JSON with error/message fields
    if isinstance(data, dict):
        for key in ("error", "message", "detail", "errors"):
            if key in data:
                value = data[key]
                if isinstance(value, str) and value:
                    suggestions.append(
                        AssertionSuggestion(
                            assertion=Assertion(type="body_contains", expected=value[:50], path="", operator="eq"),
                            confidence=0.8,
                            reason=f"Error message in '{key}' field",
                            category="content",
                        )
                    )
                    break
    elif body:
        # Non-JSON error body — suggest body_contains for first meaningful chunk
        snippet = body.strip()[:40]
        if snippet:
            suggestions.append(
                AssertionSuggestion(
                    assertion=Assertion(type="body_contains", expected=snippet, path="", operator="eq"),
                    confidence=0.5,
                    reason="Error response body content",
                    category="content",
                )
            )

    return suggestions


def _get_header(headers: dict[str, str], name: str) -> str | None:
    """Case-insensitive header lookup."""
    lower = name.lower()
    for k, v in headers.items():
        if k.lower() == lower:
            return v
    return None


def suggest_assertions(input: SuggestInput) -> SuggestOutput:
    """Generate assertion suggestions for a given response."""
    suggestions: list[AssertionSuggestion] = []

    # Always: status
    suggestions.extend(_suggest_status(input.status))

    # Performance budget
    suggestions.extend(_suggest_performance(input.elapsed_ms))

    # Content-Type header
    suggestions.extend(_suggest_content_type(input.headers))

    # Parse JSON body
    parsed_json: Any = None
    if input.body.strip():
        try:
            parsed_json = json.loads(input.body)
        except (json.JSONDecodeError, ValueError):
            pass

    if parsed_json is not None:
        suggestions.extend(_suggest_json_structure(parsed_json))
        suggestions.extend(_suggest_pagination(parsed_json))
        suggestions.extend(_suggest_auth_tokens(parsed_json))

    # Error patterns
    suggestions.extend(_suggest_error_patterns(input.status, input.body, parsed_json))

    # De-duplicate: remove suggestions with identical assertion serialization
    seen: set[str] = set()
    unique: list[AssertionSuggestion] = []
    for s in suggestions:
        key = f"{s.assertion.type}|{s.assertion.path}|{s.assertion.operator}|{s.assertion.expected}|{s.category}"
        if key not in seen:
            seen.add(key)
            unique.append(s)

    # Sort by confidence descending, limit to 15
    unique.sort(key=lambda s: s.confidence, reverse=True)
    return SuggestOutput(suggestions=unique[:15])


@router.post("/suggest", response_model=SuggestOutput)
async def suggest_endpoint(input: SuggestInput) -> SuggestOutput:
    """Suggest assertions based on response content heuristics."""
    return suggest_assertions(input)
