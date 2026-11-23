"""The Regions page (/maps/regions/5a), in the Maps section: its data, and its content without JavaScript.

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

import math
import re

from backend.helpers import region_map
from backend.helpers.data_helpers import SCHOOL_SUCCESSORS, school_name_for_season
from backend.helpers.region_files import cycle_start
from backend.helpers.region_map_image import REGION_COLORS, cycle_name, place, seasons_line, short_place
from backend.helpers.share_cards import slugify
from backend.helpers.static_pages import _e, _mark, breadcrumb_nav, class_trail, region_path

Trail = list[tuple[str, str]]


def regions_path(clazz: int) -> str:
    """ "/maps/regions/5a"."""
    return f"/maps/regions/{clazz}a"


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
    """Where a school was the season before, for its line in the list: "4-4A in 2026", "New school";
    nothing when it was in the same region then."""
    if prior_season is None:
        return ""
    was = school.get("before")
    if was and (was["class"], was["region"]) == (school["class"], school["region"]):
        return ""
    if was:
        return f"{short_place(was)} in {prior_season}"
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


def regions_header(clazz: int, payload: dict, share: str = "") -> str:
    """The page's heading: breadcrumbs, the title (with *share* beside it) and its seasons
    (``regionsHeader``)."""
    return (
        f"{breadcrumb_nav(regions_trail(clazz))}"
        f'<div class="title-row"><h1 class="title">{_e(regions_title(clazz))}</h1>{share}</div>'
        f'<p class="regions-sub">{_e(seasons_label(payload["seasons"]))}</p>'
    )


def regions_lists(clazz: int, payload: dict, current_season: int | None, teams: dict | None = None) -> str:
    """The class's schools by region (``regionsLists``), each region's heading linking to its standings
    when it has some."""
    schools = [s for s in payload["schools"] if s["class"] == clazz]
    out = []
    for g in sorted({s["region"] for s in schools}):
        href = standings_href(clazz, g, payload.get("standings_season"), current_season)
        standings = (
            f'<a class="regions-list__standings" href="{_e(href)}"><span class="visually-hidden">Region {g} </span>'
            f'{_e(str(payload["standings_season"]))} standings<span aria-hidden="true"> ›</span></a>'
            if href
            else ""
        )
        items = []
        for s in sorted((s for s in schools if s["region"] == g), key=lambda s: s["school"].lower()):
            note = team_note(s, payload.get("prior_season"))
            items.append(
                f'<li><a class="regions-list__row" href="{_e(regions_path(clazz))}?team={_e(s["slug"])}" '
                f'data-team="{_e(s["slug"])}">'
                f'{_mark(s["school"], (teams or {}).get(s["school"]))}'
                f'<span class="regions-list__team">{_e(s["school"])}</span>'
                + (f'<span class="regions-list__was">{_e(note)}</span>' if note else "")
                + "</a></li>"
            )
        out.append(
            f'<section class="regions-list__region regions-list__region--{g}"><div class="regions-list__head">'
            f'<h2 class="regions-list__name"><span class="region-chip region-chip--{g}" aria-hidden="true">{g}</span>'
            f"Region {g}</h2>{standings}</div><ul>{''.join(items)}</ul></section>"
        )
    return "".join(out)


def regions_body(
    clazz: int, payload: dict, current_season: int | None, image_url: str | None, teams: dict | None = None
) -> str:
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
        f'<div class="regions-side"><div class="regions-list">{regions_lists(clazz, payload, current_season, teams)}</div>'
        "</div></div></div>\n"
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
    """A team's link preview: "Greenwood: Region 2-5A in 2027 and 2028." and the change."""
    text = f"{school['school']}: {place(school)} in {' and '.join(str(s) for s in payload['seasons'])}."
    if school.get("before") and payload.get("prior_season"):
        text += f" {place(school['before'])} in {payload['prior_season']}."
    return text


# ----------------------------------------------------------------- the Counties pages
# /maps/counties/hinds: one county's MHSAA schools, whatever their classes, each with its region; and
# /maps/counties, every county to pick one. A school's county is its campus's (region_map.county_of),
# in each season's rows. Twins of regions.js's county functions (renderer_parity_test.py).

MHSAA_NOTE = (
    "Only schools in the MHSAA (Mississippi High School Activities Association) are shown. "
    "Schools in other associations, such as MAIS, aren't."
)


