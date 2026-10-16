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

from backend.helpers.color_contrast import contrast_ratio
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


def initials(name: str) -> str:
    """Fallback initials, as the app makes them: first letters of up to two significant words."""
    words = [w for w in re.split(r"[\s\-/]+", name) if w]
    significant = [w for w in words if w.lower() not in DROPPED_WORDS]
    return "".join(w[0].upper() for w in (significant or words)[:2])


_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")

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


def _mark(school: str, team: dict | None) -> str:
    """The team's mark as the app's ``teamMark`` draws it: its helmet image, else a helmet in its colors,
    else its initials."""
    helmet = (team or {}).get("helmet_url")
    if helmet:
        return f'<img class="mark mark--helmet" src="{_e(helmet)}" alt="" width="24" height="24" loading="lazy">'
    colors = team_colors(team)
    if colors:
        return generic_helmet(*colors)
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


def region_table(clazz: int, region: int, payload: dict, mode: str, teams: dict[str, dict], link: bool = True) -> str:
    """The region page's standings table: position, team, records, odds of each seed and the playoffs."""
    ordered = display_order(payload["teams"])
    positions = standing_positions(ordered)
    page = region_path(clazz, region)
    complete = not payload.get("remaining_games")
    rows = []
    for pos, team in zip(positions, ordered, strict=True):
        odds = "".join(f'<td class="col-odds">{_odds(mode_odds(team, key, mode))}</td>' for key, _ in ODDS_COLUMNS)
        rows.append(
            f"{_row_start(team, pos)}{_team_cell(team, page, clazz, teams, complete, link)}"
            f'<td class="col-rec">{_region_record(team)}</td>'
            f'<td class="col-rec col-overall">{_overall_record(team)}</td>{odds}</tr>'
        )
    heads = "".join(f'<th scope="col" class="col-odds">{label}</th>' for _, label in ODDS_COLUMNS)
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
    """A region page's content: title, headline, snapshot line, standings, remaining games and conditions.

    *games* are the region's ``/games`` rows, for the remaining games' dates and sites.
    """
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
        f"{region_table(clazz, region, payload, mode, teams)}{schedule}{needs}"
        "</div>\n"
    )


def class_region_block(clazz: int, block: dict, mode: str, teams: dict[str, dict], heading: str = "h2") -> str:
    """One region as the class page shows it: its title and a condensed table (position, team, region
    record, odds of 1st and of the playoffs)."""
    region = block["region"]
    ordered = display_order(block["teams"])
    positions = standing_positions(ordered)
    page = region_path(clazz, region)
    complete = region_complete(ordered)
    rows = "".join(
        f"{_row_start(t, pos)}{_team_cell(t, page, clazz, teams, complete)}"
        f'<td class="col-rec">{_region_record(t)}</td>'
        f'<td class="col-odds">{_odds(mode_odds(t, "p1", mode))}</td>'
        f'<td class="col-odds">{_odds(mode_odds(t, "p_playoffs", mode))}</td></tr>'
        for pos, t in zip(positions, ordered, strict=True)
    )
    return (
        f'<section class="region-block" aria-labelledby="region-{region}">'
        f'<{heading} class="region-block__title" id="region-{region}"><a href="{page}">Region {region}</a></{heading}>'
        '<table class="standings standings--compact">'
        f'<caption class="visually-hidden">Region {region}-{clazz}A standings</caption>'
        '<thead><tr><th scope="col" class="col-pos"><span class="visually-hidden">Position</span></th>'
        '<th scope="col" class="col-team">Team</th><th scope="col" class="col-rec">Region</th>'
        '<th scope="col" class="col-odds">1st</th><th scope="col" class="col-odds">Playoffs</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></section>"
    )


