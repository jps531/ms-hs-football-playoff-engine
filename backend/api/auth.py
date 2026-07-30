"""Auth0-based JWT authentication for the Mississippi HS Football Playoff Engine API.

Access tokens are issued by Auth0 (RS256, validated against Auth0's JWKS endpoint).
Roles and active status live in our own users table; get_current_user enriches the
decoded JWT payload with db_id and role via a single DB lookup, lazy-provisioning
a new user row (role='user') on the first authenticated request from a given Auth0 sub.
"""

import json
import os
import time
import urllib.request
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2AuthorizationCodeBearer
from jose import JWTError, jwt

AUTH0_DOMAIN = os.environ["AUTH0_DOMAIN"]
AUTH0_AUDIENCE = os.environ["AUTH0_AUDIENCE"]
_ISSUER = f"https://{AUTH0_DOMAIN}/"
_ALGORITHMS = ["RS256"]

SESSION_SECRET_KEY = os.environ["SESSION_SECRET_KEY"]
_SESSION_ALGORITHM = "HS256"
SESSION_COOKIE_NAME = "session"
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24  # 24h, matches the Auth0 access token lifetime noted in README.md

_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 86400  # refresh cached keys every 24 hours


def _get_jwks() -> dict:
    """Fetch and cache Auth0's JSON Web Key Set. Refreshes every 24 hours."""
    global _jwks_cache, _jwks_fetched_at
    if _jwks_cache is None or time.monotonic() - _jwks_fetched_at > _JWKS_TTL:
        url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
            _jwks_cache = json.load(response)
        _jwks_fetched_at = time.monotonic()
    assert _jwks_cache is not None
    return _jwks_cache


def _get_userinfo(token: str) -> dict:
    """Fetch user profile from Auth0's /userinfo endpoint using the access token."""
    req = urllib.request.Request(
        f"https://{AUTH0_DOMAIN}/userinfo",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=5) as response:  # noqa: S310
        return json.load(response)


def _find_rsa_key(jwks: dict, kid: str) -> dict:
    """Return the RSA key matching kid, or empty dict if not found."""
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return {k: key[k] for k in ("kty", "kid", "use", "n", "e") if k in key}
    return {}


oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=f"https://{AUTH0_DOMAIN}/authorize?audience={AUTH0_AUDIENCE}&scope=openid%20profile%20email",
    tokenUrl=f"https://{AUTH0_DOMAIN}/oauth/token",
)
_optional_bearer = HTTPBearer(auto_error=False)


def _decode_auth0_token(token: str) -> dict:
    """Validate an Auth0 RS256 JWT against the JWKS; raise HTTP 401 on any failure."""
    try:
        header = jwt.get_unverified_header(
            token  # NOSONAR - kid extracted here solely to select the JWKS key; full signature+claims verification is done by jwt.decode() below
        )
        rsa_key = _find_rsa_key(_get_jwks(), header.get("kid", ""))
        if not rsa_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to find signing key",
            )
        return jwt.decode(
            token,
            rsa_key,
            algorithms=_ALGORITHMS,
            audience=AUTH0_AUDIENCE,
            issuer=_ISSUER,
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> dict:
    """Validate the Auth0 JWT, look up the user in our DB, and return an enriched payload.

    Lazy-provisions a new user row (role='user') on the first authenticated request.
    Raises HTTP 401 if the account has been deactivated.
    """
    from backend.api.db import get_conn  # local import avoids circular dependency

    payload = _decode_auth0_token(token)
    sub = payload["sub"]

    async with get_conn() as conn:
        row = await (
            await conn.execute(
                "SELECT id, role, is_active FROM users WHERE auth0_id = %s",
                (sub,),
            )
        ).fetchone()

        if row is None:
            userinfo = _get_userinfo(token)
            row = await (
                await conn.execute(
                    """
                    INSERT INTO users (auth0_id, email, display_name)
                    VALUES (%s, %s, %s)
                    RETURNING id, role, is_active
                    """,
                    (sub, userinfo.get("email", ""), userinfo.get("name", sub)),
                )
            ).fetchone()

    assert row is not None
    db_id, role, is_active = row
    if not is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
        )
    return {**payload, "db_id": db_id, "role": role}


# ---------------------------------------------------------------------------
# Composable role dependencies
# ---------------------------------------------------------------------------


def require_user(payload: Annotated[dict, Depends(get_current_user)]) -> dict:
    """Require any authenticated active user."""
    return payload


def require_moderator(payload: Annotated[dict, Depends(get_current_user)]) -> dict:
    """Require moderator or owner role; raise HTTP 403 for base users."""
    if payload.get("role") not in ("moderator", "owner"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Moderator access required",
        )
    return payload


def require_owner(payload: Annotated[dict, Depends(get_current_user)]) -> dict:
    """Require owner role; raise HTTP 403 for moderators and base users."""
    if payload.get("role") != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner access required",
        )
    return payload


# ---------------------------------------------------------------------------
# Annotated type aliases for route signatures
# ---------------------------------------------------------------------------

CurrentUser = Annotated[dict, Depends(require_user)]
ModeratorAuth = Annotated[dict, Depends(require_moderator)]
OwnerAuth = Annotated[dict, Depends(require_owner)]


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_optional_bearer)],
) -> dict | None:
    """Return the current user dict if a valid Bearer token is present, else None.

    Never raises — anonymous callers simply get None so that unauthenticated
    endpoints can still record a user_id when the client happens to be logged in.
    """
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials.credentials)
    except HTTPException:
        return None


OptionalUser = Annotated[dict | None, Depends(get_optional_user)]


def optional_user_id(current_user: dict | None) -> int | None:
    """Return ``current_user["db_id"]``, or ``None`` for an anonymous caller."""
    return current_user["db_id"] if current_user else None


# ---------------------------------------------------------------------------
# Session cookie (first-party alternative to Bearer for browser navigation,
# e.g. the Prefect UI link — browsers can't attach an Authorization header to
# a plain navigation/iframe request, but they do send cookies automatically)
# ---------------------------------------------------------------------------


def mint_session_token(db_id: int, role: str) -> str:
    """Sign a short-lived session token (HS256, app-owned secret) carrying db_id/role."""
    payload = {"db_id": db_id, "role": role, "exp": int(time.time()) + SESSION_COOKIE_MAX_AGE}
    return jwt.encode(payload, SESSION_SECRET_KEY, algorithm=_SESSION_ALGORITHM)


def _decode_session_token(token: str) -> dict | None:
    """Verify a session token; return its claims, or None if invalid/expired/tampered."""
    try:
        return jwt.decode(token, SESSION_SECRET_KEY, algorithms=[_SESSION_ALGORITHM])
    except JWTError:
        return None


async def get_moderator_via_cookie_or_bearer(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_optional_bearer)],
) -> dict:
    """Authorize via session cookie OR Bearer token — used by the nginx auth_request verify
    endpoint so both a first-party session cookie and the Bearer/ModHeader workaround work."""
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token:
        claims = _decode_session_token(session_token)
        if claims is not None and claims.get("role") in ("moderator", "owner"):
            return claims

    if credentials is not None:
        payload = await get_current_user(credentials.credentials)
        if payload.get("role") in ("moderator", "owner"):
            return payload
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Moderator access required")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Moderator authentication required (session cookie or Bearer token)",
    )


ModeratorCookieOrBearerAuth = Annotated[dict, Depends(get_moderator_via_cookie_or_bearer)]
