"""MTOM/XOP: build MIME multipart SOAP messages with attachments."""

from __future__ import annotations

import base64
import uuid

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/soap", tags=["mtom"])


class MtomAttachment(BaseModel):
    filename: str
    content_base64: str
    content_type: str = "application/octet-stream"


class MtomInput(BaseModel):
    url: str
    soap_action: str
    envelope_xml: str
    attachments: list[MtomAttachment] = []


class MtomOutput(BaseModel):
    ok: bool
    response_xml: str | None = None
    error: str | None = None


@router.post("/mtom", response_model=MtomOutput)
async def mtom_send(body: MtomInput) -> MtomOutput:
    try:
        boundary = f"MIMEBoundary_{uuid.uuid4().hex}"
        root_cid = f"<root.message@theridion>"
        parts: list[str] = []

        # Root SOAP part
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Type: application/xop+xml; charset=UTF-8; type="text/xml"\r\n'
            f"Content-Transfer-Encoding: 8bit\r\n"
            f"Content-ID: {root_cid}\r\n"
            f"\r\n"
            f"{body.envelope_xml}\r\n"
        )

        # Attachment parts
        for att in body.attachments:
            cid = f"<{att.filename}@theridion>"
            parts.append(
                f"--{boundary}\r\n"
                f"Content-Type: {att.content_type}\r\n"
                f"Content-Transfer-Encoding: base64\r\n"
                f"Content-ID: {cid}\r\n"
                f"Content-Disposition: attachment; filename=\"{att.filename}\"\r\n"
                f"\r\n"
                f"{att.content_base64}\r\n"
            )

        parts.append(f"--{boundary}--\r\n")
        payload = "".join(parts)

        content_type = (
            f'multipart/related; boundary="{boundary}"; '
            f'type="application/xop+xml"; '
            f'start="{root_cid}"; '
            f'start-info="text/xml"'
        )

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                body.url,
                content=payload.encode(),
                headers={
                    "Content-Type": content_type,
                    "SOAPAction": body.soap_action,
                },
            )
        return MtomOutput(ok=resp.status_code < 500, response_xml=resp.text)
    except Exception as exc:
        return MtomOutput(ok=False, error=str(exc))
