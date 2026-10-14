"""GET /api/v1/client-config: the public keys the site's pages read."""

import asyncio

from backend.api.routers import meta


def test_reports_configured_keys(monkeypatch):
    """Every key set: all four come back."""
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "secret")
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "site")
    monkeypatch.setenv("AUTH0_DOMAIN", "x.us.auth0.com")
    monkeypatch.setenv("AUTH0_AUDIENCE", "https://api")
    monkeypatch.setenv("AUTH0_SPA_CLIENT_ID", "spa")
    config = asyncio.run(meta.get_client_config())
    assert config.model_dump() == {
        "turnstile_site_key": "site",
        "auth0_domain": "x.us.auth0.com",
        "auth0_audience": "https://api",
        "auth0_client_id": "spa",
    }


def test_unconfigured_features_are_null(monkeypatch):
    """No Turnstile secret or SPA client: those come back null, and the secret never does."""
    monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "site")
    monkeypatch.delenv("AUTH0_SPA_CLIENT_ID", raising=False)
    config = asyncio.run(meta.get_client_config())
    assert config.turnstile_site_key is None
    assert config.auth0_client_id is None
    assert "secret" not in config.model_dump_json()
