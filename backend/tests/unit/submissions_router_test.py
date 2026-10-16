"""Flood guards on the feedback form's endpoints (backend.api.routers.submissions) and the limiter's key.

Mocks get_conn with a FakeConn that answers each query in order, as in moderation_router_test.py.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.api import turnstile
from backend.api.limiter import client_ip
from backend.api.models.requests import SubmitFeedbackRequest, SubmitScoreRequest
from backend.api.routers import submissions


class FakeConn:
    """Records every query; each fetchone() pops the next queued result."""

    def __init__(self, results: list):
        """Queue the results fetchone() will return, in order."""
        self.calls: list[tuple[str, tuple]] = []
        self._results = list(results)

    async def execute(self, sql, params=()):
        """Record the call and return self, like psycopg's chained cursor."""
        self.calls.append((sql, params))
        return self

    async def fetchone(self):
        """Pop the next queued result."""
        return self._results.pop(0)


def _patch_conn(conn: FakeConn):
    """Patch the router's get_conn to yield *conn*."""

    @asynccontextmanager
    async def _get_conn():
        """Yield the fake connection."""
        yield conn

    return patch.object(submissions, "get_conn", _get_conn)


def _request(headers: dict[str, str] | None = None, client=("172.18.0.5", 5000)) -> Request:
    """A bare request for the limiter decorator (it only reads the client address and headers)."""
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(
        {"type": "http", "method": "POST", "path": "/", "headers": raw, "client": client, "query_string": b""}
    )


def _feedback(**kw) -> SubmitFeedbackRequest:
    """A feedback body with sensible defaults."""
    return SubmitFeedbackRequest(
        **{"subject": "Odds look off", "message": "Raleigh can't be 4th", "category": "odds", **kw}
    )


def _call(coro):
    """Run an endpoint coroutine; the limiter is disabled so tests don't share buckets."""
    submissions.limiter.enabled = False
    try:
        return asyncio.run(coro)
    finally:
        submissions.limiter.enabled = True


SUBMITTED = datetime(2026, 10, 14, 9, 30)


def test_new_feedback_is_queued_with_its_context():
    conn = FakeConn([None, (3,), (41, SUBMITTED)])  # no repeat, 3 in the last hour, then the insert
    with _patch_conn(conn):
        res = _call(submissions.submit_feedback(_request(), _feedback(page="/standings/3a/6?team=raleigh")))
    assert (res.id, res.type) == (41, "feedback")
    insert_sql, insert_params = conn.calls[-1]
    assert "INSERT INTO submissions" in insert_sql
    assert '"category": "odds"' in insert_params[3] and '"page": "/standings/3a/6?team=raleigh"' in insert_params[3]


def test_a_repeat_of_pending_feedback_returns_the_original():
    conn = FakeConn([(17, SUBMITTED)])
    with _patch_conn(conn):
        res = _call(submissions.submit_feedback(_request(), _feedback()))
    assert res.id == 17
    assert not any("INSERT" in sql for sql, _ in conn.calls)


def test_a_flooded_queue_refuses_new_reports():
    conn = FakeConn([None, (submissions._MAX_PENDING_PER_HOUR,)])
    with _patch_conn(conn), pytest.raises(HTTPException) as err:
        _call(submissions.submit_feedback(_request(), _feedback()))
    assert err.value.status_code == 503
    assert err.value.headers == {"Retry-After": "900"}
    assert not any("INSERT" in sql for sql, _ in conn.calls)


def test_a_filled_honeypot_looks_accepted_but_stores_nothing():
    conn = FakeConn([])
    with _patch_conn(conn):
        feedback = _call(submissions.submit_feedback(_request(), _feedback(website="http://spam.example")))
        score = _call(
            submissions.submit_score(
                _request(),
                SubmitScoreRequest(
                    school="Raleigh", date=date(2026, 10, 9), points_for=21, points_against=14, website="x"
                ),
            )
        )
    assert feedback.id == 0 and score.id == 0
    assert conn.calls == []


