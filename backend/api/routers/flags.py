"""Feature flags (backend/helpers/feature_flags.py): the owner lists and sets them on /moderate, and
GET /client-config tells each page the ones on for its viewer (``features_for``)."""

import logging

from fastapi import APIRouter, HTTPException, Request

from backend.api.auth import OwnerAuth, cookie_is_owner
from backend.api.db import get_conn
from backend.api.models.requests import SetFeatureFlagRequest
from backend.api.models.responses import FeatureFlagModel
from backend.helpers import feature_flags

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/feature-flags", tags=["feature flags"])


async def features_for(request: Request) -> list[str]:
    """The declared flags on for whoever sent *request*: those on for everyone, plus, with the owner's session
    cookie, those on for the owner. Empty, and logged, if the database can't be read: a page then shows what
    it shows with every flag off, rather than the config it also needs (sign-in, Turnstile) failing."""
    if not feature_flags.FLAGS:
        return []
    try:
        async with get_conn() as conn:
            rows = await (await conn.execute("SELECT name, state FROM feature_flags WHERE state <> 'off'")).fetchall()
        states = dict(rows)
        owner = "owner" in states.values() and await cookie_is_owner(request)
    except Exception:
        _log.exception("Couldn't read the feature flags; every flag counts as off")
        return []
    return feature_flags.visible(states, owner=owner)


@router.get("")
async def list_feature_flags(_: OwnerAuth) -> list[FeatureFlagModel]:
    """Every declared flag, with what it switches and its state (a flag never set is off). Owner only."""
    async with get_conn() as conn:
        rows = await (await conn.execute("SELECT name, state, updated_at FROM feature_flags")).fetchall()
    stored = {name: (state, updated_at) for name, state, updated_at in rows}
    return [
        FeatureFlagModel(
            name=name,
            description=description,
            state=stored.get(name, ("off", None))[0],
            updated_at=stored.get(name, ("off", None))[1],
        )
        for name, description in sorted(feature_flags.FLAGS.items())
    ]


@router.put("/{name}", responses={404: {"description": "No flag of that name is declared"}})
async def set_feature_flag(owner: OwnerAuth, name: str, body: SetFeatureFlagRequest) -> FeatureFlagModel:
    """Set a declared flag to off (nobody sees it), owner (only the owner) or on (everyone). Owner only;
    pages pick it up the next time they load."""
    if name not in feature_flags.FLAGS:
        raise HTTPException(status_code=404, detail=f"No feature flag named {name!r}")
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                """
                INSERT INTO feature_flags (name, state, updated_at, updated_by) VALUES (%s, %s, now(), %s)
                ON CONFLICT (name) DO UPDATE
                  SET state = EXCLUDED.state, updated_at = EXCLUDED.updated_at, updated_by = EXCLUDED.updated_by
                RETURNING state, updated_at
                """,
                (name, body.state, owner["db_id"]),
            )
        ).fetchone()
    _log.info("Feature flag %s set to %s by user %s", name, body.state, owner["db_id"])
    return FeatureFlagModel(name=name, description=feature_flags.FLAGS[name], state=row[0], updated_at=row[1])
