"""Cloudflare Turnstile verification (backend.api.turnstile)."""

import asyncio
import urllib.error

import pytest
from fastapi import HTTPException

from backend.api import turnstile


def _verify(token, ip="203.0.113.9"):
    """Run verify_turnstile to completion."""
    return asyncio.run(turnstile.verify_turnstile(token, ip))


@pytest.fixture
def enabled(monkeypatch):
    """Turn Turnstile on with a test secret."""
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "secret")
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "site")


def test_off_without_a_secret(monkeypatch):
    """No secret: nothing is checked and the browser gets no site key."""
    monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "site")
    assert _verify(None) is None
    assert turnstile.turnstile_site_key() is None


def test_site_key_when_on(enabled):
    """With both keys set, the page gets the site key."""
    assert turnstile.turnstile_site_key() == "site"


def test_missing_token_is_refused(enabled, monkeypatch):
    """No token never reaches Cloudflare."""
    monkeypatch.setattr(turnstile, "_siteverify", lambda *a: pytest.fail("should not call siteverify"))
    with pytest.raises(HTTPException) as err:
        _verify("")
    assert err.value.status_code == 403


def test_passing_token(enabled, monkeypatch):
    """Cloudflare's success lets the submission through, with the secret and visitor address sent."""
    calls = []
    monkeypatch.setattr(turnstile, "_siteverify", lambda *a: calls.append(a) or {"success": True})
    assert _verify("tok") is None
    assert calls == [("secret", "tok", "203.0.113.9")]


def test_failing_token_is_refused(enabled, monkeypatch):
    """A rejected (or reused) token is a 403."""
    monkeypatch.setattr(
        turnstile, "_siteverify", lambda *a: {"success": False, "error-codes": ["timeout-or-duplicate"]}
    )
    with pytest.raises(HTTPException) as err:
        _verify("tok")
    assert err.value.detail == turnstile.CHECK_FAILED


@pytest.mark.parametrize("exc", [urllib.error.URLError("down"), TimeoutError(), ValueError("bad json")])
def test_cloudflare_outage_fails_closed(enabled, monkeypatch, exc):
    """If siteverify can't answer, the submission is refused with 503 and a retry hint, not waved through."""

    def boom(*a):
        """Simulate the outage."""
        raise exc

    monkeypatch.setattr(turnstile, "_siteverify", boom)
    with pytest.raises(HTTPException) as err:
        _verify("tok")
    assert err.value.status_code == 503
    assert err.value.headers == {"Retry-After": "120"}


@pytest.mark.parametrize(
    ("origin", "reported", "ok"),
    [
        ("https://mshsfootball.com", "mshsfootball.com", True),
        ("https://mshsfootball.com", "www.mshsfootball.com", True),
        ("https://mshsfootball.com", "evil.example", False),
        ("*", "evil.example", True),  # local: no origin to check against
        ("https://mshsfootball.com", None, True),  # older responses without a hostname
    ],
)
def test_token_must_be_solved_on_this_site(enabled, monkeypatch, origin, reported, ok):
    """A token from another site's widget is refused once FRONTEND_ORIGIN names ours."""
    monkeypatch.setenv("FRONTEND_ORIGIN", origin)
    monkeypatch.setattr(turnstile, "_siteverify", lambda *a: {"success": True, "hostname": reported})
    if ok:
        assert _verify("tok") is None
    else:
        with pytest.raises(HTTPException) as err:
            _verify("tok")
        assert err.value.status_code == 403


def test_missing_secret_outside_local_is_logged(monkeypatch, caplog):
    """Production without a secret still works, but says so loudly."""
    monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert _verify(None) is None
    assert "TURNSTILE_SECRET_KEY" in caplog.text
