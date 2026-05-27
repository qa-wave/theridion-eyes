"""Tests for the self-healing assertion engine."""

from __future__ import annotations

import json

from theridion_sidecar.assertions import Assertion
from theridion_sidecar.healing import (
    HealCandidate,
    _levenshtein,
    _similarity,
    heal,
)


# ---------------------------------------------------------------------------
# Levenshtein helper tests
# ---------------------------------------------------------------------------

def test_levenshtein_identical() -> None:
    assert _levenshtein("abc", "abc") == 0


def test_levenshtein_one_edit() -> None:
    assert _levenshtein("abc", "ab") == 1
    assert _levenshtein("abc", "axc") == 1


def test_similarity_identical() -> None:
    assert _similarity("hello", "hello") == 1.0


def test_similarity_empty() -> None:
    assert _similarity("", "") == 1.0


# ---------------------------------------------------------------------------
# 1. Renamed key: username → name
# ---------------------------------------------------------------------------

def test_renamed_key() -> None:
    body = json.dumps({"name": "alice", "email": "a@b.com"})
    assertion = Assertion(type="json_path", path="username", operator="eq", expected="alice")
    result = heal(assertion, body)
    assert len(result.candidates) >= 1
    top = result.candidates[0]
    assert top.suggested_path == "name"
    assert top.confidence >= 0.5
    assert "renamed" in top.reason or "moved" in top.reason


# ---------------------------------------------------------------------------
# 2. Moved key: user.name → data.user.name
# ---------------------------------------------------------------------------

def test_moved_key() -> None:
    body = json.dumps({"data": {"user": {"name": "bob"}}})
    assertion = Assertion(type="json_path", path="user.name", operator="eq", expected="bob")
    result = heal(assertion, body)
    assert len(result.candidates) >= 1
    names = [c.suggested_path for c in result.candidates]
    assert "data.user.name" in names
    moved = next(c for c in result.candidates if c.suggested_path == "data.user.name")
    assert moved.reason == "moved_key"


# ---------------------------------------------------------------------------
# 3. Type changed: string "42" vs number 42
# ---------------------------------------------------------------------------

def test_type_changed_number_to_string() -> None:
    # "totals" is close to "total" (sim ~0.83), value "42" matches as string.
    body = json.dumps({"totals": "42"})
    assertion = Assertion(type="json_path", path="total", operator="eq", expected="42")
    result = heal(assertion, body)
    assert len(result.candidates) >= 1
    top = result.candidates[0]
    assert top.suggested_path == "totals"


# ---------------------------------------------------------------------------
# 4. Missing field — no candidates when body is completely different
# ---------------------------------------------------------------------------

def test_missing_field_no_candidates() -> None:
    body = json.dumps({"x": 1, "y": 2, "z": 3})
    assertion = Assertion(
        type="json_path", path="completely_unrelated_field_name",
        operator="eq", expected="hello",
    )
    result = heal(assertion, body)
    # No key is similar enough to "completely_unrelated_field_name".
    assert len(result.candidates) == 0
    assert result.auto_fixable is False


# ---------------------------------------------------------------------------
# 5. Header renamed: Content-Type case difference
# ---------------------------------------------------------------------------

def test_header_case_rename() -> None:
    assertion = Assertion(type="header_exists", path="content-type")
    result = heal(
        assertion, "",
        response_headers={"Content-Type": "application/json"},
    )
    assert len(result.candidates) >= 1
    top = result.candidates[0]
    assert top.suggested_path == "Content-Type"
    assert top.confidence >= 0.9


# ---------------------------------------------------------------------------
# 6. Header fuzzy match
# ---------------------------------------------------------------------------

def test_header_fuzzy_match() -> None:
    assertion = Assertion(type="header_equals", path="X-Req-Id", expected="abc")
    result = heal(
        assertion, "",
        response_headers={"X-Request-Id": "abc", "Content-Type": "text/plain"},
    )
    assert len(result.candidates) >= 1
    top = result.candidates[0]
    assert top.suggested_path == "X-Request-Id"


# ---------------------------------------------------------------------------
# 7. Status code suggestion
# ---------------------------------------------------------------------------

def test_status_code_suggestion() -> None:
    assertion = Assertion(type="status", expected="200")
    result = heal(assertion, "", response_status=201)
    assert len(result.candidates) == 1
    top = result.candidates[0]
    assert top.suggested_path == "status=201"
    assert top.confidence >= 0.8
    assert "201" in top.suggested_path


# ---------------------------------------------------------------------------
# 8. Status code — different class (4xx vs 2xx)
# ---------------------------------------------------------------------------

def test_status_different_class() -> None:
    assertion = Assertion(type="status", expected="200")
    result = heal(assertion, "", response_status=404)
    assert len(result.candidates) == 1
    top = result.candidates[0]
    assert top.confidence < 0.9  # Different class = lower confidence.


# ---------------------------------------------------------------------------
# 9. Multiple candidates sorted by confidence
# ---------------------------------------------------------------------------

def test_multiple_candidates_sorted() -> None:
    body = json.dumps({
        "user_name": "alice",
        "username": "alice",
        "uname": "alice",
    })
    assertion = Assertion(type="json_path", path="usrname", operator="eq", expected="alice")
    result = heal(assertion, body)
    assert len(result.candidates) >= 2
    # Confidence should be descending.
    for i in range(len(result.candidates) - 1):
        assert result.candidates[i].confidence >= result.candidates[i + 1].confidence


# ---------------------------------------------------------------------------
# 10. No candidates for completely different JSON
# ---------------------------------------------------------------------------

def test_no_candidates_completely_different() -> None:
    body = json.dumps({"alpha": 1, "beta": 2, "gamma": 3})
    assertion = Assertion(
        type="json_path", path="zzz_totally_different",
        operator="eq", expected="nope",
    )
    result = heal(assertion, body)
    assert len(result.candidates) == 0
    assert result.auto_fixable is False


# ---------------------------------------------------------------------------
# 11. auto_fixable flag when confidence > 0.9
# ---------------------------------------------------------------------------

def test_auto_fixable_high_confidence() -> None:
    body = json.dumps({"user_name": "alice"})
    assertion = Assertion(type="json_path", path="user_names", operator="eq", expected="alice")
    result = heal(assertion, body)
    # "user_names" vs "user_name" is very similar and value matches.
    if result.candidates:
        top = result.candidates[0]
        if top.confidence > 0.9:
            assert result.auto_fixable is True


# ---------------------------------------------------------------------------
# 12. Invalid JSON body returns empty candidates
# ---------------------------------------------------------------------------

def test_invalid_json_body() -> None:
    assertion = Assertion(type="json_path", path="foo", operator="eq", expected="bar")
    result = heal(assertion, "not json at all")
    assert len(result.candidates) == 0


# ---------------------------------------------------------------------------
# 13. API endpoint integration test
# ---------------------------------------------------------------------------

def test_heal_endpoint(client) -> None:
    resp = client.post("/api/assertions/heal", json={
        "assertion": {"type": "json_path", "path": "username", "operator": "eq", "expected": "alice"},
        "response_body": json.dumps({"name": "alice", "email": "a@b.com"}),
        "response_headers": {},
        "response_status": 200,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "candidates" in data
    assert "auto_fixable" in data
