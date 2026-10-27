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
import json
import re
from collections.abc import Iterable
from datetime import date, datetime
from xml.sax.saxutils import escape as xml_escape

from backend.helpers.certainty import CERTAIN_EPS
from backend.helpers.color_contrast import contrast_ratio
from backend.helpers.share_cards import (
    display_order,
    format_pct,
    mode_odds,
    odds_bucket,
    position_labels,
    record_text,
    slugify,
    standing_positions,
    team_status,
)

# (key, header, what it measures): headers and their full names match ODDS_COLUMNS in app.js.
ODDS_COLUMNS = (
    ("p1", "1st", "Chance of finishing 1st (the #1 seed)"),
    ("p2", "2nd", "Chance of finishing 2nd (the #2 seed)"),
    ("p3", "3rd", "Chance of finishing 3rd (the #3 seed)"),
    ("p4", "4th", "Chance of finishing 4th (the #4 seed)"),
    ("p_playoffs", "Makes playoffs", "Chance of making the playoffs as any seed"),
)
ODDS_BY_KEY = {key: (label, full) for key, label, full in ODDS_COLUMNS}


def _odds_head(key: str) -> str:
    """An odds column header: the short label on screen, what it measures for screen readers and on hover."""
    label, full = ODDS_BY_KEY[key]
    return (
        f'<th scope="col" class="col-odds" title="{full}"><span aria-hidden="true">{label}</span>'
        f'<span class="visually-hidden">{full}</span></th>'
    )


INSIGHT_ORDER = {"clinch_seed": 0, "clinch_playoffs": 1, "eliminated_if": 2}
MODE_NAMES = {"projected": "projected", "tossup": "toss-up"}
DROPPED_WORDS = {"county", "high", "school", "academy"}  # as format.js's initials()


def _e(text: object) -> str:
    """HTML-escape any value exactly as format.js's ``escapeHtml`` does (apostrophe as ``&#39;``),
    so markup shared with the app is byte-for-byte the same."""
    return html.escape(str(text), quote=True).replace("&#x27;", "&#39;")


def region_path(clazz: int, region: int) -> str:
    """ "/standings/7a/2"."""
    return f"/standings/{clazz}a/{region}"


def class_path(clazz: int) -> str:
    """ "/standings/7a"."""
    return f"/standings/{clazz}a"


def bracket_path(clazz: int) -> str:
    """ "/brackets/7a"."""
    return f"/brackets/{clazz}a"


# ---------------------------------------------------------- breadcrumbs, structured data

Trail = list[tuple[str, str]]  # [(label, path), …], home first, this page last


def class_trail(clazz: int) -> Trail:
    """Home › Class 3A."""
    return [("Home", "/"), (f"Class {clazz}A", class_path(clazz))]


def region_trail(clazz: int, region: int) -> Trail:
    """Home › Class 3A › Region 6-3A."""
    return [*class_trail(clazz), (f"Region {region}-{clazz}A", region_path(clazz, region))]


def bracket_trail(clazz: int) -> Trail:
    """Home › Class 3A › Class 3A Bracket."""
    return [*class_trail(clazz), (f"Class {clazz}A Bracket", bracket_path(clazz))]


def breadcrumb_nav(trail: Trail) -> str:
    """The visible breadcrumbs (components.js's ``breadcrumbs``): the last entry is this page, not linked."""
    items = "".join(
        f'<li aria-current="page">{_e(label)}</li>'
        if i == len(trail) - 1
        else f'<li><a href="{path}">{_e(label)}</a></li>'
        for i, (label, path) in enumerate(trail)
    )
    return f'<nav class="crumbs" aria-label="Breadcrumb"><ol>{items}</ol></nav>'


def json_ld(data: dict) -> str:
    """A ``<script type="application/ld+json">`` block (data, not code: the CSP doesn't apply to it).

    ``<`` is escaped so no value can close the element early.
    """
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f'<script type="application/ld+json">{payload}</script>'


def breadcrumb_ld(site_url: str, trail: Trail) -> dict:
    """schema.org BreadcrumbList for *trail*, the trail search results show under a page's title."""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": label, "item": f"{site_url}{path}"}
            for i, (label, path) in enumerate(trail, start=1)
        ],
    }


def website_ld(site_url: str, name: str) -> dict:
    """schema.org WebSite: the site's name as search results should show it."""
    return {"@context": "https://schema.org", "@type": "WebSite", "name": name, "url": f"{site_url}/"}


def initials(name: str) -> str:
    """Fallback initials, as the app makes them: first letters of up to two significant words."""
    words = [w for w in re.split(r"[\s\-/]+", name) if w]
    significant = [w for w in words if w.lower() not in DROPPED_WORDS]
    return "".join(w[0].upper() for w in (significant or words)[:2])


_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")
# A seed is locked when it's certain (backend.helpers.certainty; mirrors app.js).
_LOCKED = 1 - CERTAIN_EPS

# The badge icons (ICONS in components.js).
BADGE_ICONS = {
    "clinched": '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 8.5l3 3 6-7"/></svg>',
    "eliminated": '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" '
    'stroke-linecap="round"><path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/></svg>',
    "coinflip": '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6">'
    '<circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="3.2"/></svg>',
}
BADGE_ICONS["champion"] = BADGE_ICONS["clinched"]
# The Explanation's lightbulb (ICONS.bulb in components.js).
BULB_ICON = (
    '<svg class="outcome__explain-icon" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" '
    'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 11.5h4M6.5 14h3"/>'
    '<path d="M6 11.5c0-1.6-2.5-2.8-2.5-5.5a4.5 4.5 0 0 1 9 0c0 2.7-2.5 3.9-2.5 5.5"/></svg>'
)


def team_colors(team: dict | None) -> tuple[str, str] | None:
    """(shell, stripe) for a team's generic helmet, as format.js's ``teamRawColors``; None without a primary."""
    variants = (team or {}).get("color_variants") or {}
    shell = (variants.get("primary") or {}).get("raw")
    if not shell or not _HEX.match(shell):
        return None
    secondary = ((variants.get("secondary") or [{}])[0] or {}).get("raw") or str(
        (team or {}).get("secondary_color_hex") or ""
    ).split(",")[0].strip()
    return shell.upper(), (secondary.upper() if _HEX.match(secondary or "") else "#FFFFFF")


def generic_helmet(shell: str, stripe: str, size: int = 24) -> str:
    """A helmet drawn in the team's colors, as components.js's ``genericHelmet``."""
    pale = " mark--pale" if contrast_ratio(shell if shell.startswith("#") else f"#{shell}", "#FFFFFF") < 1.6 else ""
    return (
        f'<svg class="mark mark--generic{pale}" viewBox="0 0 32 28" width="{size}" height="{size}" aria-hidden="true">'
        '<g fill="none" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M20 13H30.2V22.4H21.6M19.6 17.8H30.2M25 13V22.4" stroke="#8C8C8C" stroke-width="1.7"/>'
        '<path class="helmet__shell" d="M2.5 16.2C2.5 8.2 8.8 2.6 16.4 2.6C22.4 2.6 26.6 6.2 27.8 11.3L20.2 12.2'
        'L19.2 19.4L21.4 22.9C18.8 25.2 14.6 26 10.6 25.2C5.6 24.2 2.5 20.9 2.5 16.2Z" '
        f'fill="{_e(shell)}" stroke-width="1.5" paint-order="stroke"/>'
        f'<path d="M5.2 11.8C7.2 7.4 11 5 15.6 4.6" stroke="{_e(stripe)}" stroke-width="1.8"/>'
        '<circle cx="12.4" cy="16.4" r="1.6" fill="#8C8C8C"/>'
        "</g></svg>"
    )


def _mark(school: str, team: dict | None, size: int = 24) -> str:
    """The team's mark as the app's ``teamMark`` draws it: its helmet image, else a helmet in its colors,
    else its initials."""
    helmet = (team or {}).get("helmet_url")
    if helmet:
        return (
            f'<img class="mark mark--helmet" src="{_e(helmet)}" alt="" width="{size}" height="{size}" loading="lazy">'
        )
    colors = team_colors(team)
    if colors:
        return generic_helmet(*colors, size=size)
    return f'<span class="mark mark--initials" aria-hidden="true">{_e(initials(school))}</span>'


def region_complete(teams: list[dict]) -> bool:
    """Every team has played every region game (standings.js's ``regionComplete``)."""
    n = len(teams)
    return n > 1 and all(
        t["record"]["region_wins"] + t["record"]["region_losses"] + (t["record"].get("region_ties") or 0) >= n - 1
        for t in teams
    )


def _badge(team: dict, clazz: int, complete: bool = False) -> str:
    """The team's status badges as components.js's ``statusBadges`` draws them (Clinched #1, Eliminated, …)."""
    badges = []
    status = team_status(team, clazz)
    if status:
        badges.append(status)
    if complete and team.get("coin_flip_needed"):
        badges.append(("coinflip", "Coin flip"))
    return "".join(
        f'<span class="badge badge--{_e(kind)}">{BADGE_ICONS.get(kind, "")}{_e(label)}</span>' for kind, label in badges
    )


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
        return f"{team} clinches the region" if seed == 1 else f"{team} clinches the #{seed} seed"
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


def _row_start(team: dict, pos: str) -> str:
    """A table row's opening and position cell; eliminated teams are dimmed as in the app."""
    cls = "is-eliminated" if team.get("eliminated") else ""
    return f'<tr class="{cls}"><td class="col-pos">{pos}</td>'


def _team_cell(team: dict, page: str, clazz: int, teams: dict[str, dict], complete: bool, link: bool = True) -> str:
    """The team's row header: mark, name and status badges, linking to its view of the region page.

    ``link=False`` drops the link, for a preview that is itself one link.
    """
    name = team["school"]
    inner = (
        f'{_mark(name, teams.get(name))}<span class="row-toggle__label">'
        f'<span class="team-name">{_e(name)}</span>{_badge(team, clazz, complete)}</span>'
    )
    if not link:
        return f'<th scope="row" class="col-team"><span class="team-link">{inner}</span></th>'
    href = _e(f"{page}?team={slugify(name)}")
    return f'<th scope="row" class="col-team"><a class="team-link" href="{href}">{inner}</a></th>'


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


