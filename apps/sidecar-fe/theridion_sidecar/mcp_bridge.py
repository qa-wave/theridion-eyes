"""Theridion MCP bridge -- stdio entrypoint for Claude Desktop.

Usage::

    theridion-mcp

Or directly::

    python -m theridion_sidecar.mcp_bridge

Runs the FastMCP server over stdio transport. No running sidecar
HTTP process is needed -- tools call storage/environments/httpx
directly.
"""

from __future__ import annotations

import os
import sys


def main() -> None:
    """Entry point for the MCP bridge."""
    # Ensure THERIDION_HOME is set so storage resolves correctly.
    if "THERIDION_HOME" not in os.environ:
        os.environ["THERIDION_HOME"] = str(os.path.expanduser("~/.theridion"))

    # Route all logging to stderr (never contaminate stdio transport).
    import logging

    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    from .mcp_server_v2 import mcp

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
