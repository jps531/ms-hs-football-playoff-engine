"""A team's season as an image to share: its games, its odds of each seed, its playoff path, and a
short look at its region's standings.

A 4:5 page like the region images (``region_image``), in the site's two themes and one odds mode,
built from the same data the region page shows for a picked team: the standings payload's entry for
the team (records, odds, bracket and home-game odds), the region's ``/games`` rows, and once its
region is finished, its playoff road from the class's bracket (``region_image.region_playoffs``).
"""

from __future__ import annotations

from PIL import Image

from backend.helpers.bracket_image import trophy
from backend.helpers.region_image import (
    CHAMPION_STEP,
    COL_GAP,
    COL_W,
    PAD,
    SIZE,
    _badges,
    _footer,
    _header,
    _Page,
    _records,
    _rule,
)
from backend.helpers.share_cards import (
    _inter,
    display_order,
    fit,
    format_pct,
    mode_odds,
    position_labels,
    standing_positions,
)
from backend.helpers.static_pages import MODE_LABELS, game_date

ODDS_KEYS = (("p1", "1st"), ("p2", "2nd"), ("p3", "3rd"), ("p4", "4th"), ("p_playoffs", "Playoffs"))


def team_games(team: str, games: list[dict]) -> tuple[list[dict], list[dict]]:
    """The team's regular-season games from the region's ``/games`` rows, oldest first: (played, to play).

    Played: {date, opponent, joiner, score_for, score_against, result (W/L/T), region}; to play:
    {date, opponent, joiner, region}. The joiner is "at" for a road game, "vs" otherwise (home, a
    neutral site, or one the schedule doesn't say), as the region page's schedule has it. Playoff
    games (with a ``round``) are left to the playoff road.
    """
    played, to_play = [], []
    for g in sorted(games, key=lambda g: str(g.get("date") or "9999")):
        if g.get("round") or team not in (g["team_a"], g["team_b"]):
            continue
        mine_a = g["team_a"] == team
        opponent = g["team_b"] if mine_a else g["team_a"]
        loc = g.get("location_a")
        mine = loc if mine_a else {"home": "away", "away": "home"}.get(loc, loc)
        row = {
            "date": str(g.get("date") or "")[:10] or None,
            "opponent": opponent,
            "joiner": "at" if mine == "away" else "vs",
            "region": bool(g.get("is_region_game")),
        }
        if g.get("final") and g.get("score_a") is not None and g.get("score_b") is not None:
            sf, sa = (g["score_a"], g["score_b"]) if mine_a else (g["score_b"], g["score_a"])
            played.append(
                {**row, "score_for": sf, "score_against": sa, "result": "W" if sf > sa else "L" if sf < sa else "T"}
            )
        else:
            to_play.append(row)
    return played, to_play


def playoff_rounds(team: dict, mode: str, clazz: int) -> list[dict]:
    """The team's road through the bracket, one row per round (standings.js's ``playoffPath``):
    {round, reach, neutral, host_if_reach, host_overall}. 5A-7A have no second round; the
    championship game is at a neutral site. [] without bracket odds."""
    b, h = team.get("bracket_odds"), team.get("home_game_odds")
    if not b:
        return []
    w = "_weighted" if mode == "projected" else ""

    def pick(obj: dict | None, key: str) -> float | None:
        return (obj or {}).get(f"{key}{w}") if obj else None

    odds = team.get("odds") or {}
    rounds = [
        ("First Round", odds.get(f"p_playoffs{w}"), pick(h, "first_round"), False, False),
        ("Second Round", pick(b, "second_round"), pick(h, "second_round"), False, clazz >= 5),
        ("Quarterfinals", pick(b, "quarterfinals"), pick(h, "quarterfinals"), False, False),
        ("Semifinals", pick(b, "semifinals"), pick(h, "semifinals"), False, False),
        ("Championship Game", pick(b, "finals"), None, True, False),
        ("Champions", pick(b, "champion"), None, False, False),
    ]
    return [
        {
            "round": name,
            "reach": reach,
            "neutral": neutral,
            "host_if_reach": host,
            "host_overall": host * reach if host is not None and reach is not None else None,
        }
        for name, reach, host, neutral, skip in rounds
        if not skip
    ]


def _odds_row(page: _Page, top: float, team: dict, mode: str) -> float:
    """The team's odds of each seed and of the playoffs, as large pills with their labels."""
    page.label(page_x := PAD, top + 30, "Chance of finishing", 26)
    gap = 24
    w = (SIZE[0] - 2 * PAD - gap * (len(ODDS_KEYS) - 1)) / len(ODDS_KEYS)
    for i, (key, label) in enumerate(ODDS_KEYS):
        x = page_x + i * (w + gap)
        page.label(x + w / 2, top + 84, label, 24, anchor="ms")
        page.pill(x + w, top + 150, mode_odds(team, key, mode), w, 100, 50)
    return top + 210