def _ordinal(n: int) -> str:
    """1 → '1st', 2 → '2nd', 11 → '11th'."""
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def tie_heading(tie: dict) -> tuple[str, str]:
    """A tie's heading lines (standings.js's ``tieHeading``): ("Tied for 2nd–4th", "Petal, Brandon and
    Northwest Rankin, all 3-2"). A shared record only when it is one (2-0 and 1-0 can be level)."""
    places = tie["places"]
    first, last = _ordinal(places[0]), _ordinal(places[-1])
    where = f"{first} and {last}" if len(places) == 2 else f"{first}–{last}"
    records = tie["records"]
    if len(set(records)) == 1:
        each = "both" if len(tie["teams"]) == 2 else "all"
        teams = f"{join_names(tie['teams'])}, {each} {records[0]}"
    else:
        teams = join_names([f"{t} ({r})" for t, r in zip(tie["teams"], records, strict=True)])
    return f"Tied for {where}", teams


def tiebreaks_section(ties: list[dict] | None) -> str:
    """How a finished region's ties were broken (the API's ``tiebreaks``), or nothing without any."""
    if not ties:
        return ""
    blocks = []
    for tie in ties:
        title, teams = tie_heading(tie)
        steps = "".join(f"<li>{_e(s)}</li>" for s in tie["steps"])
        blocks.append(
            f'<div class="tiebreak"><h3 class="tiebreak__title">{_e(title)}</h3>'
            f'<p class="tiebreak__teams">{_e(teams)}</p><ol class="tiebreak__steps">{steps}</ol></div>'
        )
    return (
        '<section class="section" aria-labelledby="tiebreaks-title">'
        '<h2 class="section-title" id="tiebreaks-title">How the ties were broken</h2>'
        '<p class="section-lead">The MHSAA region tiebreakers, step by step, with the actual results. '
        '<a href="/about#tiebreakers">How the tiebreakers work</a></p>'
        f"{''.join(blocks)}</section>"
    )


def region_table(clazz: int, region: int, payload: dict, mode: str, teams: dict[str, dict], link: bool = True) -> str:
    """The region page's standings table: position, team, records, odds of each seed and the playoffs."""
    ordered = display_order(payload["teams"])
    positions = position_labels(standing_positions(ordered))
    page = region_path(clazz, region)
    complete = not payload.get("remaining_games")
    rows = []
    for pos, team in zip(positions, ordered, strict=True):
        odds = "".join(f'<td class="col-odds">{_odds(mode_odds(team, key, mode))}</td>' for key, _, _ in ODDS_COLUMNS)
        rows.append(
            f"{_row_start(team, pos)}{_team_cell(team, page, clazz, teams, complete, link)}"
            f'<td class="col-rec">{_region_record(team)}</td>'
            f'<td class="col-rec col-overall">{_overall_record(team)}</td>{odds}</tr>'
        )
    heads = "".join(_odds_head(key) for key, _, _ in ODDS_COLUMNS)
    return (
        '<table class="standings">'
        f'<caption class="visually-hidden">Region {region}-{clazz}A standings and {MODE_NAMES[mode]} odds of '
        "finishing in each playoff position.</caption>"
        '<thead><tr><th scope="col" class="col-pos"><span class="visually-hidden">Position</span></th>'
        '<th scope="col" class="col-team">Team</th><th scope="col" class="col-rec">Region</th>'
        f'<th scope="col" class="col-rec col-overall">Overall</th>{heads}</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def region_body(
    clazz: int,
    region: int,
    payload: dict,
    stamp: str,
    mode: str,
    teams: dict[str, dict],
    games: list[dict] | None = None,
) -> str:
    """A region page's content: title, headline, snapshot line, standings, how any ties were broken (once
    every game is played), remaining games and conditions.

    *games* are the region's ``/games`` rows, for the remaining games' dates and sites.
    """
    schedule = _list_section("Remaining games", remaining_matchups(payload.get("remaining_games") or [], games))
    needs = _list_section("What has to happen", insight_lines(payload.get("key_insights")))
    headline = payload.get("headline")
    headline_html = f'<p class="headline">{_e(headline)}</p>' if headline else ""
    return (
        '<div class="page static-page">'
        '<header class="region-head">'
        f"{breadcrumb_nav(region_trail(clazz, region))}"
        f'<h1 class="title">Region {region}-{clazz}A</h1>{headline_html}{_provenance(stamp)}'
        "</header>"
        f"{region_table(clazz, region, payload, mode, teams)}{tiebreaks_section(payload.get('tiebreaks'))}"
        f"{schedule}{needs}"
        "</div>\n"
    )


def class_region_block(
    clazz: int, block: dict, mode: str, teams: dict[str, dict], heading: str = "h2", link: bool = True
) -> str:
    """One region as the class page shows it: its title and a condensed table (position, team, region
    record, odds of 1st and of the playoffs). ``link=False`` for a preview that is itself one link."""
    region = block["region"]
    ordered = display_order(block["teams"])
    positions = position_labels(standing_positions(ordered))
    page = region_path(clazz, region)
    complete = region_complete(ordered)
    title = f'<a href="{page}">Region {region}</a>' if link else f"Region {region}"
    labelled = f' aria-labelledby="region-{region}"' if link else ""
    heading_id = f' id="region-{region}"' if link else ""
    rows = "".join(
        f"{_row_start(t, pos)}{_team_cell(t, page, clazz, teams, complete, link)}"
        f'<td class="col-rec">{_region_record(t)}</td>'
        f'<td class="col-odds">{_odds(mode_odds(t, "p1", mode))}</td>'
        f'<td class="col-odds">{_odds(mode_odds(t, "p_playoffs", mode))}</td></tr>'
        for pos, t in zip(positions, ordered, strict=True)
    )
    return (
        f'<section class="region-block"{labelled}>'
        f'<{heading} class="region-block__title"{heading_id}>{title}</{heading}>'
        '<table class="standings standings--compact">'
        f'<caption class="visually-hidden">Region {region}-{clazz}A standings</caption>'
        '<thead><tr><th scope="col" class="col-pos"><span class="visually-hidden">Position</span></th>'
        '<th scope="col" class="col-team">Team</th><th scope="col" class="col-rec">Region</th>'
        f"{_odds_head('p1')}{_odds_head('p_playoffs')}</tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def class_body(clazz: int, standings: dict, stamp: str, mode: str, teams: dict[str, dict]) -> str:
    """A class page's content: every region's condensed table, each linking to its region page."""
    blocks = "".join(
        class_region_block(clazz, b, mode, teams) for b in sorted(standings["regions"], key=lambda b: b["region"])
    )
    return (
        '<div class="page entry-head static-page">'
        f'{breadcrumb_nav(class_trail(clazz))}<h1 class="title">Class {clazz}A</h1>{_provenance(stamp)}</div>'
        f'<div class="page region-blocks static-page">{blocks}</div>\n'
    )


def pick_featured(summary: dict) -> dict | None:
    """The region the front page uses for its examples: the most open race.

    Most teams still undecided, then the more volatile race, then the higher class, then the
    lower region number. ``{"clazz", "card"}``; None only when there are no regions at all.
    """
    cards = [{"clazz": c["class_"], "card": card} for c in summary.get("classes") or [] for card in c["regions"]]
    cards.sort(key=lambda f: (-f["card"]["teams_alive"], -f["card"]["volatility"], -f["clazz"], f["card"]["region"]))
    return cards[0] if cards else None


def _bullets(items: Iterable[str]) -> str:
    """A plain bulleted list."""
    return f'<ul class="landing-list">{"".join(f"<li>{_e(i)}</li>" for i in items)}</ul>'


def _section(key: str, title: str, body: str, level: str = "h2") -> str:
    """A front-page section with an uppercase heading."""
    cls = "landing-heading" if level == "h2" else "landing-subheading"
    return (
        f'<section class="landing-section" aria-labelledby="landing-{key}">'
        f'<{level} class="{cls}" id="landing-{key}">{_e(title)}</{level}>{body}</section>'
    )


def _class_preview_blocks(featured: dict) -> list[dict]:
    """The regions the class preview shows: the featured region and the next one (or the one before, for
    the class's last region), or the featured region alone when that's all there is."""
    region = featured["card"]["region"]
    blocks = sorted((featured.get("class_standings") or {}).get("regions") or [], key=lambda b: b["region"])
    if not any(b["region"] == region for b in blocks):
        blocks = [{"region": region, "teams": featured["standings"]["teams"]}]
    at = next(i for i, b in enumerate(blocks) if b["region"] == region)
    return blocks[at : at + 2] if at + 1 < len(blocks) else blocks[max(0, at - 1) : at + 1]


def _class_preview(featured: dict, teams: dict[str, dict]) -> str:
    """A small picture of the featured class's page (``_class_preview_blocks``), as one link to it."""
    clazz = featured["clazz"]
    shown = _class_preview_blocks(featured)
    tables = "".join(class_region_block(clazz, b, featured["mode"], teams, heading="p", link=False) for b in shown)
    return (
        f'<a class="landing-preview landing-preview--class" href="{class_path(clazz)}" '
        f'aria-label="Open the Class {clazz}A page">'
        '<div class="landing-preview__frame" aria-hidden="true"><div class="landing-preview__page">'
        f'<p class="title">Class {clazz}A</p>{_provenance(featured["stamp"])}'
        f'<div class="region-blocks">{tables}</div>'
        "</div></div>"
        f'<span class="landing-preview__label">Open Class {clazz}A</span></a>'
    )


def _lead(text: str) -> str:
    """The sentence introducing an example card."""
    return f'<p class="landing-lead">{_e(text)}</p>'


def _region_preview(featured: dict, teams: dict[str, dict]) -> str:
    """A small picture of the featured region's page, as one link to it (so nothing inside is a link)."""
    clazz, region, payload = featured["clazz"], featured["card"]["region"], featured["standings"]
    name = f"Region {region}-{clazz}A"
    headline = payload.get("headline")
    headline_html = f'<p class="headline">{_e(headline)}</p>' if headline else ""
    return (
        f'<a class="landing-preview" href="{region_path(clazz, region)}" aria-label="Open the {name} page">'
        '<div class="landing-preview__frame" aria-hidden="true"><div class="landing-preview__page">'
        f'<p class="title">{name}</p>{headline_html}{_provenance(featured["stamp"])}'
        f"{region_table(clazz, region, payload, featured['mode'], teams, link=False)}"
        "</div></div>"
        f'<span class="landing-preview__label">Open {name}</span></a>'
    )


# ------------------------------------------------------------------ scenario previews
# Pictures of the region page's scenario sections for the front page: the same cards
# components.js draws (scenarioCard, outcomeScenarioCard, conditionGroups), from the
# same grouping scenarios.js does (outcomeCards, completeScenarioCards).

COIN = (
    '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6">'
    '<circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="3.2"/></svg>'
)
SCENARIO_PREVIEW_CARDS = 2  # cards per scenario preview


def margin_text(lo: int | None, hi: int | None) -> str:
    """A chip's winning-margin suffix (format.js's ``marginText``): hi is exclusive, None unbounded."""
    lo = lo or 1
    if lo <= 1 and hi is None:
        return ""
    if hi is None:
        return f" by {lo}+"
    if hi == lo + 1:
        return f" by exactly {lo}"
    return f" by {lo}–{hi - 1}"


def join_names(names: list[str]) -> str:
    """ "A", "A and B", "A, B and C" (format.js's ``joinNames``)."""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}" if names else ""


