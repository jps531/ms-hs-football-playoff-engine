"""Moderator API key authentication dependency."""

import os
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

_KEY_ENV = "MODERATOR_API_KEY"


def require_moderator(
    x_moderator_key: Annotated[str | None, Header()] = None,
) -> None:
    """Validate the X-Moderator-Key request header.

    Reads ``MODERATOR_API_KEY`` from the environment at call time so tests
    can override it via ``monkeypatch.setenv``.  Raises HTTP 401 if the
    header is absent or does not match.
    """
    expected = os.environ.get(_KEY_ENV)
    if not expected:
        raise RuntimeError(f"Server misconfiguration: {_KEY_ENV} env var is not set")
    if x_moderator_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Moderator-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )


ModeratorAuth = Annotated[None, Depends(require_moderator)]
