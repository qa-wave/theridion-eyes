"""API Documentation Generator — create docs from saved collections."""

from __future__ import annotations

import json
import re
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import storage
from ..models import CollectionItem

router = APIRouter()


# ---- Models ------------------------------------------------------------------


class DocOptions(BaseModel):
    title: str | None = None
    description: str | None = None
    base_url: str | None = None
    include_examples: bool = True
    include_headers: bool = True
    group_by: Literal["folder", "method", "tag"] = "folder"


class DocGenerateInput(BaseModel):
    collection_id: str
    format: Literal["html", "markdown", "openapi"] = "html"
    options: DocOptions = Field(default_factory=DocOptions)


class DocGenerateOutput(BaseModel):
    content: str
    format: str
    endpoint_count: int


# ---- Helpers -----------------------------------------------------------------


def _flatten_requests(items: list[CollectionItem]) -> list[CollectionItem]:
    out: list[CollectionItem] = []
    for item in items:
        if item.is_folder:
            out.extend(_flatten_requests(item.items))
        else:
            out.append(item)
    return out


def _group_by_folder(
    items: list[CollectionItem], prefix: str = ""
) -> list[tuple[str, CollectionItem]]:
    """Return (folder_path, request) pairs preserving folder hierarchy."""
    out: list[tuple[str, CollectionItem]] = []
    for item in items:
        if item.is_folder:
            folder_path = f"{prefix}/{item.name}" if prefix else item.name
            out.extend(_group_by_folder(item.items, folder_path))
        else:
            out.append((prefix or "Root", item))
    return out


def _group_by_method(
    items: list[CollectionItem],
) -> dict[str, list[CollectionItem]]:
    groups: dict[str, list[CollectionItem]] = {}
    for req in _flatten_requests(items):
        method = req.method or "GET"
        groups.setdefault(method, []).append(req)
    return groups


METHOD_COLORS: dict[str, str] = {
    "GET": "#61affe",
    "POST": "#49cc90",
    "PUT": "#fca130",
    "PATCH": "#50e3c2",
    "DELETE": "#f93e3e",
    "HEAD": "#9012fe",
    "OPTIONS": "#0d5aa7",
}


# ---- HTML Generator ----------------------------------------------------------


def _generate_html(
    title: str,
    description: str,
    grouped: list[tuple[str, list[CollectionItem]]],
    options: DocOptions,
) -> str:
    nav_items: list[str] = []
    endpoint_sections: list[str] = []

    for group_name, requests in grouped:
        nav_items.append(
            f'<li class="nav-group">{_html_escape(group_name)}</li>'
        )
        for req in requests:
            anchor = f"endpoint-{id(req)}"
            method = req.method or "GET"
            color = METHOD_COLORS.get(method, "#999")
            url = req.url or ""
            path = urlsplit(url).path or url

            nav_items.append(
                f'<li><a href="#{anchor}">'
                f'<span class="method-badge" style="background:{color}">{method}</span>'
                f'{_html_escape(req.name)}</a></li>'
            )

            # Build endpoint section
            headers_html = ""
            if options.include_headers and req.headers:
                rows = "".join(
                    f"<tr><td><code>{_html_escape(k)}</code></td><td>{_html_escape(v)}</td></tr>"
                    for k, v in req.headers.items()
                )
                headers_html = (
                    '<h4>Headers</h4><table class="headers-table">'
                    f"<thead><tr><th>Name</th><th>Value</th></tr></thead>"
                    f"<tbody>{rows}</tbody></table>"
                )

            body_html = ""
            if options.include_examples and req.body:
                body_html = (
                    '<h4>Request Body</h4>'
                    f'<div class="code-block"><button class="copy-btn" onclick="copyCode(this)">Copy</button>'
                    f'<pre><code>{_html_escape(req.body)}</code></pre></div>'
                )

            notes_html = ""
            if req.notes:
                notes_html = f'<div class="description">{_html_escape(req.notes)}</div>'

            endpoint_sections.append(f"""
<div class="endpoint" id="{anchor}">
  <div class="endpoint-header">
    <span class="method-badge" style="background:{color}">{method}</span>
    <code class="url">{_html_escape(url)}</code>
  </div>
  <h3>{_html_escape(req.name)}</h3>
  {notes_html}
  {headers_html}
  {body_html}
</div>""")

    nav_html = "\n".join(nav_items)
    sections_html = "\n".join(endpoint_sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_html_escape(title)}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0a0b; color: #e5e5e5; display: flex; min-height: 100vh; }}