def _team_style(team: dict | None) -> str:
    """The team's UI color for a card's accent (components.js's ``teamColorStyle``), when the API has it."""
    primary = ((team or {}).get("color_variants") or {}).get("primary") or {}
    light, dark = (primary.get("light") or {}).get("ui"), (primary.get("dark") or {}).get("ui")
    if not (light and dark and _HEX.match(light) and _HEX.match(dark)):
        return ""
    return f' style="--team-ui-light:{light};--team-ui-dark:{dark}"'


def condition_chip(cond: dict, teams: dict) -> str:
    """One condition as a chip (components.js's ``conditionChip``)."""
    if cond["type"] == "game_result":
        subject = cond["school"]
        verb = "loses to" if cond.get("required_result") == "loss" else "beats"
        margin = margin_text(cond.get("min_margin"), cond.get("max_margin"))
        return (
            f'<span class="chip">{_mark(subject, teams.get(subject))}<span><span class="chip__subject">'
            f"{_e(subject)}</span> {verb} {_e(cond['opponent'])}{_e(margin)}</span></span>"
        )
    icon = COIN if cond["type"] == "coin_flip" else ""
    return f'<span class="chip chip--text">{icon}<span>{_e(cond.get("description") or "")}</span></span>'


def condition_groups(groups: list[list[dict]], teams: dict) -> str:
    """OR-of-AND condition groups (components.js's ``conditionGroups``)."""
    rendered = [
        '<div class="cond-group">'
        + '<div class="and"><span>AND</span></div>'.join(condition_chip(c, teams) for c in group)
        + "</div>"
        for group in groups
        if group
    ]
    joined = '<div class="or"><span>OR</span></div>'.join(rendered)
    return f'<div class="conditions">{joined}</div>'


def scenario_card(card: dict, teams: dict) -> str:
    """An outcome card: what happens, its odds, and the results that make it happen (``scenarioCard``)."""
    odds = "" if card.get("p") is None else _odds(card["p"])
    return (
        f'<article class="scenario"{_team_style(teams.get(card["team"]))}>'
        f'<div class="scenario__head"><h4 class="scenario__title">{_e(card["title"])}\u00a0'
        f'<span class="scenario__if">IF</span></h4>{odds}</div>'
        f'<div class="scenario__body">{condition_groups(card["groups"], teams)}</div></article>'
    )


def outcome_scenario_card(card: dict, teams: dict, p: float | None = None) -> str:
    """One complete scenario: its chance (when given), every seed it produces, who's out, and the results
    (``outcomeScenarioCard``)."""
    seeds = "".join(
        (
            f'<li class="outcome__tie"><span class="outcome__seed">{_e(s["seed"])}</span>'
            f'<span class="outcome__tie-body"><span class="outcome__tie-teams">'
            f"{''.join(_team_label(t, teams) for t in s['teams'])}</span>"
            f'<span class="outcome__tie-note">{_e(s["note"])}</span></span></li>'
        )
        if "teams" in s
        else f'<li><span class="outcome__seed">{s["seed"]}</span>{_team_label(s["team"], teams)}</li>'
        for s in card["seeds"]
    )
    out = (
        f'<p class="outcome__out"><span class="outcome__out-label">Out</span> {_e(", ".join(card["out"]))}</p>'
        if card["out"]
        else ""
    )
    # Shared conditions once, then the alternatives in a box headed "AND ONE OF", so it's clear where they end.
    common = card.get("common") or []
    alternatives = (
        f'{condition_groups([common], teams)}<div class="oneof" role="group" aria-label="And one of">'
        f'<span class="oneof__label" aria-hidden="true">AND ONE OF</span>{condition_groups(card["groups"], teams)}</div>'
        if common
        else condition_groups(card["groups"], teams)
    )
    body = (
        f'<p class="outcome__if">IF</p><div class="scenario__body">{alternatives}</div>'
        if card["groups"] or common
        else ""
    )
    title = f'<h4 class="scenario__title">{_e(card["label"])}</h4>'
    head = title if p is None else f'<div class="scenario__head">{title}{_odds(p)}</div>'
    return (
        f'<article class="scenario outcome">{head}'
        f'<ol class="outcome__seeds" aria-label="Seeds">{seeds}</ol>{out}{body}{why_this_order(card.get("why"))}</article>'
    )


def why_blocks(explanation: list[dict] | None) -> list[dict]:
    """A scenario's "why this order" (scenarios.js's ``whyBlocks``): [{title, when, steps}], one per tie
    reaching the playoff places; ``when`` None when it holds whichever way the finish comes about."""
    out = []
    for e in explanation or []:
        first, last = _ordinal(e["places"][0]), _ordinal(e["places"][-1])
        where = f"{first} and {last}" if len(e["places"]) == 2 else f"{first}–{last}"
        results = [" and ".join(f"{g['winner']} beats {g['loser']}" for g in cube) for cube in (e.get("when") or [])]
        out.append(
            {
                "title": f"{join_names(e['teams'])}, tied for {where}",
                "when": f"If {', or '.join(results)}" if results else None,
                "steps": e["steps"],
            }
        )
    return out


def why_this_order(why: list[dict] | None) -> str:
    """The card's explanation, or nothing without ties: the app opens it in a sheet (components.js's
    ``whyTies``); a page without script shows it in the card, as a disclosure."""
    if not why:
        return ""
    ties = "".join(
        f'<div class="why-tie"><p class="why-tie__title">{_e(w["title"])}</p>'
        + (f'<p class="why-tie__when">{_e(w["when"])}:</p>' if w["when"] else "")
        + f'<ol class="tiebreak__steps">{"".join(f"<li>{_e(s)}</li>" for s in w["steps"])}</ol></div>'
        for w in why
    )
    return f'<details class="outcome__why"><summary>{BULB_ICON}Explanation</summary>{ties}</details>'


def _unconditional(path: dict) -> bool:
    """A path that needs nothing to happen (already clinched or eliminated)."""
    return len(path["conditions"]) == 1 and not path["conditions"][0]


def _outcome_p(team: dict, outcome: dict, mode: str) -> float:
    """A path outcome's probability in the odds mode (scenarios.js's ``outcomeProbability``)."""
    if outcome["type"] == "seed":
        return mode_odds(team, f"p{outcome['value']}", mode)
    playoffs = mode_odds(team, "p_playoffs", mode)
    return playoffs if outcome["type"] == "playoffs" else 1 - playoffs


def outcome_cards(teams_payload: list[dict], mode: str) -> dict[str, list[dict]]:
    """Each team's paths as the region page's cards: the title race, playoff spots and seeding
    (scenarios.js's ``outcomeCards``), each likeliest first."""
    groups: dict[str, list[dict]] = {"title": [], "playoffs": [], "seeding": []}
    for t in teams_payload:
        paths = t.get("paths") or []
        seed_paths = [p for p in paths if p["outcome"]["type"] == "seed"]
        playoffs = next((p for p in paths if p["outcome"]["type"] == "playoffs"), None)
        eliminated = next((p for p in paths if p["outcome"]["type"] == "eliminated"), None)
        conditional = [p for p in seed_paths if not _unconditional(p)]

        def card(title: str, path: dict, team: dict = t) -> dict:
            """One card for *path*."""
            return {
                "team": team["school"],
                "title": title,
                "p": _outcome_p(team, path["outcome"], mode),
                "groups": path["conditions"],
            }

        school = t["school"]
        groups["title"] += [card(f"{school} wins the region", p) for p in conditional if p["outcome"]["value"] == 1]
        bubble = not t.get("clinched") and not t.get("eliminated") and playoffs and not _unconditional(playoffs)
        only_seed = seed_paths[0]["outcome"]["value"] if len(seed_paths) == 1 else None
        if bubble:
            if eliminated and len(eliminated["conditions"]) < len(playoffs["conditions"]):
                groups["playoffs"].append(card(f"{school} is eliminated", eliminated))
            elif only_seed is None:
                groups["playoffs"].append(card(f"{school} makes the playoffs", playoffs))
            elif only_seed != 1:
                groups["playoffs"].append(card(f"{school} makes the playoffs as the #{only_seed} seed", playoffs))
        if only_seed is not None:
            continue
        groups["seeding"] += [
            card(f"{school} finishes as the #{p['outcome']['value']} seed", p)
            for p in conditional
            if p["outcome"]["value"] != 1
        ]
    for cards in groups.values():
        cards.sort(key=lambda c: -c["p"])
    return groups


