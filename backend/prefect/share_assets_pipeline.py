"""Share assets: link-preview images and meta tags for every region and class page.

Runs at the end of the daily region update (and on its own as a deployment).
It reads the site's own public API, the same numbers the page shows, and
writes into ``SHARE_OUTPUT_DIR`` (a volume nginx serves):

    og/{class}-{region}.png   region card, 1200x630
    og/{class}-{region}/{team}.png
                              team card (a region link with ?team=<slug>)
    og/{class}.png            class card
    og/bracket-{class}.png    class bracket card (/brackets/{class}a)
    og/bracket-{class}/{team}.png
                              a team's road through the bracket (?team=<slug>)
    og/site.png               fallback card for every other page
    meta/{class}-{region}.html, meta/{class}.html, meta/{class}-{region}/{team}.html,
    meta/bracket-{class}.html, meta/bracket-{class}/{team}.html
                              <title>, description, Open Graph / Twitter tags
    body/{class}-{region}.html, body/{class}.html, body/site.html
                              the page's content as static HTML (backend.helpers.static_pages)
    sitemap.xml               every region, class and bracket page, for search engines

nginx splices the matching ``meta/*.html`` into the app's ``index.html``
<head> for /standings/{class}a/{region}[?team=<slug>] and /standings/{class}a
(server-side include). A team without a file falls back to its region's tags,
anything else to the generic tags in ``index.html``. It also splices the
matching ``body/*.html`` into ``<main>``, so the page reads without
JavaScript; the app replaces it on load. Cards, tags and content all come
from the same API reads in the same run, so they describe the same snapshot.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import requests
from prefect import flow, get_run_logger, task

from backend.helpers.share_cards import (
    SITE_DESCRIPTION,
    SITE_NAME,
    SITE_TITLE,
    bracket_description,
    bracket_favorites,
    bracket_title,
    class_description,
    class_title,
    description,
    meta_tags,
    odds_mode,
    provenance,
    region_title,
    render_bracket_card,
    render_class_card,
    render_region_card,
    render_site_card,
    render_team_bracket_card,
    render_team_card,
    slugify,
    team_bracket_description,
    team_bracket_title,
    team_description,
    team_road,
    team_title,
)
from backend.helpers.static_pages import (
    bracket_body,
    bracket_path,
    bracket_preview_html,
    bracket_trail,
    breadcrumb_ld,
    class_body,
    class_path,
    class_trail,
    json_ld,
    landing_body,
    layout_results,
    locked_seeds,
    pick_featured,
    pick_insight_region,
    pick_scenario_region,
    region_body,
    region_path,
    region_trail,
    sitemap_xml,
    website_ld,
)

API_URL = os.environ.get("SHARE_API_URL", "http://api:8000/api/v1")
OUTPUT_DIR = os.environ.get("SHARE_OUTPUT_DIR", "/opt/share")
SITE_URL = os.environ.get("SITE_URL", "https://mshsfootball.com")

CLASSES = range(1, 8)

Fetch = Callable[[str], object | None]


def api_fetch(path: str) -> object | None:
    """GET one API path as JSON; None when it isn't there (404)."""
    res = requests.get(f"{API_URL}{path}", timeout=120)
    if res.status_code == 404:
        return None
    res.raise_for_status()
    return res.json()


