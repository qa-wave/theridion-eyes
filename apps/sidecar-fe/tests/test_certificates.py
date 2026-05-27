"""Tests for the /api/certs endpoints — inspect, verify-chain, system."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers — generate self-signed certs on the fly
# ---------------------------------------------------------------------------

def _generate_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _build_cert(
    key: rsa.RSAPrivateKey,
    subject_cn: str,
    issuer_key: rsa.RSAPrivateKey | None = None,
    issuer_cn: str | None = None,
    not_before: datetime.datetime | None = None,
    not_after: datetime.datetime | None = None,
    is_ca: bool = False,
) -> x509.Certificate:
    """Build a certificate.  Self-signed when issuer_key is None."""
    now = datetime.datetime.now(datetime.timezone.utc)
    not_before = not_before or now - datetime.timedelta(days=1)
    not_after = not_after or now + datetime.timedelta(days=365)

    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject_cn)])
    issuer_name = (
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn or subject_cn)])
    )
    signing_key = issuer_key or key

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
    )
    if is_ca:
        builder = builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
    return builder.sign(signing_key, hashes.SHA256())


def _write_pem(cert: x509.Certificate, path: Path) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _write_key_pem(key: rsa.RSAPrivateKey, path: Path) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def ca_and_leaf(tmp_path: Path):
    """Generate a CA + leaf certificate pair."""
    ca_key = _generate_key()
    ca_cert = _build_cert(ca_key, "Test CA", is_ca=True)

    leaf_key = _generate_key()
    leaf_cert = _build_cert(
        leaf_key, "leaf.example.com",
        issuer_key=ca_key, issuer_cn="Test CA",
    )

    ca_path = tmp_path / "ca.pem"
    leaf_path = tmp_path / "leaf.pem"
    _write_pem(ca_cert, ca_path)
    _write_pem(leaf_cert, leaf_path)
    return ca_path, leaf_path, ca_cert, leaf_cert


@pytest.fixture()
def expired_cert(tmp_path: Path) -> Path:
    """Generate a self-signed expired certificate."""
    key = _generate_key()
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = _build_cert(
        key, "expired.example.com",
        not_before=now - datetime.timedelta(days=365),
        not_after=now - datetime.timedelta(days=1),
    )
    path = tmp_path / "expired.pem"
    _write_pem(cert, path)
    return path


@pytest.fixture()
def self_signed(tmp_path: Path) -> Path:
    """Generate a self-signed certificate."""
    key = _generate_key()
    cert = _build_cert(key, "self.example.com")
    path = tmp_path / "self.pem"
    _write_pem(cert, path)
    return path


# ---------------------------------------------------------------------------
# Tests — /api/certs/inspect
# ---------------------------------------------------------------------------

class TestInspect:
    def test_inspect_self_signed(self, client: TestClient, self_signed: Path) -> None:
        r = client.post("/api/certs/inspect", json={"cert_path": str(self_signed)})
        assert r.status_code == 200
        data = r.json()
        assert data["subject"]["CN"] == "self.example.com"
        assert data["issuer"]["CN"] == "self.example.com"
        assert data["is_expired"] is False
        assert len(data["fingerprint_sha256"]) > 0
        assert ":" in data["fingerprint_sha256"]

    def test_inspect_expired(self, client: TestClient, expired_cert: Path) -> None:
        r = client.post("/api/certs/inspect", json={"cert_path": str(expired_cert)})
        assert r.status_code == 200
        data = r.json()
        assert data["is_expired"] is True
        assert data["subject"]["CN"] == "expired.example.com"

    def test_inspect_leaf(self, client: TestClient, ca_and_leaf) -> None:
        _, leaf_path, _, _ = ca_and_leaf
        r = client.post("/api/certs/inspect", json={"cert_path": str(leaf_path)})
        assert r.status_code == 200
        data = r.json()
        assert data["subject"]["CN"] == "leaf.example.com"
        assert data["issuer"]["CN"] == "Test CA"
        assert data["is_expired"] is False

    def test_inspect_nonexistent(self, client: TestClient) -> None:
        r = client.post("/api/certs/inspect", json={"cert_path": "/tmp/no-such-cert.pem"})
        assert r.status_code == 400

    def test_inspect_invalid_file(self, client: TestClient, tmp_path: Path) -> None:
        bad = tmp_path / "bad.pem"
        bad.write_text("not a cert")
        r = client.post("/api/certs/inspect", json={"cert_path": str(bad)})
        assert r.status_code == 400

    def test_inspect_der_format(self, client: TestClient, tmp_path: Path) -> None:
        """Ensure DER-encoded certs can be inspected too."""
        key = _generate_key()
        cert = _build_cert(key, "der.example.com")
        der_path = tmp_path / "cert.der"
        der_path.write_bytes(cert.public_bytes(serialization.Encoding.DER))
        r = client.post("/api/certs/inspect", json={"cert_path": str(der_path)})
        assert r.status_code == 200
        assert r.json()["subject"]["CN"] == "der.example.com"


# ---------------------------------------------------------------------------
# Tests — /api/certs/verify-chain
# ---------------------------------------------------------------------------

class TestVerifyChain:
    def test_valid_chain(self, client: TestClient, ca_and_leaf) -> None:
        ca_path, leaf_path, _, _ = ca_and_leaf
        r = client.post("/api/certs/verify-chain", json={
            "cert_path": str(leaf_path),
            "ca_bundle_path": str(ca_path),
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert data["error"] is None

    def test_wrong_ca(self, client: TestClient, ca_and_leaf, tmp_path: Path) -> None:
        _, leaf_path, _, _ = ca_and_leaf
        # Generate a different CA.
        other_key = _generate_key()
        other_ca = _build_cert(other_key, "Other CA", is_ca=True)
        other_ca_path = tmp_path / "other_ca.pem"
        _write_pem(other_ca, other_ca_path)

        r = client.post("/api/certs/verify-chain", json={
            "cert_path": str(leaf_path),
            "ca_bundle_path": str(other_ca_path),
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert "issuer" in (data["error"] or "").lower() or "match" in (data["error"] or "").lower()

    def test_expired_leaf(self, client: TestClient, expired_cert: Path, tmp_path: Path) -> None:
        """Even if the issuer matches (self-signed), expired = invalid."""
        # Self-signed expired cert acts as its own CA for issuer match.
        r = client.post("/api/certs/verify-chain", json={
            "cert_path": str(expired_cert),
            "ca_bundle_path": str(expired_cert),
        })
        assert r.status_code == 200
        data = r.json()
        # Should fail because it's expired.
        assert data["valid"] is False
        assert "expired" in (data["error"] or "").lower()

    def test_nonexistent_cert(self, client: TestClient, ca_and_leaf) -> None:
        ca_path, _, _, _ = ca_and_leaf
        r = client.post("/api/certs/verify-chain", json={
            "cert_path": "/tmp/no-cert.pem",
            "ca_bundle_path": str(ca_path),
        })
        assert r.status_code == 400

    def test_nonexistent_ca(self, client: TestClient, ca_and_leaf) -> None:
        _, leaf_path, _, _ = ca_and_leaf
        r = client.post("/api/certs/verify-chain", json={
            "cert_path": str(leaf_path),
            "ca_bundle_path": "/tmp/no-ca.pem",
        })
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Tests — /api/certs/system
# ---------------------------------------------------------------------------

class TestSystemCerts:
    def test_list_system_certs(self, client: TestClient) -> None:
        r = client.get("/api/certs/system")
        assert r.status_code == 200
        data = r.json()
        assert "certificates" in data
        assert "count" in data
        assert data["count"] == len(data["certificates"])
        # On most systems there should be at least a few CA certs.
        assert data["count"] > 0
        # Spot-check structure.
        first = data["certificates"][0]
        assert "subject" in first
        assert "fingerprint_sha256" in first