def _schedule(page: _Page, x: float, top: float, bottom: float, played: list[dict], to_play: list[dict]) -> float:
    """The team's games, played then to play, as far as they fit; returns the bottom."""
    d, t = page.draw, page.t
    page.label(x, top + 30, "Schedule", 26)
    rows = [("played", g) for g in played] + [("next", g) for g in to_play]
    # Rows take the room there is, from 74px up to 100px each.
    row_h = max(74.0, min(100.0, (bottom - top - 110) / max(1, len(rows))))
    y = top + 50
    fits = max(0, int((bottom - y - 60) // row_h))
    for kind, g in rows[:fits]:
        _rule(page, y, x, x + COL_W)
        mid = y + row_h / 2
        when = game_date(g["date"]) if g["date"] else ""
        d.text((x, mid), when, font=_inter(26, 500), fill=t.text_2, anchor="lm")
        nx = x + 200
        d.text((nx, mid), g["joiner"], font=_inter(28, 500), fill=t.text_2, anchor="lm")
        nx += d.textlength(g["joiner"], font=_inter(28, 500)) + 12
        page.mark(g["opponent"], nx, mid, 40)
        nx += 50
        right = x + COL_W
        if kind == "played":
            score = f"{g['score_for']}–{g['score_against']}"
            sfont = _inter(32, 600)
            d.text((right, mid), score, font=sfont, fill=t.text, anchor="rm")
            sw = d.textlength(score, font=sfont)
            color = {"W": "#137252", "L": "#B91C1C"}.get(g["result"], t.text_2)
            d.text((right - sw - 14, mid), g["result"], font=_inter(32, 700), fill=color, anchor="rm")
            room = right - sw - 70 - nx
        else:
            room = right - nx
        tag = "  Region" if g["region"] else ""
        tag_w = d.textlength(tag, font=_inter(22, 600))
        name = fit(d, g["opponent"], _inter(32, 600), room - tag_w - 10)
        d.text((nx, mid), name, font=_inter(32, 600), fill=t.text, anchor="lm")
        if tag:
            d.text(
                (nx + d.textlength(name, font=_inter(32, 600)), mid + 2),
                tag,
                font=_inter(22, 600),
                fill=t.text_2,
                anchor="lm",
            )
        y += row_h
    _rule(page, y, x, x + COL_W)
    if len(rows) > fits:
        y += 50
        d.text(
            (x, y),
            f"+{len(rows) - fits} more games on the region page",
            font=_inter(26, 500),
            fill=t.text_2,
            anchor="ls",
        )
    return y


def _path_table(page: _Page, x: float, top: float, rows: list[dict], mode: str) -> float:
    """The playoff path table (as the region page's): round, reaches round, hosts if it gets there, hosts overall."""
    d, t = page.draw, page.t
    right = x + COL_W
    cols = (right - 480, right - 230, right)  # reaches (pill), hosts if there, hosts overall
    page.label(x, top + 30, f"Playoff path · {MODE_LABELS[mode]} odds", 26)
    head = top + 82
    page.label(cols[0], head, "Reaches", 20, anchor="rs")
    page.label(cols[1], head, "Hosts if there", 20, anchor="rs")
    page.label(cols[2], head, "Hosts overall", 20, anchor="rs")
    y = head + 16
    row_h = 66
    for r in rows:
        _rule(page, y, x, right)
        mid = y + row_h / 2
        d.text((x, mid), r["round"], font=_inter(30, 600), fill=t.text, anchor="lm")
        page.pill(cols[0], mid, r["reach"], 132, 50, 28)
        if r["neutral"]:
            d.text((cols[1], mid), "Neutral", font=_inter(28, 500), fill=t.text_2, anchor="rm")
        elif r["host_if_reach"] is not None:
            d.text((cols[1], mid), format_pct(r["host_if_reach"]), font=_inter(28, 500), fill=t.text, anchor="rm")
        if r["host_overall"] is not None:
            d.text((cols[2], mid), format_pct(r["host_overall"]), font=_inter(28, 500), fill=t.text, anchor="rm")
        y += row_h
    _rule(page, y, x, right)
    return y


def _road(page: _Page, x: float, top: float, steps: list[tuple[str, str]]) -> float:
    """The team's playoff games played (and its next one), with the trophy for a state champion."""
    d, t = page.draw, page.t
    page.label(x, top + 30, "Playoffs", 26)
    y = top + 40
    round_w = max((d.textlength(r, font=_inter(28, 600)) for r, _ in steps), default=0) + 28
    for rnd, text in steps:
        y += 52
        d.text((x, y), rnd, font=_inter(28, 600), fill=t.text_2, anchor="ls")
        d.text((x + round_w, y), text, font=_inter(32, 500), fill=t.text, anchor="ls")
    if any(text == CHAMPION_STEP for _, text in steps):
        # The trophy at the right, its foot on the last line, clear of the longer lines above.
        cup = trophy(min(220, round(y - top - 40)))
        page.img.paste(cup, (round(x + COL_W - cup.width - 10), round(y + 8 - cup.height)), cup)
    return y + 24


def _strip(page: _Page, x: float, top: float, bottom: float, payload: dict, team: str, mode: str) -> float:
    """The region's standings in one column, the team's row marked: position, team, region record, playoff odds."""
    d, t = page.draw, page.t
    ordered = display_order(payload["teams"])
    positions = position_labels(standing_positions(ordered))
    page.label(x, top + 30, "Region standings", 26)
    page.label(x + COL_W, top + 30, "Playoffs", 20, anchor="rs")
    y = top + 48
    row_h = max(62.0, min(84.0, (bottom - y - 20) / max(1, len(ordered))))
    for pos, row in zip(positions, ordered, strict=True):
        mid = y + row_h / 2
        if row["school"] == team:
            fill = t.card if t.edge is None else t.odds[1]  # the light theme's card is the page's own white
            d.rounded_rectangle((x - 12, y + 3, x + COL_W + 12, y + row_h - 3), radius=10, fill=fill)
        else:
            _rule(page, y, x, x + COL_W)
        out = row.get("eliminated")
        d.text((x, mid), pos, font=_inter(28, 600), fill=t.text_2, anchor="lm")
        page.mark(row["school"], x + 54, mid, 40)
        reg, _ = _records(row)
        right = x + COL_W
        d.text((right - 140, mid), reg, font=_inter(30, 600), fill=t.text_2 if out else t.text, anchor="rm")
        name = fit(d, row["school"], _inter(32, 600), right - 140 - 80 - (x + 106))
        d.text((x + 106, mid), name, font=_inter(32, 600), fill=t.text_2 if out else t.text, anchor="lm")
        page.pill(right, mid, mode_odds(row, "p_playoffs", mode), 116, 46, 26)
        y += row_h
    return y


def render_team_season(
    clazz: int,
    region: int,
    season: int,
    payload: dict,
    school: str,
    games: list[dict],
    stamp: str,
    mode: str,
    theme: str = "dark",
    teams: dict | None = None,
    road: list[tuple[str, str]] | None = None,
) -> list[Image.Image]:
    """The team's season: records and status, its odds of each seed and of the playoffs (in *mode*), its
    games (played with scores, then to play), its playoff path, or once its region is finished its
    playoff road (*road*: ``region_playoffs``' steps for it), and the region's standings."""
    team = next(t for t in payload["teams"] if t["school"] == school)
    page = _Page.new(theme, teams or {})
    reg, ovr = _records(team)
    complete = not payload.get("remaining_games")
    sub = f"{season} · Region {region}-{clazz}A · {ovr} overall, {reg} in region"
    top = _header(page, school, sub, [f"{MODE_LABELS[mode]} odds"])
    bx = PAD
    for kind, label in _badges(team, clazz, complete):
        bx += page.badge(bx, top - 10, kind, label, 26) + 12
    if bx > PAD:
        top += 40
    bottom = _footer(page, stamp)
    top = _odds_row(page, top, team, mode)
    played, to_play = team_games(school, games)
    left_bottom = _schedule(page, PAD, top + 20, bottom, played, to_play)
    rx = PAD + COL_W + COL_GAP
    y = top + 20
    if road and any(not text.startswith("Next:") for _, text in road):
        y = _road(page, rx, y, road)
    else:
        if road:
            y = _road(page, rx, y, road)
        rows = [] if team.get("eliminated") and not team.get("clinched") else playoff_rounds(team, mode, clazz)
        if rows:
            y = _path_table(page, rx, y + 10, rows, mode)
        elif team.get("eliminated"):
            page.label(rx, y + 30, "Playoffs", 26)
            page.draw.text(
                (rx, y + 90), "Eliminated from the playoffs", font=_inter(32, 600), fill=page.t.text_2, anchor="ls"
            )
            y += 120
    _strip(page, rx, y + 30, bottom, payload, school, mode)
    del left_bottom
    return [page.img]
