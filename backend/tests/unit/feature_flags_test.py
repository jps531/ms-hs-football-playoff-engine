"""Feature flags: who sees a flag (backend/helpers/feature_flags.py), the owner's endpoints and what
GET /client-config tells a page (backend/api/routers/flags.py), the table (migration and init.sql), and
that the pages only check flags that are declared."""

import asyncio
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.api import auth
from backend.api.models.requests import SetFeatureFlagRequest
from backend.api.routers import flags
from backend.helpers import feature_flags

ROOT = Path(__file__).resolve().parents[3]
DECLARED = {"new_bracket": "The new bracket view", "dark_map": "The dark region map"}
WHEN = datetime(2026, 11, 9, 20, 0, tzinfo=UTC)


class FakeConn:
    """Answers each execute() with the next queued rows (for fetchall) or row (for fetchone), recording the SQL."""

    def __init__(self, *answers):
        """Queue *answers*, one per execute() call."""
        self.answers = list(answers)
        self.calls = []
        self._current = None

    async def execute(self, sql, params=()):
        """Record the call and make the next answer current."""
        self.calls.append((" ".join(sql.split()), params))
        self._current = self.answers.pop(0)
        return self

    async def fetchall(self):
        """The current answer's rows."""
        return self._current

    async def fetchone(self):
        """The current answer's row."""
        return self._current


def _use(monkeypatch, conn):
    """Make the flags router's get_conn yield *conn*."""

    @asynccontextmanager
    async def get_conn():
        """Yield the fake connection."""
        yield conn

    monkeypatch.setattr(flags, "get_conn", get_conn)


def _request(cookie=None):
    """A request, with the session cookie *cookie* if given."""
    headers = [(b"cookie", f"{auth.SESSION_COOKIE_NAME}={cookie}".encode())] if cookie else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "query_string": b""})


@pytest.fixture
def declared(monkeypatch):
    """Two flags declared in code."""
    monkeypatch.setattr(feature_flags, "FLAGS", dict(DECLARED))


@pytest.fixture
def role_now(monkeypatch):
    """The users table's role for the cookie's account (set .role; None: gone or deactivated)."""
    holder = type("Role", (), {"role": "owner"})()

    async def current_role(db_id):
        """The role today."""
        return holder.role

    monkeypatch.setattr(auth, "_current_role", current_role)
    return holder


# ------------------------------------------------------------------ who sees a flag


def test_everyone_sees_flags_on_and_the_owner_also_those_on_for_the_owner(declared):
    states = {"new_bracket": "owner", "dark_map": "on", "retired_flag": "on"}
    assert feature_flags.visible(states, owner=False) == ["dark_map"]
    assert feature_flags.visible(states, owner=True) == ["dark_map", "new_bracket"]


def test_a_flag_never_set_or_set_off_is_off_and_a_row_for_an_undeclared_flag_is_ignored(declared):
    assert feature_flags.visible({}, owner=True) == []
    assert feature_flags.visible({"new_bracket": "off", "retired_flag": "owner"}, owner=True) == []


def test_declared_names_are_lowercase_words_with_a_description():
    for name, description in feature_flags.FLAGS.items():
        assert feature_flags.NAME.match(name), name
        assert description.strip(), name


# ------------------------------------------------------------------ what client-config tells a page


def test_a_visitor_gets_the_flags_on_for_everyone(monkeypatch, declared, role_now):
    conn = FakeConn([("new_bracket", "owner"), ("dark_map", "on")])
    _use(monkeypatch, conn)
    assert asyncio.run(flags.features_for(_request())) == ["dark_map"]
    assert conn.calls == [("SELECT name, state FROM feature_flags WHERE state <> 'off'", ())]


def test_the_owners_browser_also_gets_the_flags_on_for_the_owner(monkeypatch, declared, role_now):
    _use(monkeypatch, FakeConn([("new_bracket", "owner"), ("dark_map", "on")]))
    cookie = auth.mint_session_token(1, "owner")
    assert asyncio.run(flags.features_for(_request(cookie))) == ["dark_map", "new_bracket"]


@pytest.mark.parametrize(
    ("cookie", "role"),
    [
        (lambda: auth.mint_session_token(1, "owner"), "moderator"),  # demoted since the cookie was set
        (lambda: auth.mint_session_token(1, "owner"), None),  # deactivated
        (lambda: auth.mint_session_token(2, "moderator"), "moderator"),
        (lambda: "not-a-token", "owner"),
    ],
)
def test_only_the_owner_now_gets_the_owners_flags(monkeypatch, declared, role_now, cookie, role):
    role_now.role = role
    _use(monkeypatch, FakeConn([("new_bracket", "owner")]))
    assert asyncio.run(flags.features_for(_request(cookie()))) == []


