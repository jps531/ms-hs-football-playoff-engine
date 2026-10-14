"""Shared slowapi rate limiter instance, keyed by client IP address."""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def client_ip(request: Request) -> str:
    """The visitor's IP address, for rate limiting.

    The API sits behind nginx, so the socket's peer is nginx itself: keying on
    it would put every visitor in one shared bucket, letting one person's
    requests use up everyone's allowance. nginx sets ``X-Real-IP`` to the
    connecting address (replacing anything the client sent), and the API
    container publishes no port of its own, so the header can be trusted.
    Without it (tests, a local run without nginx) the socket address is used.
    """
    real_ip = request.headers.get("x-real-ip", "").strip()
    return real_ip or get_remote_address(request)


limiter = Limiter(key_func=client_ip)
