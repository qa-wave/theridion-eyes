"""Theridion Spin — automated backend testing module.

Spin provides deklarativní backend testing scenarios:
- Multi-step HTTP workflow chains with variable capture
- Pact-style consumer contract testing (V2 format)
- Database state verification (snapshot + diff)
- Schema compliance (OpenAPI / AsyncAPI / JSON Schema / protobuf)
- Lightweight performance smoke probes
"""

from __future__ import annotations

__all__ = ["runner", "contract", "workflow", "database", "schema", "performance"]