# What decides a tie a scenario leaves open, by the step it's left from (scenarios.js's OPEN_TIE_NOTES).
OPEN_TIE_NOTES = {
    3: "Order decided by the tiebreaker: point differential, then fewest points allowed",
    5: "Order decided by fewest total points allowed in region games. Teams that remain tied start the tiebreakers over among themselves, and a coin flip decides if they're tied on every other tiebreaker.",
    6: "Order decided by a coin flip",
}


def _covers(v: list[dict], w: list[dict]) -> bool:
    """True when every condition of way *v* holds whenever way *w*'s do (scenarios.js's ``covers``)."""

    def holds(x: dict, y: dict) -> bool:
        if x["type"] != "game_result" or y["type"] != "game_result":
            return x == y
        if (x["school"], x["opponent"], x["required_result"]) != (y["school"], y["opponent"], y["required_result"]):
            return False
        xlo, xhi = x.get("min_margin") or 1, x.get("max_margin")
        ylo, yhi = y.get("min_margin") or 1, y.get("max_margin")
        return xlo <= ylo and (xhi is None or (yhi is not None and yhi <= xhi))

    return all(any(holds(x, y) for y in w) for x in v)


def complete_scenario_cards(scenarios: list[dict] | None, playoff_seeds: int = 4) -> list[dict]:
    """Every distinct way the region can finish, as cards (scenarios.js's ``completeScenarioCards``):
    one card per finish, its ways from every scenario reaching it joined by OR, numbered 1, 2, 3…,
    with the finish's chance (``p`` Toss-up, ``p_weighted`` Projected; None when the snapshot has none)."""
    cards = []
    for sc in scenarios or []:
        phrases = (sc.get("title") or "").split(" AND ")
        winners = [
            {"type": "game_result", "winner": g["winner"], "loser": g["loser"], "min_margin": 1, "max_margin": None}
            for g in sc.get("game_winners") or []
        ]
        sources = sc.get("condition_groups") or [sc.get("conditions") or winners]

        def chip(c: dict, i: int) -> dict:
            if c["type"] == "game_result":
                return {
                    "type": "game_result",
                    "school": c["winner"],
                    "opponent": c["loser"],
                    "required_result": "win",
                    "min_margin": c.get("min_margin") or 1,
                    "max_margin": c.get("max_margin"),
                }
            # Older snapshots carry no description; their title then lines up with a single group.
            return {"type": "text", "description": c.get("description") or (phrases[i] if i < len(phrases) else "")}

        groups = [g for g in ([chip(c, i) for i, c in enumerate(source)] for source in sources) if g]
        for group in sc.get("coinflip_groups") or []:
            if len(group) > 1:
                word = "between" if len(group) == 2 else "among"
                flip = {"type": "coin_flip", "description": f"A coin flip settles the tie {word} {join_names(group)}"}
                groups = [[*g, flip] for g in groups] or [[flip]]
        order = sorted(
            ({"team": t, "seed": int(n)} for t, n in (sc.get("outcomes") or {}).items()), key=lambda o: o["seed"]
        )
        ties = [(set(g["teams"]), g) for g in sc.get("open_groups") or []]
        seeds, placed = [], []
        for o in order:
            if o["seed"] > playoff_seeds:
                break
            tie = next((g for members, g in ties if o["team"] in members), None)
            if tie is None:
                seeds.append(o)
                continue
            if tie in placed:
                continue
            placed.append(tie)
            places = [x["seed"] for x in order if x["team"] in tie["teams"] and x["seed"] <= playoff_seeds]
            span = str(places[0]) if places[0] == places[-1] else f"{places[0]}\u2013{places[-1]}"
            shared = (
                f"{len(places)} of these {len(tie['teams'])} make the playoffs. "
                if len(places) < len(tie["teams"])
                else ""
            )
            seeds.append(
                {
                    "seed": span,
                    "teams": tie["teams"],
                    "note": shared + OPEN_TIE_NOTES.get(tie["step"], OPEN_TIE_NOTES[3]),
                }
            )
        tied = {t for members, _ in ties for t in members}
        out = [o["team"] for o in order if o["seed"] > playoff_seeds and o["team"] not in tied]
        if any(o["seed"] > playoff_seeds and o["team"] in tied for o in order):
            out.append("the rest of the tie")
        cards.append(
            {
                "seeds": seeds,
                "out": out,
                "ways": groups,
                "p": sc.get("p"),
                "p_weighted": sc.get("p_weighted"),
                "why": why_blocks(sc.get("explanation")),
            }
        )
    # One card per finish: the ways to it from every scenario reaching it, each once.
    finishes: dict[str, dict] = {}
    for c in cards:
        finish = repr((c["seeds"], c["out"]))
        if finish not in finishes:
            finishes[finish] = {**c, "ways": list(c["ways"])}
        else:
            finishes[finish]["ways"] += [w for w in c["ways"] if w not in finishes[finish]["ways"]]
    out_cards = []
    for i, c in enumerate(finishes.values(), start=1):
        listed = c.pop("ways")
        # A way another way already covers adds nothing ("B beats A by 9+" beside "B beats A").
        ways = [
            w
            for k, w in enumerate(listed)
            if not any(j != k and _covers(v, w) and (not _covers(w, v) or j < k) for j, v in enumerate(listed))
        ]
        # Conditions every way shares are said once; the ways keep only what differs.
        common = [x for x in ways[0] if all(x in w for w in ways)] if len(ways) > 1 else []
        groups = [[x for x in w if x not in common] for w in ways] if common else ways
        out_cards.append({**c, "common": common, "groups": groups, "label": f"Scenario {i}"})
    return out_cards


def _scenario_preview(
    example: dict, teams: dict, heading: str, sub: str, cards_html: list[str], anchor: str, what: str, odds: bool = True
) -> str:
    """A picture of one of the region page's scenario sections, as one link to that section; *what*
    names it for the link's accessible name ("title scenarios"). Without *odds* on its cards, its
    provenance line leaves out the odds mode."""
    clazz, region = example["clazz"], example["region"]
    name = f"Region {region}-{clazz}A"
    grid = f'<div class="scenario-grid">{"".join(cards_html)}</div>'
    group = f'<div class="scenario-group"><h3 class="sub-title">{_e(sub)}</h3>{grid}</div>' if sub else grid
    return (
        f'<a class="landing-preview landing-preview--scenarios" href="{region_path(clazz, region)}#{anchor}" '
        f'aria-label="Open {name}’s {what}">'
        '<div class="landing-preview__frame" aria-hidden="true"><div class="landing-preview__page">'
        f'<p class="title">{name}</p>{_provenance(example["stamp"] if odds else _plain_stamp(example))}'
        f'<section class="section"><p class="section-title">{_e(heading)}</p>{group}</section>'
        "</div></div>"
        f'<span class="landing-preview__label">Open {name}</span></a>'
    )


def _plain_stamp(example: dict) -> str:
    """The example's provenance without the odds mode, for a picture with no odds in it."""
    return example.get("plain_stamp") or example["stamp"]


def _open_title_teams(entry: dict) -> int:
    """How many teams can still win the region (neither certain nor out) in *entry*'s odds mode."""
    teams = entry["standings"].get("teams") or []
    return sum(1 for t in teams if 0 < mode_odds(t, "p1", entry["mode"]) < 1)


def _bubble_teams(entry: dict) -> int:
    """How many teams can still make or miss the playoffs in *entry*'s odds mode."""
    teams = entry["standings"].get("teams") or []
    return sum(1 for t in teams if 0 < mode_odds(t, "p_playoffs", entry["mode"]) < 1)


def pick_scenario_region(
    regions: dict[tuple[int, int], dict], prefer: tuple[int, int] | None
) -> tuple[int, int] | None:
    """The region the front page's scenario examples come from: one with full scenarios and an open title
    race, so every example has something to show; better still, one with a playoff spot still open too.
    Among those, the featured region, else the most open race in its class, else in any class. *regions*
    maps (class, region) to ``{"standings", "stamp", "mode"}``."""
    candidates = [
        k for k, v in regions.items() if v["standings"].get("scenarios_available") and _open_title_teams(v) >= 2
    ]
    if not candidates:
        return None
    same_class = prefer[0] if prefer else None
    return max(
        candidates,
        key=lambda k: (
            _bubble_teams(regions[k]) > 0,
            k == prefer,
            k[0] == same_class,
            _open_title_teams(regions[k]),
            -k[0],
            -k[1],
        ),
    )


def insight_cards(insights: list[dict] | None) -> list[dict]:
    """Key insights (one guaranteed path each) as cards (scenarios.js's ``insightCards``): insights proving
    the same outcome become one card, their ways joined by OR; clinches first, then eliminations."""
    rank = {"clinch_seed": 0, "clinch_playoffs": 1, "eliminated_if": 2}
    cards: dict[str, dict] = {}
    usable = [i for i in insights or [] if i.get("conditions") and _insight_title(i)]
    for i in sorted(usable, key=lambda i: (rank[i["insight_type"]], i.get("seed") or 9)):
        key = f"{i['insight_type']}|{i['team']}|{i.get('seed') or ''}"
        card = cards.setdefault(key, {"team": i["team"], "title": _insight_title(i), "p": None, "groups": []})
        card["groups"].append(
            [
                {
                    "type": "game_result",
                    "school": c["winner"],
                    "opponent": c["loser"],
                    "required_result": "win",
                    "min_margin": c.get("min_margin"),
                    "max_margin": c.get("max_margin"),
                }
                for c in i["conditions"]
            ]
        )
    return list(cards.values())


def _insight_count(entry: dict) -> int:
    """How many "settles a spot" cards *entry*'s region page shows (none once full scenarios replace them)."""
    standings = entry["standings"]
    return 0 if standings.get("scenarios_available") else len(insight_cards(standings.get("key_insights")))


