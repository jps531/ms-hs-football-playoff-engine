"""GET /api/v1/client-config: the public keys the site's pages read."""

import asyncio
from types import SimpleNamespace

from backend.api.routers import meta


def _request(docs_url="/docs"):
    """A stand-in request whose app serves Swagger UI at *docs_url* (None: not served)."""
    return SimpleNamespace(app=SimpleNamespace(docs_url=docs_url))


def test_reports_configured_keys(monkeypatch):
    """Every key set: all of them come back."""
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "secret")
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "site")
    monkeypatch.setenv("AUTH0_DOMAIN", "x.us.auth0.com")
    monkeypatch.setenv("AUTH0_AUDIENCE", "https://api")
    monkeypatch.setenv("AUTH0_SPA_CLIENT_ID", "spa")
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    monkeypatch.setenv("POSTHOG_DASHBOARD_URL", "https://us.posthog.com/project/1/web")
    config = asyncio.run(meta.get_client_config(_request()))
    assert config.model_dump() == {
        "api_docs_url": "/docs",
        "turnstile_site_key": "site",
        "auth0_domain": "x.us.auth0.com",
        "auth0_audience": "https://api",
        "auth0_client_id": "spa",
        "posthog_key": "phc_test",
        "posthog_dashboard_url": "https://us.posthog.com/project/1/web",
    }


def test_unconfigured_features_are_null(monkeypatch):
    """No Turnstile secret or SPA client: those come back null, and the secret never does."""
    monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "site")
    monkeypatch.delenv("AUTH0_SPA_CLIENT_ID", raising=False)
    monkeypatch.delenv("POSTHOG_PROJECT_KEY", raising=False)
    monkeypatch.delenv("POSTHOG_DASHBOARD_URL", raising=False)
    config = asyncio.run(meta.get_client_config(_request(None)))
    assert config.turnstile_site_key is None
    assert config.api_docs_url is None
    assert config.auth0_client_id is None
    assert config.posthog_key is None and config.posthog_dashboard_url is None  # no visit counts
    assert "secret" not in config.model_dump_json()
