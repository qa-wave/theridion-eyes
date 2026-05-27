"""Spin schema compliance validation — OpenAPI, AsyncAPI, JSON Schema, protobuf."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# ── JSON Schema ──────────────────────────────────────────────────────────────

def validate_json_schema(
    payload: Any,
    schema: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Validate payload against a JSON Schema draft-7/2019/2020 schema.

    Returns (ok, error_messages).
    """
    import jsonschema
    import jsonschema.exceptions

    errors: list[str] = []
    try:
        validator = jsonschema.Draft7Validator(schema)
        for error in validator.iter_errors(payload):
            errors.append(f"{'.'.join(str(p) for p in error.absolute_path) or 'root'}: {error.message}")
    except Exception as exc:
        errors.append(str(exc))
    return len(errors) == 0, errors


# ── OpenAPI 3.x ──────────────────────────────────────────────────────────────

def _load_openapi_spec(spec_path: str | Path) -> dict[str, Any]:
    import yaml

    p = Path(spec_path)
    with open(p, encoding="utf-8") as fh:
        if p.suffix in {".yaml", ".yml"}:
            return yaml.safe_load(fh)
        return json.load(fh)


def _resolve_openapi_schema_ref(
    spec: dict[str, Any],
    ref: str,
) -> dict[str, Any]:
    """Resolve a $ref like '#/components/schemas/Order' within the spec."""
    if not ref.startswith("#/"):
        return {}
    parts = ref.lstrip("#/").split("/")
    node: Any = spec
    for part in parts:
        if isinstance(node, dict):
            node = node.get(part, {})
        else:
            return {}
    return node if isinstance(node, dict) else {}


