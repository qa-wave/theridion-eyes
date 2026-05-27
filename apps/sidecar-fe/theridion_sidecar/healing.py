"""Self-healing engine for failed assertions.

Given a failed assertion and the actual response, the engine suggests
candidate fixes by fuzzy-matching field names, header names, or status
codes. Drift is classified as renamed_key, moved_key, type_changed,
or missing_field.

Levenshtein distance is implemented inline (no external dependency).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from .assertions import Assertion


class HealCandidate(BaseModel):
    original_path: str
    suggested_path: str
    confidence: float
    reason: str


class HealOutput(BaseModel):
    candidates: list[HealCandidate]
    auto_fixable: bool


# ---------------------------------------------------------------------------
# Levenshtein distance (inline, no external dep)
# ---------------------------------------------------------------------------

def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if len(b) == 0:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[len(b)]


def _similarity(a: str, b: str) -> float:
    """Return a 0-1 similarity score based on Levenshtein distance."""
    if a == b:
        return 1.0
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 1.0
    return 1.0 - _levenshtein(a, b) / max_len


# ---------------------------------------------------------------------------
# JSON key extraction
# ---------------------------------------------------------------------------

def _collect_paths(data: Any, prefix: str = "") -> dict[str, Any]:
    """Walk a JSON structure and return {dot.path: value} for all leaves."""
    paths: dict[str, Any] = {}
    if isinstance(data, dict):
        for key, val in data.items():
            full = f"{prefix}.{key}" if prefix else key
            if isinstance(val, (dict, list)):
                paths.update(_collect_paths(val, full))
            else:
                paths[full] = val
    elif isinstance(data, list):
        for i, item in enumerate(data):
            full = f"{prefix}[{i}]"
            if isinstance(item, (dict, list)):
                paths.update(_collect_paths(item, full))
            else:
                paths[full] = item
    return paths


def _leaf_name(path: str) -> str:
    """Extract the final key/field name from a dot path."""
    # "data.user.name" -> "name", "items[0].id" -> "id"
    parts = path.replace("]", "").split(".")
    last = parts[-1] if parts else path
    # Strip bracket index
    if "[" in last:
        last = last.split("[")[0]
    return last


# ---------------------------------------------------------------------------
# Heal logic per assertion type
# ---------------------------------------------------------------------------

def heal(assertion: Assertion, response_body: str,
         response_headers: dict[str, str] | None = None,
         response_status: int = 200) -> HealOutput:
    """Produce heal candidates for a failed assertion."""
    candidates: list[HealCandidate] = []

    if assertion.type == "json_path":
        candidates = _heal_json_path(assertion, response_body)
    elif assertion.type in ("header_exists", "header_equals"):
        candidates = _heal_header(assertion, response_headers or {})
    elif assertion.type == "status":
        candidates = _heal_status(assertion, response_status)

    # Sort by descending confidence.
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    auto_fixable = len(candidates) > 0 and candidates[0].confidence > 0.9

    return HealOutput(candidates=candidates, auto_fixable=auto_fixable)


def _heal_json_path(assertion: Assertion, body: str) -> list[HealCandidate]:
    """Find candidate fixes for a json_path assertion."""
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return []

    original_path = assertion.path
    original_leaf = _leaf_name(original_path)
    all_paths = _collect_paths(data)

    candidates: list[HealCandidate] = []

    for actual_path, actual_value in all_paths.items():
        actual_leaf = _leaf_name(actual_path)

        # Case 1: Renamed key — same depth, similar leaf name.
        leaf_sim = _similarity(original_leaf.lower(), actual_leaf.lower())
        if leaf_sim >= 0.5 and actual_path != original_path:
            # Check if the expected value matches (type-aware).
            reason = _classify_drift(original_path, actual_path, assertion, actual_value)
            # Boost confidence if value also matches.
            value_match = _value_matches(assertion, actual_value)
            confidence = leaf_sim * 0.7 + (0.3 if value_match else 0.0)

            candidates.append(HealCandidate(
                original_path=original_path,
                suggested_path=actual_path,
                confidence=round(min(confidence, 1.0), 3),
                reason=reason,
            ))

        # Case 2: Exact leaf name at different location (moved key).
        elif actual_leaf == original_leaf and actual_path != original_path:
            value_match = _value_matches(assertion, actual_value)
            confidence = 0.85 if value_match else 0.6
            candidates.append(HealCandidate(
                original_path=original_path,
                suggested_path=actual_path,
                confidence=round(confidence, 3),
                reason="moved_key",
            ))

    # Deduplicate by suggested_path, keeping highest confidence.
    seen: dict[str, HealCandidate] = {}
    for c in candidates:
        if c.suggested_path not in seen or c.confidence > seen[c.suggested_path].confidence:
            seen[c.suggested_path] = c
    return list(seen.values())


def _classify_drift(original: str, actual: str, assertion: Assertion,
                    actual_value: Any) -> str:
    """Classify the kind of drift between original and actual paths."""
    orig_leaf = _leaf_name(original)
    actual_leaf = _leaf_name(actual)

    # Same leaf, different parent -> moved.
    if orig_leaf == actual_leaf:
        return "moved_key"

    # Different leaf at similar depth -> renamed.
    orig_depth = original.count(".")
    actual_depth = actual.count(".")
    if abs(orig_depth - actual_depth) <= 1:
        # Check if type changed.
        if assertion.expected:
            try:
                expected_num = float(assertion.expected)
                if isinstance(actual_value, str):
                    return "type_changed"
            except (ValueError, TypeError):
                if isinstance(actual_value, (int, float)):
                    return "type_changed"
        return "renamed_key"

    return "moved_key"


def _value_matches(assertion: Assertion, actual_value: Any) -> bool:
    """Check if the assertion's expected value loosely matches actual."""
    if assertion.operator == "exists":
        return True
    expected = assertion.expected
    if str(actual_value) == expected:
        return True
    # Numeric comparison.
    try:
        return float(actual_value) == float(expected)
    except (ValueError, TypeError):
        pass
    return False


def _heal_header(assertion: Assertion, headers: dict[str, str]) -> list[HealCandidate]:
    """Find candidate fixes for header assertions."""
    original = assertion.path
    candidates: list[HealCandidate] = []

    for hdr_name in headers:
        # Case-insensitive exact match (already handled by assertions, but
        # useful when the case literally differs).
        if hdr_name.lower() == original.lower() and hdr_name != original:
            candidates.append(HealCandidate(
                original_path=original,
                suggested_path=hdr_name,
                confidence=0.95,
                reason="renamed_key",
            ))
            continue

        # Partial / fuzzy match.
        sim = _similarity(original.lower(), hdr_name.lower())
        if sim >= 0.5 and hdr_name.lower() != original.lower():
            candidates.append(HealCandidate(
                original_path=original,
                suggested_path=hdr_name,
                confidence=round(sim * 0.9, 3),
                reason="renamed_key",
            ))

    return candidates


def _heal_status(assertion: Assertion, actual_status: int) -> list[HealCandidate]:
    """Suggest status code fixes when the status doesn't match."""
    try:
        expected = int(assertion.expected)
    except (ValueError, TypeError):
        return []

    if expected == actual_status:
        return []

    # Common status code confusions.
    confidence = 0.7
    reason = "type_changed"

    # Same class (2xx vs 2xx).
    if expected // 100 == actual_status // 100:
        confidence = 0.9
        reason = "renamed_key"

    return [HealCandidate(
        original_path=f"status={expected}",
        suggested_path=f"status={actual_status}",
        confidence=confidence,
        reason=reason,
    )]