def test_no_flags_declared_means_no_database_query(monkeypatch):
    monkeypatch.setattr(feature_flags, "FLAGS", {})
    conn = FakeConn()
    _use(monkeypatch, conn)
    assert asyncio.run(flags.features_for(_request())) == [] and conn.calls == []


def test_a_database_that_cant_be_read_leaves_every_flag_off(monkeypatch, declared, caplog):
    @asynccontextmanager
    async def broken():
        """A database that's down."""
        raise OSError("connection refused")
        yield

    monkeypatch.setattr(flags, "get_conn", broken)
    assert asyncio.run(flags.features_for(_request())) == []
    assert "every flag counts as off" in caplog.text


# ------------------------------------------------------------------ the owner's endpoints


def test_the_list_has_every_declared_flag_with_its_state(monkeypatch, declared):
    _use(monkeypatch, FakeConn([("dark_map", "owner", WHEN), ("retired_flag", "on", WHEN)]))
    listed = asyncio.run(flags.list_feature_flags({"db_id": 1, "role": "owner"}))
    assert [f.model_dump() for f in listed] == [
        {"name": "dark_map", "description": "The dark region map", "state": "owner", "updated_at": WHEN},
        {"name": "new_bracket", "description": "The new bracket view", "state": "off", "updated_at": None},
    ]


def test_setting_a_flag_records_its_state_and_who_set_it(monkeypatch, declared):
    conn = FakeConn(("on", WHEN))
    _use(monkeypatch, conn)
    flag = asyncio.run(
        flags.set_feature_flag({"db_id": 1, "role": "owner"}, "new_bracket", SetFeatureFlagRequest(state="on"))
    )
    assert flag.state == "on" and flag.description == "The new bracket view" and flag.updated_at == WHEN
    sql, params = conn.calls[0]
    assert sql.startswith("INSERT INTO feature_flags") and "ON CONFLICT (name) DO UPDATE" in sql
    assert params == ("new_bracket", "on", 1)


def test_an_undeclared_flag_cant_be_set(monkeypatch, declared):
    conn = FakeConn()
    _use(monkeypatch, conn)
    with pytest.raises(HTTPException) as err:
        asyncio.run(flags.set_feature_flag({"db_id": 1}, "typo_flag", SetFeatureFlagRequest(state="on")))
    assert err.value.status_code == 404 and conn.calls == []


def test_a_flag_is_set_only_to_off_owner_or_on():
    with pytest.raises(ValueError):
        SetFeatureFlagRequest(state="everyone")


def test_the_endpoints_are_the_owners_alone():
    from backend.api.main import app

    routes = {(r.path, m): r for r in app.routes if r.path.startswith("/api/v1/feature-flags") for m in r.methods}
    assert set(routes) == {("/api/v1/feature-flags", "GET"), ("/api/v1/feature-flags/{name}", "PUT")}
    for route in routes.values():
        assert any(d.call is auth.require_owner for d in route.dependant.dependencies)


# ------------------------------------------------------------------ the table, and the pages' checks


def _table(sql):
    """The feature_flags table's statements in *sql*."""
    match = re.search(
        r"-- Feature flags \(backend/helpers.*?COMMENT ON COLUMN feature_flags\.updated_by IS [^\n]*\n", sql, re.S
    )
    assert match, "no feature_flags table"
    return match.group(0)


def test_init_sql_creates_the_table_the_migration_does():
    migration = (ROOT / "sql/migrations/0001_feature_flags.sql").read_text()
    assert _table(migration) == _table((ROOT / "sql/init.sql").read_text())
    assert "CHECK (state IN ('off', 'owner', 'on'))" in migration
    assert tuple(feature_flags.STATES) == ("off", "owner", "on")


def _checked_in_pages():
    """Every flag name the pages' code checks with feature("...")."""
    names = set()
    for path in (ROOT / "nginx/html/static/js").glob("*.js"):
        code = "\n".join(line for line in path.read_text().splitlines() if not line.lstrip().startswith("//"))
        names |= set(re.findall(r"\bfeature\(\s*[\"'`]([^\"'`]+)[\"'`]", code))
    return names


def test_every_flag_the_pages_check_is_declared_and_every_declared_flag_is_checked():
    """A typo'd name would be off forever, and a flag left declared after its check is removed is a toggle
    that does nothing; CONTRIBUTING.md, "Feature flags", says to remove both together."""
    checked = _checked_in_pages()
    assert checked <= set(feature_flags.FLAGS), checked - set(feature_flags.FLAGS)
    assert set(feature_flags.FLAGS) <= checked, set(feature_flags.FLAGS) - checked