def _write_atomic(path: Path, write: Callable[[Path], None]) -> None:
    """Write via a temp file in the same directory, then rename, so nginx never serves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=path.suffix)
    os.close(fd)
    try:
        write(Path(tmp))
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _write_text(path: Path, text: str) -> None:
    """Write a UTF-8 text file atomically."""
    _write_atomic(path, lambda p: p.write_text(text, encoding="utf-8"))


def _write_png(path: Path, image) -> None:
    """Write a Pillow image as an optimized PNG atomically."""
    _write_atomic(path, lambda p: image.save(p, "PNG", optimize=True))


def build_share_assets(
    fetch: Fetch,
    out_dir: Path,
    site_url: str,
    today: date,
    season: int | None = None,
) -> dict[str, int]:
    """Render every region and class card, its meta tags and its static page content for *season*
    (default: the newest), plus the front page's content and the sitemap.

    Returns counts of what was written: {"regions", "classes", "teams", "brackets", "bracket_teams"}.
    """
    keys = ("regions", "classes", "teams", "brackets", "bracket_teams")
    if season is None:
        seasons = fetch("/seasons") or []
        if not seasons:
            return dict.fromkeys(keys, 0)
        season = seasons[0]["season"]
    site_url = site_url.rstrip("/")
    _write_png(out_dir / "og" / "site.png", render_site_card())
    # The front page's head: its canonical address and the site's name for search results.
    _write_text(
        out_dir / "meta" / "site.html",
        meta_tags(
            SITE_TITLE,
            SITE_DESCRIPTION,
            f"{site_url}/static/og/site.png?v={today:%Y%m%d}",
            f"{site_url}/",
            json_ld(website_ld(site_url, SITE_NAME)),
        ),
    )
    written = dict.fromkeys(keys, 0)
    teams = {t["school"]: t for t in fetch(f"/teams?season={season}") or []}
    sitemap: list[tuple[str, date | None]] = [("/", today), ("/methodology", None)]
    region_payloads: dict[tuple[int, int], dict] = {}
    class_standings: dict[int, dict] = {}
    class_dates: dict[int, list[dict]] = {}
    region_game_days: dict[tuple[int, int], list[date]] = {}
    for clazz in CLASSES:
        standings = fetch(f"/standings/{clazz}?season={season}")
        if not standings or not standings.get("regions"):
            continue
        class_standings[clazz] = standings
        dates = (fetch(f"/seasons/{season}/dates?class={clazz}") or {}).get("dates", [])
        class_dates[clazz] = dates
        all_teams = [t for r in standings["regions"] for t in r["teams"]]
        mode = odds_mode(all_teams)
        as_of = date.fromisoformat(standings["as_of_date"])
        stamp = provenance(as_of, dates, mode, today)
        version = f"{as_of:%Y%m%d}"

        _write_png(out_dir / "og" / f"{clazz}.png", render_class_card(clazz, standings, stamp, mode))
        _write_text(
            out_dir / "meta" / f"{clazz}.html",
            meta_tags(
                class_title(clazz),
                class_description(clazz),
                f"{site_url}/static/og/{clazz}.png?v={version}",
                f"{site_url}/standings/{clazz}a",
                json_ld(breadcrumb_ld(site_url, class_trail(clazz))),
            ),
        )
        class_page = class_body(clazz, standings, f"{season} season · {stamp}", mode, teams)
        _write_text(out_dir / "body" / f"{clazz}.html", class_page)
        sitemap.append((class_path(clazz), as_of))
        written["classes"] += 1

        bracket = _write_bracket_assets(out_dir, site_url, clazz, season, standings, stamp, mode, version, fetch, teams)
        written["brackets"] += bracket["brackets"]
        written["bracket_teams"] += bracket["bracket_teams"]
        if bracket["brackets"]:
            sitemap.append((bracket_path(clazz), as_of))

        for region in sorted(r["region"] for r in standings["regions"]):
            payload = fetch(f"/standings/{clazz}/{region}?season={season}")
            if not payload or not payload.get("teams"):
                continue
            r_mode = odds_mode(payload["teams"])
            r_as_of = date.fromisoformat(payload["as_of_date"]) if payload.get("as_of_date") else as_of
            r_stamp = provenance(r_as_of, dates, r_mode, today)
            name = f"{clazz}-{region}"
            _write_png(out_dir / "og" / f"{name}.png", render_region_card(clazz, region, payload, r_stamp, r_mode))
            headline = payload.get("headline") or (
                f"Region {region}-{clazz}A standings, playoff odds, and what every team needs to happen next."
            )
            _write_text(
                out_dir / "meta" / f"{name}.html",
                meta_tags(
                    region_title(clazz, region),
                    description(headline),
                    f"{site_url}/static/og/{name}.png?v={r_as_of:%Y%m%d}",
                    f"{site_url}/standings/{clazz}a/{region}",
                    json_ld(breadcrumb_ld(site_url, region_trail(clazz, region))),
                ),
            )
            games = fetch(f"/games?season={season}&class={clazz}&region={region}") or []
            played = {
                (g["date"], frozenset((g["team_a"], g["team_b"])))
                for g in games
                if g.get("is_region_game") and g.get("date")
            }
            if played:
                region_game_days[(clazz, region)] = sorted(date.fromisoformat(str(d)[:10]) for d, _ in played)
            body = region_body(clazz, region, payload, f"{season} season · {r_stamp}", r_mode, teams, games)
            region_payloads[(clazz, region)] = {
                "standings": payload,
                "stamp": f"{season} season · {r_stamp}",
                "plain_stamp": f"{season} season · {provenance(r_as_of, dates, None, today)}",
                "mode": r_mode,
            }
            _write_text(out_dir / "body" / f"{name}.html", body)
            sitemap.append((region_path(clazz, region), r_as_of))
            written["regions"] += 1
            written["teams"] += _write_team_assets(out_dir, site_url, clazz, region, payload, r_stamp, r_mode, r_as_of)
    # The front page, with the most open race as its live example. The app shows this same file at "/".
    summary = fetch(f"/standings/summary?season={season}")
    featured = pick_featured(summary) if summary else None
    region_data = region_payloads.get((featured["clazz"], featured["card"]["region"])) if featured else None
    if featured and region_data:
        featured.update(region_data)
        featured["class_standings"] = class_standings.get(featured["clazz"])
        featured["bracket_html"] = _bracket_preview_html(fetch, season, featured, class_standings, teams)
    else:
        featured = None
    # The scenario examples: a region with an open title race (the featured one if it has one),
    # fetched again with each team's paths. Once the regular season is over nothing is open, so they
    # show the regions as they stood going into their final week instead.
    prefer = (featured["clazz"], featured["card"]["region"]) if featured else None
    examples, final = region_payloads, False
    pick = pick_scenario_region(region_payloads, prefer)
    if (
        not pick
        and region_payloads
        and not any(v["standings"].get("remaining_games") for v in region_payloads.values())
    ):
        eves = {k: final_week_eve(days[-1], class_dates.get(k[0], [])) for k, days in region_game_days.items()}
        examples = _payloads_on(fetch, season, eves, class_dates, today)
        pick, final = pick_scenario_region(examples, prefer), True
    scenario_example = None
    if pick:
        c, r = pick
        on = f"&date={examples[pick]['date']}" if final else ""
        scenario_example = {
            **examples[pick],
            "clazz": c,
            "region": r,
            "final": final,
            "scenario_payload": fetch(f"/standings/{c}/{r}?season={season}{on}&include_team_scenarios=true"),
        }
    # The "settles a spot" example: a region still too far out for full scenarios. Late in the season
    # every region has them, so it's a region as it last stood with 7-10 region games left.
    insight_regions, earlier = region_payloads, False
    insight_pick = pick_insight_region(region_payloads, prefer)
    if not insight_pick:
        eves = {
            k: eve
            for k, days in region_game_days.items()
            if len(region_payloads.get(k, {}).get("standings", {}).get("remaining_games") or []) <= 6
            and (eve := insight_week_eve(days, class_dates.get(k[0], []), today))
        }
        insight_regions = _payloads_on(fetch, season, eves, class_dates, today)
        insight_pick, earlier = pick_insight_region(insight_regions, prefer), True
    insight_example = (
        {**insight_regions[insight_pick], "clazz": insight_pick[0], "region": insight_pick[1], "earlier": earlier}
        if insight_pick
        else None
    )
    _write_text(out_dir / "body" / "site.html", landing_body(featured, teams, scenario_example, insight_example))
    if written["regions"]:
        _write_text(out_dir / "sitemap.xml", sitemap_xml(site_url, sitemap))
    return written


def _week_starts(dates: list[dict]) -> list[tuple[date, int]]:
    """Each game week's first day and week number, in order."""
    starts: dict[int, date] = {}
    for d in dates:
        if d.get("kind") == "games":
            day = date.fromisoformat(str(d["date"])[:10])
            starts[d["week"]] = min(starts.get(d["week"], day), day)
    return sorted((day, week) for week, day in starts.items())


