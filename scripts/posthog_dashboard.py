"""Create or update the "Site activity" dashboard in PostHog from the events docs/reference/ANALYTICS.md lists.

Each panel shows the last 30 days (the dashboard's date picker changes it): bar charts with one bar per
class, region, team, link or game, biggest first, and a line of the Regions page's views by day. The
counts are views and clicks, not people: one person opening the same page twice counts twice.

Run it once, wherever Python 3 is, with a personal API key (never the project's phc_ key):

    POSTHOG_PERSONAL_API_KEY=phx_... python3 scripts/posthog_dashboard.py

The key needs the dashboard:write and insight:write scopes (PostHog: Settings → User → Personal API
keys). The project ID is read from POSTHOG_DASHBOARD_URL (.env.local's
https://us.posthog.com/project/<id>/web) or POSTHOG_PROJECT_ID.

Run it again after the panels below change: it creates the dashboard if there's none, adds the panels
it doesn't have, and updates the ones it has (matched by name). It never removes a panel, so one you
added in PostHog, or one this script no longer lists, stays.
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
# The Regions page (/regions/5a): its class, from the path.
REGIONS_PATH = r"^/regions/[1-7]a"
CLASS_OF_REGIONS_PATH = "concat(extract(properties.$pathname, '^/regions/([1-7])a'), 'A')"
FROM_REGIONS = "properties.from = 'regions'"
# regions_region_opened: "Region 2-5A".
REGION_OPENED = "concat('Region ', toString(properties.region), '-', toString(properties.class), 'A')"

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


def bars(name: str, description: str, series: list[dict], breakdown: str | None, breakdown_type: str = "hogql") -> dict:
    """An insight: *series* counted over the last 30 days, one bar per *breakdown* value, biggest first
    (without a breakdown, one bar per series)."""
    source = {
        "kind": "TrendsQuery",
        "series": series,
        "dateRange": {"date_from": "-30d"},
        "interval": "day",
        "trendsFilter": {"display": "ActionsBarValue"},
    }
    if breakdown:
        source["breakdownFilter"] = {"breakdown": breakdown, "breakdown_type": breakdown_type, "breakdown_limit": 25}
    return {"name": name, "description": description, "query": {"kind": "InsightVizNode", "source": source}}


def daily(name: str, description: str, series: list[dict]) -> dict:
    """An insight: *series* counted each day over the last 30 days, as lines."""
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
                "trendsFilter": {"display": "ActionsLineGraph"},
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
    # The Regions page (the region maps).
    daily(
        "Regions page views by day",
        "Views of the Regions pages (/regions/1a … /regions/7a), each day.",
        [events("$pageview", "Page views", f"match(properties.$pathname, '{REGIONS_PATH}')")],
    ),
    bars(
        "Most viewed region maps",
        "Regions page views, by class.",
        [events("$pageview", "Page views", f"match(properties.$pathname, '{REGIONS_PATH}')")],
        CLASS_OF_REGIONS_PATH,
    ),
    bars(
        "What people do on the Regions page",
        "Moving the map (counted once a page), picking a team on the map or in the lists, finding one, "
        "opening a region's standings, changing the season, and sharing.",
        [
            events("regions_map_moved", "Moved the map"),
            events("team_picked", "Picked a team on the map", f"{FROM_REGIONS} AND properties.via = 'map'"),
            events("team_picked", "Picked a team in the lists", f"{FROM_REGIONS} AND properties.via = 'list'"),
            events("team_search_used", "Found a team", FROM_REGIONS),
            events("regions_region_opened", "Opened a region's standings"),
            events("regions-season_changed", "Changed the season"),
            events("regions_share_opened", "Opened Share"),
            events("regions_image_shared", "Shared an image"),
        ],
        None,
    ),
    bars(
        "Teams looked up on the Regions page",
        "Teams picked on the map or in the lists, or found with the map's search.",
        [events("team_picked", "Picked", FROM_REGIONS), events("team_search_used", "Searched", FROM_REGIONS)],
        "team",
        "event",
    ),
    bars(
        "Regions opened from the Regions page",
        "Region headings followed to their standings, by region.",
        [events("regions_region_opened", "Opened")],
        REGION_OPENED,
    ),
    bars(
        "Region map images shared",
        "Regions page images shared, downloaded or linked, by image: the class's map (class), its two "
        "seasons side by side (class-compare), a team's region (team), or a team's two regions (compare).",
        [events("regions_image_shared", "Shared")],
        "image",
        "event",
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


def sync(base: str, key: str) -> int:
    """Create the dashboard if it's missing, add the panels it lacks and update the ones it has (by
    name). Returns the dashboard's id."""
    existing = call("GET", f"{base}/dashboards/?limit=200", key).get("results", [])
    found = next((d for d in existing if d.get("name") == DASHBOARD and not d.get("deleted")), None)
    if found is None:
        dashboard = call("POST", f"{base}/dashboards/", key, {"name": DASHBOARD, "description": DESCRIPTION})
        print(f"  created the {DASHBOARD} dashboard")
        on_it: dict[str, int] = {}
    else:
        dashboard = call("GET", f"{base}/dashboards/{found['id']}/", key)
        on_it = {
            tile["insight"]["name"]: tile["insight"]["id"]
            for tile in dashboard.get("tiles", [])
            if tile.get("insight") and not tile["insight"].get("deleted") and tile["insight"].get("name")
        }
    for insight in INSIGHTS:
        if insight["name"] in on_it:
            call("PATCH", f"{base}/insights/{on_it[insight['name']]}/", key, insight)
            print(f"  updated {insight['name']}")
        else:
            call("POST", f"{base}/insights/", key, {**insight, "dashboards": [dashboard["id"]]})
            print(f"  added {insight['name']}")
    return dashboard["id"]


def main() -> None:
    """Create or update the dashboard and its insights."""
    key = os.environ.get("POSTHOG_PERSONAL_API_KEY")
    if not key:
        sys.exit("Set POSTHOG_PERSONAL_API_KEY (a personal API key with dashboard:write and insight:write).")
    dashboard_id = sync(f"/api/projects/{project_id()}", key)
    print(f"{HOST}/project/{project_id()}/dashboard/{dashboard_id}")


if __name__ == "__main__":
    main()