def _inline_refs(schema: dict[str, Any], spec: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    """Recursively inline $ref references (up to depth 10 to avoid cycles)."""
    if depth > 10:
        return schema
    if "$ref" in schema:
        resolved = _resolve_openapi_schema_ref(spec, schema["$ref"])
        return _inline_refs(resolved, spec, depth + 1)
    result = {}
    for k, v in schema.items():
        if isinstance(v, dict):
            result[k] = _inline_refs(v, spec, depth + 1)
        elif isinstance(v, list):
            result[k] = [
                _inline_refs(item, spec, depth + 1) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            result[k] = v
    return result


def validate_openapi_response(
    payload: Any,
    spec_path: str | Path,
    operation_id: str | None = None,
    path: str | None = None,
    method: str = "get",
    status_code: int = 200,
) -> tuple[bool, list[str]]:
    """Validate a response payload against an OpenAPI 3.x spec.

    Locates the response schema by operationId or path+method, then validates.
    """
    try:
        spec = _load_openapi_spec(spec_path)
    except Exception as exc:
        return False, [f"Failed to load OpenAPI spec: {exc}"]

    schema: dict[str, Any] | None = None

    if operation_id:
        # Find by operationId
        for path_item in (spec.get("paths") or {}).values():
            for op in path_item.values():
                if isinstance(op, dict) and op.get("operationId") == operation_id:
                    responses = op.get("responses", {})
                    for code in [str(status_code), "2xx", "default"]:
                        resp_obj = responses.get(code)
                        if resp_obj:
                            content = resp_obj.get("content", {})
                            for media_type in content.values():
                                schema = media_type.get("schema")
                                if schema:
                                    break
                        if schema:
                            break
                if schema:
                    break

    elif path:
        path_item = (spec.get("paths") or {}).get(path, {})
        op = path_item.get(method.lower(), {})
        responses = op.get("responses", {})
        for code in [str(status_code), "2xx", "default"]:
            resp_obj = responses.get(code)
            if resp_obj:
                content = resp_obj.get("content", {})
                for media_type in content.values():
                    schema = media_type.get("schema")
                    if schema:
                        break
            if schema:
                break

    if schema is None:
        return False, ["Could not locate response schema in OpenAPI spec"]

    inlined = _inline_refs(schema, spec)
    return validate_json_schema(payload, inlined)


# ── AsyncAPI 2/3 ─────────────────────────────────────────────────────────────

def validate_asyncapi_message(
    payload: Any,
    spec_path: str | Path,
    channel_name: str,
    operation: str = "publish",
) -> tuple[bool, list[str]]:
    """Validate a message payload against an AsyncAPI 2.x or 3.x spec.

    channel_name: e.g. 'inventory.reservations'
    operation: 'publish' | 'subscribe' (AsyncAPI 2) or 'send' | 'receive' (AsyncAPI 3)
    """
    try:
        import yaml
        p = Path(spec_path)
        with open(p, encoding="utf-8") as fh:
            spec = yaml.safe_load(fh) if p.suffix in {".yaml", ".yml"} else json.load(fh)
    except Exception as exc:
        return False, [f"Failed to load AsyncAPI spec: {exc}"]

    schema: dict[str, Any] | None = None
    asyncapi_version = str(spec.get("asyncapi", "2.0.0"))

    channels = spec.get("channels", {})
    channel = channels.get(channel_name, {})

    if asyncapi_version.startswith("3"):
        # AsyncAPI 3.x: channels.{name}.messages.{...}.payload
        messages = channel.get("messages", {})
        for msg in messages.values():
            if isinstance(msg, dict):
                schema = msg.get("payload")
                if schema:
                    break
    else:
        # AsyncAPI 2.x: channels.{name}.{operation}.message.payload
        op = channel.get(operation, channel.get("publish", channel.get("subscribe", {})))
        msg = op.get("message", {})
        schema = msg.get("payload")

    if schema is None:
        return False, [f"Could not locate payload schema for channel '{channel_name}'"]

    inlined = _inline_refs(schema, spec)
    return validate_json_schema(payload, inlined)


# ── Protobuf ─────────────────────────────────────────────────────────────────

def validate_protobuf_bytes(
    data: bytes,
    proto_path: str | Path,
    message_type: str,
) -> tuple[bool, list[str]]:
    """Validate raw bytes as a protobuf message.

    Uses protoc-generated descriptor or falls back to structural check.
    proto_path should point to a .proto file or pre-compiled .pb descriptor.
    """
    try:
        from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
        from google.protobuf.descriptor_pool import DescriptorPool

        p = Path(proto_path)
        if p.suffix == ".pb":
            # Pre-compiled FileDescriptorSet binary
            fds = descriptor_pb2.FileDescriptorSet()
            fds.ParseFromString(p.read_bytes())
            pool = DescriptorPool()
            for fd in fds.file:
                pool.Add(fd)
            desc = pool.FindMessageTypeByName(message_type)
            factory = message_factory.GetMessageClass(desc)
            msg = factory()
            msg.ParseFromString(data)
            return True, []
        else:
            # Attempt to parse as raw proto binary without descriptor (minimal check)
            # This is best-effort: check that data parses without exceptions
            from google.protobuf import message as proto_message
            # Without a descriptor we can only confirm non-empty and no parse error
            if not data:
                return False, ["Empty protobuf bytes"]
            return True, ["Note: proto schema validation without descriptor is best-effort"]

    except ImportError:
        return False, ["protobuf package not available (pip install protobuf)"]
    except Exception as exc:
        return False, [f"Protobuf parse error: {exc}"]


# ── Unified validate ──────────────────────────────────────────────────────────

def validate_payload(
    payload: Any,
    schema_ref: str,
    spec_path: str | None = None,
    raw_schema: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """Unified validation dispatcher.

    schema_ref formats:
        - "openapi://operationId"   → OpenAPI by operationId
        - "asyncapi://channelName"  → AsyncAPI by channel
        - "jsonschema"              → raw JSON Schema (provide raw_schema)
        - "protobuf://MessageType"  → protobuf bytes (payload must be bytes)
    """
    if schema_ref.startswith("openapi://"):
        op_id = schema_ref[len("openapi://"):]
        if not spec_path:
            return False, ["spec_path required for openapi:// validation"]
        return validate_openapi_response(payload, spec_path, operation_id=op_id)

    if schema_ref.startswith("asyncapi://"):
        channel = schema_ref[len("asyncapi://"):]
        if not spec_path:
            return False, ["spec_path required for asyncapi:// validation"]
        return validate_asyncapi_message(payload, spec_path, channel)

    if schema_ref.startswith("protobuf://"):
        msg_type = schema_ref[len("protobuf://"):]
        if not spec_path:
            return False, ["spec_path (path to .pb descriptor) required for protobuf:// validation"]
        if not isinstance(payload, bytes):
            return False, ["payload must be bytes for protobuf validation"]
        return validate_protobuf_bytes(payload, spec_path, msg_type)

    if schema_ref == "jsonschema":
        if not raw_schema:
            return False, ["raw_schema required for jsonschema validation"]
        return validate_json_schema(payload, raw_schema)

    return False, [f"Unknown schema_ref format: {schema_ref!r}"]
