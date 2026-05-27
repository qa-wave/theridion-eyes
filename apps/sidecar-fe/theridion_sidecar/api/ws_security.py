"""WS-Security: add OASIS security headers to SOAP envelopes.

Supports:
  - UsernameToken  (PasswordText + PasswordDigest)
  - Timestamp      (Created + Expires, configurable TTL)
  - BinarySecurityToken  (X.509v3 certificate embed)
  - XML Signature  (RSA-SHA256 / RSA-SHA1 via zeep.wsse.MemorySignature /
                    BinarySignature; requires xmlsec native lib)
  - Combined       (Signature + Timestamp in one header, a.k.a.
                    TimestampSignature pattern)

The module has two distinct execution paths:

1. Raw-envelope path  (POST /api/soap/ws-security/execute)
   Takes a pre-built SOAP envelope XML string, injects the <wsse:Security>
   header using standard-library ElementTree, and POSTs it via httpx.

2. Zeep-integration path  (used by soap.py /execute endpoint)
   Returns a configured zeep.wsse plugin object that zeep applies
   transparently when building and sending the envelope.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/soap/ws-security", tags=["ws-security"])

# ---------------------------------------------------------------------------
# OASIS WS-Security namespace URIs
# ---------------------------------------------------------------------------

WSSE = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-wssecurity-secext-1.0.xsd"
)
WSU = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-wssecurity-utility-1.0.xsd"
)
SOAP = "http://schemas.xmlsoap.org/soap/envelope/"

PASSWORD_TEXT_TYPE = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-username-token-profile-1.0#PasswordText"
)
PASSWORD_DIGEST_TYPE = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-username-token-profile-1.0#PasswordDigest"
)
NONCE_ENCODING = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-soap-message-security-1.0#Base64Binary"
)
X509_VALUE_TYPE = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-x509-token-profile-1.0#X509v3"
)

# ---------------------------------------------------------------------------
# Path traversal guard
# ---------------------------------------------------------------------------

def _build_allowed_dirs() -> tuple[str, ...]:
    dirs = [str(Path.home()), "/tmp"]  # noqa: S108
    # On macOS /tmp is a symlink to /private/var/folders/… so we must
    # also include the resolved path, otherwise pytest's tmp_path fails.
    for d in list(dirs):
        resolved = str(Path(d).resolve())
        if resolved not in dirs:
            dirs.append(resolved)
    # Include the system temp directory (platform-independent).
    import tempfile

    system_tmp = str(Path(tempfile.gettempdir()).resolve())
    if system_tmp not in dirs:
        dirs.append(system_tmp)
    return tuple(dirs)


_ALLOWED_BASE_DIRS: tuple[str, ...] = _build_allowed_dirs()


def _safe_resolve_path(p: str) -> Path:
    """Resolve *p* to an absolute path and verify it sits within an allowed
    directory tree.  Raises ValueError if the path escapes the whitelist.

    The whitelist is the user's home directory and /tmp — sufficient for
    real usage (certs stored in ~/.ssl) and for tests (tmp_path).
    """
    resolved = Path(p).expanduser().resolve()
    for base in _ALLOWED_BASE_DIRS:
        try:
            resolved.relative_to(base)
            return resolved
        except ValueError:
            continue
    raise ValueError(
        f"Key/cert path {p!r} is outside the allowed directories "
        f"({', '.join(_ALLOWED_BASE_DIRS)})"
    )


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class WsSecurityConfig(BaseModel):
    """Configuration for a single WS-Security mode.

    ``type`` selects which mechanism to apply:
    - ``UsernameToken``       — username/password credential in header
    - ``Timestamp``           — Created + Expires only (no credential)
    - ``BinarySecurityToken`` — X.509 cert embed (no actual signing)
    - ``Signature``           — XML Signature, key + cert loaded from files
    - ``MemorySignature``     — XML Signature, key + cert supplied as PEM bytes
    """

    type: Literal[
        "UsernameToken", "Timestamp", "BinarySecurityToken",
        "Signature", "MemorySignature",
    ]

    # UsernameToken fields
    username: str | None = None
    password: str | None = None
    password_type: Literal["PasswordText", "PasswordDigest"] = "PasswordText"
    add_nonce: bool = True
    add_created: bool = True
    add_timestamp: bool = True
    ttl_seconds: int = Field(default=300, ge=1, le=86400)

    # BinarySecurityToken field (base64-encoded DER or PEM cert)
    certificate_base64: str | None = None

    # Signature (file-based) fields
    key_file_path: str | None = None
    cert_file_path: str | None = None
    key_file_password: str | None = None  # never logged

    # MemorySignature fields (PEM content as string)
    key_pem: str | None = None
    cert_pem: str | None = None

    # Common signature algorithm options
    signature_algorithm: Literal["RSA-SHA256", "RSA-SHA1"] = "RSA-SHA256"

    @field_validator("key_file_path", "cert_file_path", mode="before")
    @classmethod
    def _guard_paths(cls, v: str | None) -> str | None:
        if v is None:
            return None
        _safe_resolve_path(v)  # raises ValueError on traversal
        return v


class WsSecurityRequest(BaseModel):
    url: str
    soap_action: str | None = None
    envelope_xml: str
    security: WsSecurityConfig
    headers: dict[str, str] = Field(default_factory=dict)


class WsSecurityResponse(BaseModel):
    ok: bool
    status: int
    response_xml: str
    secured_envelope: str
    error: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _sig_algorithm(name: str) -> Any:
    """Return the xmlsec Transform constant for the requested algorithm."""
    try:
        import xmlsec  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "XML Signature requires the 'xmlsec' package. "
            "Install with: uv add 'zeep[xmlsec]'"
        ) from exc

    mapping: dict[str, Any] = {
        "RSA-SHA256": xmlsec.constants.TransformRsaSha256,
        "RSA-SHA1": xmlsec.constants.TransformRsaSha1,
    }
    if name not in mapping:
        raise ValueError(f"Unsupported signature algorithm: {name!r}")
    return mapping[name]


# ---------------------------------------------------------------------------
# ElementTree-based security header builders (raw-envelope path)
# ---------------------------------------------------------------------------


def _build_username_token(cfg: WsSecurityConfig) -> ET.Element:
    """Build <wsse:UsernameToken>."""
    token = ET.Element(f"{{{WSSE}}}UsernameToken")
    ET.SubElement(token, f"{{{WSSE}}}Username").text = cfg.username or ""

    password_el = ET.SubElement(token, f"{{{WSSE}}}Password")

    created_str = _utc_now_iso() if cfg.add_created else ""
    nonce_bytes = uuid.uuid4().bytes
    nonce_b64 = base64.b64encode(nonce_bytes).decode()

    if cfg.password_type == "PasswordDigest":
        # Base64( SHA-1( nonce + created + password ) )
        raw = (
            nonce_bytes
            + created_str.encode("utf-8")
            + (cfg.password or "").encode("utf-8")
        )
        digest = base64.b64encode(hashlib.sha1(raw).digest()).decode()  # noqa: S324
        password_el.text = digest
        password_el.set("Type", PASSWORD_DIGEST_TYPE)
    else:
        password_el.text = cfg.password or ""
        password_el.set("Type", PASSWORD_TEXT_TYPE)

    if cfg.add_nonce:
        nonce_el = ET.SubElement(token, f"{{{WSSE}}}Nonce")
        nonce_el.text = nonce_b64
        nonce_el.set("EncodingType", NONCE_ENCODING)

    if cfg.add_created:
        ET.SubElement(token, f"{{{WSU}}}Created").text = created_str

    return token


def _build_timestamp(ttl_seconds: int) -> ET.Element:
    """Build <wsu:Timestamp>."""
    now = datetime.now(timezone.utc)
    ts = ET.Element(f"{{{WSU}}}Timestamp")
    ET.SubElement(ts, f"{{{WSU}}}Created").text = (
        now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    )
    expires = now + timedelta(seconds=ttl_seconds)
    ET.SubElement(ts, f"{{{WSU}}}Expires").text = (
        expires.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    )
    return ts


def _build_binary_security_token(cert_b64: str) -> ET.Element:
    """Build <wsse:BinarySecurityToken> for X.509v3."""
    bst = ET.Element(f"{{{WSSE}}}BinarySecurityToken")
    bst.set("EncodingType", NONCE_ENCODING)
    bst.set("ValueType", X509_VALUE_TYPE)
    bst.text = cert_b64
    return bst


def build_security_header(cfg: WsSecurityConfig) -> ET.Element:
    """Build the complete <wsse:Security> element (ElementTree-based)."""
    sec = ET.Element(f"{{{WSSE}}}Security")
    sec.set(f"{{{SOAP}}}mustUnderstand", "1")

    if cfg.type == "UsernameToken":
        if cfg.add_timestamp:
            sec.append(_build_timestamp(cfg.ttl_seconds))
        sec.append(_build_username_token(cfg))
    elif cfg.type == "Timestamp":
        sec.append(_build_timestamp(cfg.ttl_seconds))
    elif cfg.type == "BinarySecurityToken":
        if cfg.add_timestamp:
            sec.append(_build_timestamp(cfg.ttl_seconds))
        sec.append(_build_binary_security_token(cfg.certificate_base64 or ""))
    # Signature / MemorySignature for raw-envelope path: we embed a
    # BinarySecurityToken so the recipient can identify the key, but
    # actual cryptographic signing requires zeep's lxml-based pipeline.
    # Return a header with the cert so the UI can show something useful.
    elif cfg.type in ("Signature", "MemorySignature"):
        sec.append(_build_timestamp(cfg.ttl_seconds))
        cert_b64 = _load_cert_b64(cfg)
        if cert_b64:
            sec.append(_build_binary_security_token(cert_b64))

    return sec


def _load_cert_b64(cfg: WsSecurityConfig) -> str:
    """Load certificate PEM and return base64-encoded content for embedding."""
    try:
        if cfg.type == "Signature" and cfg.cert_file_path:
            p = _safe_resolve_path(cfg.cert_file_path)
            return base64.b64encode(p.read_bytes()).decode()
        elif cfg.type == "MemorySignature" and cfg.cert_pem:
            return base64.b64encode(cfg.cert_pem.encode()).decode()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Envelope injection (raw-envelope path)
# ---------------------------------------------------------------------------

# Register namespace prefixes so serialised XML is human-friendly.
ET.register_namespace("wsse", WSSE)
ET.register_namespace("wsu", WSU)
ET.register_namespace("soap", SOAP)
ET.register_namespace("soapenv", SOAP)


def inject_security(envelope_xml: str, cfg: WsSecurityConfig) -> str:
    """Parse a SOAP envelope, inject a <wsse:Security> header, return XML.

    Note: For Signature / MemorySignature types, this path embeds a
    BinarySecurityToken to identify the key.  For full cryptographic XML
    Signature use ``build_zeep_wsse_plugin`` and let zeep sign the envelope.
    """
    root = ET.fromstring(envelope_xml)  # noqa: S314

    # Detect the SOAP namespace actually used in the document
    soap_ns = SOAP
    if root.tag.startswith("{"):
        soap_ns = root.tag.split("}")[0][1:]

    header = root.find(f"{{{soap_ns}}}Header")
    if header is None:
        header = ET.Element(f"{{{soap_ns}}}Header")
        root.insert(0, header)

    header.append(build_security_header(cfg))

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


# ---------------------------------------------------------------------------
# Zeep WSSE plugin factory (zeep-integration path)
# ---------------------------------------------------------------------------


def build_zeep_wsse_plugin(cfg: WsSecurityConfig) -> Any:
    """Return a zeep WSSE plugin object configured from *cfg*.

    The returned object implements the zeep `apply(envelope, headers)` /
    `verify(envelope)` protocol and can be assigned to ``client.wsse``.

    Raises ImportError if xmlsec is not installed (Signature types).
    Raises ValueError for invalid / unsafe paths or missing fields.
    """
    from zeep.wsse import UsernameToken  # always available
    from zeep.wsse.signature import MemorySignature  # requires xmlsec

    if cfg.type == "UsernameToken":
        return UsernameToken(
            username=cfg.username or "",
            password=cfg.password or "",
            use_digest=(cfg.password_type == "PasswordDigest"),
        )

    if cfg.type == "Timestamp":
        # zeep doesn't have a standalone Timestamp-only plugin; we use
        # UsernameToken with an empty credential as the carrier and rely
        # on the add_timestamp behaviour below instead.  Alternatively we
        # inject a raw Timestamp via a thin plugin shim.
        return _TimestampPlugin(cfg.ttl_seconds)

    if cfg.type == "Signature":
        if not cfg.key_file_path or not cfg.cert_file_path:
            raise ValueError(
                "Signature mode requires both key_file_path and cert_file_path"
            )
        key_path = _safe_resolve_path(cfg.key_file_path)
        cert_path = _safe_resolve_path(cfg.cert_file_path)
        key_data = key_path.read_bytes()
        cert_data = cert_path.read_bytes()
        password = (
            cfg.key_file_password.encode() if cfg.key_file_password else None
        )
        sig_method = _sig_algorithm(cfg.signature_algorithm)
        log.debug(
            "XML Signature plugin: cert=%s algorithm=%s",
            cert_path.name,
            cfg.signature_algorithm,
        )
        # Never log key data or password.
        return MemorySignature(
            key_data=key_data,
            cert_data=cert_data,
            password=password,
            signature_method=sig_method,
        )

    if cfg.type == "MemorySignature":
        if not cfg.key_pem or not cfg.cert_pem:
            raise ValueError(
                "MemorySignature mode requires both key_pem and cert_pem"
            )
        password = (
            cfg.key_file_password.encode() if cfg.key_file_password else None
        )
        sig_method = _sig_algorithm(cfg.signature_algorithm)
        return MemorySignature(
            key_data=cfg.key_pem.encode(),
            cert_data=cfg.cert_pem.encode(),
            password=password,
            signature_method=sig_method,
        )

    raise ValueError(f"Unsupported WS-Security type: {cfg.type!r}")


class _TimestampPlugin:
    """Minimal zeep-compatible WSSE plugin that inserts only a Timestamp."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds

    def apply(self, envelope: Any, headers: Any) -> tuple[Any, Any]:
        from lxml import etree  # type: ignore[import-untyped]

        # Locate or create the soap:Header
        body = envelope[0] if len(envelope) else None  # noqa: SIM210
        # envelope is lxml Element for the soap:Envelope
        nsmap = envelope.nsmap
        soap_ns_uri = next(
            (v for k, v in nsmap.items() if "envelope" in (v or "").lower()),
            SOAP,
        )
        header_tag = f"{{{soap_ns_uri}}}Header"
        header = envelope.find(header_tag)
        if header is None:
            header = etree.SubElement(envelope, header_tag)
            envelope.insert(0, header)

        wsse_ns = WSSE
        wsu_ns = WSU
        now = datetime.now(timezone.utc)
        ts_el = etree.SubElement(header, f"{{{wsse_ns}}}Security")
        ts_el.set(f"{{{soap_ns_uri}}}mustUnderstand", "1")
        inner_ts = etree.SubElement(ts_el, f"{{{wsu_ns}}}Timestamp")
        created_el = etree.SubElement(inner_ts, f"{{{wsu_ns}}}Created")
        created_el.text = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        expires_el = etree.SubElement(inner_ts, f"{{{wsu_ns}}}Expires")
        expires = now + timedelta(seconds=self._ttl)
        expires_el.text = expires.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        return envelope, headers

    def verify(self, envelope: Any) -> Any:
        return envelope


