"""Fake data generator — generate test data without external dependencies."""

from __future__ import annotations

import random
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/generate", tags=["generate"])


_FIRST_NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace",
                "Hank", "Ivy", "Jack", "Kate", "Leo", "Mia", "Noah", "Olivia"]
_LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
               "Miller", "Davis", "Rodriguez", "Martinez", "Wilson", "Anderson"]
_COMPANIES = ["Acme Corp", "GlobalTech", "NexGen Solutions", "DataFlow Inc",
              "CloudNine Systems", "Apex Industries", "TechVentures", "CyberLogic"]
_STREETS = ["Main St", "Oak Ave", "Park Blvd", "Elm Dr", "Cedar Ln",
            "Maple Rd", "Pine Way", "Birch Ct"]
_CITIES = ["Springfield", "Portland", "Austin", "Seattle", "Denver",
           "Nashville", "Charlotte", "Columbus"]
_WORDS = ["the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog",
          "a", "bright", "sunny", "day", "is", "perfect", "for", "testing"]


def _gen_email() -> str:
    user = "".join(random.choices(string.ascii_lowercase, k=random.randint(5, 10)))
    domains = ["example.com", "test.org", "mail.dev", "sample.io"]
    return f"{user}@{random.choice(domains)}"


def _gen_name() -> str:
    return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"


def _gen_address() -> str:
    num = random.randint(1, 9999)
    return f"{num} {random.choice(_STREETS)}, {random.choice(_CITIES)}"


def _gen_phone() -> str:
    return f"+1-{random.randint(200,999)}-{random.randint(100,999)}-{random.randint(1000,9999)}"


def _gen_url() -> str:
    path = "".join(random.choices(string.ascii_lowercase, k=8))
    return f"https://example.com/{path}"


def _gen_ip() -> str:
    return f"{random.randint(1,254)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def _gen_date() -> str:
    base = datetime.now(timezone.utc)
    delta = timedelta(days=random.randint(-365, 365))
    return (base + delta).strftime("%Y-%m-%d")


def _gen_sentence() -> str:
    length = random.randint(5, 12)
    words = [random.choice(_WORDS) for _ in range(length)]
    words[0] = words[0].capitalize()
    return " ".join(words) + "."


_GENERATORS: dict[str, object] = {
    "email": _gen_email,
    "uuid": lambda: str(uuid.uuid4()),
    "name": _gen_name,
    "address": _gen_address,
    "phone": _gen_phone,
    "company": lambda: random.choice(_COMPANIES),
    "url": _gen_url,
    "ip": _gen_ip,
    "date": _gen_date,
    "sentence": _gen_sentence,
}


@router.get("/fake")
async def generate_fake(
    type: Literal["email", "uuid", "name", "address", "phone",
                  "company", "url", "ip", "date", "sentence"] = "uuid",
    count: int = Query(default=1, ge=1, le=100),
) -> dict[str, list[str]]:
    gen = _GENERATORS[type]
    values = [gen() for _ in range(count)]  # type: ignore[operator]
    return {"values": values}