def counties_path(county: str | None = None) -> str:
    """ "/maps/counties/jefferson-davis" (or "/maps/counties", every county)."""
    return f"/maps/counties/{slugify(county)}" if county else "/maps/counties"


def county_title(county: str) -> str:
    """ "Hinds County"."""
    return f"{county} County"


def counties_trail(county: str | None = None) -> Trail:
    """Home › Counties › Hinds County (or Home › Counties)."""
    trail = [("Home", "/"), ("Counties", counties_path())]
    return [*trail, (county_title(county), counties_path(county))] if county else trail


def county_places(schools: list[dict]) -> list[dict]:
    """The places (a region in a class) a county's *schools* are in, highest class first, each with a color
    (1-8): its region's own, unless another of the county's places has it already, then the first one not
    in use (``countyPlaces``)."""
    seen: dict[str, dict] = {}
    for s in sorted(schools, key=lambda s: (-s["class"], s["region"])):
        key = f"{s['class']}-{s['region']}"
        seen.setdefault(key, {"key": key, "clazz": s["class"], "region": s["region"]})
    used: set[int] = set()
    for p in seen.values():
        own = (p["region"] - 1) % 8 + 1
        p["color"] = own if own not in used else next((c for c in range(1, 9) if c not in used), own)
        used.add(p["color"])
    return list(seen.values())


def schools_count(n: int) -> str:
    """ "9 MHSAA schools", "1 MHSAA school", "No MHSAA schools"."""
    return f"{n} MHSAA {'school' if n == 1 else 'schools'}" if n else "No MHSAA schools"


def county_count(schools: list[dict]) -> str:
    """ "9 MHSAA schools in 4 classes" (``countyCount``)."""
    classes = len({s["class"] for s in schools})
    return schools_count(len(schools)) + (f" in {classes} classes" if classes > 1 else "")


def county_lists(county: str, payload: dict, teams: dict | None = None) -> str:
    """The county's schools by class, highest first, each with its region and town (``countyLists``)."""
    mine = [s for s in payload["schools"] if s["county"] == county]
    colors = {p["key"]: p["color"] for p in county_places(mine)}
    out = []
    for c in sorted({s["class"] for s in mine}, reverse=True):
        rows = []
        for s in sorted((s for s in mine if s["class"] == c), key=lambda s: (s["region"], s["school"].lower())):
            town = f" · {_e(s['city'])}" if s.get("city") else ""
            color = colors[f"{c}-{s['region']}"]
            rows.append(
                f'<li><a class="regions-list__row" href="{_e(counties_path(county))}?team={_e(s["slug"])}" '
                f'data-team="{_e(s["slug"])}">'
                f"{_mark(s['school'], (teams or {}).get(s['school']))}"
                f'<span class="regions-list__team">{_e(s["school"])}</span>'
                f'<span class="regions-list__was"><span class="region-chip region-chip--{color}" '
                f'aria-hidden="true">{s["region"]}</span>{_e(place(s))}{town}</span></a></li>'
            )
        out.append(
            '<section class="regions-list__region county-list__class"><div class="regions-list__head">'
            f'<h2 class="regions-list__name">Class {c}A</h2>'
            f'<a class="regions-list__standings" href="{_e(regions_path(c))}">Class {c}A regions'
            '<span aria-hidden="true"> ›</span></a></div>'
            f"<ul>{''.join(rows)}</ul></section>"
        )
    return "".join(out)


def _js_number(v: float) -> str:
    """*v* rounded to a tenth (halves up) and written as JavaScript writes a number ("12", "12.3")."""
    r = math.floor(v * 10 + 0.5) / 10
    return str(int(r)) if r == int(r) else str(r)


def path_box(d: str) -> list[float] | None:
    """The box around an SVG path of absolute points (``pathBox``)."""
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
    xs, ys = nums[0::2], nums[1::2]
    return [min(xs), min(ys), max(xs), max(ys)] if xs else None


