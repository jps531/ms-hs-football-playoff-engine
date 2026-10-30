"""Flood guards on the feedback form's endpoints (backend.api.routers.submissions) and the limiter's key.

Mocks get_conn with a FakeConn that answers each query in order, as in moderation_router_test.py.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.api import turnstile
from backend.api.limiter import client_ip
from backend.api.models.requests import SubmitDateRequest, SubmitFeedbackRequest, SubmitScoreRequest
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
    """New feedback is stored with its category and the page it came from."""
    conn = FakeConn([None, (3,), (41, SUBMITTED)])  # no repeat, 3 in the last hour, then the insert
    with _patch_conn(conn):
        res = _call(submissions.submit_feedback(_request(), _feedback(page="/standings/3a/6?team=raleigh")))
    assert (res.id, res.type) == (41, "feedback")
    insert_sql, insert_params = conn.calls[-1]
    assert "INSERT INTO submissions" in insert_sql
    assert '"category": "odds"' in insert_params[3] and '"page": "/standings/3a/6?team=raleigh"' in insert_params[3]


def test_a_repeat_of_pending_feedback_returns_the_original():
    """The same feedback sent again while the first is pending returns the first, storing nothing new."""
    conn = FakeConn([(17, SUBMITTED)])
    with _patch_conn(conn):
        res = _call(submissions.submit_feedback(_request(), _feedback()))
    assert res.id == 17
    assert not any("INSERT" in sql for sql, _ in conn.calls)


def test_a_flooded_queue_refuses_new_reports():
    """Past the hourly limit of pending reports: 503 with Retry-After, and nothing stored."""
    conn = FakeConn([None, (submissions._MAX_PENDING_PER_HOUR,)])
    with _patch_conn(conn), pytest.raises(HTTPException) as err:
        _call(submissions.submit_feedback(_request(), _feedback()))
    assert err.value.status_code == 503
    assert err.value.headers == {"Retry-After": "900"}
    assert not any("INSERT" in sql for sql, _ in conn.calls)


def test_a_filled_honeypot_looks_accepted_but_stores_nothing():
    """Feedback or a score correction with the honeypot filled gets a normal-looking reply and stores nothing."""
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
    """A score correction goes through the same repeat and flood checks and is stored with its note."""
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
        patch.object(submissions, "require_game_id", AsyncMock(return_value=77)),
    ):
        res = _call(submissions.submit_score(_request(), body))
    assert (res.id, res.school) == (52, "Raleigh")
    assert '"note": "Final was 28-21"' in conn.calls[-1][1][3]
    assert '"game_id": 77' in conn.calls[-1][1][3]  # finds the game if its date changes before review


def test_a_score_for_a_game_not_yet_played_is_refused():
    """A game's score can be reported from its day on (Mississippi time), even before it has one."""
    conn = FakeConn([])
    body = SubmitScoreRequest(school="Raleigh", date=date(2099, 10, 9), points_for=28, points_against=21)
    with (
        _patch_conn(conn),
        patch.object(submissions, "require_school_exists"),
        patch.object(submissions, "require_game_id", AsyncMock(return_value=77)),
        pytest.raises(HTTPException) as exc,
    ):
        _call(submissions.submit_score(_request(), body))
    assert (exc.value.status_code, exc.value.detail) == (422, "That game hasn’t been played yet")
    assert conn.calls == []


def _date_report(conn, **kw):
    """Send a date report through the router with the school/game checks patched out (game 77)."""
    body = SubmitDateRequest(**{"school": "Raleigh", "date": date(2026, 10, 9), "new_date": date(2026, 10, 10), **kw})
    with (
        _patch_conn(conn),
        patch.object(submissions, "require_school_exists"),
        patch.object(submissions, "require_game_id", AsyncMock(return_value=77)),
    ):
        return _call(submissions.submit_date(_request(), body))


def test_a_date_report_is_stored_with_the_game_and_both_dates():
    # season lookup, no repeat, quiet hour, insert
    conn = FakeConn([(2026,), None, (0,), (53, SUBMITTED)])
    res = _date_report(conn, note="Moved for weather")
    assert (res.id, res.type, res.school) == (53, "date", "Raleigh")
    stored = conn.calls[-1][1][3]
    assert '"game_id": 77' in stored and '"date": "2026-10-09"' in stored and '"new_date": "2026-10-10"' in stored


@pytest.mark.parametrize(
    ("new_date", "season", "detail"),
    [
        (date(2026, 10, 9), None, "That’s the date we have. Change it to the right date."),
        (date(2027, 10, 9), (2026,), "The new date has to be in the same season as the game."),
    ],
    ids=["same date", "another season"],
)
def test_a_date_report_needs_a_new_date_in_the_games_season(new_date, season, detail):
    conn = FakeConn([season] if season else [])
    with pytest.raises(HTTPException) as exc:
        _date_report(conn, new_date=new_date)
    assert (exc.value.status_code, exc.value.detail) == (422, detail)
    assert not any("INSERT" in sql for sql, _ in conn.calls)


def test_limits_key_on_the_visitor_not_on_nginx():
    """Behind nginx every request comes from nginx's address; X-Real-IP carries the visitor's."""
    assert client_ip(_request({"X-Real-IP": "203.0.113.9"})) == "203.0.113.9"
    assert client_ip(_request({"X-Real-IP": "  "})) == "172.18.0.5"
    assert client_ip(_request()) == "172.18.0.5"