def pick_insight_region(regions: dict[tuple[int, int], dict], prefer: tuple[int, int] | None) -> tuple[int, int] | None:
    """The region the front page's "settles a spot" example comes from: one still too far out for full
    scenarios, with results that settle a spot anyway; two or more cards' worth if possible, then the
    featured region, its class, and the most cards. *regions* is shaped as for ``pick_scenario_region``."""
    candidates = [k for k, v in regions.items() if _insight_count(v)]
    if not candidates:
        return None
    same_class = prefer[0] if prefer else None
    return max(
        candidates,
        key=lambda k: (
            _insight_count(regions[k]) >= SCENARIO_PREVIEW_CARDS,
            k == prefer,
            k[0] == same_class,
            _insight_count(regions[k]),
            -k[0],
            -k[1],
        ),
    )


def insight_preview(example: dict | None, teams: dict) -> str:
    """The front page's "settles a spot" example: a lead-in and a picture of the region page's cards for
    results that settle a spot no matter what else happens. *example* is the region picked by
    ``pick_insight_region`` with its stamp and mode: ``{"clazz", "region", "stamp", "mode", "standings"}``;
    ``"earlier": True`` when it's from earlier in the season (every region now has full scenarios)."""
    if not example:
        return ""
    cards = insight_cards(example["standings"].get("key_insights"))[:SCENARIO_PREVIEW_CARDS]
    if not cards:
        return ""
    clazz, region = example["clazz"], example["region"]
    name = f"Region {region}-{clazz}A"
    left = len(example["standings"].get("remaining_games") or [])
    games = f"{left} region game{'s' if left != 1 else ''}"
    lead = (
        f"Earlier in the season, with {games} left in {name}, these results would settle a spot no matter what "
        "else happened:"
        if example.get("earlier")
        else f"{name} still has {games} left, too many for full scenarios, but these results settle a spot no "
        "matter what else happens:"
    )
    intro = (
        f"Full scenarios appear once five or fewer region games remain; {left} are left. Until then, these are "
        "results that settle a spot no matter what else happens."
    )
    grid = "".join(scenario_card(c, teams) for c in cards)
    return _lead(lead) + (
        f'<a class="landing-preview landing-preview--scenarios" href="{region_path(clazz, region)}#scen-title" '
        f'aria-label="Open {name}’s results that settle a spot">'
        '<div class="landing-preview__frame" aria-hidden="true"><div class="landing-preview__page">'
        f'<p class="title">{name}</p>{_provenance(_plain_stamp(example))}'
        f'<section class="section"><p class="section-title">What has to happen</p>'
        f'<p class="prose muted">{_e(intro)}</p>'
        f'<div class="scenario-group scenario-group--spaced"><div class="scenario-grid">{grid}</div></div>'
        "</section></div></div>"
        f'<span class="landing-preview__label">Open {name}</span></a>'
    )


def scenario_previews(example: dict | None, teams: dict) -> dict[str, str]:
    """The front page's four scenario examples, each a lead-in and a preview: ``{"title", "playoffs",
    "seeding", "unique"}``, "" for any with nothing to show. *example* is the region picked by
    ``pick_scenario_region`` with its stamp and mode: ``{"clazz", "region", "stamp", "mode",
    "scenario_payload"}``, the payload including each team's paths; ``"final": True`` when the regular
    season is over and it's the region as it stood going into its final week."""
    empty = {"title": "", "playoffs": "", "seeding": "", "unique": ""}
    payload = (example or {}).get("scenario_payload")
    if not payload or not payload.get("scenarios_available"):
        return empty
    name = f"Region {example['region']}-{example['clazz']}A"
    final = example.get("final")
    then = " going into its final week" if final else ""
    leads = {
        "title": f"Here’s what {'had' if final else 'has'} to happen for the two likeliest champions of {name}{then}:",
        "playoffs": f"Here’s what {'decided' if final else 'decides'} the last playoff spots in {name}{then}:",
        "seeding": f"Here’s what {'would put' if final else 'puts'} teams in {name} at a particular seed:",
    }
    groups = outcome_cards(payload.get("teams") or [], example["mode"])
    out = dict(empty)
    for key, sub, what in (
        ("title", "The region title", "title scenarios"),
        ("playoffs", "Playoff spots", "playoff spot scenarios"),
        ("seeding", "Seeding", "seeding scenarios"),
    ):
        if groups[key]:
            cards = [scenario_card(c, teams) for c in groups[key][:SCENARIO_PREVIEW_CARDS]]
            out[key] = _lead(leads[key]) + _scenario_preview(
                example, teams, "What has to happen", sub, cards, "scen-title", what
            )
    complete = complete_scenario_cards(payload.get("scenarios"))
    if complete:
        key = "p_weighted" if example["mode"] == "projected" else "p"
        with_odds = all(c[key] is not None for c in complete)
        cards = [
            outcome_scenario_card(c, teams, c[key] if with_odds else None) for c in complete[:SCENARIO_PREVIEW_CARDS]
        ]
        ways = f"{len(complete)} way{'s' if len(complete) != 1 else ''}"
        first = "Here’s the first:" if len(complete) == 1 else "Here are the first two:"
        lead = (
            f"Going into its final week, {name} could finish {ways}." if final else f"{name} can still finish {ways}."
        )
        out["unique"] = _lead(f"{lead} {first}") + _scenario_preview(
            example, teams, "Scenarios", "", cards, "all-scen-title", "complete scenarios", odds=with_odds
        )
    return out


# ------------------------------------------------------------------ bracket preview
# A picture of the bracket page: the top quarter of one half of the featured class's
# tree (three rounds of the same game cards the page draws), with one game's sheet
# open beside it, the way it looks after tapping that game. Mirrors bracket.js and
# the bracket view in app.js (treeRow, bracketSide, gameDetail); laid out here with
# fixed positions, since there's no page to measure.

SEED_NAMES = {1: "#1 Seed", 2: "#2 Seed", 3: "#3 Seed", 4: "#4 Seed"}
HALF_NAMES = {"N": "North", "S": "South"}
CARD_H, PITCH, COL_W, COL_GAP = 98, 112, 240, 36
LOCK = (
    '<svg class="lock" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6">'
    '<rect x="3.5" y="7" width="9" height="7" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 015 0v2"/></svg>'
)
SHEET_LIST = 3  # occupants per side the preview's sheet lists
SHEET_MATCHUPS = 2  # and matchups


def position_name(region: int, seed: int) -> str:
    """ "Region 3 #1 Seed", as bracket.js's ``positionName``."""
    return f"Region {region} {SEED_NAMES.get(seed, f'#{seed} Seed')}"


def side_label(feeders: list[dict]) -> str:
    """Where a side comes from, as bracket.js's ``sideLabel`` says it."""
    names = [position_name(f["region"], f["seed"]) for f in feeders]
    if len(names) <= 2:
        return " or ".join(names)
    by_region: dict[int, list[int]] = {}
    for f in feeders:
        by_region.setdefault(f["region"], []).append(f["seed"])
    regions = sorted(by_region)
    full = {r: all(k in by_region[r] for k in (1, 2, 3, 4)) for r in regions}
    if all(full.values()):
        if len(regions) == 1:
            return f"Region {regions[0]} (Any Seed)"
        if len(regions) == 2:
            return f"Region {regions[0]} or {regions[1]} (Any Seed)"
        if all(not i or r == regions[i - 1] + 1 for i, r in enumerate(regions)):
            return f"Regions {regions[0]}–{regions[-1]} (Any Seed)"
        return f"Regions {', '.join(map(str, regions[:-1]))} or {regions[-1]} (Any Seed)"
    parts = []
    for r in regions:
        if full[r]:
            parts.append(f"Region {r} (Any Seed)")
        else:
            seeds = ", ".join(SEED_NAMES.get(k, f"#{k} Seed") for k in sorted(by_region[r]))
            parts.append(f"Region {r} ({seeds})")
    return ", ".join(parts)


def _pick(obj: dict, key: str, mode: str) -> float | None:
    """A value in the odds mode: the weighted one for Projected when there is one."""
    weighted = obj.get(f"{key}_weighted")
    return weighted if mode == "projected" and weighted is not None else obj.get(key)


def occupants(side: dict, mode: str) -> list[dict]:
    """Who might fill a side, likeliest first (bracket.js's ``occupants``)."""
    out = [
        {"team": o["team"], "p": _pick(o, "p_reach", mode) or 0.0, "locked": o.get("is_locked")}
        for o in side.get("occupants") or []
    ]
    out = [o for o in out if o["p"] > 0 or o["locked"]]
    return sorted(out, key=lambda o: (-o["p"], o["team"]))


def locked_team(side: dict) -> str | None:
    """The team certain to fill a side, or None."""
    return next((o["team"] for o in side.get("occupants") or [] if o.get("is_locked")), None)


def round_picks(col: dict, mode: str, results: dict) -> dict[str, str]:
    """Which team each open side of a tree column shows, so no team shows in two slots of one round
    (bracket.js's ``roundPicks``): ``"{game id}:{a|b}" -> team``.

    Taking every (team, side) chance in the column, likeliest first, a team goes to the side where
    it's likeliest and that side is filled; a side whose teams are all likelier elsewhere falls back
    to its likeliest. Ties go to the better seed (first round) or the earlier slot. A team locked
    into or playing in the column counts as placed.
    """
    placed: set[str] = set()
    open_sides = []
    for i, entry in enumerate(col["games"]):
        game = entry["game"]
        result = results.get(game["id"])
        for j, key in enumerate(("a", "b")):
            side = game[f"side_{key}"]
            locked = locked_team(side) or (result and (result["winner"] if key == "a" else result["loser"]))
            if locked or result:
                if locked:
                    placed.add(locked)
                continue
            feeders = side.get("feeders") or []
            rank = feeders[0]["seed"] if len(feeders) == 1 else 2 * i + j
            open_sides += [(f"{game['id']}:{key}", o["team"], o["p"], rank) for o in occupants(side, mode)]
    picks: dict[str, str] = {}
    for side_id, team, _, _ in sorted(open_sides, key=lambda o: (-o[2], o[3], o[1])):
        if side_id not in picks and team not in placed:
            picks[side_id] = team
            placed.add(team)
    return picks


