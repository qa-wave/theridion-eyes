"""Advanced API lifecycle endpoints — split into logical sub-modules.

This package keeps the heavier "platform" features behind narrow HTTP
contracts: OpenAPI import/export/contract checks, examples, vault,
dependency graphing, flows, snapshots, HAR, TLS inspection, proxy
recording, collection-backed mocks, and git-aware review summaries.

The combined router is available as ``from theridion_sidecar.api.advanced import router``.
"""

from __future__ import annotations

from fastapi import APIRouter

from .analysis_ops import router as analysis_router
from .misc_ops import router as misc_router
from .openapi_ops import router as openapi_router
from .proxy_ops import router as proxy_router
from .security_ops import router as security_router
from .testing_ops import router as testing_router

router = APIRouter(prefix="/api/advanced", tags=["advanced"])

router.include_router(openapi_router)
router.include_router(security_router)
router.include_router(testing_router)
router.include_router(proxy_router)
router.include_router(analysis_router)
router.include_router(misc_router)
