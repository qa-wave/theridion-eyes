"""Collection docs: generate documentation from a collection."""

from __future__ import annotations

import html as html_mod
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from theridion_sidecar import storage

router = APIRouter(prefix="/api/docs", tags=["collection-docs"])


class DocsOutput(BaseModel):
    markdown: str = ""
    html: str = ""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _collect_toc(items: list, prefix: str = "") -> list[tuple[str, str, int]]:
    """Return list of (name, slug, depth) for TOC generation."""
    entries: list[tuple[str, str, int]] = []
    for item in items:
        d = item.model_dump() if hasattr(item, "model_dump") else item
        name = d.get("name", "Untitled")
        slug = _slug(f"{prefix}-{name}" if prefix else name)
        if d.get("is_folder"):
            entries.append((name, slug, 0))
            if d.get("items"):
                for child_name, child_slug, child_depth in _collect_toc(d["items"], name):
                    entries.append((child_name, child_slug, child_depth + 1))
        else:
            method = d.get("method", "GET")
            label = f"{method} {name}"
            entries.append((label, slug, 0))
    return entries


def _items_to_md(items: list, depth: int = 0) -> str:
    lines: list[str] = []
    heading = "#" * min(depth + 3, 6)
    for item in items:
        d = item.model_dump() if hasattr(item, "model_dump") else item
        name = d.get("name", "Untitled")
        if d.get("is_folder"):
            lines.append(f"{heading} {name}\n")
            if d.get("items"):
                lines.append(_items_to_md(d["items"], depth + 1))
        else:
            method = d.get("method", "GET")
            url = d.get("url", "")
            lines.append(f"{heading} {name}\n")
            lines.append(f"**{method}** `{url}`\n")
            if d.get("headers"):
                lines.append("**Headers:**\n")
                for k, v in d["headers"].items():
                    lines.append(f"- `{k}: {v}`")
                lines.append("")
            if d.get("body"):
                lines.append("**Request Body:**\n")
                lines.append(f"```json\n{d['body']}\n```\n")
            if d.get("auth") and d["auth"].get("type", "none") != "none":
                auth = d["auth"]
                lines.append(f"**Auth:** {auth['type']}\n")
            if d.get("notes"):
                lines.append(f"> {d['notes']}\n")
            # Examples
            if d.get("examples"):
                lines.append("**Examples:**\n")
                for ex in d["examples"]:
                    ex_d = ex if isinstance(ex, dict) else ex.model_dump() if hasattr(ex, "model_dump") else {}
                    lines.append(f"- *{ex_d.get('name', 'Example')}*: `{ex_d.get('method', 'GET')} {ex_d.get('url', '')}`")
                lines.append("")
            lines.append("---\n")
    return "\n".join(lines)


def _md_to_html(md: str, title: str) -> str:
    """Convert markdown to dark-themed HTML (simple conversion)."""
    h = html_mod.escape(md)
    # Headings
    for i in range(6, 0, -1):
        pattern = re.compile(r"^" + "#" * i + r"\s+(.+)$", re.MULTILINE)
        h = pattern.sub(rf'<h{i} style="margin-top:1.5em;">\1</h{i}>', h)
    # Bold
    h = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", h)
    # Italic
    h = re.sub(r"\*(.+?)\*", r"<em>\1</em>", h)
    # Inline code
    h = re.sub(r"`([^`]+)`", r'<code style="background:#1e1e2e;padding:2px 6px;border-radius:4px;font-size:0.85em;">\1</code>', h)
    # Code blocks
    h = re.sub(
        r"```(\w*)\n(.*?)```",
        r'<pre style="background:#1e1e2e;padding:12px;border-radius:8px;overflow-x:auto;font-size:0.85em;border:1px solid #333;"><code>\2</code></pre>',
        h,
        flags=re.DOTALL,
    )
    # Blockquotes
    h = re.sub(r"^&gt;\s*(.+)$", r'<blockquote style="border-left:3px solid #666;padding-left:12px;color:#aaa;margin:8px 0;">\1</blockquote>', h, flags=re.MULTILINE)
    # List items
    h = re.sub(r"^- (.+)$", r"<li>\1</li>", h, flags=re.MULTILINE)
    # Horizontal rules
    h = re.sub(r"^---$", '<hr style="border:none;border-top:1px solid #333;margin:16px 0;">', h, flags=re.MULTILINE)
    # Paragraphs (double newlines)
    h = re.sub(r"\n\n+", "</p><p>", h)
    # Single newlines
    h = h.replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{html_mod.escape(title)}</title>
  <style>
    body {{
      background: #0a0a0f;
      color: #e0e0e0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      max-width: 900px;
      margin: 0 auto;
      padding: 40px 24px;
      line-height: 1.7;
    }}
    h1 {{ color: #6ee7b7; border-bottom: 2px solid #333; padding-bottom: 8px; }}
    h2 {{ color: #a78bfa; }}
    h3 {{ color: #93c5fd; }}
    h4, h5, h6 {{ color: #d4d4d8; }}
    strong {{ color: #f0f0f0; }}
    a {{ color: #6ee7b7; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{ color: #6ee7b7; }}
    pre code {{ color: #d4d4d8; }}
    li {{ margin: 4px 0; list-style: disc; margin-left: 20px; }}
    .toc {{ background: #111118; border: 1px solid #333; border-radius: 8px; padding: 16px 24px; margin-bottom: 32px; }}
    .toc a {{ color: #93c5fd; }}
    .toc ul {{ list-style: none; padding-left: 16px; }}
    .toc > ul {{ padding-left: 0; }}
  </style>
</head>
<body>
  <h1>{html_mod.escape(title)} — API Documentation</h1>
  <p>{h}</p>
</body>
</html>"""


@router.post("/generate/{collection_id}", response_model=DocsOutput)
async def generate_docs(collection_id: str) -> DocsOutput:
    col = storage.load_collection(collection_id)
    if col is None:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Build TOC
    toc_entries = _collect_toc(col.items)
    toc_lines = ["## Table of Contents\n"]
    for name, slug, depth in toc_entries:
        indent = "  " * depth
        toc_lines.append(f"{indent}- [{name}](#{slug})")
    toc_lines.append("\n---\n")

    md = f"# {col.name}\n\n"
    md += "\n".join(toc_lines)
    md += "\n"
    md += _items_to_md(col.items)

    html_out = _md_to_html(md, col.name)
    return DocsOutput(markdown=md, html=html_out)