def _split_host(a: str, b: str, p_host_a: float) -> str:
    """Who'd likelier host an undecided pairing, and how likely: "60% chance Raleigh hosts"."""
    return (
        f"{format_pct(p_host_a)} chance {a} hosts"
        if p_host_a >= 0.5
        else f"{format_pct(1 - p_host_a)} chance {b} hosts"
    )


def _hosting(p_host_a: float | None) -> str:
    """Who hosts a pairing: "a", "b", "split" or "neutral" (bracket.js's ``hosting``)."""
    if p_host_a is None:
        return "neutral"
    if p_host_a >= 0.995:
        return "a"
    if p_host_a <= 0.005:
        return "b"
    return "split"


def game_matchups(game: dict, mode: str) -> list[dict]:
    """The game's pairings in the odds mode, likeliest first (bracket.js's ``matchups``)."""
    ms = [
        {
            "a": m["team_a"],
            "b": m["team_b"],
            "p": _pick(m, "p_matchup", mode) or 0.0,
            "host_a": _pick(m, "p_host_a", mode),
        }
        for m in game.get("matchups") or []
    ]
    return sorted((m for m in ms if m["p"] > 0), key=lambda m: (-m["p"], m["a"], m["b"]))


def settled_host(game: dict, mode: str) -> str | None:
    """Which side hosts whoever gets there, when that's settled (app.js's ``settledHost``)."""
    if game["id"] == "final":
        return "neutral"
    hosts = {_hosting(m["host_a"]) for m in game_matchups(game, mode)}
    return next(iter(hosts)) if len(hosts) == 1 and "split" not in hosts else None


def layout_results(layout: dict | None) -> dict[str, dict]:
    """Played games' results keyed by matchup game id (bracket.js's ``layoutResults``)."""
    out: dict[str, dict] = {}

    def result(r: dict | None) -> dict | None:
        """One result as the cards use it."""
        if not r or not (r.get("winner") or {}).get("school"):
            return None
        return {
            "winner": r["winner"]["school"],
            "loser": (r.get("loser") or {}).get("school"),
            "winner_score": r.get("winner_score"),
            "loser_score": r.get("loser_score"),
        }

    for half, rounds in ((layout or {}).get("halves") or {}).items():
        for k, games in enumerate(rounds):
            for i, g in enumerate(games):
                if res := result(g.get("result")):
                    out[f"{half}-{k}-{i}"] = res
    if final := result(((layout or {}).get("championship") or {}).get("result")):
        out["final"] = final
    return out


def locked_seeds(class_standings: dict | None, games: list[dict] | None = None) -> dict[str, tuple[int, int]]:
    """Teams sure of a seed: school -> (region, seed), for their "Region 3 #1 Seed" label.

    From the standings, and failing that from the first-round spot a team is locked into in *games*.
    """
    seeds = {}
    for block in (class_standings or {}).get("regions") or []:
        for t in block["teams"]:
            seed = next((k for k in (1, 2, 3, 4) if (t["odds"].get(f"p{k}") or 0) >= _LOCKED), None)
            if seed:
                seeds[t["school"]] = (block["region"], seed)
    for g in games or []:
        for side in (g["side_a"], g["side_b"]):
            feeders = side.get("feeders") or []
            team = locked_team(side) if len(feeders) == 1 else None
            if team and team not in seeds:
                seeds[team] = (feeders[0]["region"], feeders[0]["seed"])
    return seeds


def _tree_line(gutter: str, team: str | None, name: str, teams: dict, sub: str, value: str, cls: str) -> str:
    """One row of a compact card (app.js's ``treeLine``)."""
    mark = _mark(team, teams.get(team), size=22) if team else '<span class="mark"></span>'
    sub_html = f'<span class="trow__sub">{sub}</span>' if sub else ""
    return (
        f'<span class="trow{cls}"><span class="trow__gutter">{gutter}</span>{mark}'
        f'<span class="trow__text"><span class="trow__name">{_e(name)}</span>{sub_html}</span>'
        f'<span class="trow__value">{value}</span></span>'
    )


def _tree_row(game: dict, side_key: str, result: dict | None, gutter: str, ctx: dict) -> str:
    """One side of a compact card: the result, the locked team, or the round's pick for it (see
    ``round_picks``; else its likeliest team) with its odds."""
    side = game[f"side_{side_key}"]
    teams = ctx["teams"]
    if result:
        team = locked_team(side) or (result["winner"] if side_key == "a" else result["loser"])
        won = team == result["winner"]
        score = result["winner_score"] if won else result["loser_score"]
        cls = " trow--result is-winner" if won else " trow--result"
        return _tree_line(gutter, team, team or "", teams, "", _e(score) if score is not None else "", cls)
    locked = locked_team(side)
    if locked:
        seed = ctx["seeds"].get(locked)
        label = position_name(*seed) if seed else "Clinched a playoff spot"
        sub = f'{LOCK}<span class="visually-hidden">Locked in: </span>{_e(label)}'
        return _tree_line(gutter, locked, locked, teams, sub, "", " trow--locked")
    listed = occupants(side, ctx["mode"])
    if not listed:
        return _tree_line(gutter, None, "No team can get here", teams, "", "", " trow--empty")
    feeders = side.get("feeders") or []
    if len(feeders) == 1:  # first round: the region/seed this slot is for
        sub = _e(position_name(feeders[0]["region"], feeders[0]["seed"]))
    else:
        sub = f"+{len(listed) - 1} more" if len(listed) > 1 else ""
    pick = (ctx.get("picks") or {}).get(f"{game['id']}:{side_key}")
    shown = next((o for o in listed if o["team"] == pick), listed[0])
    value = _odds(shown["p"]) + '<span class="visually-hidden"> chance to play here</span>'
    return _tree_line(gutter, shown["team"], shown["team"], teams, sub, value, "")


def _side_order(host: str | None) -> tuple[list[str], str]:
    """Sides top to bottom (home team last) and the word between them."""
    return (["b", "a"] if host == "a" else ["a", "b"]), ("at" if host in ("a", "b") else "vs")


def _tree_card(game: dict, ctx: dict, selected: bool) -> str:
    """A compact game card, as the tree draws it; the selected one is the game whose sheet is open."""
    result = ctx["results"].get(game["id"])
    state = (
        "played"
        if result
        else (
            "determined"
            if locked_team(game["side_a"]) and locked_team(game["side_b"])
            else "partial"
            if locked_team(game["side_a"]) or locked_team(game["side_b"])
            else "projected"
        )
    )
    order, joiner = _side_order(settled_host(game, ctx["mode"]))
    rows = _tree_row(game, order[0], result, "", ctx) + _tree_row(game, order[1], result, joiner, ctx)
    where = ", ".join(x for x in (game["round"], STATE_LABEL[state]) if x)
    return (
        f'<span class="tgame tgame--{state}{" is-path" if selected else ""}">'
        f'<span class="visually-hidden">{_e(where)}: </span>{rows}</span>'
    )


STATE_LABEL = {"played": "Final", "determined": "Matchup set", "partial": "One spot set", "projected": ""}
HALF_NAMES = {"N": "North", "S": "South"}
ROUND_SHORT = {
    "First Round": "R1",
    "Second Round": "R2",
    "Quarterfinals": "QF",
    "Semifinals": "SF",
    "Championship Game": "CG",
}


def tree_columns(games: list[dict]) -> list[dict]:
    """The bracket as columns, both halves stacked in each round, then the final (bracket.js's ``treeColumns``).

    Each column is ``{"name", "games": [{"game", "feeders"}]}``; feeders index the previous column.
    """
    halves: dict[str, dict[str, dict]] = {}
    final = None
    for g in games:
        if g["id"] == "final":
            final = g
            continue
        half, k = g["id"].split("-")[:2]
        halves.setdefault(half, {}).setdefault(k, {"name": g["round"], "games": []})["games"].append(g)
    shown = [[r for _, r in sorted(rounds.items(), key=lambda kv: int(kv[0]))] for rounds in halves.values()]
    depth = max((len(h) for h in shown), default=0)
    cols: list[dict] = []
    for k in range(depth):
        col, offset = [], 0
        for rounds in shown:
            prev = len(rounds[k - 1]["games"]) if k > 0 else 0
            for i, game in enumerate(rounds[k]["games"]):
                feeders = [] if k == 0 else [j for j in (offset + 2 * i, offset + 2 * i + 1) if j < offset + prev]
                col.append({"game": game, "feeders": feeders})
            offset += prev
        cols.append({"name": shown[0][k]["name"], "games": col})
    if final and depth:
        cols.append(
            {"name": final["round"], "games": [{"game": final, "feeders": list(range(len(cols[-1]["games"])))}]}
        )
    return cols


def tree_centers(cols: list[dict]) -> tuple[list[list[float]], float]:
    """Each card's vertical center and the tree's height, unscrolled (bracket.js's ``treeLayout`` at focus 0)."""
    centers: list[list[float]] = []
    for r, col in enumerate(cols):
        centers.append(
            [
                sum(centers[r - 1][j] for j in g["feeders"]) / len(g["feeders"])
                if r > 0 and g["feeders"]
                else i * PITCH + CARD_H / 2
                for i, g in enumerate(col["games"])
            ]
        )
    height = max((max(c) + CARD_H / 2 for c in centers if c), default=0)
    return centers, height


