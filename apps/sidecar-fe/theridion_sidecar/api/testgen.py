"""Service-definition test generator.

Takes an OpenAPI (3.x / Swagger 2.x, YAML or JSON) or WSDL/SOAP service
definition and produces a Theridion collection populated with categorised
test requests:

  * **is_alive**   — one or two minimal liveness checks
  * **smoke**      — happy-path coverage of every operation
  * **regression** — negative cases (404s, 400s, fault paths) for the
                     operations where they're meaningful

The generator is intentionally heuristic, not a contract validator: the
goal is to give the user a useful starting point that they can run and
edit, not to enumerate every spec edge case.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any
from xml.etree import ElementTree as ET

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import storage
from ..assertions import Assertion
from ..models import Collection, CollectionItem

router = APIRouter(prefix="/api/testgen", tags=["testgen"])


# --------------------------------------------------------------------------- #
# Public input/output models
# --------------------------------------------------------------------------- #


class ParseInput(BaseModel):
    content: str = Field(..., min_length=1)
    base_url: str | None = None


class OperationSummary(BaseModel):
    method: str
    path: str  # for OpenAPI; for SOAP we put the operation name here
    summary: str = ""
    has_path_params: bool = False
    has_request_body: bool = False


class ParseOutput(BaseModel):
    kind: str  # "openapi" | "wsdl" | "unknown"
    service_name: str
    base_url: str
    operations: list[OperationSummary] = Field(default_factory=list)
    # Just for the UI to show — number of tests each category would produce.
    expected_counts: dict[str, int] = Field(default_factory=dict)


class GenerateInput(BaseModel):
    content: str = Field(..., min_length=1)
    base_url: str | None = None
    collection_name: str | None = None
    categories: list[str] = Field(default_factory=lambda: ["is_alive", "smoke", "regression"])


class GenerateOutput(BaseModel):
    collection_id: str
    collection_name: str
    counts: dict[str, int]


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@router.post("/parse", response_model=ParseOutput)
def parse(body: ParseInput) -> ParseOutput:
    return _parse(body.content, body.base_url)


@router.post("/generate", response_model=GenerateOutput)
def generate(body: GenerateInput) -> GenerateOutput:
    parsed = _parse(body.content, body.base_url)
    if parsed.kind == "unknown":
        raise HTTPException(
            status_code=400,
            detail="Could not detect OpenAPI or WSDL in the provided content.",
        )

    cats = {c for c in body.categories if c in {"is_alive", "smoke", "regression"}}
    if not cats:
        raise HTTPException(status_code=400, detail="Pick at least one category.")

    name = body.collection_name or f"{parsed.service_name} — generated tests"

    if parsed.kind == "openapi":
        coll, counts = _build_openapi_collection(
            body.content, name, parsed.base_url, cats,
        )
    else:
        coll, counts = _build_wsdl_collection(
            body.content, name, parsed.base_url, cats,
        )

    storage._atomic_write(coll)
    return GenerateOutput(
        collection_id=coll.id,
        collection_name=coll.name,
        counts=counts,
    )


# --------------------------------------------------------------------------- #
# Format detection + summary
# --------------------------------------------------------------------------- #


def _parse(content: str, base_url_override: str | None) -> ParseOutput:
    text = content.strip()
    if text.startswith("<"):
        return _summarise_wsdl(text, base_url_override)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        data = None
    if isinstance(data, dict) and ("openapi" in data or "swagger" in data):
        return _summarise_openapi(data, base_url_override)
    return ParseOutput(kind="unknown", service_name="", base_url="")


# --------------------------------------------------------------------------- #
# OpenAPI
# --------------------------------------------------------------------------- #


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _summarise_openapi(spec: dict[str, Any], base_url_override: str | None) -> ParseOutput:
    info = spec.get("info") or {}
    name = info.get("title") or "OpenAPI service"
    base_url = base_url_override or _openapi_base_url(spec)

    ops: list[OperationSummary] = []
    for path, methods in (spec.get("paths") or {}).items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if method.lower() not in HTTP_METHODS:
                continue
            if not isinstance(op, dict):
                continue
            ops.append(OperationSummary(
                method=method.upper(),
                path=path,
                summary=op.get("summary", "") or op.get("operationId", "") or "",
                has_path_params="{" in path,
                has_request_body=bool(op.get("requestBody")),
            ))

    return ParseOutput(
        kind="openapi",
        service_name=name,
        base_url=base_url,
        operations=ops,
        expected_counts=_openapi_expected_counts(spec, ops),
    )


def _openapi_base_url(spec: dict[str, Any]) -> str:
    servers = spec.get("servers") or []
    if servers and isinstance(servers[0], dict) and servers[0].get("url"):
        return str(servers[0]["url"]).rstrip("/")
    host = spec.get("host")
    if host:
        scheme = (spec.get("schemes") or ["http"])[0]
        base = spec.get("basePath") or ""
        return f"{scheme}://{host}{base}".rstrip("/")
    return ""


def _openapi_expected_counts(spec: dict[str, Any], ops: list[OperationSummary]) -> dict[str, int]:
    health = any(o.method == "GET" and o.path.endswith("/health") for o in ops)
    is_alive = 1 if health else (1 if ops else 0)
    smoke = sum(1 for o in ops if _can_smoke(o))
    regression = sum(1 for o in ops if _can_regress(o))
    return {"is_alive": is_alive, "smoke": smoke, "regression": regression}


def _can_smoke(o: OperationSummary) -> bool:
    return True  # every operation gets at least one happy-path attempt


def _can_regress(o: OperationSummary) -> bool:
    return o.has_path_params or o.has_request_body


def _build_openapi_collection(
    raw: str,
    name: str,
    base_url: str,
    categories: set[str],
) -> tuple[Collection, dict[str, int]]:
    spec: dict[str, Any] = yaml.safe_load(raw)
    base_url = base_url.rstrip("/")
    counts = {"is_alive": 0, "smoke": 0, "regression": 0}
    folders: list[CollectionItem] = []

    paths: dict[str, Any] = spec.get("paths") or {}

    if "is_alive" in categories:
        is_alive_items = _openapi_is_alive(paths, base_url)
        if is_alive_items:
            folders.append(_folder("Is alive", is_alive_items))
            counts["is_alive"] = len(is_alive_items)

    if "smoke" in categories:
        smoke_items = _openapi_smoke(spec, paths, base_url)
        if smoke_items:
            folders.append(_folder("Smoke tests", smoke_items))
            counts["smoke"] = len(smoke_items)

    if "regression" in categories:
        regression_items = _openapi_regression(spec, paths, base_url)
        if regression_items:
            folders.append(_folder("Regression tests", regression_items))
            counts["regression"] = len(regression_items)

    coll = Collection(id=str(uuid.uuid4()), name=name, version=1, items=folders)
    return coll, counts


def _openapi_is_alive(paths: dict[str, Any], base_url: str) -> list[CollectionItem]:
    out: list[CollectionItem] = []
    health_path = next(
        (p for p in paths if p.endswith("/health") and isinstance(paths[p], dict) and "get" in paths[p]),
        None,
    )
    if health_path:
        out.append(_request_item(
            name=f"GET {health_path}",
            method="GET",
            url=f"{base_url}{health_path}",
            assertions=[
                _A("status", expected="200"),
                _A("response_time", expected="2000"),
            ],
        ))
        return out

    # Fallback: pick the first parameter-less GET as a liveness probe.
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        op = methods.get("get")
        if not isinstance(op, dict):
            continue
        if "{" in path:
            continue
        out.append(_request_item(
            name=f"GET {path} (liveness)",
            method="GET",
            url=f"{base_url}{path}",
            assertions=[
                _A("status", expected="200"),
                _A("response_time", expected="2000"),
            ],
        ))
        return out

    return out


def _openapi_smoke(
    spec: dict[str, Any], paths: dict[str, Any], base_url: str,
) -> list[CollectionItem]:
    out: list[CollectionItem] = []
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if method.lower() not in HTTP_METHODS:
                continue
            if not isinstance(op, dict):
                continue
            item = _openapi_smoke_request(
                spec, path, method.upper(), op, base_url,
            )
            if item is not None:
                out.append(item)
    return out


def _openapi_smoke_request(
    spec: dict[str, Any],
    path: str,
    method: str,
    op: dict[str, Any],
    base_url: str,
) -> CollectionItem | None:
    # Resolve path parameters to sample values.
    resolved_path = path
    path_params = [p for p in (op.get("parameters") or []) if p.get("in") == "path"]
    for p in path_params:
        sample = _sample_for_param(p)
        resolved_path = resolved_path.replace("{" + p["name"] + "}", str(sample))

    # Pick the success status from the spec; default 200.
    success_status = _pick_success_status(op)

    assertions: list[Assertion] = [
        _A("status", expected=str(success_status)),
        _A("response_time", expected="3000"),
    ]

    # If the operation declares a JSON response, add a content-type header check.
    if _has_json_response(op):
        assertions.append(_A("header_exists", path="content-type"))

    headers: dict[str, str] = {}
    body: str | None = None
    request_body = op.get("requestBody")
    if isinstance(request_body, dict):
        sample = _sample_request_body(spec, request_body)
        if sample is not None:
            body = json.dumps(sample, ensure_ascii=False)
            headers["content-type"] = "application/json"

    # Inject auth header(s) for any apiKey-in-header schemes that apply.
    for hdr_name, hdr_value in _apikey_headers_for_op(spec, op):
        headers[hdr_name] = hdr_value

    label = op.get("summary") or f"{method} {path}"

    return _request_item(
        name=label,
        method=method,
        url=f"{base_url}{resolved_path}",
        headers=headers,
        body=body,
        assertions=assertions,
    )


def _openapi_regression(
    spec: dict[str, Any], paths: dict[str, Any], base_url: str,
) -> list[CollectionItem]:
    out: list[CollectionItem] = []
    # Track which protected ops we've already covered with a no-auth test —
    # one negative auth test per (method, path) is enough.
    auth_covered: set[tuple[str, str]] = set()
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if method.lower() not in HTTP_METHODS or not isinstance(op, dict):
                continue
            mt = method.upper()
            # ---- Missing API key → 401/403 (only when the op is protected
            # by an apiKey scheme; GETs only to stay side-effect-free).
            auth_headers = _apikey_headers_for_op(spec, op)
            if auth_headers and mt == "GET" and (mt, path) not in auth_covered:
                resolved_path = path
                for p in [pp for pp in (op.get("parameters") or []) if pp.get("in") == "path"]:
                    resolved_path = resolved_path.replace(
                        "{" + p["name"] + "}", str(_sample_for_param(p)),
                    )
                out.append(_request_item(
                    name=f"{mt} {path} — no API key → 401",
                    method=mt,
                    url=f"{base_url}{resolved_path}",
                    assertions=[_A("status", expected="401")],
                ))
                auth_covered.add((mt, path))
            # Path params → missing-id 404 test (only on GETs to keep it
            # idempotent; PATCH/DELETE may have side effects).
            if "{" in path and mt == "GET":
                # Replace EVERY path param with a clearly bogus value.
                bogus_path = re.sub(r"\{[^}]+\}", "DOES-NOT-EXIST-999", path)
                req_headers: dict[str, str] = {}
                for hdr_name, hdr_value in _apikey_headers_for_op(spec, op):
                    req_headers[hdr_name] = hdr_value
                out.append(_request_item(
                    name=f"{mt} {path} — missing → 404",
                    method=mt,
                    url=f"{base_url}{bogus_path}",
                    headers=req_headers,
                    assertions=[
                        _A("status", expected="404"),
                    ],
                ))
            # Required body with no body → 400 (skip if generator can't
            # tell which fields are required).
            request_body = op.get("requestBody")
            if isinstance(request_body, dict) and request_body.get("required"):
                resolved_path = path
                for p in [pp for pp in (op.get("parameters") or []) if pp.get("in") == "path"]:
                    resolved_path = resolved_path.replace(
                        "{" + p["name"] + "}", str(_sample_for_param(p)),
                    )
                out.append(_request_item(
                    name=f"{mt} {path} — empty body → 4xx",
                    method=mt,
                    url=f"{base_url}{resolved_path}",
                    headers={"content-type": "application/json"},
                    body="{}",
                    assertions=[
                        _A("status", expected="400"),
                    ],
                ))
            # Enum body fields → invalid value → 4xx.
            if isinstance(request_body, dict):
                bad = _bad_enum_body(spec, request_body)
                if bad is not None:
                    resolved_path = path
                    for p in [pp for pp in (op.get("parameters") or []) if pp.get("in") == "path"]:
                        resolved_path = resolved_path.replace(
                            "{" + p["name"] + "}", str(_sample_for_param(p)),
                        )
                    out.append(_request_item(
                        name=f"{mt} {path} — invalid enum → 4xx",
                        method=mt,
                        url=f"{base_url}{resolved_path}",
                        headers={"content-type": "application/json"},
                        body=json.dumps(bad, ensure_ascii=False),
                        assertions=[
                            _A("status", expected="400"),
                        ],
                    ))
    return out


# --------------------------------------------------------------------------- #
# OpenAPI helpers
# --------------------------------------------------------------------------- #


def _pick_success_status(op: dict[str, Any]) -> int:
    responses = op.get("responses") or {}
    for code in responses:
        s = str(code)
        if s.startswith("2"):
            try:
                return int(s)
            except ValueError:
                continue
    return 200


def _has_json_response(op: dict[str, Any]) -> bool:
    for code, resp in (op.get("responses") or {}).items():
        if not str(code).startswith("2") or not isinstance(resp, dict):
            continue
        content = resp.get("content") or {}
        if any(k.startswith("application/json") for k in content):
            return True
    return False


def _sample_for_param(param: dict[str, Any]) -> Any:
    if "example" in param:
        return param["example"]
    schema = param.get("schema") or {}
    if "example" in schema:
        return schema["example"]
    return _sample_for_schema(schema, {}) or "1"


def _sample_request_body(spec: dict[str, Any], rb: dict[str, Any]) -> Any:
    content = rb.get("content") or {}
    for mt, media in content.items():
        if not mt.startswith("application/json"):
            continue
        if not isinstance(media, dict):
            continue
        if "example" in media:
            return media["example"]
        examples = media.get("examples") or {}
        if examples:
            first = next(iter(examples.values()))
            if isinstance(first, dict) and "value" in first:
                return first["value"]
        schema = media.get("schema") or {}
        return _sample_for_schema(schema, spec)
    return None


def _sample_for_schema(schema: dict[str, Any], spec: dict[str, Any]) -> Any:
    if not isinstance(schema, dict):
        return None
    # $ref
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/"):
        resolved = _resolve_ref(spec, ref)
        if isinstance(resolved, dict):
            return _sample_for_schema(resolved, spec)
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        out: dict[str, Any] = {}
        required = set(schema.get("required") or [])
        for k, v in (schema.get("properties") or {}).items():
            if required and k not in required:
                continue
            out[k] = _sample_for_schema(v, spec)
        # If no required fields were declared, fill in everything so the
        # request is realistic.
        if not out:
            for k, v in (schema.get("properties") or {}).items():
                out[k] = _sample_for_schema(v, spec)
        return out
    if t == "array":
        return [_sample_for_schema(schema.get("items") or {}, spec)]
    fmt = schema.get("format", "")
    if t == "string":
        if fmt == "date-time":
            return "2026-01-01T00:00:00.000Z"
        if fmt == "date":
            return "2026-01-01"
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        return "sample"
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "boolean":
        return True
    return None


def _bad_enum_body(spec: dict[str, Any], rb: dict[str, Any]) -> dict[str, Any] | None:
    """Build a body where the first enum field is set to a bogus value."""
    content = rb.get("content") or {}
    for mt, media in content.items():
        if not mt.startswith("application/json") or not isinstance(media, dict):
            continue
        schema = media.get("schema") or {}
        sample = _sample_for_schema(schema, spec)
        if not isinstance(sample, dict):
            return None
        enum_field = _find_enum_field(schema, spec)
        if enum_field is None:
            return None
        sample[enum_field] = "__bogus__"
        return sample
    return None


def _find_enum_field(schema: dict[str, Any], spec: dict[str, Any]) -> str | None:
    if not isinstance(schema, dict):
        return None
    ref = schema.get("$ref")
    if isinstance(ref, str):
        resolved = _resolve_ref(spec, ref)
        if isinstance(resolved, dict):
            return _find_enum_field(resolved, spec)
    for k, v in (schema.get("properties") or {}).items():
        if not isinstance(v, dict):
            continue
        if isinstance(v.get("enum"), list) and v["enum"]:
            return k
    return None


def _apikey_headers_for_op(
    spec: dict[str, Any], op: dict[str, Any],
) -> list[tuple[str, str]]:
    """Return (header, sample_value) pairs for every apiKey-in-header scheme
    that applies to *op*. Empty if the op is unauthenticated.

    Sample values are extracted from the scheme's description (any token
    matching `key:\\s*<value>` or `token:\\s*<value>`); fallback `<api-key>`.
    """
    schemes = (spec.get("components") or {}).get("securitySchemes") or {}
    if not isinstance(schemes, dict) or not schemes:
        return []

    # Per-op security overrides global. `security: []` means "no auth".
    sec_req = op.get("security")
    if sec_req is None:
        sec_req = spec.get("security") or []
    if not sec_req:
        return []

    out: list[tuple[str, str]] = []
    for requirement in sec_req:
        if not isinstance(requirement, dict):
            continue
        for scheme_name in requirement:
            scheme = schemes.get(scheme_name)
            if not isinstance(scheme, dict):
                continue
            if scheme.get("type") != "apiKey":
                continue
            if scheme.get("in") != "header":
                continue
            hdr = scheme.get("name")
            if not hdr:
                continue
            value = _extract_sample_key(scheme.get("description") or "") or "<api-key>"
            out.append((str(hdr), value))
    # Dedupe by header name, keeping the first value.
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for h, v in out:
        if h.lower() in seen:
            continue
        seen.add(h.lower())
        deduped.append((h, v))
    return deduped


_KEY_VALUE_RE = re.compile(
    r"(?:key|token)\s*[:=]\s*([A-Za-z0-9][A-Za-z0-9_\-.]{4,})",
    re.IGNORECASE,
)


def _extract_sample_key(description: str) -> str | None:
    m = _KEY_VALUE_RE.search(description or "")
    return m.group(1) if m else None


def _resolve_ref(spec: dict[str, Any], ref: str) -> Any:
    parts = ref.lstrip("#/").split("/")
    node: Any = spec
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


# --------------------------------------------------------------------------- #
# WSDL / SOAP
# --------------------------------------------------------------------------- #


def _summarise_wsdl(text: str, base_url_override: str | None) -> ParseOutput:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return ParseOutput(kind="unknown", service_name="", base_url="")

    name = root.attrib.get("name") or "SOAP service"
    target_ns = root.attrib.get("targetNamespace", "")
    soap_action_prefix = target_ns + "#" if target_ns else ""

    base_url = base_url_override or _wsdl_endpoint(root) or ""

    ops: list[OperationSummary] = []
    for op_name in _wsdl_operations(root):
        ops.append(OperationSummary(
            method="POST",
            path=op_name,
            summary=f"SOAPAction {soap_action_prefix}{op_name}",
            has_path_params=False,
            has_request_body=True,
        ))

    return ParseOutput(
        kind="wsdl",
        service_name=name,
        base_url=base_url,
        operations=ops,
        expected_counts={
            "is_alive": 1,
            "smoke": len(ops),
            "regression": min(len(ops), 3),
        },
    )


def _wsdl_endpoint(root: ET.Element) -> str | None:
    # Pull the soap:address location from any port — the WSDL we ship has one.
    for el in root.iter():
        if el.tag.endswith("}address") or el.tag == "address":
            loc = el.attrib.get("location")
            if loc:
                return loc.rstrip("?wsdl").rstrip("/")
    return None


def _wsdl_operations(root: ET.Element) -> list[str]:
    names: list[str] = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag != "operation":
            continue
        parent_tag = ""
        # ET doesn't give us parent; we collect names from <portType>/<binding>
        # by accepting all unique names. That's good enough — they match.
        n = el.attrib.get("name")
        if n and n not in names:
            names.append(n)
        del parent_tag
    return names


def _build_wsdl_collection(
    raw: str,
    name: str,
    base_url: str,
    categories: set[str],
) -> tuple[Collection, dict[str, int]]:
    root = ET.fromstring(raw)
    target_ns = root.attrib.get("targetNamespace") or "urn:service"
    endpoint = base_url or _wsdl_endpoint(root) or ""
    ops = _wsdl_operations(root)
    counts = {"is_alive": 0, "smoke": 0, "regression": 0}
    folders: list[CollectionItem] = []

    soap_headers = {"content-type": "text/xml; charset=utf-8"}

    def envelope(body_xml: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" '
            f'xmlns:tns="{target_ns}"><soap:Body>{body_xml}</soap:Body></soap:Envelope>'
        )

    if "is_alive" in categories and endpoint:
        wsdl_url = f"{endpoint}?wsdl"
        items = [_request_item(
            name="WSDL reachable",
            method="GET",
            url=wsdl_url,
            assertions=[
                _A("status", expected="200"),
                _A("body_contains", expected="<definitions"),
                _A("body_contains", expected=target_ns),
            ],
        )]
        folders.append(_folder("Is alive", items))
        counts["is_alive"] = len(items)

    if "smoke" in categories and endpoint:
        items: list[CollectionItem] = []
        for op in ops:
            items.append(_request_item(
                name=f"{op}",
                method="POST",
                url=endpoint,
                headers={**soap_headers, "SOAPAction": f"{target_ns}#{op}"},
                body=envelope(f"<tns:{op}Request/>"),
                assertions=[
                    _A("status", expected="200"),
                    _A("body_contains", expected=f"{op}Response"),
                ],
            ))
        if items:
            folders.append(_folder("Smoke tests", items))
            counts["smoke"] = len(items)

    if "regression" in categories and endpoint:
        items: list[CollectionItem] = []
        # 1. Unknown SOAP operation → fault.
        items.append(_request_item(
            name="Unknown SOAPAction → fault",
            method="POST",
            url=endpoint,
            headers={**soap_headers, "SOAPAction": f"{target_ns}#NoSuchOperation"},
            body=envelope("<tns:NoSuchOperationRequest/>"),
            assertions=[
                _A("status", expected="400"),
                _A("body_contains", expected="Fault"),
            ],
        ))
        # 2. If the WSDL has a "Get<X>" op, missing id → fault.
        get_op = next((o for o in ops if o.lower().startswith("get")), None)
        if get_op:
            items.append(_request_item(
                name=f"{get_op} — missing id → fault",
                method="POST",
                url=endpoint,
                headers={**soap_headers, "SOAPAction": f"{target_ns}#{get_op}"},
                body=envelope(
                    f"<tns:{get_op}Request><tns:id>DOES-NOT-EXIST-999</tns:id></tns:{get_op}Request>"
                ),
                assertions=[
                    _A("status", expected="404"),
                    _A("body_contains", expected="Fault"),
                ],
            ))
        # 3. Malformed envelope → 4xx.
        items.append(_request_item(
            name="Malformed envelope → 4xx",
            method="POST",
            url=endpoint,
            headers=soap_headers,
            body="<not-soap/>",
            assertions=[
                _A("status", expected="400"),
            ],
        ))
        folders.append(_folder("Regression tests", items))
        counts["regression"] = len(items)

    coll = Collection(id=str(uuid.uuid4()), name=name, version=1, items=folders)
    return coll, counts


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _A(kind: str, *, expected: str = "", path: str = "", operator: str = "eq") -> Assertion:
    return Assertion(type=kind, expected=expected, path=path, operator=operator)


def _folder(name: str, items: list[CollectionItem]) -> CollectionItem:
    return CollectionItem(
        id=str(uuid.uuid4()),
        name=name,
        is_folder=True,
        items=items,
    )


def _request_item(
    *,
    name: str,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    assertions: list[Assertion] | None = None,
) -> CollectionItem:
    return CollectionItem(
        id=str(uuid.uuid4()),
        name=name,
        is_folder=False,
        method=method,
        url=url,
        headers=headers or {},
        body=body,
        assertions=assertions or [],
    )