def test_form_fields_are_validated():
    """A bad email, a page on another site, or an unknown category is refused; blank email and page are fine."""
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


# ------------------------------------------------------------- logo and helmet uploads
# The files are checked (type, size, and what the bytes really are) before anything is stored,
# so a refused file leaves no submission without an image in the moderation queue.


def _upload(contents: bytes, content_type: str = "image/png", name: str = "logo.png"):
    """An uploaded file as FastAPI hands it to the endpoint."""
    import io

    from fastapi import UploadFile
    from starlette.datastructures import Headers

    return UploadFile(io.BytesIO(contents), filename=name, headers=Headers({"content-type": content_type}))


def _png() -> bytes:
    """A real, tiny PNG."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


class _Stored:
    """Patches what the upload endpoints store and upload; records what happened."""

    def __init__(self):
        self.inserted: list[tuple] = []
        self.uploaded: list[str] = []

    def __enter__(self):
        async def ok(*args, **kwargs):
            """The school exists; the account is under its cap."""

        async def insert(conn, stype, school, user_id, payload):
            """Store the submission; return its id and time."""
            self.inserted.append((stype, school, user_id))
            return 41, SUBMITTED

        async def update(conn, submission_id, payload):
            """Record the image paths on the submission."""

        async def upload(file, fn):
            """Stand in for Cloudinary: read the file and return a path."""
            await file.read()
            self.uploaded.append(file.filename)
            return f"staged/{file.filename}"

        self._patches = [
            patch.object(submissions, "require_school_exists", ok),
            patch.object(submissions, "_require_under_account_cap", ok),
            patch.object(submissions, "insert_submission", insert),
            patch.object(submissions, "update_submission_payload", update),
            patch.object(submissions, "save_and_upload", upload),
            _patch_conn(FakeConn([])),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()
        return False


USER = {"db_id": 7, "role": "user"}


def test_a_logo_that_is_a_real_image_is_stored_and_uploaded():
    """A real PNG: one pending logo submission, then its image is uploaded."""
    with _Stored() as stored:
        out = _call(submissions.submit_logo(_request(), USER, "Raleigh", "primary", _upload(_png())))
    assert out.id == 41 and stored.inserted == [("logo", "Raleigh", 7)] and stored.uploaded == ["logo.png"]


@pytest.mark.parametrize(
    ("contents", "content_type"),
    [
        (b"<html><script>alert(1)</script></html>", "image/png"),  # a page renamed .png
        (b"%PDF-1.7", "application/pdf"),  # not an image type at all
        (b"", "image/png"),  # empty
    ],
)
def test_a_logo_that_isnt_an_allowed_image_is_refused_before_anything_is_stored(contents, content_type):
    """422, and no submission row: the moderation queue never gets an entry with no image."""
    with _Stored() as stored:
        with pytest.raises(HTTPException) as err:
            _call(submissions.submit_logo(_request(), USER, "Raleigh", "primary", _upload(contents, content_type)))
    assert err.value.status_code == 422
    assert stored.inserted == [] and stored.uploaded == []


def test_an_oversized_logo_is_refused_before_anything_is_stored():
    """Past the size limit: 422, nothing stored."""
    from backend.helpers.image_helpers import MAX_UPLOAD_FILE_BYTES

    big = _png() + b"\0" * MAX_UPLOAD_FILE_BYTES
    with _Stored() as stored:
        with pytest.raises(HTTPException) as err:
            _call(submissions.submit_logo(_request(), USER, "Raleigh", "primary", _upload(big)))
    assert err.value.status_code == 422 and stored.inserted == []


def _helmet_form():
    """The helmet form's text fields."""
    return submissions._HelmetForm(school="Raleigh", year_first_worn=2024, description="Gold shell, black mask")


def test_a_helmet_with_one_bad_image_among_good_ones_stores_nothing():
    """Every file is checked first, so a bad third image doesn't leave a submission with two."""
    images = [_upload(_png(), name="a.png"), _upload(_png(), name="b.png"), _upload(b"<svg onload=x>", name="c.png")]
    with _Stored() as stored:
        with pytest.raises(HTTPException) as err:
            _call(submissions.submit_helmet(_request(), USER, _helmet_form(), images, [], None))
    assert err.value.status_code == 422 and stored.inserted == [] and stored.uploaded == []


def test_a_helmet_with_good_images_and_a_logo_uploads_each():
    """All real images: one submission, every image and the logo uploaded."""
    images = [_upload(_png(), name="left.png"), _upload(_png(), name="right.png")]
    with _Stored() as stored:
        _call(
            submissions.submit_helmet(
                _request(), USER, _helmet_form(), images, ["left", "right"], _upload(_png(), name="logo.png")
            )
        )
    assert stored.inserted == [("helmet", "Raleigh", 7)]
    assert stored.uploaded == ["left.png", "right.png", "logo.png"]


@pytest.mark.parametrize(
    ("count", "labels", "detail"),
    [(6, [], "At most 5 images"), (2, ["left"], "same length"), (1, ["sideways"], "Invalid image label")],
)
def test_helmet_image_limits_and_labels_are_checked_first(count, labels, detail):
    """Too many images, labels that don't line up, or an unknown label: 422 before any database work."""
    images = [_upload(_png(), name=f"{i}.png") for i in range(count)]
    with _Stored() as stored:
        with pytest.raises(HTTPException) as err:
            _call(submissions.submit_helmet(_request(), USER, _helmet_form(), images, labels, None))
    assert err.value.status_code == 422 and detail in err.value.detail and stored.inserted == []
