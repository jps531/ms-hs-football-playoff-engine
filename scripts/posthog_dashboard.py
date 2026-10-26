"""Create the "Site activity" dashboard in PostHog from the events docs/ANALYTICS.md lists.

Each panel is a bar chart of the last 30 days (the dashboard's date picker changes it), one bar per
class, region, team, link or game, biggest first. The counts are views and clicks, not people: one
person opening the same page twice counts twice.

Run it once, wherever Python 3 is, with a personal API key (never the project's phc_ key):

    POSTHOG_PERSONAL_API_KEY=phx_... python3 scripts/posthog_dashboard.py

The key needs the dashboard:write and insight:write scopes (PostHog: Settings → User → Personal API
keys). The project ID is read from POSTHOG_DASHBOARD_URL (.env.local's
https://us.posthog.com/project/<id>/web) or POSTHOG_PROJECT_ID. Nothing is changed if a dashboard
with this name already exists; delete it in PostHog first to rebuild it.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

HOST = os.environ.get("POSTHOG_HOST", "https://us.posthog.com")  # private API: us.posthog.com, not us.i.
DASHBOARD = "Site activity"
DESCRIPTION = (
    "Views and clicks, not people: opening the same page twice counts twice. Built by scripts/posthog_dashboard.py."
)

# Class and region from the page's path (/standings/4a/2, /brackets/4a). [0-9], not \d: a backslash
# in a SQL string literal is an escape.
CLASS_PATH = r"^/(standings|brackets)/[1-7]a"
CLASS_OF_PATH = "concat(extract(properties.$pathname, '^/(?:standings|brackets)/([1-7])a'), 'A')"
REGION_PATH = r"^/standings/[1-7]a/[0-9]+"
REGION_OF_PATH = (
    "concat('Region ', extract(properties.$pathname, '^/standings/[1-7]a/([0-9]+)'), '-', "
    "extract(properties.$pathname, '^/standings/([1-7])a'), 'A')"
)
# bracket_game_opened's game is the bracket's game id: "final", or "<N|S>-<round>-<index from the top>".
GAME_LABEL = (
    "concat(toString(properties.class), 'A ', properties.round, "
    "if(properties.game = 'final', '', concat(', ', if(startsWith(properties.game, 'N'), 'North', 'South'), "
    "' half, game ', toString(toInt(splitByChar('-', properties.game)[3]) + 1), ' from the top')))"
)


def events(event: str, name: str, where: str | None = None) -> dict:
    """One series: every *event*, optionally only those matching the SQL condition *where*."""
    node = {"kind": "EventsNode", "event": event, "custom_name": name, "math": "total"}
    if where:
        node["properties"] = [{"type": "hogql", "key": where}]
    return node


def bars(name: str, description: str, series: list[dict], breakdown: str, breakdown_type: str = "hogql") -> dict:
    """An insight: *series* counted over the last 30 days, one bar per *breakdown* value, biggest first."""
    return {
        "name": name,
        "description": description,
        "query": {
            "kind": "InsightVizNode",
            "source": {
                "kind": "TrendsQuery",
                "series": series,
                "dateRange": {"date_from": "-30d"},
                "interval": "day",
                "breakdownFilter": {"breakdown": breakdown, "breakdown_type": breakdown_type, "breakdown_limit": 25},
                "trendsFilter": {"display": "ActionsBarValue"},
            },
        },
    }


INSIGHTS = [
    bars(
        "Most viewed classes",
        "Standings and bracket page views, by class.",
        [events("$pageview", "Page views", f"match(properties.$pathname, '{CLASS_PATH}')")],
        CLASS_OF_PATH,
    ),
    bars(
        "Most viewed regions",
        "Region standings page views, by region.",
        [events("$pageview", "Page views", f"match(properties.$pathname, '{REGION_PATH}')")],
        REGION_OF_PATH,
    ),
    bars(
        "Most picked teams",
        "Teams picked in the standings or a bracket game, or chosen from the search box.",
        [events("team_picked", "Picked"), events("team_search_used", "Searched")],
        "team",
        "event",
    ),
    bars(
        "Front page links followed",
        "Where front-page clicks went, by the part of the page the link was in.",
        [events("home_link_clicked", "Clicks")],
        "concat(coalesce(properties.section, '?'), ' → ', properties.to)",
    ),
    bars(
        "Scenario groups opened",
        "Folded scenario groups opened, by heading (groups that start open aren't counted).",
        [events("scenarios_opened", "Opened")],
        "section",
        "event",
    ),
    bars(
        "Most viewed brackets",
        "Bracket page views, by class.",
        [events("$pageview", "Page views", r"match(properties.$pathname, '^/brackets/[1-7]a')")],
        CLASS_OF_PATH,
    ),
    bars(
        "Most opened bracket games",
        "Bracket games opened, by class, round and slot.",
        [events("bracket_game_opened", "Opened")],
        GAME_LABEL,
    ),
]


def project_id() -> str:
    """The project ID, from POSTHOG_PROJECT_ID or the dashboard URL in POSTHOG_DASHBOARD_URL."""
    if os.environ.get("POSTHOG_PROJECT_ID"):
        return os.environ["POSTHOG_PROJECT_ID"]
    m = re.search(r"/project/(\d+)", os.environ.get("POSTHOG_DASHBOARD_URL", ""))
    if not m:
        sys.exit("Set POSTHOG_PROJECT_ID, or POSTHOG_DASHBOARD_URL as in .env.local.")
    return m.group(1)


def call(method: str, path: str, key: str, body: dict | None = None) -> dict:
    """One private-API request; exits with PostHog's message on an error."""
    req = urllib.request.Request(
        f"{HOST}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path}: HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")


def main() -> None:
    """Create the dashboard and its insights, unless the dashboard is already there."""
    key = os.environ.get("POSTHOG_PERSONAL_API_KEY")
    if not key:
        sys.exit("Set POSTHOG_PERSONAL_API_KEY (a personal API key with dashboard:write and insight:write).")
    base = f"/api/projects/{project_id()}"

    existing = call("GET", f"{base}/dashboards/?limit=200", key).get("results", [])
    if any(d.get("name") == DASHBOARD and not d.get("deleted") for d in existing):
        sys.exit(f'A dashboard named "{DASHBOARD}" already exists; delete it in PostHog to rebuild it.')

    dashboard = call("POST", f"{base}/dashboards/", key, {"name": DASHBOARD, "description": DESCRIPTION})
    for insight in INSIGHTS:
        call("POST", f"{base}/insights/", key, {**insight, "dashboards": [dashboard["id"]]})
        print(f"  added {insight['name']}")
    print(f"{HOST}/project/{project_id()}/dashboard/{dashboard['id']}")


if __name__ == "__main__":
    main()