def final_week_eve(last_game: date, dates: list[dict]) -> date:
    """The day before the week of a region's last region game: the last snapshot with that week still to play."""
    start = max((day for day, _ in _week_starts(dates) if day <= last_game), default=last_game)
    return start - timedelta(days=1)


def insight_week_eve(game_days: list[date], dates: list[dict], today: date) -> date | None:
    """The last day before a game week when a region still had 7-10 region games left, the stretch when its
    page shows results that settle a spot instead of full scenarios; None if it never did."""
    eves = [day - timedelta(days=1) for day, _ in _week_starts(dates)]
    fits = [eve for eve in eves if eve < today and 7 <= sum(1 for g in game_days if g > eve) <= 10]
    return max(fits, default=None)


def _payloads_on(
    fetch: Fetch, season: int, days: dict[tuple[int, int], date], class_dates: dict, today: date
) -> dict[tuple[int, int], dict]:
    """Each region in *days* as it stood on its day, shaped like the run's own region payloads."""
    out: dict[tuple[int, int], dict] = {}
    for (clazz, region), day in sorted(days.items()):
        payload = fetch(f"/standings/{clazz}/{region}?season={season}&date={day}")
        if not payload or not payload.get("teams"):
            continue
        mode = odds_mode(payload["teams"])
        as_of = date.fromisoformat(payload["as_of_date"]) if payload.get("as_of_date") else day
        stamp, plain = (provenance(as_of, class_dates.get(clazz, []), m, today) for m in (mode, None))
        out[(clazz, region)] = {
            "standings": payload,
            "stamp": f"{season} season · {stamp}",
            "plain_stamp": f"{season} season · {plain}",
            "mode": mode,
            "date": day,
        }
    return out