def bracket_body(clazz: int, games: list[dict], ctx: dict, stamp: str) -> str:
    """A bracket page's content, as the app first draws it on a wide screen: both halves, every round,
    each game between the two that feed it (app.js's ``bracketView``/``bracketHtml``). The lines
    joining games, and tapping a game, come with the app.

    *ctx* holds ``mode``, ``results``, ``seeds`` and ``teams``. Returns "" without games.
    """
    cols = tree_columns(games)
    if not cols:
        return ""
    picks = {k: v for c in cols for k, v in round_picks(c, ctx["mode"], ctx["results"]).items()}
    ctx = {**ctx, "picks": picks}
    centers, height = tree_centers(cols)
    halves = list(dict.fromkeys(g["id"].split("-")[0] for g in games if g["id"] != "final"))
    half_control = ""
    if len(halves) > 1:
        buttons = "".join(
            f'<button type="button" class="half-control__item{" half-control__item--both" if h == "both" else ""}" '
            f'data-half="{h}" aria-pressed="{"true" if h == "both" else "false"}">'
            f"{'Both halves' if h == 'both' else _e(HALF_NAMES.get(h, h))}</button>"
            for h in ["both", *halves]
        )
        half_control = f'<div class="half-control" role="group" aria-label="Bracket half">{buttons}</div>'
    tabs = "".join(
        f'<button type="button" class="round-tabs__item" data-round-jump="{i}" aria-current="{"true" if i == 0 else "false"}" '
        f'aria-label="{_e(c["name"])}" title="{_e(c["name"])}">{_e(ROUND_SHORT.get(c["name"], c["name"]))}</button>'
        for i, c in enumerate(cols)
    )
    columns = "".join(
        f'<section class="tcol" aria-label="{_e(c["name"])}"><h3 class="tcol__title">{_e(c["name"])}</h3>'
        f'<ol class="tcol__body" style="height:{height:g}px">'
        + "".join(
            f'<li class="tslot" style="transform:translateY({centers[r][i] - CARD_H / 2:g}px)">'
            f"{_tree_card(g['game'], ctx, False)}</li>"
            for i, g in enumerate(c["games"])
        )
        + "</ol></section>"
        for r, c in enumerate(cols)
    )
    return (
        '<div class="page static-page">'
        '<header class="entry-head bracket-head">'
        f'{breadcrumb_nav(bracket_trail(clazz))}<h1 class="title">Class {clazz}A Bracket</h1>{_provenance(stamp)}'
        '<p class="focus-note muted">Select a game to see all possible matchups and locations, and pick a team to follow its path.</p>'
        "</header>"
        f'<div id="bracket-host">{half_control}'
        f'<div class="round-tabs" role="group" aria-label="Jump to a round">{tabs}</div>'
        f'<div class="tree" style="--card-h:{CARD_H}px"><div class="tree__cols">{columns}</div></div>'
        "</div></div>\n"
    )


def _sheet_side(game: dict, side_key: str, host: str | None, ctx: dict) -> str:
    """One side in the open sheet: its locked team, or who might fill it (app.js's ``bracketSide``)."""
    side = game[f"side_{side_key}"]
    teams = ctx["teams"]
    home = '<span class="bteam__home">Home</span>' if host == side_key else ""

    def name(team: str) -> str:
        """A team as the sheet lists it."""
        return (
            f'<span class="bteam__name">{_mark(team, teams.get(team))}<span class="team-name">{_e(team)}</span></span>'
        )

    locked = locked_team(side)
    if locked:
        seed = ctx["seeds"].get(locked)
        label = position_name(*seed) if seed else "Clinched a playoff spot"
        return (
            f'<div class="bteam bteam--locked">{name(locked)}<span class="bteam__fact">{LOCK}'
            f'<span class="visually-hidden">Locked in: </span>{_e(label)}</span>{home}</div>'
        )
    listed = occupants(side, ctx["mode"])
    first_round = len(side["feeders"]) == 1
    label = (
        f'<p class="bside__label">{_e(side_label(side["feeders"])) if first_round else ""}{home}</p>'
        if first_round or home
        else ""
    )
    if not listed:
        return f'<div class="bside">{label}<p class="bside__empty muted">No team can get here</p></div>'
    items = "".join(f'<li class="bteam">{name(o["team"])}{_odds(o["p"])}</li>' for o in listed[:SHEET_LIST])
    more = f'<p class="bside__more">Show all {len(listed)}</p>' if len(listed) > SHEET_LIST else ""
    return f'<div class="bside">{label}<ul class="bside__list">{items}</ul>{more}</div>'


def _team_label(name: str, teams: dict) -> str:
    """A team with its mark (components.js's ``teamLabel``)."""
    return f'<span class="team">{_mark(name, teams.get(name))}<span class="team-name">{_e(name)}</span></span>'


def _sheet(game: dict, ctx: dict) -> str:
    """The game sheet as it opens over the bracket: both sides, then their possible matchups."""
    host = settled_host(game, ctx["mode"])
    order, joiner = _side_order(host)
    kicker = " · ".join(x for x in (game["round"], HALF_NAMES.get(game.get("half"))) if x)
    rows = []
    for m in game_matchups(game, ctx["mode"])[:SHEET_MATCHUPS]:
        h = _hosting(m["host_a"])
        away, home = (m["b"], m["a"]) if h == "a" else (m["a"], m["b"])
        word = "at" if h in ("a", "b") else "vs"
        note = "Neutral site" if h == "neutral" else (_split_host(m["a"], m["b"], m["host_a"]) if h == "split" else "")
        note_html = f'<span class="opp-list__host">{_e(note)}</span>' if note else ""
        rows.append(
            '<li><span class="mu__teams">'
            f'<span class="mu__line"><span class="vs"></span>{_team_label(away, ctx["teams"])}</span>'
            f'<span class="mu__line"><span class="vs">{word}</span>{_team_label(home, ctx["teams"])}</span>'
            f"</span>{_odds(m['p'])}{note_html}</li>"
        )
    matchups = (
        f'<h4 class="bgame__heading">Possible matchups</h4><ol class="opp-list opp-list--matchups">{"".join(rows)}</ol>'
        if rows
        else ""
    )
    return (
        '<div class="game-sheet bracket-preview__sheet">'
        f'<div class="game-sheet__head"><div><p class="game-sheet__kicker">{_e(kicker)}</p>'
        '<p class="game-sheet__title">Who might play here</p></div></div>'
        '<div class="game-sheet__body"><div class="bgame bgame--sheet">'
        f"{_sheet_side(game, order[0], host, ctx)}"
        f'<div class="bgame__vs" aria-hidden="true"><span>{joiner}</span></div>'
        f"{_sheet_side(game, order[1], host, ctx)}"
        f'</div><div class="bgame__detail">{matchups}</div></div></div>'
    )


def bracket_preview_html(clazz: int, games: list[dict], ctx: dict) -> str:
    """The bracket page in miniature: three rounds of one half's top quarter, with a game's sheet open.

    *ctx* holds ``mode``, ``results``, ``seeds`` and ``teams``. Returns "" without enough games.
    """
    by_id = {g["id"]: g for g in games}
    half = next((g.get("half") for g in games if g["id"] != "final"), None)
    cols = []
    for k in range(3):
        col = [by_id.get(f"{half}-{k}-{i}") for i in range(4 >> k)]
        if not all(col):
            break
        cols.append(col)
    if len(cols) < 2:
        return ""
    centers = [[CARD_H / 2 + PITCH * i for i in range(len(cols[0]))]]
    for k in range(1, len(cols)):
        prev = centers[-1]
        centers.append([(prev[2 * i] + prev[2 * i + 1]) / 2 for i in range(len(cols[k]))])
    height = PITCH * len(cols[0]) - (PITCH - CARD_H)
    selected = cols[1][0]["id"]
    left = [k * (COL_W + COL_GAP) for k in range(len(cols))]
    lines = []
    for k in range(1, len(cols)):
        for i in range(len(cols[k])):
            for j in (2 * i, 2 * i + 1):
                x1, x2 = left[k - 1] + COL_W, left[k]
                xm = (x1 + x2) / 2
                lines.append(f"M{x1} {centers[k - 1][j]:.1f}H{xm:g}V{centers[k][i]:.1f}H{x2}")
    titles = "".join(
        f'<p class="tcol__title" style="left:{left[k]}px;width:{COL_W}px">{_e(col[0]["round"])}</p>'
        for k, col in enumerate(cols)
    )
    cards = "".join(
        f'<span class="bracket-preview__slot" style="left:{left[k]}px;top:{centers[k][i] - CARD_H / 2:g}px;'
        f'width:{COL_W}px;height:{CARD_H}px">{_tree_card(g, ctx, g["id"] == selected)}</span>'
        for k, col in enumerate(cols)
        for i, g in enumerate(col)
    )
    width = left[-1] + COL_W
    return (
        '<div class="bracket-preview">'
        f'<div class="bracket-preview__tree" style="width:{width}px">'
        f'<div class="bracket-preview__titles">{titles}</div>'
        f'<div class="bracket-preview__cols" style="height:{height}px">'
        f'<svg class="tree__lines" width="{width}" height="{height}" aria-hidden="true"><path d="{"".join(lines)}"/></svg>'
        f"{cards}</div></div>"
        f"{_sheet(by_id[selected], ctx)}"
        "</div>"
    )


def _bracket_preview(featured: dict) -> str:
    """The featured class's bracket page in miniature, as one link to it; just the link without data."""
    clazz, preview = featured["clazz"], featured.get("bracket_html")
    if not preview:
        return f'<p><a href="{bracket_path(clazz)}">See the {clazz}A bracket</a></p>'
    return (
        f'<a class="landing-preview landing-preview--bracket" href="{bracket_path(clazz)}" '
        f'aria-label="Open the Class {clazz}A bracket">'
        '<div class="landing-preview__frame" aria-hidden="true"><div class="landing-preview__page">'
        f'<p class="title">Class {clazz}A Bracket</p>{_provenance(featured["stamp"])}{preview}'
        "</div></div>"
        f'<span class="landing-preview__label">Open the {clazz}A bracket</span></a>'
    )