def county_mark(base: dict, county: str, size: int = 24, shade: int | None = None) -> str:
    """A county's mark, its outline as a team's helmet is its (``countyMark``)."""
    c = next((x for x in base["counties"] if x["name"] == county), None)
    if c is None:
        return ""
    d = c.get("icon") or c["d"]
    x0, y0, x1, y1 = path_box(d)
    pad = max(x1 - x0, y1 - y0) * 0.06
    box = " ".join(_js_number(v) for v in (x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad))
    fill = "county-mark--site" if shade is None else f"county-shade--{shade}"
    return (
        f'<svg class="mark county-mark {fill}" viewBox="{box}" width="{size}" height="{size}" aria-hidden="true">'
        f'<path d="{d}"/></svg>'
    )


def count_shade(n: int) -> int:
    """A count's shade on the statewide map (``countShade``)."""
    return 0 if n == 0 else 1 if n == 1 else 2 if n == 2 else 3 if n <= 4 else 4


def counties_list(base: dict, counts: dict[str, int]) -> str:
    """Every county by name, a row each with its mark and its MHSAA schools (``countiesList``)."""
    rows = []
    for c in sorted(base["counties"], key=lambda c: c["name"].lower()):
        n = counts.get(c["name"], 0)
        rows.append(
            f'<li><a class="regions-list__row county-row{"" if n else " is-empty"}" '
            f'href="{_e(counties_path(c["name"]))}" data-county="{_e(c["name"])}">'
            f"{county_mark(base, c['name'], 28, count_shade(n))}"
            f'<span class="regions-list__team">{_e(c["name"])}</span>'
            f'<span class="regions-list__was">{_e(schools_count(n))}</span></a></li>'
        )
    return f'<ul class="counties-list">{"".join(rows)}</ul>'


def county_header(county: str, payload: dict, base: dict, share: str = "") -> str:
    """The county page's heading (``countyHeader``)."""
    mine = [s for s in payload["schools"] if s["county"] == county]
    return (
        f"{breadcrumb_nav(counties_trail(county))}"
        f'<div class="title-row"><h1 class="title county-title">'
        f"{county_mark(base, county, 44)}<span>{_e(county_title(county))}</span></h1>{share}</div>"
        f'<p class="regions-sub">{_e(county_count(mine))}, {_e(seasons_label(payload["seasons"]))}</p>'
        f'<p class="county-note muted">{_e(MHSAA_NOTE)}</p>'
    )


def county_body(county: str, payload: dict, base: dict, teams: dict | None = None) -> str:
    """A county's page as plain HTML: its heading and its schools by class (the app adds the map)."""
    mine = [s for s in payload["schools"] if s["county"] == county]
    lists = (
        f'<div class="regions-list county-list">{county_lists(county, payload, teams)}</div>'
        if mine
        else f'<p class="notice">No MHSAA school is in {_e(county_title(county))} in the '
        f'{_e(seasons_label(payload["seasons"]))}. <a href="{counties_path()}">Pick another county</a>.</p>'
    )
    return (
        f'<div class="page static-page regions-page county-page"><header class="entry-head">'
        f"{county_header(county, payload, base)}</header>{lists}</div>\n"
    )


def county_description(county: str, payload: dict) -> str:
    """A county page's description for search results and link previews."""
    mine = [s for s in payload["schools"] if s["county"] == county]
    seasons = " and ".join(str(s) for s in payload["seasons"])
    if not mine:
        return f"{county_title(county)}, Mississippi has no MHSAA football school in {seasons}."
    places = ", ".join(
        f"{s['school']} ({short_place(s)})" for s in sorted(mine, key=lambda s: (-s["class"], s["school"].lower()))
    )
    return f"{county_title(county)}, Mississippi's MHSAA football schools in {seasons} and their regions: {places}."


def counties_body(base: dict, payload: dict) -> str:
    """The statewide page as plain HTML: its heading and every county with its MHSAA schools' count."""
    counts = {c["name"]: 0 for c in base["counties"]}
    for s in payload["schools"]:
        if s["county"] in counts:
            counts[s["county"]] += 1
    return (
        '<div class="page static-page regions-page counties-page"><header class="entry-head">'
        f"{breadcrumb_nav(counties_trail())}"
        '<div class="title-row"><h1 class="title">Counties</h1></div>'
        f'<p class="regions-sub">Each county\'s MHSAA schools, {_e(seasons_label(payload["seasons"]))}</p>'
        f'<p class="county-note muted">{_e(MHSAA_NOTE)}</p></header>'
        f'<h2 class="counties-list__title">Every county</h2>{counties_list(base, counts)}</div>\n'
    )
