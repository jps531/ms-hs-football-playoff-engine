"""Static HTML for region and class pages, and the sitemap.

The share-assets pipeline writes these next to each page's meta tags. nginx
includes a page's file inside ``<main id="app">`` (server-side include), so a
search engine, a link preview, or a browser without JavaScript gets the actual
race: the headline, the standings table, the remaining games, what each team
needs, and the snapshot it all reflects. The app replaces it on load, the same
way it replaces the "loading" state today, so it is a floor under the page,
not a second version of it.

Everything here comes from the same API payloads the app reads, through the
same ordering and formatting helpers as the share cards (which mirror the
site's JavaScript), so the static page and the live one agree.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable
from datetime import date
from xml.sax.saxutils import escape as xml_escape

from backend.helpers.share_cards import (
    display_order,
    format_pct,
    mode_odds,
    odds_bucket,
    record_text,
    slugify,
    standing_positions,
    team_status,
)

ODDS_COLUMNS = (("p1", "1st"), ("p2", "2nd"), ("p3", "3rd"), ("p4", "4th"), ("p_playoffs", "Playoffs"))
INSIGHT_ORDER = {"clinch_seed": 0, "clinch_playoffs": 1, "eliminated_if": 2}
MODE_NAMES = {"projected": "projected", "tossup": "toss-up"}
DROPPED_WORDS = {"county", "high", "school", "academy"}  # as format.js's initials()


def _e(text: object) -> str:
    """HTML-escape any value."""
    return html.escape(str(text), quote=True)


def region_path(clazz: int, region: int) -> str:
    """ "/standings/7a/2"."""
    return f"/standings/{clazz}a/{region}"


def class_path(clazz: int) -> str:
    """ "/standings/7a"."""
    return f"/standings/{clazz}a"


def bracket_path(clazz: int) -> str:
    """ "/brackets/7a"."""
    return f"/brackets/{clazz}a"


def initials(name: str) -> str:
    """Fallback initials, as the app makes them: first letters of up to two significant words."""
    words = [w for w in re.split(r"[\s\-/]+", name) if w]
    significant = [w for w in words if w.lower() not in DROPPED_WORDS]
    return "".join(w[0].upper() for w in (significant or words)[:2])


def _mark(school: str, team: dict | None) -> str:
    """The team's helmet image when it has one, else its initials, as the app's ``teamMark`` falls back to."""
    helmet = (team or {}).get("helmet_url")
    if helmet:
        return f'<img class="mark mark--helmet" src="{_e(helmet)}" alt="" width="24" height="24" loading="lazy">'
    return f'<span class="mark mark--initials" aria-hidden="true">{_e(initials(school))}</span>'


def _badge(team: dict, clazz: int) -> str:
    """The team's status badge (Clinched #1, Eliminated, …), text only."""
    status = team_status(team, clazz)
    if not status:
        return ""
    kind, label = status
    return f'<span class="badge badge--{_e(kind)}">{_e(label)}</span>'


def _odds(p: float | None) -> str:
    """An odds cell's contents, colored like the app's."""
    return f'<span class="odds odds--{odds_bucket(p)}">{_e(format_pct(p))}</span>'


def _provenance(stamp: str) -> str:
    """The snapshot line, plain text, under the title."""
    return f'<p class="provenance provenance--static">{_e(stamp)}</p>'


def _orient(team_a: str, team_b: str, location_a: str | None) -> tuple[str, str, str]:
    """(first, joiner, second) with the visitor first, as standings.js's ``orient``: "at" when the site is known."""
    if location_a == "home":
        return team_b, "at", team_a
    if location_a == "away":
        return team_a, "at", team_b
    return team_a, "vs", team_b


def game_date(iso: str | None) -> str:
    """ "Thu, Nov 6", as format.js's ``gameDate``; "" without a date."""
    if not iso:
        return ""
    d = date.fromisoformat(iso)
    return f"{d:%a}, {d:%b} {d.day}"


def remaining_matchups(remaining: list[dict], games: list[dict] | None) -> list[str]:
    """Each remaining region game as the page lists it: "Thu, Nov 6: Murrah at Germantown".

    Mirrors the region view: the schedule (``/games``) gives the date and, when it knows
    the site, home and away; otherwise the standings' own ``location_a`` does. Dated games
    come first, oldest first, in the standings' order within a day.
    """
    scheduled: dict[frozenset[str], dict] = {}
    for g in games or []:
        played = g.get("final") and g.get("score_a") is not None and g.get("score_b") is not None
        if g.get("is_region_game") and not played:
            scheduled[frozenset((g["team_a"], g["team_b"]))] = g
    out = []
    for i, game in enumerate(remaining):
        listed = scheduled.get(frozenset((game["team_a"], game["team_b"])))
        sides = _orient(listed["team_a"], listed["team_b"], listed.get("location_a")) if listed else None
        if not sides or (sides[1] != "at" and game.get("location_a")):
            sides = _orient(game["team_a"], game["team_b"], game.get("location_a"))
        when = (listed or {}).get("date")
        out.append((when or "9999", i, f"{game_date(when)}: " if when else "", " ".join(sides)))
    return [f"{prefix}{text}" for _, _, prefix, text in sorted(out)]


