"""Integrations: send notifications to Slack, Teams, or custom webhooks."""

from __future__ import annotations

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


class NotifyInput(BaseModel):
    provider: str  # "slack" | "teams" | "webhook"
    url: str
    message: str
    payload: dict | None = None


class NotifyOutput(BaseModel):
    ok: bool
    status_code: int = 0
    error: str | None = None


@router.post("/notify", response_model=NotifyOutput)
async def notify(body: NotifyInput) -> NotifyOutput:
    try:
        if body.provider == "slack":
            payload = body.payload or {"text": body.message}
        elif body.provider == "teams":
            payload = body.payload or {"text": body.message}
        else:
            payload = body.payload or {"message": body.message}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(body.url, json=payload)
        return NotifyOutput(ok=resp.status_code < 400, status_code=resp.status_code)
    except Exception as exc:
        return NotifyOutput(ok=False, error=str(exc))


class FailedRequestInfo(BaseModel):
    name: str
    status: int = 0
    error: str = ""


class FailureNotifyInput(BaseModel):
    webhook_url: str
    collection_name: str
    failed_requests: list[FailedRequestInfo]
    total: int
    passed: int
    failed: int


class FailureNotifyOutput(BaseModel):
    ok: bool
    status_code: int = 0
    error: str | None = None


def _build_slack_payload(body: FailureNotifyInput) -> dict:
    failures_text = "\n".join(
        f"  - {r.name}: status={r.status} {r.error}" for r in body.failed_requests[:10]
    )
    return {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"Theridion: {body.collection_name} test run failed"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Total:* {body.total}  |  *Passed:* {body.passed}  |  *Failed:* {body.failed}\n\n"
                        f"*Failed requests:*\n{failures_text}"
                    ),
                },
            },
        ],
    }


def _build_teams_payload(body: FailureNotifyInput) -> dict:
    failures_text = "\n\n".join(
        f"- **{r.name}**: status={r.status} {r.error}" for r in body.failed_requests[:10]
    )
    return {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "FF0000",
        "summary": f"Theridion: {body.collection_name} test run failed",
        "sections": [
            {
                "activityTitle": f"Theridion: {body.collection_name}",
                "facts": [
                    {"name": "Total", "value": str(body.total)},
                    {"name": "Passed", "value": str(body.passed)},
                    {"name": "Failed", "value": str(body.failed)},
                ],
                "text": failures_text,
            }
        ],
    }


def _build_discord_payload(body: FailureNotifyInput) -> dict:
    failures_text = "\n".join(
        f"- {r.name}: status={r.status} {r.error}" for r in body.failed_requests[:10]
    )
    return {
        "content": (
            f"**Theridion: {body.collection_name} test run failed**\n"
            f"Total: {body.total} | Passed: {body.passed} | Failed: {body.failed}\n\n"
            f"Failed requests:\n{failures_text}"
        )
    }


@router.post("/notify-on-failure", response_model=FailureNotifyOutput)
async def notify_on_failure(body: FailureNotifyInput) -> FailureNotifyOutput:
    try:
        url_lower = body.webhook_url.lower()
        if "hooks.slack.com" in url_lower:
            payload = _build_slack_payload(body)
        elif "webhook.office.com" in url_lower or "microsoft" in url_lower:
            payload = _build_teams_payload(body)
        elif "discord.com" in url_lower:
            payload = _build_discord_payload(body)
        else:
            payload = {
                "collection": body.collection_name,
                "total": body.total,
                "passed": body.passed,
                "failed": body.failed,
                "failed_requests": [r.model_dump() for r in body.failed_requests],
            }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(body.webhook_url, json=payload)
        return FailureNotifyOutput(ok=resp.status_code < 400, status_code=resp.status_code)
    except Exception as exc:
        return FailureNotifyOutput(ok=False, error=str(exc))