def _bracket_preview_html(fetch: Fetch, season: int, featured: dict, class_standings: dict, teams: dict) -> str:
    """The front page's picture of the featured class's bracket page, from the bracket's own data."""
    clazz = featured["clazz"]
    games = (fetch(f"/bracket/matchups?season={season}&class={clazz}") or {}).get("games") or []
    if not games:
        return ""
    layout = (fetch(f"/bracket?season={season}&class={clazz}") or {}).get("bracket_layout")
    projected = any(o.get("p_reach_weighted") is not None for g in games for o in g["side_a"]["occupants"])
    ctx = {
        "mode": "projected" if projected else "tossup",
        "results": layout_results(layout),
        "seeds": locked_seeds(class_standings.get(clazz)),
        "teams": teams,
    }
    return bracket_preview_html(clazz, games, ctx)


def _write_bracket_assets(
    out_dir: Path,
    site_url: str,
    clazz: int,
    season: int,
    standings: dict,
    stamp: str,
    mode: str,
    version: str,
    fetch: Fetch,
    teams_by_school: dict | None = None,
) -> dict[str, int]:
    """The class bracket card, its page content, and each playoff team's road card; removes ones for teams
    no longer in it."""
    teams = [t for r in standings["regions"] for t in r["teams"]]
    regions = {t["school"]: r["region"] for r in standings["regions"] for t in r["teams"]}
    favorites = bracket_favorites(teams, mode)
    if not favorites:  # no bracket odds yet (e.g. before any region is computed)
        return {"brackets": 0, "bracket_teams": 0}
    name = f"bracket-{clazz}"
    page = f"{site_url}/brackets/{clazz}a"
    _write_png(out_dir / "og" / f"{name}.png", render_bracket_card(clazz, favorites, regions, stamp, mode))
    _write_text(
        out_dir / "meta" / f"{name}.html",
        meta_tags(
            bracket_title(clazz),
            description(bracket_description(clazz, favorites, mode)),
            f"{site_url}/static/og/{name}.png?v={version}",
            page,
            json_ld(breadcrumb_ld(site_url, bracket_trail(clazz))),
        ),
    )
    matchups = fetch(f"/bracket/matchups?season={season}&class={clazz}") or {}
    games = matchups.get("games") or []
    if games:
        layout = (fetch(f"/bracket?season={season}&class={clazz}") or {}).get("bracket_layout")
        projected = any(o.get("p_reach_weighted") is not None for g in games for o in g["side_a"]["occupants"])
        ctx = {
            "mode": "projected" if projected else "tossup",
            "results": layout_results(layout),
            "seeds": locked_seeds(standings),
            "teams": teams_by_school or {},
        }
        page_body = bracket_body(clazz, games, ctx, f"{season} season · {stamp}")
        if page_body:
            _write_text(out_dir / "body" / f"{name}.html", page_body)
    current: set[str] = set()
    for team in favorites:
        road = team_road(games, team["school"], mode)
        slug = slugify(team["school"])
        if not road or not slug:
            continue
        current.add(slug)
        _write_png(
            out_dir / "og" / name / f"{slug}.png",
            render_team_bracket_card(clazz, regions.get(team["school"]), team, road, stamp, mode),
        )
        champion = (team.get("bracket_odds") or {}).get("champion_weighted" if mode == "projected" else "champion")
        _write_text(
            out_dir / "meta" / name / f"{slug}.html",
            meta_tags(
                team_bracket_title(team["school"], clazz),
                description(team_bracket_description(team["school"], road, champion)),
                f"{site_url}/static/og/{name}/{slug}.png?v={version}",
                f"{page}?team={slug}",
            ),
        )
    _remove_others(out_dir / "meta" / name, ".html", current)
    _remove_others(out_dir / "og" / name, ".png", current)
    return {"brackets": 1, "bracket_teams": len(current)}


