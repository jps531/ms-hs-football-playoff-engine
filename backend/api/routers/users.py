"""User profile, social features, and owner-level user management endpoints."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from psycopg import sql

from backend.api.auth import CurrentUser, OwnerAuth
from backend.api.db import get_conn
from backend.api.models.requests import PatchUserRequest, SetUserActiveRequest, SetUserRoleRequest
from backend.api.models.responses import (
    AttendedGameModel,
    SubmissionSummary,
    UserAdminRow,
    UserProfileResponse,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_user_row(conn, user_id: int) -> dict:
    """Fetch a full user row; raise 404 if not found."""
    row = await (
        await conn.execute(
            """
            SELECT id, email, display_name, phone, hometown, role, favorite_team,
                   is_active, created_at
            FROM users WHERE id = %s
            """,
            (user_id,),
        )
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return {
        "id": row[0],
        "email": row[1],
        "display_name": row[2],
        "phone": row[3],
        "hometown": row[4],
        "role": row[5],
        "favorite_team": row[6],
        "is_active": row[7],
        "created_at": row[8],
    }


async def _build_profile(conn, user: dict) -> UserProfileResponse:
    """Attach followed_teams and games_attended_count to a user dict."""
    followed_rows = await (
        await conn.execute(
            "SELECT school FROM user_followed_teams WHERE user_id = %s ORDER BY school",
            (user["id"],),
        )
    ).fetchall()
    count_row = await (
        await conn.execute(
            "SELECT COUNT(*) FROM user_attended_games WHERE user_id = %s",
            (user["id"],),
        )
    ).fetchone()
    assert count_row is not None
    return UserProfileResponse(
        **user,
        followed_teams=[r[0] for r in followed_rows],
        games_attended_count=count_row[0],
    )


# ---------------------------------------------------------------------------
# Own profile
# ---------------------------------------------------------------------------


@router.get("/me", responses={404: {"description": "User not found"}})
async def get_my_profile(current_user: CurrentUser) -> UserProfileResponse:
    """Return the authenticated user's full profile."""
    user_id: int = current_user["db_id"]
    async with get_conn() as conn:
        user = await _get_user_row(conn, user_id)
        return await _build_profile(conn, user)


@router.patch("/me", responses={404: {"description": "User not found"}})
async def patch_my_profile(body: PatchUserRequest, current_user: CurrentUser) -> UserProfileResponse:
    """Update mutable profile fields."""
    user_id: int = current_user["db_id"]
    updates = body.model_dump(exclude_none=True)
    if updates:
        set_clause = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(k)) for k in updates)
        query = sql.SQL("UPDATE users SET {}, updated_at = NOW() WHERE id = %s").format(set_clause)
        async with get_conn() as conn:
            await conn.execute(query, list(updates.values()) + [user_id])
    async with get_conn() as conn:
        user = await _get_user_row(conn, user_id)
        return await _build_profile(conn, user)


# ---------------------------------------------------------------------------
# Followed teams
# ---------------------------------------------------------------------------


@router.get("/me/followed-teams")
async def list_followed_teams(current_user: CurrentUser) -> list[str]:
    """Return the list of school names the authenticated user follows."""
    user_id: int = current_user["db_id"]
    async with get_conn() as conn:
        rows = await (
            await conn.execute(
                "SELECT school FROM user_followed_teams WHERE user_id = %s ORDER BY school",
                (user_id,),
            )
        ).fetchall()
    return [r[0] for r in rows]


@router.put(
    "/me/followed-teams/{school}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "School not found"}},
)
async def follow_team(school: str, current_user: CurrentUser) -> None:
    """Follow a team (idempotent)."""
    user_id: int = current_user["db_id"]
    async with get_conn() as conn:
        exists = await (await conn.execute("SELECT 1 FROM schools WHERE school = %s", (school,))).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail=f"School '{school}' not found")
        await conn.execute(
            "INSERT INTO user_followed_teams (user_id, school) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_id, school),
        )


