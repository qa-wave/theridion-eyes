"""Path traversal security tests for file-based storage.

Tests that collection_id and env_id cannot be used to escape the
storage root by verifying the uuid.UUID() guard in _path_for().

These are unit-level tests (no HTTP) so they run without a server.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest

from theridion_sidecar import storage, environments


# ---------------------------------------------------------------------------
# Traversal payloads to reject
# ---------------------------------------------------------------------------

TRAVERSAL_PAYLOADS = [
    # Classic traversal
    "../../../etc/passwd",
    "../../etc/shadow",
    "../..",
    # Null-byte termination
    "valid\x00../../etc/passwd",
    # Absolute path
    "/etc/passwd",
    # Windows style
    "..\\..\\windows\\system32",
    # URL-encoded (should still fail uuid parse)
    "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    # Valid-looking prefix + traversal
    "aabbccdd-0000-0000-0000-000000000000/../../../etc/passwd",
    # Script injection
    "<script>alert(1)</script>",
    # Empty string
    "",
    # Just dots
    ".....",
]


# ---------------------------------------------------------------------------
# Storage (collections)
# ---------------------------------------------------------------------------


class TestStoragePathTraversal:
    """Ensure _path_for() in storage.py rejects all non-UUID inputs."""

    def test_valid_uuid_accepted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A proper UUID v4 string must be accepted — baseline sanity."""
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        valid_id = str(uuid.uuid4())
        path = storage._path_for(valid_id)
        # Must be inside the collections dir, not above it
        assert str(path).startswith(str(tmp_path))
        assert ".." not in str(path)

    @pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
    def test_non_uuid_collection_id_raises(
        self, payload: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_path_for() must raise ValueError for any non-UUID collection_id.

        Attack: collection_id = '../../../etc/passwd' would write/read
        outside ~/.theridion/collections/ if UUID validation were absent.
        """
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        with pytest.raises((ValueError, AttributeError)):
            storage._path_for(payload)

    @pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
    def test_get_with_traversal_returns_none_or_raises(
        self, payload: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """storage.get() must not return file contents for traversal payloads.

        Expected: ValueError (uuid parse fails) or None (not found).
        Must NOT open a file outside the storage root.
        """
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        try:
            result = storage.get(payload)
            assert result is None, f"Expected None for payload {payload!r}, got {result}"
        except (ValueError, AttributeError):
            pass  # UUID parse rejection — correct

    @pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
    def test_delete_collection_traversal_safe(
        self, payload: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """storage.delete_collection() must not delete files via traversal."""
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        try:
            result = storage.delete_collection(payload)
            assert result is False, f"Expected False for payload {payload!r}"
        except (ValueError, AttributeError):
            pass

    def test_resolved_path_stays_under_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even for valid UUIDs, the resolved path must remain under storage root.

        This is the defense-in-depth check: after uuid.UUID() validation,
        the resulting path should never point outside ~/.theridion/collections/.
        """
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        for _ in range(10):
            valid_id = str(uuid.uuid4())
            path = storage._path_for(valid_id)
            resolved = path.resolve()
            root_resolved = (tmp_path / "collections").resolve()
            assert str(resolved).startswith(str(root_resolved)), (
                f"Path {resolved} escaped storage root {root_resolved}"
            )


# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------


class TestEnvironmentsPathTraversal:
    """Same guarantees for environments._path_for()."""

    def test_valid_uuid_accepted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        valid_id = str(uuid.uuid4())
        path = environments._path_for(valid_id)
        assert str(path).startswith(str(tmp_path))
        assert ".." not in str(path)

    @pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
    def test_non_uuid_env_id_raises(
        self, payload: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """environments._path_for() must raise ValueError for traversal payloads."""
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        with pytest.raises((ValueError, AttributeError)):
            environments._path_for(payload)

    @pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
    def test_get_with_traversal_returns_none_or_raises(
        self, payload: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """environments.get() must not expose files via traversal IDs."""
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        try:
            result = environments.get(payload)
            assert result is None, f"Expected None for payload {payload!r}, got {result}"
        except (ValueError, AttributeError):
            pass

    @pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
    def test_delete_env_traversal_safe(
        self, payload: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """environments.delete() must not delete arbitrary files via traversal."""
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        try:
            result = environments.delete(payload)
            assert result is False, f"Expected False for payload {payload!r}"
        except (ValueError, AttributeError):
            pass

    def test_resolved_path_stays_under_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Resolved env path must stay within the environments subdirectory."""
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        for _ in range(10):
            valid_id = str(uuid.uuid4())
            path = environments._path_for(valid_id)
            resolved = path.resolve()
            root_resolved = (tmp_path / "environments").resolve()
            assert str(resolved).startswith(str(root_resolved)), (
                f"Path {resolved} escaped env root {root_resolved}"
            )


# ---------------------------------------------------------------------------
# Regression: the UUID guard is the only path-construction gate
# (no secondary .resolve() + is_relative_to() check needed today,
#  but document the invariant so a future refactor doesn't regress it)
# ---------------------------------------------------------------------------


def test_uuid_guard_is_strict_format() -> None:
    """uuid.UUID() rejects any string that isn't a canonical UUID.

    Verify a few representative formats that should fail, independent
    of the storage module, to document the assumption.
    """
    bad = [
        "../etc/passwd",
        "00000000-0000-0000-0000-00000000000G",  # invalid hex
        "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "",
        "not-a-uuid",
    ]
    for b in bad:
        with pytest.raises(ValueError, match=re.compile("badly formed|invalid|", re.I)):
            uuid.UUID(b)


def test_uuid_guard_accepts_valid_uuids() -> None:
    """uuid.UUID() accepts all four valid UUID forms used in practice."""
    valid = [
        "550e8400-e29b-41d4-a716-446655440000",  # v4 canonical
        "550E8400-E29B-41D4-A716-446655440000",  # uppercase
        str(uuid.uuid4()),  # fresh v4
        str(uuid.uuid5(uuid.NAMESPACE_DNS, "theridion.app")),  # v5
    ]
    for v in valid:
        u = uuid.UUID(v)
        assert u is not None
