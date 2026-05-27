"""SOAP / WSDL inspection and execution via `zeep`.

Wraps the bits of `zeep` we need behind a small typed surface so the
HTTP layer never imports zeep directly. zeep is synchronous; we keep
these functions sync and rely on FastAPI's threadpool offloading for
non-blocking I/O.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel
from zeep import Client
from zeep.helpers import serialize_object

log = logging.getLogger(__name__)


class SoapOperation(BaseModel):
    name: str
    soap_action: str | None = None
    documentation: str | None = None


class SoapPort(BaseModel):
    name: str
    binding: str
    address: str | None = None
    operations: list[SoapOperation]


class SoapService(BaseModel):
    name: str
    ports: list[SoapPort]


class WsdlSummary(BaseModel):
    target_namespace: str | None
    services: list[SoapService]


def inspect_wsdl(wsdl_url: str) -> WsdlSummary:
    """Parse a WSDL and return a JSON-friendly summary of its services."""
    client = Client(wsdl=wsdl_url)
    services: list[SoapService] = []
    for svc_name, svc in client.wsdl.services.items():
        ports: list[SoapPort] = []
        for port_name, port in svc.ports.items():
            ops: list[SoapOperation] = []
            # Iterate the binding's operations. `_operations` is private but
            # is the only stable way to enumerate them; zeep provides no
            # public accessor in 4.x.
            for op_name, op in port.binding._operations.items():
                ops.append(
                    SoapOperation(
                        name=op_name,
                        soap_action=getattr(op, "soapaction", None) or None,
                        documentation=_doc(op),
                    )
                )
            address = None
            try:
                address = port.binding_options.get("address")
            except (AttributeError, KeyError):
                pass
            ports.append(
                SoapPort(
                    name=port_name,
                    binding=str(port.binding.name),
                    address=address,
                    operations=ops,
                )
            )
        services.append(SoapService(name=svc_name, ports=ports))
    # zeep's Document has no single target_namespace attr in 4.x — try a
    # few likely names, otherwise pull it from the first service's
    # binding's portType for a reasonable approximation.
    tns = getattr(client.wsdl, "target_namespace", None) or getattr(
        client.wsdl, "tns", None
    )
    if tns is None:
        try:
            first_svc = next(iter(client.wsdl.services.values()))
            first_port = next(iter(first_svc.ports.values()))
            tns = first_port.binding.port_type.name.namespace
        except (StopIteration, AttributeError):
            tns = None
    return WsdlSummary(
        target_namespace=str(tns) if tns else None,
        services=services,
    )


def execute_operation(
    wsdl_url: str,
    operation: str,
    args: dict[str, Any],
    wsse_plugin: Any = None,
) -> Any:
    """Invoke a SOAP operation by name with the given keyword args.

    If *wsse_plugin* is provided it is attached to the zeep Client so that
    zeep automatically adds the WS-Security header to every request.  The
    plugin must implement the ``apply(envelope, headers)`` / ``verify(envelope)``
    protocol from ``zeep.wsse``.

    Returns a JSON-serializable representation of the response. Network,
    schema, and SOAP faults bubble up as exceptions for the caller to
    translate into a meaningful HTTP response.
    """
    client = Client(wsdl=wsdl_url, wsse=wsse_plugin)
    callable_ = getattr(client.service, operation, None)
    if callable_ is None:
        raise ValueError(f"operation {operation!r} not found in WSDL")
    result = callable_(**args)
    return serialize_object(result, dict)


def _doc(op: Any) -> str | None:
    raw = getattr(op, "documentation", None)
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None
