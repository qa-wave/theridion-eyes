"""Flows: execute a block graph in topological order."""

from __future__ import annotations

import asyncio
import time

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/flows", tags=["flows"])


class FlowBlock(BaseModel):
    id: str
    type: str = "request"  # "request" | "transform" | "condition" | "delay"
    config: dict = {}
    next: list[str] = []


class FlowExecuteInput(BaseModel):
    blocks: list[FlowBlock]


class BlockResult(BaseModel):
    block_id: str
    output: dict = {}
    error: str | None = None


class FlowExecuteOutput(BaseModel):
    results: list[BlockResult] = []
    elapsed_ms: float = 0


def _topo_sort(blocks: list[FlowBlock]) -> list[FlowBlock]:
    by_id = {b.id: b for b in blocks}
    visited: set[str] = set()
    order: list[str] = []

    # Build reverse dependency: which blocks point to me
    incoming: dict[str, set[str]] = {b.id: set() for b in blocks}
    for b in blocks:
        for n in b.next:
            if n in incoming:
                incoming[n].add(b.id)

    def visit(bid: str) -> None:
        if bid in visited:
            return
        visited.add(bid)
        for dep in incoming.get(bid, set()):
            visit(dep)
        order.append(bid)

    for b in blocks:
        visit(b.id)

    return [by_id[bid] for bid in order if bid in by_id]


@router.post("/execute", response_model=FlowExecuteOutput)
async def execute_flow(body: FlowExecuteInput) -> FlowExecuteOutput:
    start = time.monotonic()
    sorted_blocks = _topo_sort(body.blocks)
    results: list[BlockResult] = []

    for block in sorted_blocks:
        try:
            if block.type == "delay":
                delay_s = block.config.get("seconds", 0)
                await asyncio.sleep(min(delay_s, 5))
                results.append(BlockResult(block_id=block.id, output={"delayed": delay_s}))
            elif block.type == "request":
                url = block.config.get("url", "")
                method = block.config.get("method", "GET")
                if url:
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.request(method, url)
                    results.append(BlockResult(
                        block_id=block.id,
                        output={"status": resp.status_code, "body_preview": resp.text[:500]},
                    ))
                else:
                    results.append(BlockResult(block_id=block.id, output={"skipped": True}))
            elif block.type == "transform":
                results.append(BlockResult(block_id=block.id, output=block.config))
            elif block.type == "condition":
                results.append(BlockResult(block_id=block.id, output={"evaluated": True}))
            else:
                results.append(BlockResult(block_id=block.id, output={"type": block.type}))
        except Exception as exc:
            results.append(BlockResult(block_id=block.id, error=str(exc)))

    elapsed = (time.monotonic() - start) * 1000
    return FlowExecuteOutput(results=results, elapsed_ms=round(elapsed, 2))