def test_score_corrections_go_through_the_same_guard():
    # (the school/game existence checks are patched out) no repeat, quiet hour, insert
    conn = FakeConn([None, (0,), (52, SUBMITTED)])
    body = SubmitScoreRequest(
        school="Raleigh",
        date=date(2026, 10, 9),
        points_for=28,
        points_against=21,
        note="Final was 28-21",
        page="/standings/3a/6",
    )
    with (
        _patch_conn(conn),
        patch.object(submissions, "require_school_exists"),
        patch.object(submissions, "require_game_exists"),
    ):
        res = _call(submissions.submit_score(_request(), body))
    assert (res.id, res.school) == (52, "Raleigh")
    assert '"note": "Final was 28-21"' in conn.calls[-1][1][3]


def test_limits_key_on_the_visitor_not_on_nginx():
    """Behind nginx every request comes from nginx's address; X-Real-IP carries the visitor's."""
    assert client_ip(_request({"X-Real-IP": "203.0.113.9"})) == "203.0.113.9"
    assert client_ip(_request({"X-Real-IP": "  "})) == "172.18.0.5"
    assert client_ip(_request()) == "172.18.0.5"


def test_form_fields_are_validated():
    with pytest.raises(ValueError):
        _feedback(email="not-an-email")
    with pytest.raises(ValueError):
        _feedback(page="https://elsewhere.example/")
    with pytest.raises(ValueError):
        _feedback(category="spam")
    assert _feedback(email="", page="").email == ""


def test_a_failed_turnstile_check_stores_nothing(monkeypatch):
    """With Turnstile on, a missing token is refused before the queue is touched."""
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "secret")
    conn = FakeConn([])
    with _patch_conn(conn), pytest.raises(HTTPException) as err:
        _call(submissions.submit_feedback(_request(), _feedback()))
    assert err.value.status_code == 403
    assert conn.calls == []


def test_a_passed_turnstile_check_is_queued(monkeypatch):
    """A token Cloudflare accepts goes on to the usual guard, checked against the visitor's address."""
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "secret")
    seen = []
    monkeypatch.setattr(turnstile, "_siteverify", lambda s, t, ip: seen.append((t, ip)) or {"success": True})
    conn = FakeConn([None, (0,), (42, SUBMITTED)])
    with _patch_conn(conn):
        res = _call(
            submissions.submit_feedback(_request({"X-Real-IP": "203.0.113.9"}), _feedback(turnstile_token="tok"))
        )
    assert res.id == 42
    assert seen == [("tok", "203.0.113.9")]
    assert "turnstile" not in conn.calls[-1][1][-1]  # the stored payload (JSON text)


def test_the_honeypot_answers_before_turnstile(monkeypatch):
    """A bot that fills the honeypot gets the fake success, not a 403 that tells it what to fix."""
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "secret")
    res = _call(submissions.submit_feedback(_request(), _feedback(website="spam")))
    assert res.id == 0


# --------------------------------------------- signed-in asset and data endpoints


@pytest.mark.parametrize("path", ["/logos", "/helmets", "/colors", "/locations", "/helmet-assignments"])
def test_asset_and_data_endpoints_need_a_signed_in_account(path):
    """Each depends on CurrentUser (a valid Auth0 token), not the optional user the forms take."""
    from backend.api.auth import require_user

    route = next(r for r in submissions.router.routes if r.path == f"/api/v1/submissions{path}")
    deps = {d.call for d in route.dependant.dependencies}
    assert require_user in deps


@pytest.mark.parametrize("path", ["/feedback", "/scores"])
def test_the_feedback_form_stays_open_to_anonymous_visitors(path):
    """The site's own form posts without signing in."""
    from backend.api.auth import require_user

    route = next(r for r in submissions.router.routes if r.path == f"/api/v1/submissions{path}")
    assert require_user not in {d.call for d in route.dependant.dependencies}


def test_an_account_under_the_daily_cap_may_submit():
    """Below the cap nothing is raised, and the count is scoped to that account and those types."""
    conn = FakeConn([(submissions._MAX_PER_ACCOUNT_PER_DAY - 1,)])
    asyncio.run(submissions._require_under_account_cap(conn, 7))
    sql, params = conn.calls[0]
    assert "user_id = %s" in sql and params[0] == 7
    assert set(params[1]) == {"logo", "helmet", "colors", "location", "helmet_assignment"}


def test_an_account_at_the_daily_cap_is_refused():
    """At the cap: 429."""
    conn = FakeConn([(submissions._MAX_PER_ACCOUNT_PER_DAY,)])
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(submissions._require_under_account_cap(conn, 7))
    assert exc_info.value.status_code == 429
