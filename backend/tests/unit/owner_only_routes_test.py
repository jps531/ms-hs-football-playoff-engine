"""The public API serves what the site shows: win probabilities, rankings and what-ifs are the owner's."""

import asyncio
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.routing import APIRoute

from backend.api.auth import require_owner
from backend.api.main import app
from backend.api.models.responses import GameModel
from backend.api.routers import games

OWNER_ONLY = {
    ("GET", "/api/v1/games/probability"),
    ("GET", "/api/v1/games/upsets"),
    ("POST", "/api/v1/games/probability/live"),
    ("POST", "/api/v1/games/probability/overtime"),
    ("GET", "/api/v1/rankings/statewide"),
    ("GET", "/api/v1/rankings/{clazz}"),
    ("GET", "/api/v1/ratings"),
    ("GET", "/api/v1/ratings/movers"),
    ("GET", "/api/v1/ratings/{team}/trend"),
    ("POST", "/api/v1/standings/{clazz}/{region}/simulate"),
    ("POST", "/api/v1/standings/{clazz}/{region}/teams/{team}/simulate"),
    ("POST", "/api/v1/hosting/{clazz}/simulate"),
    ("POST", "/api/v1/hosting/{clazz}/{region}/simulate"),
    ("POST", "/api/v1/hosting/{clazz}/{region}/teams/{team}/simulate"),
    ("POST", "/api/v1/bracket/simulate"),
}

# What the site's pages and the share-card pipeline read: these stay open to everyone.
PUBLIC = {
    ("GET", "/api/v1/games"),
    ("GET", "/api/v1/standings/{clazz}/{region}"),
    ("GET", "/api/v1/standings/{clazz}"),
    ("GET", "/api/v1/hosting/{clazz}/{region}"),
    ("GET", "/api/v1/bracket"),
    ("GET", "/api/v1/bracket/matchups"),
    ("GET", "/api/v1/insights"),
}


def _routes():
    return {
        (method, r.path): r for r in app.routes if isinstance(r, APIRoute) for method in r.methods if method != "HEAD"
    }


def _owner_gated(route: APIRoute) -> bool:
    return any(d.dependency is require_owner for d in route.dependencies)


@pytest.mark.parametrize(("method", "path"), sorted(OWNER_ONLY))
def test_route_is_owner_only(method, path):
    routes = _routes()
    assert (method, path) in routes, f"{method} {path} no longer exists"
    assert _owner_gated(routes[(method, path)])


@pytest.mark.parametrize(("method", "path"), sorted(PUBLIC))
def test_site_routes_stay_public(method, path):
    assert not _owner_gated(_routes()[(method, path)])


def _game(**probs) -> GameModel:
    return GameModel(
        game_id=1,
        season=2026,
        date=date(2026, 10, 30),
        team_a="A",
        team_b="B",
        score_a=None,
        score_b=None,
        location_a=None,
        is_region_game=True,
        status="scheduled",
        final=False,
        **probs,
    )


@asynccontextmanager
async def _no_db():
    class _Conn:
        async def execute(self, *_a, **_k):
            class _Rows:
                def __aiter__(self):
                    return self

                async def __anext__(self):
                    raise StopAsyncIteration

            return _Rows()

    yield _Conn()


@pytest.mark.parametrize(("viewer", "shown"), [(None, False), ({"role": "moderator"}, False), ({"role": "owner"}, True)])
def test_games_win_probabilities_are_the_owners(viewer, shown):
    """``/games`` keeps its schedule and scores public but blanks the win probabilities for everyone but the owner."""
    game = _game(pregame_prob=0.7, live_prob=0.8, prob_as_of=None)
    with patch.object(games, "get_conn", _no_db), patch.object(games, "build_game_models", return_value=[game]):
        out = asyncio.run(games.list_games(season=2026, viewer=viewer))
    assert (out[0].pregame_prob, out[0].live_prob) == ((0.7, 0.8) if shown else (None, None))
