"""scripts/posthog_dashboard.py: the panels it builds, and that a second run updates rather than duplicates."""

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "posthog_dashboard", Path(__file__).resolve().parents[3] / "scripts" / "posthog_dashboard.py"
)
pd = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pd)

ANALYTICS = (Path(__file__).resolve().parents[3] / "docs" / "reference" / "ANALYTICS.md").read_text()


def _events(insight: dict) -> list[str]:
    """The events a panel counts."""
    return [s["event"] for s in insight["query"]["source"]["series"]]


def test_every_panel_counts_events_the_site_sends():
    """Each event a panel counts is one the analytics doc lists (so the site sends it)."""
    for insight in pd.INSIGHTS:
        for event in _events(insight):
            assert f"`{event}`" in ANALYTICS or event == "$pageview", (insight["name"], event)


def test_the_regions_page_has_its_panels():
    """The Regions page's six panels, each named once, the daily views as a line."""
    names = {i["name"] for i in pd.INSIGHTS}
    assert {
        "Regions page views by day",
        "Most viewed region maps",
        "What people do on the Regions page",
        "Teams looked up on the Regions page",
        "Regions opened from the Regions page",
        "Region map images shared",
    } <= names
    assert len(names) == len(pd.INSIGHTS)  # names are how a second run finds a panel, so they're unique
    daily = next(i for i in pd.INSIGHTS if i["name"] == "Regions page views by day")["query"]["source"]
    assert daily["trendsFilter"]["display"] == "ActionsLineGraph" and "breakdownFilter" not in daily


class _PostHog:
    """A stand-in for PostHog's private API: one project's dashboards and insights."""

    def __init__(self, dashboard: dict | None = None):
        self.dashboards = [dashboard] if dashboard else []
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method, path, key, body=None):
        self.calls.append((method, path))
        if method == "GET" and path.endswith("/dashboards/?limit=200"):
            return {"results": self.dashboards}
        if method == "GET" and "/dashboards/" in path:
            return self.dashboards[0]
        if method == "POST" and path.endswith("/dashboards/"):
            return {"id": 7, **body}
        return {"id": 99}


def test_a_first_run_creates_the_dashboard_and_every_panel(monkeypatch):
    """No dashboard yet: it's created, with every panel."""
    api = _PostHog()
    monkeypatch.setattr(pd, "call", api)
    assert pd.sync("/api/projects/1", "phx_test") == 7
    assert api.calls.count(("POST", "/api/projects/1/insights/")) == len(pd.INSIGHTS)


def test_a_later_run_updates_its_panels_and_adds_the_new_ones(monkeypatch):
    """Panels already there (by name) are updated in place; missing ones added; others left alone."""
    tiles = [
        {"insight": {"id": 11, "name": "Most viewed classes"}},
        {"insight": {"id": 12, "name": "Something added by hand"}},
    ]
    api = _PostHog({"id": 5, "name": pd.DASHBOARD, "tiles": tiles})
    monkeypatch.setattr(pd, "call", api)
    assert pd.sync("/api/projects/1", "phx_test") == 5
    assert ("PATCH", "/api/projects/1/insights/11/") in api.calls
    assert not any(path.endswith("/insights/12/") for _, path in api.calls)  # never touched, never removed
    assert api.calls.count(("POST", "/api/projects/1/insights/")) == len(pd.INSIGHTS) - 1
    assert not any(m == "DELETE" for m, _ in api.calls)


def test_it_needs_a_personal_key(monkeypatch):
    """Without a personal API key it stops before calling PostHog."""
    monkeypatch.delenv("POSTHOG_PERSONAL_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        pd.main()