.sidebar {{ width: 280px; background: #111113; border-right: 1px solid #262626; padding: 1.5rem 0; overflow-y: auto; position: fixed; top: 0; bottom: 0; }}
.sidebar h1 {{ font-size: 1rem; padding: 0 1.5rem 0.5rem; color: #fafafa; }}
.sidebar p {{ font-size: 0.75rem; padding: 0 1.5rem 1rem; color: #a3a3a3; }}
.sidebar input {{ width: calc(100% - 3rem); margin: 0 1.5rem 1rem; padding: 0.5rem; background: #1a1a1c; border: 1px solid #333; border-radius: 6px; color: #e5e5e5; font-size: 0.8rem; }}
.sidebar ul {{ list-style: none; }}
.sidebar li a {{ display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 1.5rem; color: #a3a3a3; text-decoration: none; font-size: 0.8rem; transition: background 0.15s; }}
.sidebar li a:hover {{ background: #1a1a1c; color: #fafafa; }}
.sidebar .nav-group {{ padding: 0.8rem 1.5rem 0.3rem; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #666; }}
.main {{ margin-left: 280px; flex: 1; padding: 3rem; max-width: 900px; }}
.main > h1 {{ font-size: 1.5rem; margin-bottom: 0.5rem; }}
.main > p {{ color: #a3a3a3; margin-bottom: 2rem; }}
.endpoint {{ border: 1px solid #262626; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; background: #111113; }}
.endpoint-header {{ display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem; }}
.method-badge {{ display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.7rem; font-weight: 700; color: #fff; text-transform: uppercase; }}
.url {{ font-size: 0.85rem; color: #a3a3a3; word-break: break-all; }}
.endpoint h3 {{ font-size: 1rem; margin-bottom: 0.5rem; }}
.description {{ color: #a3a3a3; font-size: 0.85rem; margin-bottom: 0.75rem; }}
.headers-table {{ width: 100%; border-collapse: collapse; margin: 0.5rem 0 1rem; font-size: 0.8rem; }}
.headers-table th, .headers-table td {{ padding: 0.4rem 0.6rem; border: 1px solid #262626; text-align: left; }}
.headers-table th {{ background: #1a1a1c; color: #a3a3a3; font-weight: 600; }}
h4 {{ font-size: 0.8rem; margin: 1rem 0 0.4rem; color: #a3a3a3; text-transform: uppercase; letter-spacing: 0.03em; }}
.code-block {{ position: relative; background: #0a0a0b; border: 1px solid #262626; border-radius: 6px; padding: 1rem; margin: 0.5rem 0; }}
.code-block pre {{ overflow-x: auto; font-size: 0.8rem; line-height: 1.5; }}
.code-block code {{ color: #e5e5e5; }}
.copy-btn {{ position: absolute; top: 0.5rem; right: 0.5rem; background: #262626; border: none; color: #a3a3a3; padding: 0.3rem 0.6rem; border-radius: 4px; font-size: 0.7rem; cursor: pointer; }}
.copy-btn:hover {{ background: #333; color: #fafafa; }}
</style>
</head>
<body>
<nav class="sidebar">
  <h1>{_html_escape(title)}</h1>
  <p>{_html_escape(description)}</p>
  <input type="text" id="search" placeholder="Search endpoints..." oninput="filterEndpoints(this.value)">
  <ul id="nav-list">
    {nav_html}
  </ul>
</nav>
<main class="main">
  <h1>{_html_escape(title)}</h1>
  <p>{_html_escape(description)}</p>
  {sections_html}
</main>
<script>
function copyCode(btn) {{
  const code = btn.parentElement.querySelector('code').textContent;
  navigator.clipboard.writeText(code);
  btn.textContent = 'Copied!';
  setTimeout(() => btn.textContent = 'Copy', 1500);
}}
function filterEndpoints(query) {{
  const q = query.toLowerCase();
  document.querySelectorAll('.endpoint').forEach(el => {{
    const text = el.textContent.toLowerCase();
    el.style.display = text.includes(q) ? '' : 'none';
  }});
  document.querySelectorAll('#nav-list li a').forEach(a => {{
    const text = a.textContent.toLowerCase();
    a.parentElement.style.display = text.includes(q) ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""


# ---- Markdown Generator ------------------------------------------------------


def _generate_markdown(
    title: str,
    description: str,
    grouped: list[tuple[str, list[CollectionItem]]],
    options: DocOptions,
) -> str:
    lines: list[str] = [f"# {title}", ""]
    if description:
        lines.extend([description, ""])

    lines.append("## Table of Contents")
    lines.append("")
    for group_name, requests in grouped:
        lines.append(f"### {group_name}")
        for req in requests:
            method = req.method or "GET"
            anchor = re.sub(r"[^a-z0-9-]", "", req.name.lower().replace(" ", "-"))
            lines.append(f"- [{method} {req.name}](#{anchor})")
        lines.append("")

    lines.append("---")
    lines.append("")

    for group_name, requests in grouped:
        lines.append(f"## {group_name}")
        lines.append("")
        for req in requests:
            method = req.method or "GET"
            url = req.url or ""
            lines.append(f"### {req.name}")
            lines.append("")
            lines.append(f"**`{method}`** `{url}`")
            lines.append("")

            if req.notes:
                lines.append(req.notes)
                lines.append("")

            if options.include_headers and req.headers:
                lines.append("#### Headers")
                lines.append("")
                lines.append("| Name | Value |")
                lines.append("|------|-------|")
                for k, v in req.headers.items():
                    lines.append(f"| `{k}` | `{v}` |")
                lines.append("")

            if options.include_examples and req.body:
                lines.append("#### Request Body")
                lines.append("")
                lines.append("```json")
                lines.append(req.body)
                lines.append("```")
                lines.append("")

            lines.append("---")
            lines.append("")

    return "\n".join(lines)


# ---- OpenAPI Generator -------------------------------------------------------


def _generate_openapi(
    title: str,
    description: str,
    requests: list[CollectionItem],
    options: DocOptions,
) -> str:
    base_url = options.base_url or ""
    paths: dict[str, Any] = {}

    for req in requests:
        method = (req.method or "GET").lower()
        url = req.url or "/"
        # Extract path from full URL
        parsed = urlsplit(url)
        path = parsed.path or "/"
        if not base_url and parsed.scheme:
            base_url = f"{parsed.scheme}://{parsed.netloc}"

        if path not in paths:
            paths[path] = {}

        operation: dict[str, Any] = {
            "summary": req.name,
            "operationId": re.sub(r"[^a-zA-Z0-9_]", "_", req.name.lower()),
            "responses": {
                "200": {"description": "Successful response"},
            },
        }

        if req.notes:
            operation["description"] = req.notes

        if options.include_headers and req.headers:
            parameters = []
            for k, v in req.headers.items():
                if k.lower() in ("content-type", "accept", "authorization"):
                    continue
                parameters.append({
                    "name": k,
                    "in": "header",
                    "schema": {"type": "string"},
                    "example": v,
                })
            if parameters:
                operation["parameters"] = parameters

        if options.include_examples and req.body:
            try:
                body_json = json.loads(req.body)
                operation["requestBody"] = {
                    "content": {
                        "application/json": {
                            "example": body_json,
                        }
                    },
                }
            except (json.JSONDecodeError, TypeError):
                operation["requestBody"] = {
                    "content": {
                        "text/plain": {
                            "example": req.body,
                        }
                    },
                }

        paths[path][method] = operation

    spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {
            "title": title,
            "description": description,
            "version": "1.0.0",
        },
        "paths": paths,
    }
    if base_url:
        spec["servers"] = [{"url": base_url}]

    return json.dumps(spec, indent=2, ensure_ascii=False)


# ---- Utility -----------------------------------------------------------------


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_grouped(
    items: list[CollectionItem], options: DocOptions
) -> list[tuple[str, list[CollectionItem]]]:
    """Build grouped list of (group_name, requests) based on group_by option."""
    if options.group_by == "method":
        method_groups = _group_by_method(items)
        return [(method, reqs) for method, reqs in sorted(method_groups.items())]
    elif options.group_by == "tag":
        # Use folder names as tags
        folder_pairs = _group_by_folder(items)
        groups: dict[str, list[CollectionItem]] = {}
        for folder, req in folder_pairs:
            groups.setdefault(folder, []).append(req)
        return list(groups.items())
    else:
        # Default: folder
        folder_pairs = _group_by_folder(items)
        groups_f: dict[str, list[CollectionItem]] = {}
        for folder, req in folder_pairs:
            groups_f.setdefault(folder, []).append(req)
        return list(groups_f.items())


# ---- Endpoint ----------------------------------------------------------------


@router.post("/api/docs/generate", response_model=DocGenerateOutput)
def generate_docs(body: DocGenerateInput) -> DocGenerateOutput:
    coll = storage.get(body.collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")

    options = body.options
    title = options.title or coll.name
    description = options.description or f"API documentation for {coll.name}"
    all_requests = _flatten_requests(coll.items)
    endpoint_count = len(all_requests)

    if body.format == "openapi":
        content = _generate_openapi(title, description, all_requests, options)
    else:
        grouped = _build_grouped(coll.items, options)
        if body.format == "markdown":
            content = _generate_markdown(title, description, grouped, options)
        else:
            content = _generate_html(title, description, grouped, options)

    return DocGenerateOutput(
        content=content,
        format=body.format,
        endpoint_count=endpoint_count,
    )
