"""SOAP-over-HTTP endpoints (inspect a WSDL, execute an operation).

The ``/execute`` endpoint accepts an optional ``wsse`` field that enables
WS-Security authentication.  Supported modes:

  ``UsernameToken``    — username/password credential in the SOAP header
  ``Timestamp``        — Created + Expires timestamp only
  ``Signature``        — XML Signature using key + cert loaded from files
  ``MemorySignature``  — XML Signature using key + cert supplied as PEM text
  ``BinarySecurityToken`` — embeds an X.509 cert; no cryptographic signing
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import soap
from .ws_security import WsSecurityConfig, build_zeep_wsse_plugin

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/soap", tags=["soap"])


class InspectInput(BaseModel):
    wsdl_url: str = Field(..., min_length=1)


class ExecuteInput(BaseModel):
    wsdl_url: str = Field(..., min_length=1)
    operation: str = Field(..., min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    wsse: WsSecurityConfig | None = None


class ExecuteOutput(BaseModel):
    ok: bool
    result: Any = None
    fault: str | None = None


@router.post("/inspect", response_model=soap.WsdlSummary)
def inspect(body: InspectInput) -> soap.WsdlSummary:
    try:
        return soap.inspect_wsdl(body.wsdl_url)
    except Exception as e:
        # zeep raises a variety of XMLParseError, HTTPError, etc.; we
        # collapse them to 400 with the message preserved so the desktop
        # can show what went wrong.
        raise HTTPException(status_code=400, detail=f"WSDL error: {e}") from e


@router.post("/execute", response_model=ExecuteOutput)
def execute(body: ExecuteInput) -> ExecuteOutput:
    # Build the WSSE plugin if WS-Security is requested.
    wsse_plugin = None
    if body.wsse is not None:
        try:
            wsse_plugin = build_zeep_wsse_plugin(body.wsse)
        except (ValueError, ImportError) as exc:
            raise HTTPException(status_code=400, detail=f"WS-Security error: {exc}") from exc
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"WS-Security configuration error: {exc}"
            ) from exc

    try:
        result = soap.execute_operation(body.wsdl_url, body.operation, body.args, wsse_plugin)
        return ExecuteOutput(ok=True, result=result)
    except ValueError as e:
        # operation not found
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        # SOAP fault, transport error, schema mismatch — surface as a 200
        # ExecuteOutput with `ok=false` so the UI can render the fault
        # detail next to the inputs without falling out of "happy path".
        return ExecuteOutput(ok=False, fault=str(e))
