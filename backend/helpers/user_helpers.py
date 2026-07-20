"""Authorization policy for owner-only user management endpoints."""

from fastapi import HTTPException


def assert_role_changeable(current_role: str) -> None:
    """Raise HTTP 409 if *current_role* is ``"owner"`` — the owner account's role is protected."""
    if current_role == "owner":
        raise HTTPException(status_code=409, detail="Cannot change the role of the owner account")


def assert_active_changeable(current_role: str, new_is_active: bool) -> None:
    """Raise HTTP 409 if this update would deactivate the owner account."""
    if current_role == "owner" and not new_is_active:
        raise HTTPException(status_code=409, detail="Cannot deactivate the owner account")
