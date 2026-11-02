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
    COL_GAP,
    COL_W,
    PAD,
    SIZE,
    _badges,
    _footer,
    _Page,
    _records,
    _rule,
    _wrap,
)
from backend.helpers.share_cards import (
    _inter,
    _nippo,
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
    row_h = max(74.0, min(112.0, (bottom - top - 110) / max(1, len(rows))))
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


LADDER_H = 430  # the playoff section's boxes


def _opponent_lines(page: _Page, x: float, base: float, width: float, joiner: str, opponent: str) -> float:
    """ "vs" (or "to", "at"), the opponent's helmet and name at baseline *base*; a name too long for the
    rest of the line goes on its own lines under it, wrapped (never cut short). Returns the last
    baseline."""
    d, t = page.draw, page.t
    font = _inter(32, 600)
    d.text((x, base), joiner, font=_inter(30, 500), fill=t.text_2, anchor="ls")
    jw = d.textlength(joiner, font=_inter(30, 500)) + 12
    known = not opponent.startswith(("the ", "an "))
    if known:
        page.mark(opponent, x + jw, base - 12, 42)
        jw += 54
    if d.textlength(opponent, font=font) <= width - jw:
        d.text((x + jw, base), opponent, font=font, fill=t.text, anchor="ls")
        return base
    small = _inter(28, 600)
    lines = _wrap(d, opponent, small, width)
    for k, line in enumerate(lines):
        d.text((x, base + 40 * (k + 1)), line, font=small, fill=t.text, anchor="ls")
    return base + 40 * len(lines)


def score_size(d, letter: str, score: str, width: float) -> int:
    """The largest size (56 down to 28) at which a playoff result's letter and score fit in *width*: a score is
    never cut short."""
    for size in range(56, 28, -2):
        if d.textlength(letter, font=_inter(size + 4, 700)) + 14 + d.textlength(score, font=_inter(size, 700)) <= width:
            return size
    return 28


def _ladder(page: _Page, top: float, rounds: list[dict], road: list[dict]) -> float:
    """The team's road through the bracket, one box per round, left to right like a bracket: a played
    round's result, the next game's opponent and who hosts, and each round ahead with the chance of
    reaching it and of hosting it; the trophy in the last box for a state champion. Returns its bottom."""
    d, t = page.draw, page.t
    page.label(PAD, top + 30, "Playoffs", 26)
    by_round = {r["round"]: r for r in road}
    lost = next((i for i, r in enumerate(rounds) if by_round.get(r["round"], {}).get("kind") == "lost"), None)
    champion = by_round.get("Championship Game", {}).get("kind") == "won"
    # Each box is as wide as with all the class's rounds shown; a road that ends in a loss stops there.
    n, gap = len(rounds), 34
    w = (SIZE[0] - 2 * PAD - gap * (n - 1)) / n
    if lost is not None:
        rounds = rounds[: lost + 1]
    y0, h = top + 56, LADDER_H - 56
    for i, r in enumerate(rounds):
        x = PAD + i * (w + gap)
        if i:
            d.line((x - gap, y0 + h / 2, x, y0 + h / 2), fill=t.line, width=3)
        played = by_round.get(r["round"])
        d.rounded_rectangle((x, y0, x + w, y0 + h), radius=16, fill=t.card, outline=t.edge, width=2 if t.edge else 0)
        cx, inner = x + 22, w - 44
        name = "Champion" if r["round"] == "Champions" else r["round"]
        page.label(cx, y0 + 44, fit(d, name.upper(), _inter(20, 600), inner), 20)
        if r["round"] == "Champions" and champion:
            cup = trophy(round(h - 96))
            page.img.paste(cup, (round(x + (w - cup.width) / 2), round(y0 + 70)), cup)
            continue
        if played and played["kind"] in ("won", "lost"):
            won = played["kind"] == "won"
            letter = "W" if won else "L"
            colour = "#137252" if won else "#B91C1C"
            if played["score_for"] is not None and played["score_against"] is not None:
                score = f"{played['score_for']}\u2013{played['score_against']}"
                size = score_size(d, letter, score, inner)
                lw = d.textlength(letter, font=_inter(size + 4, 700)) + 14
                d.text((cx + lw, y0 + 150), score, font=_inter(size, 700), fill=t.text, anchor="ls")
            else:
                size = 56
            d.text((cx, y0 + 150), letter, font=_inter(size + 4, 700), fill=colour, anchor="ls")
            _opponent_lines(page, cx, y0 + 226, inner, "vs" if won else "to", played["opponent"])
            continue
        if played and played["kind"] == "next":
            joiner = "at" if played["where"] == "away" else "vs"
            d.text((cx, y0 + 124), "Next", font=_inter(32, 700), fill=t.text, anchor="ls")
            below = _opponent_lines(page, cx, y0 + 196, inner, joiner, played["opponent"])
            where = {"home": "At home", "away": "Away", "neutral": "Neutral site"}.get(played["where"], "")
            if where:
                d.text((cx, below + 48), where, font=_inter(28, 500), fill=t.text_2, anchor="ls")
            continue
        # A round ahead: the chance of reaching it, then of hosting it.
        page.pill(x + w - 22, y0 + 122, r["reach"], inner, 84, 46)
        if r["neutral"]:
            d.text((cx, y0 + 226), "Neutral site", font=_inter(28, 500), fill=t.text_2, anchor="ls")
        elif r["host_if_reach"] is not None:
            page.label(cx, y0 + 210, "Hosts", 20)
            for k, line in enumerate(
                (f"{format_pct(r['host_if_reach'])} if there", f"{format_pct(r['host_overall'])} overall")
            ):
                d.text((cx, y0 + 254 + k * 42), line, font=_inter(28, 500), fill=t.text_2, anchor="ls")
    return y0 + h


def _strip(page: _Page, x: float, top: float, bottom: float, payload: dict, team: str, mode: str) -> float:
    """The region's standings in one column, the team's row marked: position, team, region record, playoff odds."""
    d, t = page.draw, page.t
    ordered = display_order(payload["teams"])
    positions = position_labels(standing_positions(ordered))
    page.label(x, top + 30, "Region standings", 26)
    page.label(x + COL_W, top + 30, "Playoffs", 20, anchor="rs")
    y = top + 48
    row_h = max(62.0, min(104.0, (bottom - y - 20) / max(1, len(ordered))))
    after_team = False
    for pos, row in zip(positions, ordered, strict=True):
        mid = y + row_h / 2
        if row["school"] == team:
            fill = t.card if t.edge is None else t.odds[1]  # the light theme's card is the page's own white
            d.rounded_rectangle((x - 12, y + 3, x + COL_W + 12, y + row_h - 3), radius=10, fill=fill)
        elif not after_team:  # no rule touches the team's row, above or below
            _rule(page, y, x, x + COL_W)
        after_team = row["school"] == team
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


def _title(page: _Page, school: str, sub: str, mode: str) -> float:
    """The team's helmet beside its name, the season and records under it; returns where content starts."""
    d, t = page.draw, page.t
    size = 150
    page.mark(school, PAD, PAD + 70, size)
    x = PAD + size + 36
    page.label(SIZE[0] - PAD, PAD + 40, f"{MODE_LABELS[mode]} odds", 26, anchor="rs")
    font = _nippo(124)
    d.text((x, PAD + 104), fit(d, school, font, SIZE[0] - PAD - 340 - x), font=font, fill=t.text, anchor="ls")
    d.text((x, PAD + 168), sub, font=_inter(40, 500), fill=t.text_2, anchor="ls")
    return PAD + 168


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
    road: list[dict] | None = None,
) -> list[Image.Image]:
    """The team's season: its helmet, records and status, its odds of each seed and of the playoffs (in
    *mode*), its games (played with scores, then to play), its region's standings, and across the
    bottom its road through the playoffs (*road*: ``region_image.playoff_road`` once its region is
    finished: results and its next game; the rounds ahead with their chances)."""
    team = next(t for t in payload["teams"] if t["school"] == school)
    page = _Page.new(theme, teams or {})
    reg, ovr = _records(team)
    complete = not payload.get("remaining_games")
    top = _title(page, school, f"{season} · Region {region}-{clazz}A · {ovr} overall, {reg} in region", mode)
    bx = PAD + 186
    for kind, label in _badges(team, clazz, complete):
        bx += page.badge(bx, top + 44, kind, label, 26) + 12
    top += 90
    bottom = _footer(page, stamp)
    top = _odds_row(page, top, team, mode)
    ladder_top = bottom - LADDER_H - 20
    played, to_play = team_games(school, games)
    _schedule(page, PAD, top + 20, ladder_top - 30, played, to_play)
    _strip(page, PAD + COL_W + COL_GAP, top + 20, ladder_top - 30, payload, school, mode)
    in_running = not (team.get("eliminated") and not team.get("clinched"))
    rounds = playoff_rounds(team, mode, clazz) if in_running else []
    if rounds:
        _ladder(page, ladder_top, rounds, road or [])
    else:
        page.label(PAD, ladder_top + 30, "Playoffs", 26)
        page.draw.text(
            (PAD, ladder_top + 110),
            "Eliminated from the playoffs",
            font=_inter(40, 600),
            fill=page.t.text_2,
            anchor="ls",
        )
    return [page.img]
