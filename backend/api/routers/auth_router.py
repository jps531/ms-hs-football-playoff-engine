"""Auth endpoints: internal nginx auth-check only.

Auth0 handles all user-facing authentication (login, registration,
password reset, token refresh, MFA). This router exists solely for the
nginx auth_request subrequest that gates the Prefect UI.
"""

from fastapi import APIRouter

from backend.api.auth import ModeratorAuth

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/verify-moderator", include_in_schema=False)
async def verify_moderator_for_nginx(_: ModeratorAuth) -> None:
    """Internal endpoint called by nginx auth_request to gate the Prefect UI.

    Returns 200 when the Bearer token is valid and the role is moderator or owner.
    FastAPI's ModeratorAuth dependency raises 401/403 automatically on failure.
    """
