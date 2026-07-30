"""Auth endpoints: nginx auth-check, plus session cookie mint/clear for browser navigation.

Auth0 handles all user-facing authentication (login, registration,
password reset, token refresh, MFA) via Bearer JWTs. The session cookie
endpoints here are a first-party addition on top of that for contexts a
Bearer header can't reach — a plain browser navigation/iframe request, e.g.
the Prefect UI link — not a replacement for the Bearer flow.
"""

import os

from fastapi import APIRouter, Response

from backend.api.auth import (
    SESSION_COOKIE_MAX_AGE,
    SESSION_COOKIE_NAME,
    CurrentUser,
    ModeratorCookieOrBearerAuth,
    mint_session_token,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/verify-moderator", include_in_schema=False)
async def verify_moderator_for_nginx(_: ModeratorCookieOrBearerAuth) -> None:
    """Internal endpoint called by nginx auth_request to gate the Prefect UI.

    Returns 200 when either the session cookie or the Bearer token is valid and the role is
    moderator or owner. FastAPI's ModeratorCookieOrBearerAuth dependency raises 401/403
    automatically on failure.
    """


@router.post("/session", status_code=204)
async def create_session(response: Response, current_user: CurrentUser) -> None:
    """Mint a first-party session cookie for the authenticated caller.

    Call this once after the normal Auth0 Bearer-token login completes. Lets a browser
    context that can't attach an Authorization header (plain navigation, e.g. the Prefect UI
    link) authenticate via cookie instead.
    """
    token = mint_session_token(current_user["db_id"], current_user["role"])
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
        secure=os.getenv("ENVIRONMENT", "local") != "local",
    )


@router.delete("/session", status_code=204)
async def clear_session(response: Response) -> None:
    """Clear the session cookie. Bearer-token access is unaffected."""
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
