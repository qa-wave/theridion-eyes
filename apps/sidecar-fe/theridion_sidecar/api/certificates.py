"""Client certificate inspection and chain verification endpoints.

Supports mTLS workflows: inspect PEM/DER certificates, verify chains,
and list system CA certificates.
"""

from __future__ import annotations

import ssl
import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/certs", tags=["certificates"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CertInfo(BaseModel):
    subject: dict[str, str] = Field(default_factory=dict)
    issuer: dict[str, str] = Field(default_factory=dict)
    not_before: str
    not_after: str
    serial: str
    fingerprint_sha256: str
    is_expired: bool
    extensions: list[str] = Field(default_factory=list)


class InspectRequest(BaseModel):
    cert_path: str = Field(..., min_length=1)


class VerifyChainRequest(BaseModel):
    cert_path: str = Field(..., min_length=1)
    ca_bundle_path: str = Field(..., min_length=1)


class VerifyChainResponse(BaseModel):
    valid: bool
    error: str | None = None


class SystemCertEntry(BaseModel):
    subject: str
    fingerprint_sha256: str


class SystemCertsResponse(BaseModel):
    certificates: list[SystemCertEntry] = Field(default_factory=list)
    count: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_cert(path_str: str) -> x509.Certificate:
    """Load a certificate from a file path (PEM or DER)."""
    p = Path(path_str).expanduser().resolve()
    if not p.is_file():
        raise HTTPException(status_code=400, detail=f"file not found: {path_str}")
    data = p.read_bytes()
    # Try PEM first, fall back to DER.
    try:
        return x509.load_pem_x509_certificate(data)
    except Exception:
        pass
    try:
        return x509.load_der_x509_certificate(data)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"cannot parse certificate: {exc}"
        ) from exc


def _name_to_dict(name: x509.Name) -> dict[str, str]:
    """Convert an x509.Name to a flat dict of common attributes."""
    oid_map = {
        NameOID.COMMON_NAME: "CN",
        NameOID.ORGANIZATION_NAME: "O",
        NameOID.ORGANIZATIONAL_UNIT_NAME: "OU",
        NameOID.COUNTRY_NAME: "C",
        NameOID.STATE_OR_PROVINCE_NAME: "ST",
        NameOID.LOCALITY_NAME: "L",
        NameOID.EMAIL_ADDRESS: "EMAIL",
    }
    result: dict[str, str] = {}
    for attr in name:
        label = oid_map.get(attr.oid, attr.oid.dotted_string)
        result[label] = str(attr.value)
    return result


