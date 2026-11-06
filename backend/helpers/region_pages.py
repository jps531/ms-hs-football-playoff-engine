"""The Regions page (/regions/5a): its data, and its content without JavaScript.

The share-assets pipeline writes, under the share folder (served at /static/regions/):

- ``regions/map.json``: the state and its counties (``region_map.base_map``), the same every season;
- ``regions/{season}.json``: one season's schools and region shapes (``season_payload``);
- ``regions/index.json``: which seasons there are, newest first (``season_options``).

The app's Regions view (``regions.js``) draws the map from those files; ``regions_body`` is the same
page as plain HTML (its lists and an image of the map), for search engines and link previews, and the
app replaces it on load.

A season is listed with the season after it when the two have the same regions (as the two seasons
of a cycle do, unless a school moved mid-cycle): "2027 and 2028".
"""

from __future__ import annotations

from backend.helpers import region_map
from backend.helpers.data_helpers import SCHOOL_SUCCESSORS, school_name_for_season
from backend.helpers.region_files import cycle_start
from backend.helpers.region_map_image import REGION_COLORS, cycle_name, place, seasons_line, short_place
from backend.helpers.share_cards import slugify
from backend.helpers.static_pages import _e, breadcrumb_nav, class_trail, region_path

Trail = list[tuple[str, str]]


def regions_path(clazz: int) -> str:
    """ "/regions/5a"."""
    return f"/regions/{clazz}a"


def regions_trail(clazz: int) -> Trail:
    """Home › Class 5A › Class 5A Regions (Class 5A is the class's standings, as on the bracket page)."""
    return [*class_trail(clazz), (f"Class {clazz}A Regions", regions_path(clazz))]


def regions_title(clazz: int) -> str:
    """The page's title."""
    return f"Class {clazz}A Regions"


def seasons_label(seasons: list[int]) -> str:
    """ "2027 and 2028 seasons", or "2026 season" (as the images say it)."""
    return seasons_line(seasons)


# ----------------------------------------------------------------- data


def school_rows(teams: list[dict]) -> list[dict]:
    """A season's schools ({school, class, region, city, x, y, county}) from ``/teams``: projected onto
    the state grid, x and y in meters. A school without coordinates, or whose coordinates fall outside
    Mississippi, keeps its place in the lists with x and y None (it gets no dot; a dot in the wrong
    place would be worse than none)."""
    rows = []
    for t in teams:
        if t.get("class_") is None or t.get("region") is None:
            continue
        x = y = county = None
        if t.get("latitude") is not None and t.get("longitude") is not None:
            px, py = region_map.project(t["latitude"], t["longitude"])
            county = region_map.county_of(px, py)
            if county:
                x, y = px, py
        rows.append(
            {
                "school": t["school"],
                "class": t["class_"],
                "region": t["region"],
                "city": t.get("city") or "",
                "county": county,
                "x": x,
                "y": y,
            }
        )
    return sorted(rows, key=lambda r: (r["class"], r["region"], r["school"].lower()))


def mapped(rows: list[dict]) -> list[dict]:
    """The rows that have a place on the map."""
    return [r for r in rows if r["x"] is not None]


def assignments(rows: list[dict]) -> dict[str, tuple[int, int]]:
    """{school: (class, region)}."""
    return {r["school"]: (r["class"], r["region"]) for r in rows}


def season_options(seasons: dict[int, list[dict]]) -> list[dict]:
    """The page's season choices, newest first, from each season's rows: a season is grouped with the
    one after it when their regions are the same. [{season, seasons, label}], ``season`` the first."""
    options: list[dict] = []
    for season in sorted(seasons):
        last = options[-1] if options else None
        if (
            last
            and last["seasons"][-1] == season - 1
            and len(last["seasons"]) == 1
            and cycle_start(season) == last["season"]
            and assignments(seasons[season]) == assignments(seasons[season - 1])
        ):
            last["seasons"].append(season)
        else:
            options.append({"season": season, "seasons": [season]})
    for o in options:
        o["label"] = " and ".join(str(s) for s in o["seasons"])
    return sorted(options, key=lambda o: -o["season"])


def prior_rows(rows: list[dict], season: int) -> dict[str, dict]:
    """The season before's rows by the school's name in *season* (a renamed school under its new name)."""
    return {school_name_for_season(r["school"], season): r for r in rows}


def successor_of(school: str, season: int) -> str | None:
    """The old school *school* carries on, when it's a new school starting in *season*."""
    return next((old for old, new, first in SCHOOL_SUCCESSORS if new == school and first == season), None)


