"""Tests for WS-Security header injection and envelope handling."""

from __future__ import annotations

import base64
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from theridion_sidecar.api.ws_security import (
    WSSE,
    WSU,
    SOAP,
    WsSecurityConfig,
    build_security_header,
    inject_security,
)

SAMPLE_ENVELOPE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
    "<soap:Header/>"
    "<soap:Body><TestOp><x>1</x></TestOp></soap:Body>"
    "</soap:Envelope>"
)

ENVELOPE_NO_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
    "<soap:Body><Ping/></soap:Body>"
    "</soap:Envelope>"
)


# ---- Unit tests for header builders ----------------------------------------


def test_username_token_text() -> None:
    cfg = WsSecurityConfig(
        type="UsernameToken",
        username="alice",
        password="secret",
        password_type="PasswordText",
        add_nonce=True,
        add_created=True,
        add_timestamp=False,
    )
    sec = build_security_header(cfg)
    xml_str = ET.tostring(sec, encoding="unicode")
    assert "alice" in xml_str
    assert "secret" in xml_str
    assert "PasswordText" in xml_str
    # Nonce and Created should be present
    assert "Nonce" in xml_str
    assert "Created" in xml_str


def test_username_token_digest() -> None:
    cfg = WsSecurityConfig(
        type="UsernameToken",
        username="bob",
        password="pass123",
        password_type="PasswordDigest",
        add_nonce=True,
        add_created=True,
        add_timestamp=False,
    )
    sec = build_security_header(cfg)
    xml_str = ET.tostring(sec, encoding="unicode")
    assert "bob" in xml_str
    assert "PasswordDigest" in xml_str
    # Password should NOT be plaintext
    assert "pass123" not in xml_str


def test_timestamp_element() -> None:
    cfg = WsSecurityConfig(type="Timestamp", ttl_seconds=600)
    sec = build_security_header(cfg)
    xml_str = ET.tostring(sec, encoding="unicode")
    assert "Created" in xml_str
    assert "Expires" in xml_str


def test_binary_security_token() -> None:
    cert_b64 = base64.b64encode(b"fake-cert-data").decode()
    cfg = WsSecurityConfig(
        type="BinarySecurityToken",
        certificate_base64=cert_b64,
        add_timestamp=False,
    )
    sec = build_security_header(cfg)
    xml_str = ET.tostring(sec, encoding="unicode")
    assert cert_b64 in xml_str
    assert "X509v3" in xml_str


# ---- Unit tests for envelope injection ------------------------------------


def test_inject_into_existing_header() -> None:
    cfg = WsSecurityConfig(type="Timestamp", ttl_seconds=60)
    result = inject_security(SAMPLE_ENVELOPE, cfg)
    root = ET.fromstring(result)
    header = root.find(f"{{{SOAP}}}Header")
    assert header is not None
    sec = header.find(f"{{{WSSE}}}Security")
    assert sec is not None


def test_inject_creates_header_if_missing() -> None:
    cfg = WsSecurityConfig(type="Timestamp", ttl_seconds=60)
    result = inject_security(ENVELOPE_NO_HEADER, cfg)
    root = ET.fromstring(result)
    header = root.find(f"{{{SOAP}}}Header")
    assert header is not None
    sec = header.find(f"{{{WSSE}}}Security")
    assert sec is not None


def test_malformed_envelope_raises(client: TestClient) -> None:
    resp = client.post(
        "/api/soap/ws-security/execute",
        json={
            "url": "http://localhost:9999",
            "envelope_xml": "THIS IS NOT XML",
            "security": {"type": "Timestamp"},
        },
    )
    assert resp.status_code == 422


def test_username_token_roundtrip_injection() -> None:
    cfg = WsSecurityConfig(
        type="UsernameToken",
        username="user1",
        password="pw",
        password_type="PasswordText",
        add_timestamp=True,
    )
    result = inject_security(SAMPLE_ENVELOPE, cfg)
    root = ET.fromstring(result)
    sec = root.find(f".//{{{WSSE}}}Security")
    assert sec is not None
    # Should have both Timestamp and UsernameToken
    assert sec.find(f"{{{WSU}}}Timestamp") is not None
    assert sec.find(f"{{{WSSE}}}UsernameToken") is not None