def _insight_title(insight: dict) -> str | None:
    """The outcome, worded as the page's scenario cards word it (``insightCards`` in scenarios.js)."""
    team, kind, seed = insight["team"], insight["insight_type"], insight.get("seed")
    if kind == "clinch_seed":
        return f"{team} clinches the region" if seed == 1 else f"{team} clinches the No. {seed} seed"
    if kind == "clinch_playoffs":
        return f"{team} clinches a playoff spot"
    if kind == "eliminated_if":
        return f"{team} is eliminated"
    return None


def insight_lines(insights: Iterable[dict] | None) -> list[str]:
    """What has to happen, one line per outcome as the page's cards have it: clinches first, by seed,
    then eliminations; each outcome's alternative ways joined by "or".

    Each way is the engine's own condition text (the part of ``rendered`` after the colon).
    """
    ways: dict[tuple, tuple[str | None, list[str]]] = {}
    ordered = sorted(
        (i for i in insights or [] if i.get("insight_type") in INSIGHT_ORDER and ": " in (i.get("rendered") or "")),
        key=lambda i: (INSIGHT_ORDER[i["insight_type"]], i.get("seed") or 9),
    )
    for insight in ordered:
        condition = insight["rendered"].split(": ", 1)[1].replace("; ", " and ")
        key = (insight["insight_type"], insight["team"], insight.get("seed"))
        conditions = ways.setdefault(key, (_insight_title(insight), []))[1]
        if condition not in conditions:
            conditions.append(condition)
    return [f"{title} if {' or if '.join(conditions)}" for title, conditions in ways.values()]


def _row_start(team: dict, pos: int) -> str:
    """A table row's opening and position cell; eliminated teams are dimmed as in the app."""
    cls = "is-eliminated" if team.get("eliminated") else ""
    return f'<tr class="{cls}"><td class="col-pos">{pos}</td>'


def _team_cell(team: dict, page: str, clazz: int, teams: dict[str, dict]) -> str:
    """The team's row header: mark, name and status badge, linking to its view of the region page."""
    name = team["school"]
    href = _e(f"{page}?team={slugify(name)}")
    label = f'<span class="team-name">{_e(name)}</span>{_badge(team, clazz)}'
    return (
        f'<th scope="row" class="col-team"><a class="team-link" href="{href}">'
        f'{_mark(name, teams.get(name))}<span class="row-toggle__label">{label}</span></a></th>'
    )


def _region_record(team: dict) -> str:
    """ "4–1" in region play."""
    r = team["record"]
    return _e(record_text(r["region_wins"], r["region_losses"], r.get("region_ties") or 0))


def _overall_record(team: dict) -> str:
    """ "7–2" overall."""
    r = team["record"]
    return _e(record_text(r["wins"], r["losses"], r.get("ties") or 0))


def _list_section(title: str, items: list[str]) -> str:
    """A titled bulleted list, or nothing when *items* is empty."""
    if not items:
        return ""
    lis = "".join(f"<li>{_e(item)}</li>" for item in items)
    return f'<section class="section"><h2 class="section-title">{_e(title)}</h2><ul class="static-list">{lis}</ul></section>'