@router.delete("/me/followed-teams/{school}", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_team(school: str, current_user: CurrentUser) -> None:
    """Unfollow a team."""
    user_id: int = current_user["db_id"]
    async with get_conn() as conn:
        await conn.execute(
            "DELETE FROM user_followed_teams WHERE user_id = %s AND school = %s",
            (user_id, school),
        )


# ---------------------------------------------------------------------------
# Attended games
# ---------------------------------------------------------------------------


@router.get("/me/attended-games")
async def list_attended_games(current_user: CurrentUser) -> list[AttendedGameModel]:
    """Return all games the authenticated user has marked as attended."""
    user_id: int = current_user["db_id"]
    async with get_conn() as conn:
        rows = await (
            await conn.execute(
                """
                SELECT uag.school, uag.date, g.opponent, g.result
                FROM user_attended_games uag
                JOIN games_effective g ON g.school = uag.school AND g.date = uag.date
                WHERE uag.user_id = %s
                ORDER BY uag.date DESC
                """,
                (user_id,),
            )
        ).fetchall()
    return [AttendedGameModel(school=r[0], date=r[1], opponent=r[2], result=r[3]) for r in rows]


@router.put(
    "/me/attended-games/{school}/{game_date}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Game not found"}},
)
async def mark_attended(school: str, game_date: date, current_user: CurrentUser) -> None:
    """Mark a game as attended (idempotent)."""
    user_id: int = current_user["db_id"]
    async with get_conn() as conn:
        exists = await (
            await conn.execute("SELECT 1 FROM games WHERE school = %s AND date = %s", (school, game_date))
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail=f"Game for '{school}' on {game_date} not found")
        await conn.execute(
            "INSERT INTO user_attended_games (user_id, school, date) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (user_id, school, game_date),
        )


@router.delete("/me/attended-games/{school}/{game_date}", status_code=status.HTTP_204_NO_CONTENT)
async def unmark_attended(school: str, game_date: date, current_user: CurrentUser) -> None:
    """Remove an attendance record."""
    user_id: int = current_user["db_id"]
    async with get_conn() as conn:
        await conn.execute(
            "DELETE FROM user_attended_games WHERE user_id = %s AND school = %s AND date = %s",
            (user_id, school, game_date),
        )


# ---------------------------------------------------------------------------
# Own submissions
# ---------------------------------------------------------------------------


@router.get("/me/submissions")
async def list_my_submissions(current_user: CurrentUser) -> list[SubmissionSummary]:
    """Return all submissions created by the authenticated user."""
    user_id: int = current_user["db_id"]
    async with get_conn() as conn:
        rows = await (
            await conn.execute(
                """
                SELECT id, type, status, school, submitted_at, reviewed_at
                FROM submissions WHERE user_id = %s ORDER BY submitted_at DESC
                """,
                (user_id,),
            )
        ).fetchall()
    return [
        SubmissionSummary(
            id=r[0],
            type=r[1],
            status=r[2],
            school=r[3],
            submitted_at=r[4],
            reviewed_at=r[5],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Owner-only user management
# ---------------------------------------------------------------------------


@router.get("/")
async def list_users(_: OwnerAuth) -> list[UserAdminRow]:
    """List all user accounts (owner only)."""
    async with get_conn() as conn:
        rows = await (
            await conn.execute(
                "SELECT id, email, display_name, role, is_active, created_at FROM users ORDER BY created_at DESC"
            )
        ).fetchall()
    return [
        UserAdminRow(
            id=r[0],
            email=r[1],
            display_name=r[2],
            role=r[3],
            is_active=r[4],
            created_at=r[5],
        )
        for r in rows
    ]


@router.patch(
    "/{user_id}/role",
    responses={404: {"description": "User not found"}, 409: {"description": "Cannot demote the only owner"}},
)
async def set_user_role(user_id: int, body: SetUserRoleRequest, _: OwnerAuth) -> UserAdminRow:
    """Promote or demote a user to moderator or user role (owner only)."""
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                "SELECT id, email, display_name, role, is_active, created_at FROM users WHERE id = %s",
                (user_id,),
            )
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        if row[3] == "owner":
            raise HTTPException(status_code=409, detail="Cannot change the role of the owner account")
        updated = await (
            await conn.execute(
                "UPDATE users SET role = %s, updated_at = NOW() WHERE id = %s "
                "RETURNING id, email, display_name, role, is_active, created_at",
                (body.role, user_id),
            )
        ).fetchone()
    assert updated is not None
    return UserAdminRow(
        id=updated[0],
        email=updated[1],
        display_name=updated[2],
        role=updated[3],
        is_active=updated[4],
        created_at=updated[5],
    )


@router.patch(
    "/{user_id}/active",
    responses={404: {"description": "User not found"}, 409: {"description": "Cannot deactivate the owner"}},
)
async def set_user_active(user_id: int, body: SetUserActiveRequest, _: OwnerAuth) -> UserAdminRow:
    """Activate or deactivate a user account (owner only)."""
    async with get_conn() as conn:
        row = await (await conn.execute("SELECT role FROM users WHERE id = %s", (user_id,))).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        if row[0] == "owner" and not body.is_active:
            raise HTTPException(status_code=409, detail="Cannot deactivate the owner account")
        updated = await (
            await conn.execute(
                "UPDATE users SET is_active = %s, updated_at = NOW() WHERE id = %s "
                "RETURNING id, email, display_name, role, is_active, created_at",
                (body.is_active, user_id),
            )
        ).fetchone()
    assert updated is not None
    return UserAdminRow(
        id=updated[0],
        email=updated[1],
        display_name=updated[2],
        role=updated[3],
        is_active=updated[4],
        created_at=updated[5],
    )