def season_payload(option: dict, rows: list[dict], prior: list[dict] | None, played: list[int]) -> dict:
    """One season choice's data for the page: its schools (with where each was the season before) and
    each class's region shapes, in the page's SVG units. *played* is every season with games."""
    season = option["season"]
    before = prior_rows(prior or [], season)
    schools = []
    for r in rows:
        was = before.get(r["school"])
        point = region_map.svg_point(r["x"], r["y"]) if r["x"] is not None else None
        schools.append(
            {
                "school": r["school"],
                "slug": slugify(r["school"]),
                "class": r["class"],
                "region": r["region"],
                "city": r["city"],
                "county": r["county"],
                "x": round(point[0], 1) if point else None,
                "y": round(point[1], 1) if point else None,
                "before": {"class": was["class"], "region": was["region"]} if was else None,
                "successor_of": successor_of(r["school"], season),
            }
        )
    regions: dict[str, dict[str, dict]] = {}
    for clazz in sorted({r["class"] for r in rows}):
        for g, shape in region_map.region_shapes(mapped([r for r in rows if r["class"] == clazz])).items():
            x0, y0, x1, y1 = shape.bounds
            (bx0, by1), (bx1, by0) = region_map.svg_point(x0, y0), region_map.svg_point(x1, y1)
            regions.setdefault(str(clazz), {})[str(g)] = {
                "d": region_map.svg_path(shape),
                "box": [round(bx0, 1), round(by0, 1), round(bx1, 1), round(by1, 1)],
            }
    return {
        "season": season,
        "seasons": option["seasons"],
        "label": option["label"],
        "cycle": cycle_name(cycle_start(season)),
        "prior_season": season - 1 if prior else None,
        "standings_season": max((s for s in option["seasons"] if s in played), default=None),
        "schools": schools,
        "regions": regions,
        "colors": {theme: list(colors) for theme, colors in REGION_COLORS.items()},
    }


# ----------------------------------------------------------------- the page without JavaScript


def team_note(school: dict, prior_season: int | None) -> str:
    """Where a school was the season before, for its line in the list: "4A-4 in 2026", "New school"."""
    if prior_season is None:
        return ""
    if school.get("before"):
        return f"{short_place(school['before'])} in {prior_season}"
    if school.get("successor_of"):
        return "New school"
    return f"Not in a region in {prior_season}"


def standings_href(clazz: int, region: int, standings_season: int | None, current_season: int | None) -> str | None:
    """Where a region's heading links: its standings in the newest of the choice's seasons that has
    games (no link while none has: that region has no standings yet)."""
    if standings_season is None:
        return None
    path = region_path(clazz, region)
    return path if standings_season == current_season else f"{path}?season={standings_season}"


def regions_header(clazz: int, payload: dict) -> str:
    """The page's heading: breadcrumbs, title, and which seasons and cycle it shows (``regionsHeader``)."""
    return (
        f"{breadcrumb_nav(regions_trail(clazz))}"
        f'<h1 class="title">{_e(regions_title(clazz))}</h1>'
        f'<p class="regions-sub">{_e(seasons_label(payload["seasons"]))} · MHSAA {_e(payload["cycle"])} regions</p>'
    )


def regions_lists(clazz: int, payload: dict, current_season: int | None) -> str:
    """The class's schools by region (``regionsLists``), each region's heading linking to its standings
    when it has some."""
    schools = [s for s in payload["schools"] if s["class"] == clazz]
    out = []
    for g in sorted({s["region"] for s in schools}):
        href = standings_href(clazz, g, payload.get("standings_season"), current_season)
        heading = f'<a href="{_e(href)}">Region {g}</a>' if href else f"Region {g}"
        items = []
        for s in sorted((s for s in schools if s["region"] == g), key=lambda s: s["school"].lower()):
            note = team_note(s, payload.get("prior_season"))
            items.append(
                f'<li><a href="{_e(regions_path(clazz))}?team={_e(s["slug"])}" data-team="{_e(s["slug"])}">'
                f"{_e(s['school'])}</a>"
                + (f' <span class="regions-list__was">{_e(note)}</span>' if note else "")
                + "</li>"
            )
        out.append(
            '<section class="regions-list__region"><h2 class="regions-list__name">'
            f'<span class="region-chip region-chip--{g}" aria-hidden="true">{g}</span>{heading}</h2>'
            f"<ul>{''.join(items)}</ul></section>"
        )
    return "".join(out)


def regions_body(clazz: int, payload: dict, current_season: int | None, image_url: str | None) -> str:
    """The Regions page for *clazz* as plain HTML: ``regionsPage``'s, with an image of the map in
    place of the map the app draws."""
    figure = (
        f'<img class="regions-map__image" src="{_e(image_url)}" width="1080" height="1350" '
        f'alt="Map of Mississippi with each Class {clazz}A school as a dot numbered by its region">'
        if image_url
        else ""
    )
    return (
        f'<div class="page static-page regions-page"><header class="entry-head">{regions_header(clazz, payload)}</header>'
        f'<div class="regions-layout"><figure class="regions-map">{figure}</figure>'
        f'<div class="regions-list">{regions_lists(clazz, payload, current_season)}</div></div>'
        f'<p class="regions-note">{_e(MAP_NOTE)}</p></div>\n'
    )


MAP_NOTE = (
    "Each dot is a school, at the location the site has for it (for a public school, the federal NCES geocode "
    "of its address). The shaded shapes are drawn around each region’s schools; MHSAA doesn’t draw region "
    "boundaries. County lines: U.S. Census Bureau."
)


def regions_description(clazz: int, payload: dict) -> str:
    """The page's description for search results and link previews."""
    n = len({s["region"] for s in payload["schools"] if s["class"] == clazz})
    count = sum(1 for s in payload["schools"] if s["class"] == clazz)
    return (
        f"Mississippi high school football's Class {clazz}A regions for the "
        f"{seasons_label(payload['seasons'])}: {count} schools in {n} regions, on a map."
    )


def team_regions_description(school: dict, payload: dict) -> str:
    """A team's link preview: "Greenwood: 5A Region 2 in 2027 and 2028." and the change."""
    text = f"{school['school']}: {place(school)} in {' and '.join(str(s) for s in payload['seasons'])}."
    if school.get("before") and payload.get("prior_season"):
        text += f" {place(school['before'])} in {payload['prior_season']}."
    return text