def _cert_info(cert: x509.Certificate) -> CertInfo:
    """Extract structured info from an x509 certificate."""
    now = datetime.datetime.now(datetime.timezone.utc)
    fp = cert.fingerprint(hashes.SHA256()).hex(":")
    extensions: list[str] = []
    for ext in cert.extensions:
        try:
            extensions.append(ext.oid._name)
        except Exception:
            extensions.append(ext.oid.dotted_string)
    return CertInfo(
        subject=_name_to_dict(cert.subject),
        issuer=_name_to_dict(cert.issuer),
        not_before=cert.not_valid_before_utc.isoformat(),
        not_after=cert.not_valid_after_utc.isoformat(),
        serial=format(cert.serial_number, "x"),
        fingerprint_sha256=fp,
        is_expired=now > cert.not_valid_after_utc,
        extensions=extensions,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/inspect", response_model=CertInfo)
async def inspect_cert(req: InspectRequest) -> CertInfo:
    """Inspect a certificate file and return structured details."""
    cert = _load_cert(req.cert_path)
    return _cert_info(cert)


@router.post("/verify-chain", response_model=VerifyChainResponse)
async def verify_chain(req: VerifyChainRequest) -> VerifyChainResponse:
    """Verify that a certificate chains to the given CA bundle."""
    cert_path = Path(req.cert_path).expanduser().resolve()
    ca_path = Path(req.ca_bundle_path).expanduser().resolve()

    if not cert_path.is_file():
        raise HTTPException(status_code=400, detail=f"cert file not found: {req.cert_path}")
    if not ca_path.is_file():
        raise HTTPException(status_code=400, detail=f"CA bundle not found: {req.ca_bundle_path}")

    try:
        # Use OpenSSL context to verify the chain.
        ctx = ssl.create_default_context(cafile=str(ca_path))
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED

        # Load the cert and verify it against the CA bundle using
        # cryptography's verification API.
        cert = _load_cert(req.cert_path)
        ca_data = ca_path.read_bytes()

        # Parse all CA certs from the bundle.
        ca_certs: list[x509.Certificate] = []
        try:
            # PEM bundle — may contain multiple certs.
            for pem_cert in _iter_pem_certs(ca_data):
                ca_certs.append(pem_cert)
        except Exception:
            # Single DER cert.
            ca_certs.append(x509.load_der_x509_certificate(ca_data))

        if not ca_certs:
            return VerifyChainResponse(valid=False, error="no CA certificates found in bundle")

        # Simple chain check: cert issuer matches a CA subject.
        issuer_match = any(
            cert.issuer == ca.subject for ca in ca_certs
        )
        if not issuer_match:
            return VerifyChainResponse(
                valid=False,
                error="certificate issuer does not match any CA in the bundle",
            )

        # Verify the signature using the issuing CA's public key.
        issuing_ca = next(ca for ca in ca_certs if ca.subject == cert.issuer)
        try:
            from cryptography.hazmat.primitives.asymmetric import ec, padding, utils
            pub = issuing_ca.public_key()
            if isinstance(pub, rsa.RSAPublicKey):
                pub.verify(
                    cert.signature,
                    cert.tbs_certificate_bytes,
                    padding.PKCS1v15(),
                    cert.signature_hash_algorithm,  # type: ignore[arg-type]
                )
            elif isinstance(pub, ec.EllipticCurvePublicKey):
                pub.verify(
                    cert.signature,
                    cert.tbs_certificate_bytes,
                    ec.ECDSA(cert.signature_hash_algorithm),  # type: ignore[arg-type]
                )
            else:
                # Ed25519, Ed448, etc — try generic verify.
                pub.verify(cert.signature, cert.tbs_certificate_bytes)  # type: ignore[union-attr]
        except Exception as exc:
            return VerifyChainResponse(valid=False, error=f"signature verification failed: {exc}")

        # Check expiry.
        now = datetime.datetime.now(datetime.timezone.utc)
        if now > cert.not_valid_after_utc:
            return VerifyChainResponse(valid=False, error="certificate is expired")

        return VerifyChainResponse(valid=True)

    except HTTPException:
        raise
    except Exception as exc:
        return VerifyChainResponse(valid=False, error=str(exc))


def _iter_pem_certs(data: bytes) -> list[x509.Certificate]:
    """Parse all PEM certificates from a byte buffer."""
    certs: list[x509.Certificate] = []
    # Split on PEM markers.
    pem_marker = b"-----BEGIN CERTIFICATE-----"
    parts = data.split(pem_marker)
    for part in parts[1:]:
        pem = pem_marker + part
        end_idx = pem.find(b"-----END CERTIFICATE-----")
        if end_idx != -1:
            pem = pem[: end_idx + len(b"-----END CERTIFICATE-----")]
            certs.append(x509.load_pem_x509_certificate(pem))
    return certs


@router.get("/system", response_model=SystemCertsResponse)
async def list_system_certs() -> SystemCertsResponse:
    """List system CA certificates available on this platform."""
    entries: list[SystemCertEntry] = []
    try:
        # ssl.create_default_context loads the system trust store.
        ctx = ssl.create_default_context()
        der_certs = ctx.get_ca_certs(binary_form=True)
        for der_data in der_certs:
            try:
                cert = x509.load_der_x509_certificate(der_data)
                cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
                subject_str = cn[0].value if cn else cert.subject.rfc4514_string()
                fp = cert.fingerprint(hashes.SHA256()).hex(":")
                entries.append(SystemCertEntry(subject=str(subject_str), fingerprint_sha256=fp))
            except Exception:
                continue
    except Exception:
        pass
    return SystemCertsResponse(certificates=entries, count=len(entries))
