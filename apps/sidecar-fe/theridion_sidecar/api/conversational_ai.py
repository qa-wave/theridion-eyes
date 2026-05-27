"""Conversational AI: chat with Ollama about APIs and collections."""

from __future__ import annotations

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/ai", tags=["conversational-ai"])


class AiChatContext(BaseModel):
    collections: list[str] | None = None
    environment: str | None = None
    recent_responses: list[str] | None = None


class AiChatInput(BaseModel):
    message: str
    context: AiChatContext | None = None


class AiSuggestion(BaseModel):
    action: str
    label: str


class AiChatOutput(BaseModel):
    response: str = ""
    suggestions: list[AiSuggestion] = []
    error: str | None = None


@router.post("/chat", response_model=AiChatOutput)
async def ai_chat(body: AiChatInput) -> AiChatOutput:
    prompt = f"User question about API testing: {body.message}"
    if body.context:
        if body.context.collections:
            prompt += f"\nCollections: {', '.join(body.context.collections)}"
        if body.context.environment:
            prompt += f"\nEnvironment: {body.context.environment}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "http://localhost:11434/api/generate",
                json={"model": "llama3.2", "prompt": prompt, "stream": False},
            )
        if resp.status_code == 200:
            data = resp.json()
            return AiChatOutput(
                response=data.get("response", ""),
                suggestions=[
                    AiSuggestion(action="new_request", label="Create a request"),
                    AiSuggestion(action="run_collection", label="Run collection"),
                ],
            )
        return AiChatOutput(error=f"Ollama returned {resp.status_code}")
    except Exception as exc:
        return AiChatOutput(
            error=f"Could not reach Ollama: {exc}",
            suggestions=[AiSuggestion(action="install_ollama", label="Install Ollama")],
        )