def class_body(clazz: int, standings: dict, stamp: str, mode: str, teams: dict[str, dict]) -> str:
    """A class page's content: every region's condensed table, each linking to its region page."""
    blocks = "".join(
        class_region_block(clazz, b, mode, teams) for b in sorted(standings["regions"], key=lambda b: b["region"])
    )
    return (
        '<div class="page entry-head static-page">'
        f'<h1 class="title">Class {clazz}A</h1>{_provenance(stamp)}</div>'
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


def _class_example(featured: dict, teams: dict[str, dict]) -> str:
    """The featured region as the class page shows it."""
    clazz, payload = featured["clazz"], featured["standings"]
    block = {"region": featured["card"]["region"], "teams": payload["teams"]}
    return (
        '<figure class="landing-example">'
        f"{class_region_block(clazz, block, featured['mode'], teams, heading='h3')}"
        f'<figcaption class="landing-example__caption muted">Class {clazz}A, {_e(featured["stamp"])}. '
        f'<a href="{class_path(clazz)}">See every {clazz}A region</a></figcaption>'
        "</figure>"
    )


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


def _bracket_preview(featured: dict) -> str:
    """The featured class's bracket card (drawn each morning with the share cards), linking to its bracket."""
    clazz, image = featured["clazz"], featured.get("bracket_image")
    if not image:
        return f'<p><a href="{bracket_path(clazz)}">See the {clazz}A bracket</a></p>'
    return (
        f'<a class="landing-preview landing-preview--image" href="{bracket_path(clazz)}">'
        f'<img src="{_e(image)}" width="1200" height="630" loading="lazy" '
        f'alt="Class {clazz}A playoff bracket preview: the likeliest team in each spot">'
        f'<span class="landing-preview__label">Open the {clazz}A bracket</span></a>'
    )


WHAT_WE_DO = (
    "We work out every way each Mississippi high school football region race can still finish, then rank "
    "each finish with the MHSAA’s own tiebreaker rules. That gives every team’s odds of making the playoffs "
    "and of landing each seed, and the exact results it needs to get there. Every region, every class, "
    "updated every morning."
)
HOW_IT_WORKS = (
    "With a handful of region games left, we play out every possible combination of results; earlier in the "
    "season we simulate the rest of the schedule 50,000 times. Projected odds weigh each game by the two "
    "teams’ Elo ratings and home field; Toss-up odds treat every game as a coin flip. Scores come from AHSFHS."
)


def landing_body(featured: dict | None, teams: dict[str, dict]) -> str:
    """The front page: who we are and how it works on the left, a tour of the site on the right, with the
    most open race (``featured``) as the live example throughout.

    *featured* is ``{"clazz", "card", "standings", "stamp", "mode", "bracket_image"}`` or None.
    The app shows this same file at "/", so there is one renderer and nothing changes when it loads.
    """
    intro = (
        '<div class="landing-intro">'
        '<p class="landing-kicker">Welcome to</p>'
        '<h1 class="landing-title">Mississippi High School Football</h1>'
        '<img class="landing-helmet" src="/static/helmet.webp" width="1000" height="851" alt="">'
        f"{_section('what', 'What we do', f'<p>{_e(WHAT_WE_DO)}</p>')}"
        + _section(
            "how",
            "How it works",
            f'<p>{_e(HOW_IT_WORKS)}</p><p><a href="/methodology">More on how the odds work</a></p>',
        )
        + "</div>"
    )
    class_extra = _class_example(featured, teams) if featured else ""
    region_extra = _region_preview(featured, teams) if featured else ""
    bracket_extra = _bracket_preview(featured) if featured else ""
    region_scenarios = "".join(
        _section(key, title, f"<p>{_e(text)}</p>", level="h3")
        for key, title, text in (
            (
                "title-scenarios",
                "Region title scenarios",
                "Scenarios for how each eligible team can still win the region.",
            ),
            (
                "seeding-scenarios",
                "Team seeding scenarios",
                "Scenarios for how each eligible team can finish as a given seed.",
            ),
            ("unique-scenarios", "Unique region scenarios", "Each unique seeding finish possible in a given region."),
        )
    )
    tour = (
        '<div class="landing-tour">'
        + _section(
            "class",
            "Class standings",
            "<p>Standings for each region in each class.</p>"
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
                "<p>Detailed standings for a given region.</p>"
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
            "<p>Each class’s playoff bracket, filled in with who is likely to land in each spot. Pick a game to "
            "see every team that could play there, how likely each matchup is, and who would host.</p>" + bracket_extra,
        )
        + "</div>"
    )
    return f'<div class="page landing">{intro}{tour}</div>\n'


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
