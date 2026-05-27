"""Apache Camel test project generation endpoint."""

from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..camel.generator import CamelGeneratedProject, CamelRoute, generate_test

router = APIRouter(prefix="/api/camel", tags=["camel"])


@router.post("/generate", response_model=CamelGeneratedProject)
def generate(body: CamelRoute) -> CamelGeneratedProject:
    """Generate a complete Maven project with JUnit 5 Camel tests."""
    return generate_test(body)


@router.post("/download")
def download(body: CamelRoute) -> StreamingResponse:
    """Generate a Maven project and return it as a ZIP archive."""
    project = generate_test(body)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, content in project.files.items():
            zf.writestr(path, content)
    buf.seek(0)

    zip_name = f"{body.route_id}-camel-tests.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )
