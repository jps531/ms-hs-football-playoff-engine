"""The Regions pages' files, written by the share-assets pipeline (``share_assets_pipeline``).

For every season whose regions are loaded (each cycle file's seasons with schools in ``/teams``):

- ``regions/map.json``, ``regions/index.json`` and ``regions/{season}.json``: the page's data
  (``region_pages``), served at /static/regions/;

- the images to share (``region_map_image``), for every choice the page offers, so its Share button
  always has them: ``regions/{season}/{c}a-{theme}.png``, the class's two seasons side by side
  ``regions/{season}/compare/{c}a-{theme}.png`` (when there's a season before), each team's
  ``regions/{season}/team/{slug}-{theme}.png`` and its two regions compared
  ``regions/{season}/compare/{slug}-{theme}.png``. Like the region images, only those whose content
  changed are drawn (``image_jobs``), and a choice the page no longer offers loses its folder;

- the Counties pages' images (``county_jobs``): each county's, against the season before, every season
  of it, and every county shaded, with their link previews;

- the Timeline view's images (``timeline_jobs``), every season of regions on one image: each class's
  ``regions/timeline/{c}a-{theme}.png`` and each school's ``regions/timeline/team/{slug}-{theme}.png``;

and for the newest choice (the page's default):

- ``body/counties.html``, ``meta/counties.html`` and each county's ``body/counties-{slug}.html`` and
  ``meta/counties-{slug}.html``: the Counties pages without JavaScript, and their link previews (the
  site's card);

- ``body/regions-{c}.html`` and ``meta/regions-{c}.html`` (+ ``meta/regions-{c}/{slug}.html`` for a
  team's link): the page without JavaScript, and its link preview, with the previews
  ``og/regions-{c}.png`` and ``og/regions-{c}/{slug}.png``.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Callable
from datetime import date
from pathlib import Path

from PIL import Image

from backend.helpers import region_map
from backend.helpers.data_helpers import SCHOOL_RENAMES, names_in, school_name_for_season
from backend.helpers.engine_settings import CLASSES
from backend.helpers.image_jobs import (
    CLASS_REGIONS,
    CLASS_REGIONS_CARD,
    CLASS_REGIONS_COMPARED,
    CLASS_TIMELINE,
    COUNTIES,
    COUNTIES_CARD,
    COUNTY,
    COUNTY_CARD,
    COUNTY_COMPARED,
    COUNTY_TIMELINE,
    TEAM_REGION,
    TEAM_REGION_CARD,
    TEAM_REGIONS_COMPARED,
    TEAM_TIMELINE,
    ImageJob,
    draw_images,
)
from backend.helpers.region_files import REGIONS_DIR
from backend.helpers.region_pages import (
    counties_body,
    counties_path,
    counties_trail,
    county_body,
    county_description,
    county_title,
    regions_body,
    regions_description,
    regions_path,
    regions_title,
    regions_trail,
    school_rows,
    season_options,
    season_payload,
    seasons_label,
    team_regions_description,
)
from backend.helpers.share_cards import description, meta_tags, slugify
from backend.helpers.static_pages import breadcrumb_ld, json_ld

THEMES = ("light", "dark")
_log = logging.getLogger(__name__)
Fetch = Callable[[str], object]
Writer = Callable[[Path, str], None]


def loaded_seasons(fetch: Fetch) -> dict[int, list[dict]]:
    """Each season that has a region file and schools in the database: its rows (``school_rows``)."""
    seasons: dict[int, list[dict]] = {}
    for path in sorted(REGIONS_DIR.glob("*.csv")):
        first = int(path.name[:4])
        for season in (first, first + 1):
            teams = fetch(f"/teams?season={season}") or []
            rows = school_rows(teams)
            if rows:
                seasons[season] = rows
                unplaced = [r["school"] for r in rows if r["x"] is None]
                if unplaced:
                    _log.warning(
                        "%d: no place on the map (no coordinates, or outside Mississippi): %s", season, unplaced
                    )
    return seasons


def _colors(teams: list[dict], names: set[str]) -> dict[str, dict]:
    """What a helmet needs, for the *names* only (so an image's content is just what it shows)."""
    return {
        t["school"]: {"color_variants": t.get("color_variants"), "secondary_color_hex": t.get("secondary_color_hex")}
        for t in teams
        if t["school"] in names
    }


def image_jobs(
    option: dict, rows: list[dict], prior: list[dict], teams: list[dict], previews: bool = True
) -> list[ImageJob]:
    """A choice's images: each class's map, each team's region and its two regions compared (light and
    dark), and with *previews* (the newest choice's) the link previews."""
    season, seasons = option["season"], option["seasons"]
    jobs: list[ImageJob] = []
    for clazz in CLASSES:
        mine = [r for r in rows if r["class"] == clazz]
        if not mine:
            continue
        for theme in THEMES:
            jobs.append(
                ImageJob(
                    f"regions/{season}/{clazz}a-{theme}.png",
                    CLASS_REGIONS,
                    {"clazz": clazz, "seasons": seasons, "schools": mine, "theme": theme},
                )
            )
        if previews:
            jobs.append(
                ImageJob(
                    f"og/regions-{clazz}.png",
                    CLASS_REGIONS_CARD,
                    {"clazz": clazz, "seasons": seasons, "schools": mine},
                )
            )
        then = [s for s in prior if s["class"] == clazz]
        if then:
            # The two seasons' class, plus the other season's rows of the schools that moved in or out.
            names_now, names_then = {s["school"] for s in mine}, {s["school"] for s in then}
            moved_now = [s for s in rows if s["school"] in names_then - names_now]
            moved_then = [s for s in prior if s["school"] in names_now - names_then]
            kwargs = {"clazz": clazz, "seasons": seasons, "schools": mine + moved_now, "prior": then + moved_then}
            for theme in THEMES:
                jobs.append(
                    ImageJob(
                        f"regions/{season}/compare/{clazz}a-{theme}.png",
                        CLASS_REGIONS_COMPARED,
                        {**kwargs, "theme": theme},
                    )
                )
    prior_by = {r["school"]: r for r in prior}
    for r in rows:
        slug = slugify(r["school"])
        before = prior_by.get(r["school"])
        mine = [s for s in rows if s["class"] == r["class"]]
        then = [s for s in prior if before and s["class"] == before["class"]]
        mates = {s["school"] for s in mine if s["region"] == r["region"]}
        # The season before, cut to what the images show: the team's class then, and its mates' rows.
        shown_prior = then + [s for s in prior if s["school"] in mates and s not in then]
        former = {s["school"] for s in then if before and s["region"] == before["region"]}
        names = mates | former
        # This season, cut likewise: the team's class, and where its former region-mates are now (in
        # any class), so "Former Region Members" says where each went rather than that it's gone.
        shown = mine + [s for s in rows if s["school"] in former and s["class"] != r["class"]]
        kwargs = {
            "school": r["school"],
            "seasons": seasons,
            "schools": shown,
            "prior": shown_prior,
            "teams": _colors(teams, names),
        }
        for theme in THEMES:
            jobs.append(ImageJob(f"regions/{season}/team/{slug}-{theme}.png", TEAM_REGION, {**kwargs, "theme": theme}))
            if before:
                jobs.append(
                    ImageJob(
                        f"regions/{season}/compare/{slug}-{theme}.png",
                        TEAM_REGIONS_COMPARED,
                        {**kwargs, "theme": theme},
                    )
                )
        if previews:
            jobs.append(ImageJob(f"og/regions-{r['class']}/{slug}.png", TEAM_REGION_CARD, kwargs))
    return jobs


def timeline_jobs(options: list[dict], seasons: dict[int, list[dict]], teams: dict[int, list[dict]]) -> list[ImageJob]:
    """The Timeline view's images: each class's regions over every season (*options*, the page's choices,
    with each choice's rows in *seasons* and its ``/teams`` in *teams*), and each school's, light and
    dark. A school is drawn under its name in the newest season it played (as the page follows it), and
    a renamed school's old name not at all (its links go to the new name's); before a consolidation, a
    season shows every school merged into it (``names_in``)."""
    ordered = sorted(options, key=lambda o: o["season"])
    jobs: list[ImageJob] = []
    for clazz in CLASSES:
        cycles = [
            {"seasons": o["seasons"], "schools": [r for r in seasons[o["season"]] if r["class"] == clazz]}
            for o in ordered
        ]
        if not any(c["schools"] for c in cycles):
            continue
        for theme in THEMES:
            jobs.append(
                ImageJob(
                    f"regions/timeline/{clazz}a-{theme}.png",
                    CLASS_TIMELINE,
                    {"clazz": clazz, "cycles": cycles, "theme": theme},
                )
            )
    newest: dict[str, int] = {}
    for o in ordered:
        for r in seasons[o["season"]]:
            newest[r["school"]] = o["season"]
    renamed = {old for old, _, _ in SCHOOL_RENAMES}
    for name, season in sorted(newest.items()):
        if name in renamed:
            continue
        cycles = []
        for o in ordered:
            rows = seasons[o["season"]]
            by_name = {r["school"]: r for r in rows}
            mine = [by_name[n] for n in names_in(name, season, o["season"]) if n in by_name]
            places = {(r["class"], r["region"]) for r in mine}
            cycles.append(
                {
                    "seasons": o["seasons"],
                    "rows": mine,
                    "schools": [r for r in rows if (r["class"], r["region"]) in places],
                }
            )
        kwargs = {"school": name, "cycles": cycles, "teams": _colors(teams.get(season) or [], {name})}
        for theme in THEMES:
            jobs.append(
                ImageJob(
                    f"regions/timeline/team/{slugify(name)}-{theme}.png", TEAM_TIMELINE, {**kwargs, "theme": theme}
                )
            )
    return jobs


def _county_rows(rows: list[dict], county: str) -> list[dict]:
    """What a county's images need of a season: every school in the classes its schools are in (each
    class's region shapes are drawn from all its schools, as on the page)."""
    classes = {r["class"] for r in rows if r.get("county") == county}
    return [r for r in rows if r["class"] in classes]


def county_jobs(options: list[dict], seasons: dict[int, list[dict]]) -> list[ImageJob]:
    """The Counties pages' images, light and dark: for every choice of regions, each county's
    (``regions/{season}/county/{slug}``), the county against the season before when there is one
    (``…/county-compare/{slug}``) and every county shaded (``regions/{season}/counties``); each county's
    every season (``regions/timeline/county/{slug}``); and, for the newest choice, the link previews
    (``og/counties/{slug}.png``, ``og/counties.png``). A county with no school that season has none."""
    names = sorted(region_map.counties(), key=str.lower)
    ordered = sorted(options, key=lambda o: o["season"])
    by_season = {s: o for o in ordered for s in o["seasons"]}
    newest = ordered[-1]
    jobs: list[ImageJob] = []
    for option in ordered:
        season, rows = option["season"], seasons[option["season"]]
        counts = {n: 0 for n in names}
        for r in rows:
            if r.get("county") in counts:
                counts[r["county"]] += 1
        for theme in THEMES:
            jobs.append(
                ImageJob(
                    f"regions/{season}/counties-{theme}.png",
                    COUNTIES,
                    {"seasons": option["seasons"], "counts": counts, "theme": theme},
                )
            )
        if option is newest:
            jobs.append(ImageJob("og/counties.png", COUNTIES_CARD, {"seasons": option["seasons"], "counts": counts}))
        before = by_season.get(season - 1)
        for county in names:
            slug = slugify(county)
            mine = _county_rows(rows, county)
            if mine:
                kwargs = {"county": county, "seasons": option["seasons"], "schools": mine}
                for theme in THEMES:
                    jobs.append(
                        ImageJob(f"regions/{season}/county/{slug}-{theme}.png", COUNTY, {**kwargs, "theme": theme})
                    )
                if option is newest:
                    jobs.append(ImageJob(f"og/counties/{slug}.png", COUNTY_CARD, kwargs))
            then = _county_rows(seasons[before["season"]], county) if before else []
            if before and (mine or then):
                older = {"label": before["label"], "seasons": before["seasons"], "schools": then}
                newer = {"label": option["label"], "seasons": option["seasons"], "schools": mine}
                for theme in THEMES:
                    jobs.append(
                        ImageJob(
                            f"regions/{season}/county-compare/{slug}-{theme}.png",
                            COUNTY_COMPARED,
                            {"county": county, "older": older, "newer": newer, "theme": theme},
                        )
                    )
    for county in names:
        cycles = [{"seasons": o["seasons"], "schools": _county_rows(seasons[o["season"]], county)} for o in ordered]
        if any(c["schools"] for c in cycles):
            for theme in THEMES:
                jobs.append(
                    ImageJob(
                        f"regions/timeline/county/{slugify(county)}-{theme}.png",
                        COUNTY_TIMELINE,
                        {"county": county, "cycles": cycles, "theme": theme},
                    )
                )
    return jobs


def maps_example(out_dir: Path, clazz: int, season: int, drawn: set[str]) -> dict:
    """What the front page's Maps section shows (static_pages.landing_body's *regions_example*): class
    *clazz*'s map in *season* (the regions shown first), and those of the other views' images the step
    drew (*drawn*, write_regions' *drawn_files*): the class beside the season before ("compare"), every
    season's ("timeline", its size, read from the file) and the county with the most MHSAA schools that
    season, the first by name among those tied ("county")."""
    example: dict = {"clazz": clazz, "season": season}
    if f"regions/{season}/compare/{clazz}a-light.png" in drawn:
        example["compare"] = True
    timeline = f"regions/timeline/{clazz}a-light.png"
    if timeline in drawn:
        with Image.open(out_dir / timeline) as img:
            example["timeline"] = img.size
    try:
        rows = json.loads((out_dir / "regions" / f"{season}.json").read_text())["schools"]
    except (OSError, ValueError, KeyError):
        rows = []
    counts = Counter(r["county"] for r in rows if r.get("county"))
    drawn_counties = [c for c in counts if f"regions/{season}/county/{slugify(c)}-light.png" in drawn]
    if drawn_counties:
        example["county"] = min(drawn_counties, key=lambda c: (-counts[c], c))
    return example


def write_regions(
    fetch: Fetch,
    out_dir: Path,
    site_url: str,
    today: date,
    played: list[int],
    write: Writer,
    drawn_files: set[str] | None = None,
) -> tuple[dict[str, int], list[tuple[str, date | None, list[str]]]]:
    """Write the Regions pages' files; returns counts ({"region_maps", "region_map_images",
    "region_map_images_kept"}) and the pages for the sitemap. *drawn_files*, when given, gets every
    image file the step keeps (relative to *out_dir*), for ``image_jobs.sweep``."""
    counts = {"region_maps": 0, "region_map_images": 0, "region_map_images_kept": 0}
    seasons = loaded_seasons(fetch)
    if not seasons:
        return counts, []
    current = played[0] if played else None
    options = season_options(seasons)
    write(out_dir / "regions" / "map.json", json.dumps(region_map.base_map(), separators=(",", ":")))
    write(
        out_dir / "regions" / "index.json",
        json.dumps({"default": options[0]["season"], "options": options, "current_season": current}),
    )
    payloads = {}
    for option in options:
        season = option["season"]
        prior = seasons.get(season - 1)
        payloads[season] = season_payload(option, seasons[season], prior, played)
        write(out_dir / "regions" / f"{season}.json", json.dumps(payloads[season], separators=(",", ":")))
        counts["region_maps"] += 1

    # Every choice's images, so the page's Share button has them whichever regions it shows; the
    # link previews are the newest choice's.
    newest = options[0]
    jobs: list[ImageJob] = []
    prune = [f"og/regions-{c}" for c in CLASSES]
    by_school: dict[str, dict] = {}
    teams_by_season: dict[int, list[dict]] = {}
    for option in options:
        season = option["season"]
        # The season before, under each school's name this season (a renamed school is the same school).
        prior = [{**r, "school": school_name_for_season(r["school"], season)} for r in seasons.get(season - 1) or []]
        teams = teams_by_season[season] = fetch(f"/teams?season={season}") or []
        if option is newest:
            by_school = {t["school"]: t for t in teams}
        jobs += image_jobs(option, seasons[season], prior, teams, previews=option is newest)
        prune += [f"regions/{season}", f"regions/{season}/team", f"regions/{season}/compare"]
    jobs += timeline_jobs(options, seasons, teams_by_season)
    prune += ["regions/timeline", "regions/timeline/team"]
    jobs += county_jobs(options, seasons)
    prune += ["regions/timeline/county", "og/counties"]
    prune += [f"regions/{o['season']}/{kind}" for o in options for kind in ("county", "county-compare")]
    files: dict[str, list[str]] = {}
    drawn = draw_images(out_dir, jobs, prune=prune, files_out=files)
    counts["region_map_images"], counts["region_map_images_kept"] = drawn["drawn"], drawn["kept"]
    if drawn_files is not None:
        drawn_files.update(f for pages in files.values() for f in pages)
    season = newest["season"]

    payload = payloads[season]
    sitemap = []
    for clazz in CLASSES:
        if not any(s["class"] == clazz for s in payload["schools"]):
            continue
        page_url = f"{site_url}{regions_path(clazz)}"
        version = f"?v={today:%Y%m%d}"
        image = f"{site_url}/static/regions/{season}/{clazz}a-light.png"
        write(
            out_dir / "body" / f"regions-{clazz}.html",
            regions_body(clazz, payload, current, f"/static/regions/{season}/{clazz}a-light.png{version}", by_school),
        )
        write(
            out_dir / "meta" / f"regions-{clazz}.html",
            meta_tags(
                regions_title(clazz),
                description(regions_description(clazz, payload)),
                f"{site_url}/static/og/regions-{clazz}.png{version}",
                page_url,
                json_ld(breadcrumb_ld(site_url, regions_trail(clazz))),
            ),
        )
        team_dir = out_dir / "meta" / f"regions-{clazz}"
        keep = set()
        for school in (s for s in payload["schools"] if s["class"] == clazz):
            keep.add(school["slug"])
            write(
                team_dir / f"{school['slug']}.html",
                meta_tags(
                    f"{school['school']}: {regions_title(clazz)}",
                    description(team_regions_description(school, payload)),
                    f"{site_url}/static/og/regions-{clazz}/{school['slug']}.png{version}",
                    f"{page_url}?team={school['slug']}",
                ),
            )
        for path in team_dir.glob("*.html"):
            if path.stem not in keep:
                path.unlink(missing_ok=True)
        sitemap.append((regions_path(clazz), None, [image]))

    # The Counties pages (the newest regions): every county, and each county's schools, each with its
    # link preview (county_jobs draws them).
    base = region_map.base_map()
    names = sorted((c["name"] for c in base["counties"]), key=str.lower)
    version = f"?v={today:%Y%m%d}"
    card = f"{site_url}/static/og/site.png{version}"
    write(out_dir / "body" / "counties.html", counties_body(base, payload))
    write(
        out_dir / "meta" / "counties.html",
        meta_tags(
            "Counties",
            description(
                f"Every Mississippi county's MHSAA football schools for the {seasons_label(payload['seasons'])}, "
                "with each school's class and region, on a map."
            ),
            f"{site_url}/static/og/counties.png{version}",
            f"{site_url}{counties_path()}",
            json_ld(breadcrumb_ld(site_url, counties_trail())),
        ),
    )
    sitemap.append((counties_path(), None, []))
    has = {c: any(s["county"] == c for s in payload["schools"]) for c in names}
    for county in names:
        slug = counties_path(county).rsplit("/", 1)[1]
        write(out_dir / "body" / f"counties-{slug}.html", county_body(county, payload, base, by_school))
        write(
            out_dir / "meta" / f"counties-{slug}.html",
            meta_tags(
                county_title(county),
                description(county_description(county, payload)),
                # Its own preview, or the site's for a county with no school (it has no image).
                f"{site_url}/static/og/counties/{slug}.png{version}" if has[county] else card,
                f"{site_url}{counties_path(county)}",
                json_ld(breadcrumb_ld(site_url, counties_trail(county))),
            ),
        )
        sitemap.append((counties_path(county), None, []))
    return counts, sitemap
