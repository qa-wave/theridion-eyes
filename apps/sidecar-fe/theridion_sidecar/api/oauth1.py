"""OAuth 1.0: generate OAuth 1.0a signature headers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["oauth1"])


class OAuth1Input(BaseModel):
    consumer_key: str
    consumer_secret: str
    token: str = ""
    token_secret: str = ""
    url: str
    method: str = "GET"


class OAuth1Output(BaseModel):
    authorization_header: str
    signed_url: str


@router.post("/oauth1", response_model=OAuth1Output)
async def oauth1_sign(body: OAuth1Input) -> OAuth1Output:
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex

    params = {
        "oauth_consumer_key": body.consumer_key,
        "oauth_nonce": nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp,
        "oauth_version": "1.0",
    }
    if body.token:
        params["oauth_token"] = body.token

    parsed = urllib.parse.urlparse(body.url)
    query_params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    for k, v in query_params.items():
        params[k] = v[0]

    sorted_params = sorted(params.items())
    param_str = urllib.parse.urlencode(sorted_params, quote_via=urllib.parse.quote)

    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    base_string = (
        f"{body.method.upper()}&"
        f"{urllib.parse.quote(base_url, safe='')}&"
        f"{urllib.parse.quote(param_str, safe='')}"
    )

    signing_key = (
        f"{urllib.parse.quote(body.consumer_secret, safe='')}&"
        f"{urllib.parse.quote(body.token_secret, safe='')}"
    )

    sig = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()

    params["oauth_signature"] = sig
    auth_parts = ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
        for k, v in sorted(params.items())
        if k.startswith("oauth_")
    )
    auth_header = f"OAuth {auth_parts}"

    return OAuth1Output(authorization_header=auth_header, signed_url=body.url)