# ---------------------------------------------------------------------------
# HTTP route — raw-envelope path
# ---------------------------------------------------------------------------


@router.post("/execute", response_model=WsSecurityResponse)
async def ws_security_execute(body: WsSecurityRequest) -> WsSecurityResponse:
    """Inject WS-Security header into the envelope and POST to the endpoint.

    This path handles UsernameToken, Timestamp, and BinarySecurityToken
    without the need for file-system key access.  For Signature types the
    endpoint embeds the certificate but does not perform cryptographic
    signing — use the ``/api/soap/execute`` endpoint with the ``wsse``
    field for full XML Signature support.
    """
    try:
        secured = inject_security(body.envelope_xml, body.security)
    except ET.ParseError as exc:
        raise HTTPException(
            status_code=422, detail=f"Malformed SOAP envelope: {exc}"
        ) from exc

    send_headers: dict[str, str] = {
        "Content-Type": "text/xml; charset=utf-8",
        **body.headers,
    }
    if body.soap_action:
        send_headers["SOAPAction"] = body.soap_action

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                body.url, content=secured, headers=send_headers
            )
        return WsSecurityResponse(
            ok=resp.status_code < 500,
            status=resp.status_code,
            response_xml=resp.text,
            secured_envelope=secured,
        )
    except Exception as exc:
        return WsSecurityResponse(
            ok=False,
            status=0,
            response_xml="",
            secured_envelope=secured,
            error=str(exc),
        )