def region_body(
    clazz: int,
    region: int,
    payload: dict,
    stamp: str,
    mode: str,
    teams: dict[str, dict],
    games: list[dict] | None = None,
) -> str:
    """A region page's content: title, headline, snapshot line, standings, remaining games and conditions.

    *games* are the region's ``/games`` rows, for the remaining games' dates and sites.
    """
    ordered = display_order(payload["teams"])
    positions = standing_positions(ordered)
    page = region_path(clazz, region)
    rows = []
    for pos, team in zip(positions, ordered, strict=True):
        odds = "".join(f'<td class="col-odds">{_odds(mode_odds(team, key, mode))}</td>' for key, _ in ODDS_COLUMNS)
        rows.append(
            f"{_row_start(team, pos)}{_team_cell(team, page, clazz, teams)}"
            f'<td class="col-rec">{_region_record(team)}</td>'
            f'<td class="col-rec col-overall">{_overall_record(team)}</td>{odds}</tr>'
        )
    heads = "".join(f'<th scope="col" class="col-odds">{label}</th>' for _, label in ODDS_COLUMNS)
    table = (
        '<table class="standings">'
        f'<caption class="visually-hidden">Region {region}-{clazz}A standings and {MODE_NAMES[mode]} odds of '
        "finishing in each playoff position.</caption>"
        '<thead><tr><th scope="col" class="col-pos"><span class="visually-hidden">Position</span></th>'
        '<th scope="col" class="col-team">Team</th><th scope="col" class="col-rec">Region</th>'
        f'<th scope="col" class="col-rec col-overall">Overall</th>{heads}</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    schedule = _list_section("Remaining games", remaining_matchups(payload.get("remaining_games") or [], games))
    needs = _list_section("What has to happen", insight_lines(payload.get("key_insights")))
    headline = payload.get("headline")
    headline_html = f'<p class="headline">{_e(headline)}</p>' if headline else ""
    return (
        '<div class="page static-page">'
        '<header class="region-head">'
        f'<p class="region-head__links"><a href="{class_path(clazz)}">All {clazz}A regions</a> '
        f'<a href="{bracket_path(clazz)}">{clazz}A Bracket</a></p>'
        f'<h1 class="title">Region {region}-{clazz}A</h1>{headline_html}{_provenance(stamp)}'
        "</header>"
        f"{table}{schedule}{needs}"
        "</div>\n"
    )


def class_body(clazz: int, standings: dict, stamp: str, mode: str, teams: dict[str, dict]) -> str:
    """A class page's content: every region's condensed table, each linking to its region page."""
    blocks = []
    for block in sorted(standings["regions"], key=lambda b: b["region"]):
        region = block["region"]
        ordered = display_order(block["teams"])
        positions = standing_positions(ordered)
        page = region_path(clazz, region)
        rows = "".join(
            f"{_row_start(t, pos)}{_team_cell(t, page, clazz, teams)}"
            f'<td class="col-rec">{_region_record(t)}</td>'
            f'<td class="col-odds">{_odds(mode_odds(t, "p1", mode))}</td>'
            f'<td class="col-odds">{_odds(mode_odds(t, "p_playoffs", mode))}</td></tr>'
            for pos, t in zip(positions, ordered, strict=True)
        )
        blocks.append(
            f'<section class="region-block" aria-labelledby="region-{region}">'
            f'<h2 class="region-block__title" id="region-{region}"><a href="{page}">Region {region}</a></h2>'
            '<table class="standings standings--compact">'
            f'<caption class="visually-hidden">Region {region}-{clazz}A standings</caption>'
            '<thead><tr><th scope="col" class="col-pos"><span class="visually-hidden">Position</span></th>'
            '<th scope="col" class="col-team">Team</th><th scope="col" class="col-rec">Region</th>'
            '<th scope="col" class="col-odds">1st</th><th scope="col" class="col-odds">Playoffs</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></section>"
        )
    return (
        '<div class="page entry-head static-page">'
        f'<h1 class="title">Class {clazz}A</h1>{_provenance(stamp)}</div>'
        f'<div class="page region-blocks static-page">{"".join(blocks)}</div>\n'
    )


def site_body(regions_by_class: dict[int, list[int]], brackets: Iterable[int]) -> str:
    """The front page's content: every class, its regions and bracket, as links."""
    with_bracket = set(brackets)
    sections = []
    for clazz in sorted(regions_by_class):
        links = "".join(
            f'<li><a href="{region_path(clazz, r)}">Region {r}-{clazz}A</a></li>'
            for r in sorted(regions_by_class[clazz])
        )
        bracket = f' · <a href="{bracket_path(clazz)}">{clazz}A Bracket</a>' if clazz in with_bracket else ""
        sections.append(
            f'<section class="section"><h2 class="section-title"><a href="{class_path(clazz)}">Class {clazz}A</a>'
            f'{bracket}</h2><ul class="static-list static-list--inline">{links}</ul></section>'
        )
    return (
        '<div class="page static-page">'
        '<h1 class="title">Mississippi high school football playoff races</h1>'
        '<p class="prose">Every MHSAA region race: who’s in, who’s out, and exactly what has to happen next.</p>'
        f"{''.join(sections)}</div>\n"
    )


def sitemap_xml(site_url: str, pages: Iterable[tuple[str, date | None]]) -> str:
    """A sitemap of *pages* ((path, last modified)), for search engines."""
    site = site_url.rstrip("/")
    entries = []
    for path, modified in pages:
        lastmod = f"<lastmod>{modified.isoformat()}</lastmod>" if modified else ""
        entries.append(f"<url><loc>{xml_escape(site + path)}</loc>{lastmod}</url>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(entries) + "\n</urlset>\n"
    )