# Paragraphs of trusted markup (emphasis), like PRINCIPLES_HTML below.
ABOUT_THE_SITE_HTML = (
    "This website was developed to answer the question that comes up every October in Mississippi high school "
    "football: <strong><em>“What does our playoff picture look like?”</em></strong>",
    "This website sets out to answer that question by providing scenarios for every way each region race can "
    "finish based on the MHSAA’s tiebreaker rules. This allows us to determine each team’s odds of finishing in "
    "each place and therefore in each playoff slot. From there, we look at the playoff bracket and give an outlook "
    "for each playoff game, including which teams are likely to play in which slot and which teams are most likely "
    "to play at home.",
)
# Paragraphs of trusted markup (emphasis and a link), unlike the plain-text constants around them.
PRINCIPLES_HTML = (
    "The two core principles we kept in mind when building this website were <em>accuracy</em> and "
    "<em>ease of use</em>. We never want to provide inaccurate information, and we never want any information to "
    "be confusing. Please use our "
    '<a href="/feedback" data-feedback="other">feedback form</a> if you see anything that violates either of '
    "those principles.",
    "To reinforce the “accuracy” principle, we want to make clear that the scenarios, headlines, and numbers on "
    "this website all come from rules-based logic and math applied to completed games, the MHSAA’s tiebreaker "
    "and playoff rules, and each team’s Elo rating. "
    "<strong><em>No generative AI models are used to produce any metrics you see on this website</em></strong>.",
)
# Each step matches the pipeline's thresholds (region_scenarios_pipeline.py: _R_ALWAYS_MARGIN,
# _R_MAX_ATOMS, _R_MAX_COMPUTE; api_helpers.DISPLAY_THRESHOLD); docs/SCENARIO_COMPUTATION.md has the detail.
HOW_IT_WORKS_HTML = (
    "When there are <strong>5 or fewer</strong> games remaining in a given region, our logic builds the final "
    "standings for each possible combination of outcomes, breaks any ties, and counts how often each team lands "
    "in each seed. From there, it produces odds for each team and easy-to-read scenarios for every possible "
    "outcome.",
    "When there are <strong>6 to 10</strong> remaining games in a given region, we still build out each possible "
    "outcome, but only display scenario insights for key games, since the full scenario list is generally very "
    "long at this stage. From this point on, a tie that comes down to point differential is worked out as if each "
    "remaining game were won by 7 points, so the odds in those races are close but not exact. The key-game "
    "insights are still checked against every possible margin.",
    "When there are <strong>11 to 15</strong> remaining games in a region, we still build out each possible "
    "outcome, but do not display any scenarios, as there will be too many to reasonably display.",
    "When there are <strong>more than 15</strong> remaining games in a region, it becomes impractical to build out "
    "each possible outcome. In these cases, we simulate the rest of the schedule 50,000 times, using each team’s "
    "Elo rating to set its chance of winning each game. Toss-up odds get their own 50,000 runs with every game a "
    "coin flip. These simulated numbers are used to display each team’s odds of finishing as each seed.",
)
SCORES_SOURCE = "Scores are sourced from AHSFHS and are updated every morning."
NOT_AFFILIATED = "This website is not associated with the MHSAA or any of its member schools."


CLASSES = range(1, 8)


def class_grid() -> str:
    """The front page's way in: every class's standings and bracket, a button each (landing.js's
    ``classGrid`` writes the same). Hidden words make each link say what it opens."""

    def row(key: str, label: str, path) -> str:
        items = "".join(
            f'<li><a class="landing-classes__item" href="{path(c)}">{c}A'
            f'<span class="visually-hidden"> {label.lower()}</span></a></li>'
            for c in CLASSES
        )
        return (
            f'<div class="landing-classes__row"><p class="landing-classes__label" id="classes-{key}">{label}</p>'
            f'<ul class="landing-classes__list" aria-labelledby="classes-{key}">{items}</ul></div>'
        )

    return (
        '<nav class="landing-classes" aria-label="Classes">'
        f"{row('standings', 'Standings', class_path)}{row('brackets', 'Brackets', bracket_path)}</nav>"
    )


def landing_computed_span(
    featured: dict | None, scenario_example: dict | None = None, insight_example: dict | None = None
) -> tuple[str | None, str | None]:
    """The earliest and latest times the front page's numbers were calculated, as stored (ISO), or Nones.

    Covers everything the page shows: the featured class's standings (its preview, region card and bracket
    all come from those rows) and the regions behind the scenario examples, which may be earlier snapshots.
    """
    stamps = []
    if featured:
        cs = featured.get("class_standings") or {}
        stamps += [cs.get("computed_from"), cs.get("computed_to")]
        stamps.append(((featured.get("standings") or {}).get("computation_state") or {}).get("computed_at"))
    for ex in (scenario_example, insight_example):
        for payload in (ex or {}).get("standings"), (ex or {}).get("scenario_payload"):
            stamps.append(((payload or {}).get("computation_state") or {}).get("computed_at"))
    times = sorted((datetime.fromisoformat(str(t)), str(t)) for t in stamps if t)
    return (times[0][1], times[-1][1]) if times else (None, None)


def landing_body(
    featured: dict | None,
    teams: dict[str, dict],
    scenario_example: dict | None = None,
    insight_example: dict | None = None,
) -> str:
    """The front page: who we are and how it works on the left, a tour of the site on the right, with the
    most open race (``featured``) as the live example throughout.

    *featured* is ``{"clazz", "card", "standings", "stamp", "mode", "bracket_html"}`` or None.
    The app shows this same file at "/", so there is one renderer and nothing changes when it loads.
    """
    intro = (
        '<div class="landing-intro">'
        '<p class="landing-kicker">Welcome to</p>'
        '<h1 class="landing-title">Mississippi High School Football</h1>'
        '<img class="landing-helmet" src="/static/helmet.webp" width="1000" height="851" alt="">'
        f"{class_grid()}"
        + _section("about", "About the site", "".join(f"<p>{p}</p>" for p in ABOUT_THE_SITE_HTML))
        + _section("principles", "Principles", "".join(f"<p>{p}</p>" for p in PRINCIPLES_HTML))
        + _section(
            "how",
            "How it works",
            f'<ul class="landing-list">{"".join(f"<li>{i}</li>" for i in HOW_IT_WORKS_HTML)}</ul>'
            f"<p>{_e(SCORES_SOURCE)}</p>"
            f"<p><strong>{_e(NOT_AFFILIATED)}</strong></p>"
            '<p><a href="/about">More on how the odds work</a></p>',
        )
        + "</div>"
    )
    class_extra = region_extra = bracket_extra = ""
    if featured:
        c, r = featured["clazz"], featured["card"]["region"]
        unsettled = (
            ", one of the most unsettled races in the state as of the latest update" if featured["card"]["teams_alive"] > 0 else ""
        )
        # The preview's first region is always the one shown; whether the next fits beside it depends on
        # the preview's width, so the sentence names only the first.
        first = _class_preview_blocks(featured)[0]["region"]
        class_lead = f"Here’s Class {c}A as of the latest update, starting with Region {first}:"
        class_extra = _lead(class_lead) + _class_preview(featured, teams)
        region_extra = _lead(f"Here’s Region {r}-{c}A{unsettled}:") + _region_preview(featured, teams)
        lead = f"Here’s the Class {c}A bracket, with one game opened up the way it looks after you tap it:"
        bracket_extra = (_lead(lead) if featured.get("bracket_html") else "") + _bracket_preview(featured)
    examples = {**scenario_previews(scenario_example, teams), "settled": insight_preview(insight_example, teams)}
    region_scenarios = "".join(
        _section(key, title, f"<p>{_e(text)}</p>{examples[example]}", level="h3")
        for key, title, text, example in (
            (
                "settling-results",
                "Results that settle a spot",
                "Before full scenarios are ready, view the results that clinch a seed, clinch a playoff spot, or "
                "knock a team out, no matter what else happens.",
                "settled",
            ),
            (
                "title-scenarios",
                "Region title scenarios",
                "View scenarios for how each eligible team can still win the region.",
                "title",
            ),
            (
                "playoff-scenarios",
                "Playoff spot scenarios",
                "View scenarios for how each team on the bubble can still make or miss the playoffs.",
                "playoffs",
            ),
            (
                "seeding-scenarios",
                "Team seeding scenarios",
                "View scenarios for how each eligible team can finish as a given seed.",
                "seeding",
            ),
            (
                "unique-scenarios",
                "Unique region scenarios",
                "View each unique seeding finish possible in a given region. When the playoff seeding in a "
                "finish comes down to tiebreakers, open its Explanation to see how each tie breaks, step by step.",
                "unique",
            ),
        )
    )
    tour = (
        '<div class="landing-tour">'
        + _section(
            "insights",
            "Insights we provide",
            "<p>Below are some explanations and examples of each insight that this website provides.</p>",
        )
        + _section(
            "class",
            "Class standings",
            "<p>View the standings for each region in each class, including:</p>"
            + _bullets(
                (
                    "Each team’s region record",
                    "Which teams have clinched playoff spots or specific seeds",
                    "Each team’s chance of making the playoffs",
                    "Each team’s chance of winning the region",
                )
            )
            + class_extra,
        )
        + _section(
            "region",
            "Region breakdown",
            _section(
                "region-standings",
                "Standings",
                "<p>View detailed standings for a given region, including:</p>"
                + _bullets(
                    (
                        "A headline summing up the race",
                        "Each team’s region and overall records",
                        "Which teams have clinched playoff spots or specific seeds",
                        "Each team’s chance of making the playoffs",
                        "Each team’s chance of finishing at each seed",
                        "An expanded view of each team: its completed and remaining games and its playoff path odds",
                    )
                )
                + region_extra,
                level="h3",
            )
            + region_scenarios,
        )
        + _section(
            "bracket",
            "Bracket page",
            "<p>View each class’s playoff bracket, filled in with who is likely to land in each spot. Pick a game to "
            "see every team that could play there, how likely each matchup is, and who would host.</p>" + bracket_extra,
        )
        + "</div>"
    )
    # When the numbers shown were calculated, for the footer (the app reads these once the page is up).
    start, end = landing_computed_span(featured, scenario_example, insight_example)
    span = f' data-computed-from="{_e(start)}" data-computed-to="{_e(end)}"' if start else ""
    return f'<div class="page landing"{span}>{intro}{tour}</div>\n'


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
