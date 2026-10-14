"""Cloudflare Turnstile checks for the site's public forms.

The feedback form renders a Turnstile widget and sends its token as
``turnstile_token``; ``verify_turnstile`` checks it with Cloudflare's
siteverify endpoint before a submission is queued. Each token is single-use.

Turnstile is on when ``TURNSTILE_SECRET_KEY`` is set (the browser gets the
matching ``TURNSTILE_SITE_KEY`` from ``/api/v1/meta/client-config``), so local
runs and tests need no keys. If Cloudflare itself can't be reached the check
fails open: the per-IP limits and the queue's circuit breaker still apply,
and an outage there shouldn't take the form down with it.
"""

import asyncio
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import HTTPException, status

_log = logging.getLogger(__name__)

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_TIMEOUT_SECONDS = 5

CHECK_FAILED = "The spam check didn't pass. Please try again."


def turnstile_secret() -> str:
    """The siteverify secret, or "" when Turnstile is off."""
    return os.getenv("TURNSTILE_SECRET_KEY", "").strip()


def turnstile_site_key() -> str | None:
    """The public site key the browser renders the widget with, or None when Turnstile is off."""
    if not turnstile_secret():
        return None
    return os.getenv("TURNSTILE_SITE_KEY", "").strip() or None


def _siteverify(secret: str, token: str, remote_ip: str | None) -> dict:
    """POST the token to Cloudflare's siteverify endpoint and return its JSON answer."""
    fields = {"secret": secret, "response": token}
    if remote_ip:
        fields["remoteip"] = remote_ip
    request = urllib.request.Request(_VERIFY_URL, data=urllib.parse.urlencode(fields).encode(), method="POST")
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed https URL
        return json.load(response)


async def verify_turnstile(token: str | None, remote_ip: str | None) -> None:
    """Raise HTTP 403 unless *token* passes Turnstile; a no-op while Turnstile is off.

    Fails open, with a warning logged, when Cloudflare can't be reached or answers garbage.
    """
    secret = turnstile_secret()
    if not secret:
        return
    if not token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=CHECK_FAILED)
    try:
        result = await asyncio.to_thread(_siteverify, secret, token, remote_ip)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        _log.warning("turnstile: siteverify unavailable, letting the submission through: %s", exc)
        return
    if not result.get("success"):
        _log.info("turnstile: rejected token, errors=%s", result.get("error-codes"))
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=CHECK_FAILED)
