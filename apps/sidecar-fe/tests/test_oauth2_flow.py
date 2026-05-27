"""Tests for OAuth2 endpoints: PKCE, client_credentials, token reuse, password grant."""

from __future__ import annotations

import base64
import hashlib
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from theridion_sidecar.api.oauth2 import generate_pkce, _cb
from theridion_sidecar.main import create_app

# ---------------------------------------------------------------------------
# Shared mock helper
# ---------------------------------------------------------------------------


def _make_mock_client(json_body: dict, status_code: int = 200):
    """Return an AsyncMock for httpx.AsyncClient whose post() returns the given body."""
    mock_response = httpx.Response(status_code, json=json_body)
    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=mock_response)
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=None)
    return mock_instance


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """OAuth2 test client with auth token and isolated home directory."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    import theridion_sidecar.main as _main
    monkeypatch.setattr(_main, "_SIDECAR_TOKEN", "test-token-fixture")
    app = _main.create_app()
    tc = TestClient(app)
    tc.headers["X-Theridion-Token"] = "test-token-fixture"
    yield tc


@pytest.fixture(autouse=True)
def reset_callback_state():
    """Reset callback server state between tests."""
    _cb.code = None
    _cb.state = None
    _cb.error = None
    _cb.received = False
    _cb.server = None
    _cb.thread = None
    yield
    # Ensure callback server is stopped after each test
    if _cb.server is not None:
        try:
            _cb.server.server_close()
        except Exception:
            pass
        _cb.server = None
    _cb.received = True  # Signal thread to stop
    import time
    # Give thread a moment to exit, then reset state cleanly
    if _cb.thread is not None and _cb.thread.is_alive():
        _cb.thread.join(timeout=2)
    _cb.thread = None
    _cb.received = False
    _cb.code = None
    _cb.state = None
    _cb.error = None


class TestPKCEGeneration:
    """Test PKCE code_verifier and code_challenge generation."""

    def test_generate_pkce_returns_tuple(self):
        verifier, challenge = generate_pkce()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)

    def test_verifier_length(self):
        verifier, _ = generate_pkce()
        # token_urlsafe(96) produces 128 chars
        assert 43 <= len(verifier) <= 128

    def test_challenge_is_s256_of_verifier(self):
        verifier, challenge = generate_pkce()
        expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected_challenge = base64.urlsafe_b64encode(expected_digest).rstrip(b"=").decode("ascii")
        assert challenge == expected_challenge

    def test_unique_per_call(self):
        v1, c1 = generate_pkce()
        v2, c2 = generate_pkce()
        assert v1 != v2
        assert c1 != c2


class TestAuthorizeUrl:
    """Test the authorize-url endpoint."""

    def test_basic_authorize_url(self, client: TestClient):
        resp = client.post("/api/auth/oauth2/authorize-url", json={
            "auth_url": "https://accounts.google.com/o/oauth2/auth",
            "client_id": "my-client-id",
            "scope": "openid email",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "url" in data
        assert "state" in data
        assert data["code_verifier"] is not None
        assert data["code_challenge"] is not None
        # URL should contain PKCE params
        assert "code_challenge=" in data["url"]
        assert "code_challenge_method=S256" in data["url"]
        assert "client_id=my-client-id" in data["url"]

    def test_authorize_url_without_pkce(self, client: TestClient):
        resp = client.post("/api/auth/oauth2/authorize-url", json={
            "auth_url": "https://example.com/auth",
            "client_id": "test",
            "use_pkce": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code_verifier"] is None
        assert data["code_challenge"] is None
        assert "code_challenge" not in data["url"]

    def test_authorize_url_with_custom_state(self, client: TestClient):
        resp = client.post("/api/auth/oauth2/authorize-url", json={
            "auth_url": "https://example.com/auth",
            "client_id": "test",
            "state": "my-custom-state",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "my-custom-state"
        assert "state=my-custom-state" in data["url"]

    def test_authorize_url_preserves_existing_params(self, client: TestClient):
        resp = client.post("/api/auth/oauth2/authorize-url", json={
            "auth_url": "https://example.com/auth?audience=my-api",
            "client_id": "test",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "audience=my-api" in data["url"]


class TestCallbackServer:
    """Test callback server start/stop/poll."""

    def test_start_callback_server(self, client: TestClient):
        resp = client.post("/api/auth/oauth2/callback-server/start", json={
            "port": 19876,
            "timeout_seconds": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["port"] == 19876
        assert data["status"] == "listening"
        # Clean up
        client.post("/api/auth/oauth2/callback-server/stop")

    def test_poll_waiting(self, client: TestClient):
        client.post("/api/auth/oauth2/callback-server/start", json={
            "port": 19877,
            "timeout_seconds": 5,
        })
        resp = client.get("/api/auth/oauth2/callback-server/result")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "waiting"
        # Clean up
        client.post("/api/auth/oauth2/callback-server/stop")

    def test_stop_callback_server(self, client: TestClient):
        client.post("/api/auth/oauth2/callback-server/start", json={
            "port": 19878,
            "timeout_seconds": 10,
        })
        resp = client.post("/api/auth/oauth2/callback-server/stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

    def test_poll_not_running(self, client: TestClient):
        resp = client.get("/api/auth/oauth2/callback-server/result")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_running"

    def test_double_start_returns_409(self, client: TestClient):
        client.post("/api/auth/oauth2/callback-server/start", json={
            "port": 19879,
            "timeout_seconds": 10,
        })
        resp = client.post("/api/auth/oauth2/callback-server/start", json={
            "port": 19880,
            "timeout_seconds": 10,
        })
        assert resp.status_code == 409
        # Clean up
        client.post("/api/auth/oauth2/callback-server/stop")


class TestTokenExchange:
    """Test token exchange with a mocked token endpoint."""

    def test_exchange_success(self, client: TestClient):
        mock_response = httpx.Response(
            200,
            json={
                "access_token": "test-access-token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": "test-refresh-token",
                "scope": "openid email",
            },
        )
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_instance

            resp = client.post("/api/auth/oauth2/token", json={
                "token_url": "https://example.com/token",
                "client_id": "my-client",
                "client_secret": "my-secret",
                "code": "auth-code-123",
                "redirect_uri": "http://localhost:9876/oauth2/callback",
                "code_verifier": "test-verifier",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "test-access-token"
        assert data["refresh_token"] == "test-refresh-token"
        assert data["expires_in"] == 3600

    def test_exchange_error_response(self, client: TestClient):
        mock_response = httpx.Response(
            400,
            json={"error": "invalid_grant"},
            text='{"error": "invalid_grant"}',
        )
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_instance

            resp = client.post("/api/auth/oauth2/token", json={
                "token_url": "https://example.com/token",
                "client_id": "my-client",
                "code": "bad-code",
            })

        assert resp.status_code == 400


class TestTokenRefresh:
    """Test token refresh with a mocked token endpoint."""

    def test_refresh_success(self, client: TestClient):
        mock_response = httpx.Response(
            200,
            json={
                "access_token": "new-access-token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": "new-refresh-token",
            },
        )
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_instance

            resp = client.post("/api/auth/oauth2/refresh", json={
                "token_url": "https://example.com/token",
                "refresh_token": "old-refresh-token",
                "client_id": "my-client",
                "client_secret": "my-secret",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "new-access-token"
        assert data["refresh_token"] == "new-refresh-token"
        assert data["expires_in"] == 3600

    def test_refresh_without_secret(self, client: TestClient):
        mock_response = httpx.Response(
            200,
            json={
                "access_token": "refreshed-token",
                "token_type": "Bearer",
                "expires_in": 1800,
            },
        )
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_instance

            resp = client.post("/api/auth/oauth2/refresh", json={
                "token_url": "https://example.com/token",
                "refresh_token": "my-refresh-token",
                "client_id": "public-client",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "refreshed-token"

    def test_refresh_error(self, client: TestClient):
        mock_response = httpx.Response(
            401,
            json={"error": "invalid_grant"},
            text='{"error": "invalid_grant"}',
        )
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_instance

            resp = client.post("/api/auth/oauth2/refresh", json={
                "token_url": "https://example.com/token",
                "refresh_token": "expired-token",
                "client_id": "my-client",
            })

        assert resp.status_code == 401


class TestRefreshRotation:
    """Test that refresh token rotation (RFC 6749 §6) is handled correctly."""

    def test_rotation_new_refresh_token_is_returned(self, client: TestClient):
        """When server returns a new refresh_token, the new one is in the response."""
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_client({
                "access_token": "new-access",
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": "rotated-refresh-token",
            })
            resp = client.post("/api/auth/oauth2/refresh", json={
                "token_url": "https://example.com/token",
                "refresh_token": "old-refresh-token",
                "client_id": "my-client",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["refresh_token"] == "rotated-refresh-token"

    def test_rotation_fallback_to_original_when_server_omits_refresh(
        self, client: TestClient
    ):
        """When server does NOT return refresh_token, the original is preserved."""
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_client({
                "access_token": "new-access",
                "token_type": "Bearer",
                "expires_in": 3600,
                # no refresh_token in response
            })
            resp = client.post("/api/auth/oauth2/refresh", json={
                "token_url": "https://example.com/token",
                "refresh_token": "original-refresh",
                "client_id": "my-client",
            })

        assert resp.status_code == 200
        data = resp.json()
        # Original refresh token should be preserved (rotation: fall-back)
        assert data["refresh_token"] == "original-refresh"


class TestClientCredentials:
    """Tests for the Client Credentials grant."""

    def test_basic_client_credentials(self, client: TestClient):
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_client({
                "access_token": "cc-access-token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "read write",
            })
            resp = client.post("/api/auth/oauth2/client-credentials", json={
                "token_url": "https://example.com/token",
                "client_id": "service-client",
                "client_secret": "super-secret",
                "scope": "read write",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "cc-access-token"
        assert data["expires_in"] == 3600
        assert data["expires_at"] is not None

    def test_client_credentials_expires_at_is_future(self, client: TestClient):
        """expires_at must be in the future."""
        before = time.time()
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_client({
                "access_token": "tok",
                "token_type": "Bearer",
                "expires_in": 3600,
            })
            resp = client.post("/api/auth/oauth2/client-credentials", json={
                "token_url": "https://example.com/token",
                "client_id": "svc",
                "client_secret": "secret",
            })
        after = time.time()

        assert resp.status_code == 200
        expires_at = resp.json()["expires_at"]
        assert before + 3600 <= expires_at <= after + 3600

    def test_client_credentials_basic_auth(self, client: TestClient):
        """When use_basic_auth=True, credentials must not appear in form body."""
        captured: dict = {}

        async def _fake_post(url, *, data=None, headers=None, **kwargs):
            captured["headers"] = headers or {}
            captured["data"] = data or {}
            return httpx.Response(200, json={"access_token": "tok", "token_type": "Bearer"})

        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.post = _fake_post
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_instance

            resp = client.post("/api/auth/oauth2/client-credentials", json={
                "token_url": "https://example.com/token",
                "client_id": "svc",
                "client_secret": "svc-secret",
                "use_basic_auth": True,
            })

        assert resp.status_code == 200
        assert "Authorization" in captured["headers"]
        assert captured["headers"]["Authorization"].startswith("Basic ")
        assert "client_id" not in captured["data"]
        assert "client_secret" not in captured["data"]

    def test_client_credentials_extra_params(self, client: TestClient):
        """Extra params (e.g. audience) are forwarded in the form body."""
        captured: dict = {}

        async def _fake_post(url, *, data=None, headers=None, **kwargs):
            captured["data"] = data or {}
            return httpx.Response(200, json={"access_token": "tok", "token_type": "Bearer"})

        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.post = _fake_post
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_instance

            resp = client.post("/api/auth/oauth2/client-credentials", json={
                "token_url": "https://example.com/token",
                "client_id": "svc",
                "client_secret": "svc-secret",
                "extra_params": {"audience": "https://api.example.com"},
            })

        assert resp.status_code == 200
        assert captured["data"].get("audience") == "https://api.example.com"

    def test_client_credentials_error_response(self, client: TestClient):
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_client(
                {"error": "invalid_client"}, status_code=401
            )
            resp = client.post("/api/auth/oauth2/client-credentials", json={
                "token_url": "https://example.com/token",
                "client_id": "bad-svc",
                "client_secret": "wrong",
            })
        assert resp.status_code == 401

    def test_client_credentials_no_expires_in(self, client: TestClient):
        """If token endpoint omits expires_in, expires_at should be None."""
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_client({
                "access_token": "tok",
                "token_type": "Bearer",
                # no expires_in
            })
            resp = client.post("/api/auth/oauth2/client-credentials", json={
                "token_url": "https://example.com/token",
                "client_id": "svc",
                "client_secret": "secret",
            })
        assert resp.status_code == 200
        assert resp.json()["expires_at"] is None


class TestTokenReuse:
    """Tests for the token-reuse / auto-refresh endpoint."""

    def test_valid_token_returned_as_is(self, client: TestClient):
        future = time.time() + 3600
        resp = client.post("/api/auth/oauth2/token-reuse", json={
            "access_token": "my-token",
            "expires_at": future,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "valid"
        assert data["access_token"] == "my-token"

    def test_expired_token_no_refresh_returns_expired(self, client: TestClient):
        past = time.time() - 100
        resp = client.post("/api/auth/oauth2/token-reuse", json={
            "access_token": "old-token",
            "expires_at": past,
            # no refresh_token / token_url
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "expired"

    def test_expired_token_with_refresh_is_refreshed(self, client: TestClient):
        past = time.time() - 100
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_client({
                "access_token": "fresh-token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": "new-rt",
            })
            resp = client.post("/api/auth/oauth2/token-reuse", json={
                "access_token": "old-token",
                "refresh_token": "old-rt",
                "expires_at": past,
                "token_url": "https://example.com/token",
                "client_id": "my-client",
                "client_secret": "secret",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "refreshed"
        assert data["access_token"] == "fresh-token"
        assert data["refresh_token"] == "new-rt"

    def test_unknown_status_for_token_without_expiry(self, client: TestClient):
        resp = client.post("/api/auth/oauth2/token-reuse", json={
            "access_token": "unknown-expiry-token",
            # expires_at not set
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "unknown"

    def test_empty_access_token_is_expired(self, client: TestClient):
        future = time.time() + 3600
        resp = client.post("/api/auth/oauth2/token-reuse", json={
            "access_token": "",
            "expires_at": future,
        })
        assert resp.status_code == 200
        # No access_token at all → can't be valid
        assert resp.json()["status"] == "expired"

    def test_expiry_buffer_respected(self, client: TestClient):
        """Token that expires within buffer window is treated as expired."""
        # expires 30 s from now — within default 60 s buffer
        near_future = time.time() + 30
        resp = client.post("/api/auth/oauth2/token-reuse", json={
            "access_token": "almost-expired",
            "expires_at": near_future,
            "expiry_buffer_seconds": 60,
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "expired"

    def test_expired_token_refresh_fails_gracefully(self, client: TestClient):
        """If refresh call fails, status is 'expired' with message."""
        past = time.time() - 100
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_client(
                {"error": "invalid_grant"}, status_code=400
            )
            resp = client.post("/api/auth/oauth2/token-reuse", json={
                "access_token": "old",
                "refresh_token": "bad-rt",
                "expires_at": past,
                "token_url": "https://example.com/token",
                "client_id": "my-client",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "expired"
        assert "refresh failed" in data["message"]


class TestPasswordGrant:
    """Tests for the (deprecated) Resource Owner Password Credentials grant."""

    def test_password_grant_success(self, client: TestClient):
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_client({
                "access_token": "password-grant-token",
                "token_type": "Bearer",
                "expires_in": 1800,
                "refresh_token": "pwd-rt",
            })
            resp = client.post("/api/auth/oauth2/password", json={
                "token_url": "https://legacy.example.com/token",
                "username": "user@example.com",
                "password": "hunter2",
                "client_id": "legacy-app",
                "scope": "profile",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "password-grant-token"
        assert data["refresh_token"] == "pwd-rt"

    def test_password_grant_error(self, client: TestClient):
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_client(
                {"error": "invalid_grant"}, status_code=401
            )
            resp = client.post("/api/auth/oauth2/password", json={
                "token_url": "https://legacy.example.com/token",
                "username": "bad-user",
                "password": "wrong",
                "client_id": "legacy-app",
            })
        assert resp.status_code == 401

    def test_password_grant_with_client_secret(self, client: TestClient):
        with patch("theridion_sidecar.api.oauth2.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_client({
                "access_token": "tok",
                "token_type": "Bearer",
            })
            resp = client.post("/api/auth/oauth2/password", json={
                "token_url": "https://legacy.example.com/token",
                "username": "admin",
                "password": "adminpass",
                "client_id": "conf-client",
                "client_secret": "conf-secret",
            })
        assert resp.status_code == 200