def _remove_others(folder: Path, suffix: str, keep: set[str]) -> None:
    """Delete *folder*'s *suffix* files whose names aren't in *keep* (teams that moved or left)."""
    for path in folder.glob(f"*{suffix}"):
        if path.stem not in keep:
            path.unlink(missing_ok=True)


def _write_team_assets(
    out_dir: Path, site_url: str, clazz: int, region: int, payload: dict, stamp: str, mode: str, as_of: date
) -> int:
    """Each team's card and meta file for one region; removes ones for teams no longer in it."""
    name = f"{clazz}-{region}"
    meta_dir = out_dir / "meta" / name
    og_dir = out_dir / "og" / name
    current: set[str] = set()
    for team in payload["teams"]:
        slug = slugify(team["school"])
        if not slug:
            continue
        current.add(slug)
        _write_png(og_dir / f"{slug}.png", render_team_card(clazz, region, team, stamp, mode))
        _write_text(
            meta_dir / f"{slug}.html",
            meta_tags(
                team_title(team, clazz, region),
                description(team_description(team, clazz, region, mode)),
                f"{site_url}/static/og/{name}/{slug}.png?v={as_of:%Y%m%d}",
                f"{site_url}/standings/{clazz}a/{region}?team={slug}",
            ),
        )
    # A team that moved regions (or a renamed one) shouldn't keep a stale card here.
    _remove_others(meta_dir, ".html", current)
    _remove_others(og_dir, ".png", current)
    return len(current)


@task(name="Write share assets", retries=1, retry_delay_seconds=30)
def write_share_assets(season: int | None = None) -> dict[str, int]:
    """Prefect task: render every share card and meta file into SHARE_OUTPUT_DIR."""
    logger = get_run_logger()
    written = build_share_assets(api_fetch, Path(OUTPUT_DIR), SITE_URL, date.today(), season)
    logger.info(
        "Share assets written to %s: %d regions, %d classes, %d teams, %d brackets, %d bracket teams",
        OUTPUT_DIR,
        written["regions"],
        written["classes"],
        written["teams"],
        written["brackets"],
        written["bracket_teams"],
    )
    return written


@flow(name="Share Assets Flow")
def share_assets_flow(season: int | None = None) -> dict[str, int]:
    """Re-render share cards from the current API data (also runs after the daily region update)."""
    return write_share_assets(season)
