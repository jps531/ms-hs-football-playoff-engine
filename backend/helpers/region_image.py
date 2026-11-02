"""A region as images to share: its overview (standings and remaining games), and its scenarios.

Each is a 4:5 portrait page (1080x1350, drawn at twice that), in the site's two themes, with the
odds in one mode (Projected or Toss-up). An image whose content runs past one page continues on
more, "1 of 3", each page standing on its own (title, stamp, a short standings strip); past
``SHOW_ALL_PAGES`` it stops at ``CAPPED_PAGES`` and points to the region page for the rest.

Every sentence comes from the region page's own builders in ``static_pages`` (which mirror its
JavaScript and are tested against it), so an image says what the page says. Like ``bracket_image``
it's pure: it takes the API's payloads and returns Pillow images; the share-assets pipeline writes
the files. The stamp says what the numbers are from, so a copy passed around stays honest.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from backend.helpers.bracket_image import THEMES, Theme, helmet, trophy
from backend.helpers.certainty import CERTAIN_EPS
from backend.helpers.share_cards import (
    SITE_HOST,
    _inter,
    _nippo,
    _tracked,
    _tracked_width,
    display_order,
    fit,
    format_pct,
    mode_odds,
    odds_bucket,
    position_labels,
    record_text,
    standing_positions,
    team_status,
)
from backend.helpers.static_pages import (
    MODE_LABELS,
    complete_scenario_cards,
    initials,
    insight_cards,
    locked_team,
    margin_text,
    region_path,
    remaining_games,
    team_colors,
    tie_heading,
)

SIZE = (2160, 2700)  # 1080x1350 at 2x
PAD = 104
SHOW_ALL_PAGES = 5  # a list that fits in this many pages is shown in full
CAPPED_PAGES = 4  # a longer one stops here, and its last page points to the region page for the rest
CLINCHED_BG = "#137252"  # --state-clinched (brand-700), both themes
ELIMINATED_BG = "#B91C1C"  # --state-eliminated
COINFLIP_BG = "#FBBF24"  # --state-coinflip


# ----------------------------------------------------------------- drawing helpers


@dataclass
class _Page:
    """One page being drawn: its image, the theme, and the teams (for helmets)."""

    img: Image.Image
    draw: ImageDraw.ImageDraw
    t: Theme
    teams: dict

    @classmethod
    def new(cls, theme: str, teams: dict) -> _Page:
        """A blank page in *theme*."""
        t = THEMES[theme]
        img = Image.new("RGB", SIZE, t.bg)
        return cls(img, ImageDraw.Draw(img), t, teams)

    def mark(self, school: str, x: float, mid: float, size: int) -> None:
        """A team's helmet in its colors, or its initials in a circle when it has none."""
        colors = team_colors(self.teams.get(school))
        top = round(mid - size / 2)
        if colors:
            icon = helmet(colors[0], colors[1], size, self.t.pale_edge)
            self.img.paste(icon, (round(x), top), icon)
            return
        self.draw.rounded_rectangle((x, top, x + size, top + size), radius=size / 2, fill=self.t.rule)
        font = _inter(round(size * 0.4), 600)
        self.draw.text((x + size / 2, mid), initials(school), font=font, fill=self.t.text_2, anchor="mm")

    def pill(self, right: float, mid: float, p: float | None, w: float, h: float, size: int) -> None:
        """An odds pill, its right edge at *right*, in the odds ramp."""
        box = (right - w, mid - h / 2, right, mid + h / 2)
        self.draw.rounded_rectangle(box, radius=h * 0.2, fill=self.t.odds[odds_bucket(p)])
        self.draw.text((right - 16, mid), format_pct(p), font=_inter(size, 600), fill=self.t.odds_text, anchor="rm")

    def badge(self, x: float, mid: float, kind: str, label: str, size: int = 24) -> float:
        """A status badge (Clinched #1, Eliminated, Coin flip) at *x*; returns its width."""
        font = _inter(size, 600)
        w = self.draw.textlength(label, font=font) + size
        bg = {"eliminated": ELIMINATED_BG, "coinflip": COINFLIP_BG}.get(kind, CLINCHED_BG)
        fg = "#272727" if kind == "coinflip" else "#FFFFFF"
        h = size * 1.55
        self.draw.rounded_rectangle((x, mid - h / 2, x + w, mid + h / 2), radius=size * 0.35, fill=bg)
        self.draw.text((x + size / 2, mid), label, font=font, fill=fg, anchor="lm")
        return w

    def label(self, x: float, base: float, text: str, size: int = 24, color: str | None = None, anchor="ls") -> None:
        """A small letter-spaced label ("REMAINING GAMES")."""
        _tracked(self.draw, (x, base), text.upper(), _inter(size, 600), color or self.t.text_2, 2, anchor=anchor)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: float) -> list[str]:
    """*text* in lines no wider than *width*, broken at spaces (a single overlong word is cut to fit)."""
    lines: list[str] = []
    line = ""
    for word in text.split(" "):
        trial = f"{line} {word}" if line else word
        if draw.textlength(trial, font=font) <= width:
            line = trial
            continue
        if line:
            lines.append(line)
        line = word if draw.textlength(word, font=font) <= width else fit(draw, word, font, width)
    if line:
        lines.append(line)
    return lines


def _header(page: _Page, title: str, subtitle: str, right: list[str]) -> float:
    """Title (and a line under it), with up to two small labels at the right; returns where content starts."""
    d, t = page.draw, page.t
    right_w = max((_tracked_width(d, r.upper(), _inter(26, 600), 2) for r in right), default=0)
    font = _nippo(124)
    d.text((PAD, PAD + 104), fit(d, title, font, SIZE[0] - 2 * PAD - right_w - 40), font=font, fill=t.text, anchor="ls")
    for i, r in enumerate(right):
        page.label(SIZE[0] - PAD, PAD + 40 + i * 44, r, 26, anchor="rs")
    top = PAD + 104
    if subtitle:
        f = _inter(42, 500)
        for line in _wrap(d, subtitle, f, SIZE[0] - 2 * PAD)[:3]:
            top += 62
            d.text((PAD, top), line, font=f, fill=t.text_2, anchor="ls")
    return top + 56


def _footer(page: _Page, stamp: str) -> float:
    """The stamp and the site's address along the bottom; returns where content must end."""
    base = SIZE[1] - PAD + 8
    page.label(PAD, base, stamp, 28)
    page.draw.text((SIZE[0] - PAD, base), SITE_HOST, font=_inter(44, 600), fill=page.t.text, anchor="rs")
    return SIZE[1] - PAD - 90


def _rule(page: _Page, y: float, x0: float = PAD, x1: float = SIZE[0] - PAD) -> None:
    """A hairline across."""
    page.draw.line((x0, y, x1, y), fill=page.t.rule, width=2)


def _records(team: dict) -> tuple[str, str]:
    """(region, overall) records as the page writes them."""
    r = team["record"]
    return (
        record_text(r["region_wins"], r["region_losses"], r.get("region_ties") or 0),
        record_text(r["wins"], r["losses"], r.get("ties") or 0),
    )


def _badges(team: dict, clazz: int, complete: bool) -> list[tuple[str, str]]:
    """The team's status badges as the page draws them (``statusBadges``)."""
    out = []
    status = team_status(team, clazz)
    if status:
        out.append(status)
    if complete and team.get("coin_flip_needed"):
        out.append(("coinflip", "Coin flip"))
    return out


# ----------------------------------------------------------------- the overview

ODDS_KEYS = (("p1", "1st"), ("p2", "2nd"), ("p3", "3rd"), ("p4", "4th"), ("p_playoffs", "Playoffs"))


def _standings_table(page: _Page, top: float, clazz: int, payload: dict, mode: str, row_h: float = 112) -> float:
    """The region page's standings table; returns its bottom."""
    d, t = page.draw, page.t
    ordered = display_order(payload["teams"])
    positions = position_labels(standing_positions(ordered))
    complete = not payload.get("remaining_games")
    right = SIZE[0] - PAD
    pill_w, gap = 150, 14
    pill_rights = [right - (len(ODDS_KEYS) - 1 - i) * (pill_w + gap) for i in range(len(ODDS_KEYS))]
    overall_right = pill_rights[0] - pill_w - 40
    region_right = overall_right - 140
    head = top + 30
    page.label(PAD, head, "Standings", 26)
    for (_, name), r in zip(ODDS_KEYS, pill_rights, strict=True):
        page.label(r - 16, head, name, 22, anchor="rs")
    page.label(region_right, head, "Region", 22, anchor="rs")
    page.label(overall_right, head, "Overall", 22, anchor="rs")
    y = head + 22
    name_x = PAD + 76 + 76
    for pos, team in zip(positions, ordered, strict=True):
        _rule(page, y)
        mid = y + row_h / 2
        out = team.get("eliminated")
        d.text((PAD, mid), pos, font=_inter(36, 600), fill=t.text_2, anchor="lm")
        page.mark(team["school"], PAD + 70, mid, 64)
        badges = _badges(team, clazz, complete)
        name_font = _inter(42, 600)
        name = fit(d, team["school"], name_font, region_right - 150 - name_x)
        d.text(
            (name_x, mid - (14 if badges else 0)), name, font=name_font, fill=t.text_2 if out else t.text, anchor="lm"
        )
        bx = name_x
        for kind, label in badges:
            bx += page.badge(bx, mid + 30, kind, label, 22) + 10
        reg, ovr = _records(team)
        d.text((region_right, mid), reg, font=_inter(38, 600), fill=t.text_2 if out else t.text, anchor="rm")
        d.text((overall_right, mid), ovr, font=_inter(38, 500), fill=t.text_2, anchor="rm")
        for (key, _), r in zip(ODDS_KEYS, pill_rights, strict=True):
            page.pill(r, mid, mode_odds(team, key, mode), pill_w, 64, 34)
        y += row_h
    _rule(page, y)
    return y


def _games_list(page: _Page, top: float, bottom: float, rows: list[dict]) -> tuple[float, int]:
    """The remaining games, in two columns when one won't hold them; returns (bottom, how many didn't fit)."""
    d, t = page.draw, page.t
    page.label(PAD, top + 30, "Remaining games", 26)
    y0 = top + 56
    row_h = 84
    per_col = max(0, int((bottom - y0) // row_h))
    cols = 1 if len(rows) <= per_col else 2
    col_w = (SIZE[0] - 2 * PAD - (60 if cols == 2 else 0)) / cols
    shown = rows[: per_col * cols]
    date_w = max((d.textlength(r["date"], font=_inter(32, 500)) for r in shown), default=0) + 28
    for i, g in enumerate(shown):
        c, r = divmod(i, per_col) if cols == 2 else (0, i)
        x = PAD + c * (col_w + 60)
        mid = y0 + r * row_h + row_h / 2
        d.text((x, mid), g["date"], font=_inter(32, 500), fill=t.text_2, anchor="lm")
        x += date_w
        room = col_w - date_w
        font, joiner_font = _inter(36, 600), _inter(32, 500)
        joiner = f" {g['joiner']} "
        jw = d.textlength(joiner, font=joiner_font)
        each = (room - jw - 2 * 52) / 2
        page.mark(g["first"], x, mid, 42)
        first = fit(d, g["first"], font, each)
        d.text((x + 52, mid), first, font=font, fill=t.text, anchor="lm")
        x += 52 + d.textlength(first, font=font)
        d.text((x, mid), joiner, font=joiner_font, fill=t.text_2, anchor="lm")
        x += jw
        page.mark(g["second"], x, mid, 42)
        d.text((x + 52, mid), fit(d, g["second"], font, each), font=font, fill=t.text, anchor="lm")
    used = (per_col if cols == 2 else len(shown)) if shown else 0
    return y0 + used * row_h, len(rows) - len(shown)


def _ties(page: _Page, top: float, bottom: float, ties: list[dict]) -> bool:
    """How a finished region's ties were broken, step by step, when it all fits; False when it doesn't."""
    d, t = page.draw, page.t
    width = SIZE[0] - 2 * PAD
    step_font, head_font, teams_font = _inter(30, 400), _inter(36, 600), _inter(32, 500)
    blocks = []
    for tie in ties:
        title, names = tie_heading(tie)
        steps = [_wrap(d, f"{i}. {s}", step_font, width - 30) for i, s in enumerate(tie["steps"], start=1)]
        blocks.append((title, _wrap(d, names, teams_font, width), steps))
    need = 56 + sum(48 + 44 * len(n) + sum(42 * len(s) + 8 for s in steps) + 24 for _, n, steps in blocks)
    if top + need > bottom:
        return False
    page.label(PAD, top + 30, "How the ties were broken", 26)
    y = top + 56
    for title, names, steps in blocks:
        y += 44
        d.text((PAD, y), title, font=head_font, fill=t.text, anchor="ls")
        for line in names:
            y += 44
            d.text((PAD, y), line, font=teams_font, fill=t.text_2, anchor="ls")
        for lines in steps:
            for j, line in enumerate(lines):
                y += 42
                d.text((PAD + (30 if j else 0), y), line, font=step_font, fill=t.text, anchor="ls")
            y += 8
        y += 24
    return True


# ----------------------------------------------------------------- a finished region's playoffs


CHAMPION_STEP = "Won the state championship"


def _round_index(game: dict) -> int:
    """A bracket game's round, first round 0 (the championship game last)."""
    return 99 if game["id"] == "final" else int(game["id"].split("-")[1])


def _opponent(game: dict, side: str, results: dict, games: list[dict]) -> str:
    """Who *side*'s team plays in *game*: the locked team, the region seed that goes there, or the
    winner of the game that feeds it."""
    other = game["side_b" if side == "side_a" else "side_a"]
    team = locked_team(other)
    if team:
        return team
    feeders = other.get("feeders") or []
    if len(feeders) == 1:
        return f"the Region {feeders[0]['region']} #{feeders[0]['seed']} seed"
    return "an opponent not yet set"


def _hosts(game: dict, team: str, opponent: str) -> str | None:
    """ "home", "away" or "neutral" for *team* against a known *opponent*; None when it isn't certain."""
    for m in game.get("matchups") or []:
        if {m["team_a"], m["team_b"]} == {team, opponent}:
            host_a = m.get("p_host_a")
            if host_a is None:
                return "neutral"
            p = host_a if m["team_a"] == team else 1 - host_a
            return "home" if p >= 1 else "away" if p <= 0 else None
    return None


def region_seeds(payload: dict) -> dict[str, int]:
    """A finished region's playoff teams and their seeds (each certain of its seed); {} while games remain."""
    if payload.get("remaining_games"):
        return {}
    return {
        t["school"]: k
        for t in payload["teams"]
        for k in (1, 2, 3, 4)
        if (t["odds"].get(f"p{k}") or 0) >= 1 - CERTAIN_EPS
    }


def playoff_road(team: str, games: list[dict], results: dict) -> list[dict]:
    """A team's playoff games, played then the next while it's still in: [{round, kind, opponent,
    score_for, score_against, where}], kind "won", "lost" or "next"; *where* (for the next game) is
    "home", "away" or "neutral" when it's certain who hosts, else None. A won "Championship Game" is
    the title. *games* are the class's ``/bracket/matchups`` games, *results* the played ones
    (``static_pages.layout_results``)."""
    road = []
    for g in sorted(games, key=lambda g: (_round_index(g), g["id"])):
        res = results.get(g["id"])
        if res and team in (res["winner"], res["loser"]):
            won = res["winner"] == team
            mine, theirs = (
                (res.get("winner_score"), res.get("loser_score"))
                if won
                else (res.get("loser_score"), res.get("winner_score"))
            )
            road.append(
                {
                    "round": g["round"],
                    "kind": "won" if won else "lost",
                    "opponent": res["loser"] if won else res["winner"],
                    "score_for": mine,
                    "score_against": theirs,
                    "where": None,
                }
            )
            if not won:
                break
            continue
        side = next((k for k in ("side_a", "side_b") if locked_team(g[k]) == team), None)
        if side and not res:
            opponent = _opponent(g, side, results, games)
            road.append(
                {
                    "round": g["round"],
                    "kind": "next",
                    "opponent": opponent,
                    "score_for": None,
                    "score_against": None,
                    "where": _hosts(g, team, opponent),
                }
            )
            break
    return road


def road_steps(road: list[dict]) -> list[tuple[str, str]]:
    """A playoff road as lines: ("First Round", "Beat Holly Springs 49–8"), ("Quarterfinals", "Lost to
    Noxubee County 33–34"), ("Second Round", "Next: at Hazlehurst" / "Next: vs Kossuth, at home" / "Next:
    vs the Region 5 #4 seed"), and ("", "Won the state championship") after a won final."""
    steps = []
    for r in road:
        if r["kind"] == "next":
            text = f"at {r['opponent']}" if r["where"] == "away" else f"vs {r['opponent']}"
            steps.append((r["round"], f"Next: {text}{', at home' if r['where'] == 'home' else ''}"))
            continue
        score = (
            f" {r['score_for']}\u2013{r['score_against']}"
            if r["score_for"] is not None and r["score_against"] is not None
            else ""
        )
        steps.append((r["round"], f"{'Beat' if r['kind'] == 'won' else 'Lost to'} {r['opponent']}{score}"))
        if r["kind"] == "won" and r["round"] == "Championship Game":
            steps.append(("", CHAMPION_STEP))
    return steps


def region_playoffs(seeds: dict[str, int], games: list[dict], results: dict) -> list[dict]:
    """Each of the region's playoff teams on its road: [{seed, team, steps: [(round, text)]}], seed order
    (``playoff_road`` as ``road_steps``' lines). *seeds* maps the region's seeded teams to their seed."""
    return [
        {"seed": seed, "team": team, "steps": road_steps(playoff_road(team, games, results))}
        for team, seed in sorted(seeds.items(), key=lambda kv: kv[1])
    ]


def _playoffs(page: _Page, top: float, bottom: float, paths: list[dict]) -> bool:
    """The region's playoff teams and their road, when it fits; False when it doesn't."""
    d, t = page.draw, page.t
    round_font, text_font = _inter(30, 600), _inter(34, 500)
    round_w = max((d.textlength(r, font=round_font) for p in paths for r, _ in p["steps"]), default=0) + 36
    need = 56 + sum(76 + 50 * max(1, len(p["steps"])) + 20 for p in paths)
    if not paths or top + need > bottom:
        return False
    page.label(PAD, top + 30, "Playoffs", 26)
    y = top + 56
    for p in paths:
        _rule(page, y)
        mid = y + 40
        d.text((PAD, mid), str(p["seed"]), font=_inter(36, 600), fill=t.text_2, anchor="lm")
        page.mark(p["team"], PAD + 70, mid, 56)
        d.text((PAD + 146, mid), p["team"], font=_inter(40, 600), fill=t.text, anchor="lm")
        block_top = y
        y += 76
        for rnd, text in p["steps"] or [("", "Not yet set")]:
            y += 50
            d.text((PAD + 146, y), rnd, font=round_font, fill=t.text_2, anchor="ls")
            d.text((PAD + 146 + round_w, y), text, font=text_font, fill=t.text, anchor="ls")
        if any(text == CHAMPION_STEP for _, text in p["steps"]):
            # The state champion gets the trophy, at the right of its road.
            cup = trophy(min(240, round(y - block_top - 16)))
            page.img.paste(
                cup, (round(SIZE[0] - PAD - cup.width - 40), round((block_top + y) / 2 - cup.height / 2 + 10)), cup
            )
        y += 20
    return True


def render_region_overview(
    clazz: int,
    region: int,
    season: int,
    payload: dict,
    games: list[dict] | None,
    stamp: str,
    mode: str,
    theme: str = "dark",
    teams: dict | None = None,
    playoffs: list[dict] | None = None,
) -> list[Image.Image]:
    """The region at a glance: its headline, standings with the odds of each seed and the playoffs (in
    *mode*), and the remaining games; once every region game is played, its playoff teams' road
    (*playoffs*, from ``region_playoffs``) and how its ties were broken, as far as they fit. One page;
    what doesn't fit is pointed to on the region page."""
    page = _Page.new(theme, teams or {})
    top = _header(
        page, f"{season} Region {region}-{clazz}A", payload.get("headline") or "", [f"{MODE_LABELS[mode]} odds"]
    )
    bottom = _footer(page, stamp)
    rows = remaining_games(payload.get("remaining_games") or [], games)
    paths = [] if rows else (playoffs or [])
    # The table's rows take the room the rest leaves, from 100px up to 150px each.
    rest_h = (100 + 84 * len(rows)) if rows else (96 + sum(96 + 50 * max(1, len(p["steps"])) for p in paths))
    spare = bottom - top - 52 - rest_h - 40
    row_h = max(100, min(150, spare / max(1, len(payload["teams"]))))
    y = _standings_table(page, top, clazz, payload, mode, row_h)
    if rows:
        y, left_out = _games_list(page, y + 40, bottom, rows)
        if left_out:
            page.draw.text(
                (PAD, y + 40),
                f"+{left_out} more at {SITE_HOST}{region_path(clazz, region)}",
                font=_inter(32, 500),
                fill=page.t.text_2,
                anchor="ls",
            )
        return [page.img]
    notes = []
    if paths and _playoffs(page, y + 40, bottom, paths):
        y += 40 + 56 + sum(76 + 50 * max(1, len(p["steps"])) + 20 for p in paths)
    elif paths:
        notes.append("The playoff teams' road")
    if payload.get("tiebreaks") and not _ties(page, y + 40, bottom - 60 * (len(notes) + 1), payload["tiebreaks"]):
        notes.append("How the ties were broken")
    for i, note in enumerate(notes):
        page.draw.text(
            (PAD, bottom - 20 - 50 * (len(notes) - 1 - i)),
            f"{note}: {SITE_HOST}{region_path(clazz, region)}",
            font=_inter(32, 500),
            fill=page.t.text_2,
            anchor="ls",
        )
    return [page.img]


# ----------------------------------------------------------------- the scenarios

COL_GAP = 40
COL_W = (SIZE[0] - 2 * PAD - COL_GAP) / 2
CARD_PAD = 36


def _strip(page: _Page, top: float, payload: dict, mode: str) -> float:
    """A short standings strip in two columns: position, team, region record, playoff odds."""
    d, t = page.draw, page.t
    ordered = display_order(payload["teams"])
    positions = position_labels(standing_positions(ordered))
    page.label(PAD, top + 30, "Standings", 24)
    page.label(SIZE[0] - PAD, top + 30, "Playoffs", 22, anchor="rs")
    page.label(PAD + COL_W, top + 30, "Playoffs", 22, anchor="rs")
    per_col = (len(ordered) + 1) // 2
    row_h = 70
    y0 = top + 48
    for i, (pos, team) in enumerate(zip(positions, ordered, strict=True)):
        c, r = divmod(i, per_col)
        x = PAD + c * (COL_W + COL_GAP)
        mid = y0 + r * row_h + row_h / 2
        _rule(page, mid - row_h / 2, x, x + COL_W)
        out = team.get("eliminated")
        d.text((x, mid), pos, font=_inter(30, 600), fill=t.text_2, anchor="lm")
        page.mark(team["school"], x + 56, mid, 44)
        reg, _ = _records(team)
        right = x + COL_W
        d.text((right - 150, mid), reg, font=_inter(32, 600), fill=t.text_2 if out else t.text, anchor="rm")
        name = fit(d, team["school"], _inter(34, 600), right - 150 - 90 - (x + 112))
        d.text((x + 112, mid), name, font=_inter(34, 600), fill=t.text_2 if out else t.text, anchor="lm")
        page.pill(right, mid, mode_odds(team, "p_playoffs", mode), 124, 50, 28)
    bottom = y0 + per_col * row_h
    _rule(page, bottom, PAD, PAD + COL_W)
    _rule(page, bottom, PAD + COL_W + COL_GAP, SIZE[0] - PAD)
    return bottom


# A card is drawn twice: once to measure, once on the page. Each piece is a function of (page, x, y,
# draw?) that returns its height, so measuring and drawing can't disagree.


def _cond_text(cond: dict) -> tuple[str | None, str]:
    """A condition as (bold subject, the rest): ("Ridgeland", "beats Greenville by 1–6"), or (None, text)."""
    if cond["type"] == "game_result":
        verb = "loses to" if cond.get("required_result") == "loss" else "beats"
        return cond[
            "school"
        ], f" {verb} {cond['opponent']}{margin_text(cond.get('min_margin'), cond.get('max_margin'))}"
    return None, cond.get("description") or ""


def _conditions(page: _Page, x: float, y: float, width: float, groups: list[list[dict]], draw: bool) -> float:
    """OR-of-AND conditions, one condition a line: AND before each after the first in a way, an OR rule
    between ways. Returns the height."""
    d, t = page.draw, page.t
    bold, plain, small = _inter(32, 600), _inter(32, 400), _inter(22, 600)
    line_h, and_w = 46, 64
    h = 0.0
    for gi, group in enumerate(g for g in groups if g):
        if gi:
            if draw:
                mid = y + h + 30
                d.line((x, mid, x + width, mid), fill=t.rule, width=2)
                tw = _tracked_width(d, "OR", small, 2)
                d.rectangle((x + width / 2 - tw / 2 - 14, mid - 16, x + width / 2 + tw / 2 + 14, mid + 16), fill=t.card)
                _tracked(d, (x + width / 2 - tw / 2, mid + 8), "OR", small, t.text_2, 2)
            h += 60
        for ci, cond in enumerate(group):
            subject, rest = _cond_text(cond)
            left = x + and_w
            room = width - and_w
            if subject:
                room -= 46
            sw = d.textlength(subject, font=bold) if subject else 0
            lines = _wrap(d, rest.strip(), plain, room - sw - 10) if subject else _wrap(d, rest, plain, room)
            if draw:
                base = y + h + 34
                if ci:
                    _tracked(d, (x, base), "AND", small, t.text_2, 2)
                cx = left
                if subject:
                    page.mark(subject, cx, base - 11, 36)
                    cx += 46
                    d.text((cx, base), subject, font=bold, fill=t.text, anchor="ls")
                    cx += sw + 10
                for li, line in enumerate(lines):
                    d.text(
                        (cx if li == 0 else left + (46 if subject else 0), base + li * line_h),
                        line,
                        font=plain,
                        fill=t.text,
                        anchor="ls",
                    )
            h += line_h * max(1, len(lines))
    return h + 8


def _why(page: _Page, x: float, y: float, width: float, why: list[dict], draw: bool) -> float:
    """A scenario's "why this order": each tie, the results that pick it out, and the steps. Returns the height."""
    d, t = page.draw, page.t
    head, body, small = _inter(30, 600), _inter(28, 400), _inter(22, 600)
    h = 46.0
    if draw:
        _tracked(d, (x, y + 34), "WHY THIS ORDER", small, t.text_2, 2)
    for w in why:
        lines = [(head, t.text, s) for s in _wrap(d, w["title"], head, width)]
        if w["when"]:
            lines += [(body, t.text_2, s) for s in _wrap(d, f"{w['when']}:", body, width)]
        for i, step in enumerate(w["steps"], start=1):
            lines += [(body, t.text, s) for s in _wrap(d, f"{i}. {step}", body, width)]
        for font, color, s in lines:
            h += 40
            if draw:
                d.text((x, y + h), s, font=font, fill=color, anchor="ls")
        h += 14
    return h


def _scenario_card(page: _Page, x: float, y: float, card: dict, mode: str, explain: bool, draw: bool) -> float:
    """One way the region can finish: its chance, its seeds, who's out, the results, and (when *explain*)
    why the tied teams are in this order. Returns its height."""
    d, t = page.draw, page.t
    inner = COL_W - 2 * CARD_PAD
    left = x + CARD_PAD
    h = CARD_PAD + 8
    p = card["p_weighted"] if mode == "projected" else card["p"]
    if draw:
        d.text((left, y + h + 34), card["label"], font=_inter(40, 700), fill=t.text, anchor="ls")
        if p is not None:
            page.pill(x + COL_W - CARD_PAD, y + h + 20, p, 136, 56, 30)
    h += 70
    seed_font, note_font = _inter(32, 600), _inter(26, 400)
    for s in card["seeds"]:
        names = s["teams"] if "teams" in s else [s["team"]]
        text = ", ".join(names)
        lines = _wrap(d, text, seed_font, inner - 60 - 46)
        notes = _wrap(d, s["note"], note_font, inner - 60) if "note" in s else []
        if draw:
            base = y + h + 32
            d.text((left, base), str(s["seed"]), font=_inter(30, 600), fill=t.text_2, anchor="ls")
            page.mark(names[0], left + 60, base - 11, 36)
            for i, line in enumerate(lines):
                d.text((left + 106, base + i * 44), line, font=seed_font, fill=t.text, anchor="ls")
            for i, line in enumerate(notes):
                d.text((left + 60, base + len(lines) * 44 + i * 36), line, font=note_font, fill=t.text_2, anchor="ls")
        h += 44 * len(lines) + 36 * len(notes) + 4
    if card["out"]:
        lines = _wrap(d, ", ".join(card["out"]), _inter(28, 500), inner - 84)
        if draw:
            _tracked(d, (left, y + h + 34), "OUT", _inter(22, 600), t.text_2, 2)
            for i, line in enumerate(lines):
                d.text((left + 84, y + h + 34 + i * 40), line, font=_inter(28, 500), fill=t.text_2, anchor="ls")
        h += 40 * len(lines) + 10
    common = card.get("common") or []
    if card["groups"] or common:
        h += 12
        if draw:
            d.line((left, y + h, left + inner, y + h), fill=t.rule, width=2)
            _tracked(d, (left, y + h + 40), "IF", _inter(22, 600), t.text_2, 2)
        h += 48
        if common:
            h += _conditions(page, left, y + h, inner, [common], draw)
            box_top = y + h + 6
            inner_h = _conditions(page, left + 24, box_top + 44, inner - 48, card["groups"], False)
            if draw:
                d.rounded_rectangle(
                    (left, box_top, left + inner, box_top + inner_h + 56), radius=12, outline=t.rule, width=2
                )
                _tracked(d, (left + 24, box_top + 34), "AND ONE OF", _inter(22, 600), t.text_2, 2)
                _conditions(page, left + 24, box_top + 44, inner - 48, card["groups"], True)
            h += inner_h + 70
        else:
            h += _conditions(page, left, y + h, inner, card["groups"], draw)
    if card.get("why"):
        if explain:
            h += _why(page, left, y + h, inner, card["why"], draw)
        else:
            if draw:
                d.text(
                    (left, y + h + 34),
                    "Why this order: on the region page",
                    font=_inter(26, 500),
                    fill=t.text_2,
                    anchor="ls",
                )
            h += 46
    if card.get("more_ways"):
        n = card["more_ways"]
        if draw:
            d.text(
                (left, y + h + 34),
                f"OR {n} more {'way' if n == 1 else 'ways'}: on the region page",
                font=_inter(28, 600),
                fill=t.text_2,
                anchor="ls",
            )
        h += 50
    return h + CARD_PAD


def _insight_card(page: _Page, x: float, y: float, card: dict, draw: bool) -> float:
    """A "settles a spot no matter what else happens" card: the outcome and the results. Returns its height."""
    d, t = page.draw, page.t
    inner = COL_W - 2 * CARD_PAD
    left = x + CARD_PAD
    h = CARD_PAD + 8
    lines = _wrap(d, f"{card['title']} IF", _inter(36, 700), inner)
    if draw:
        for i, line in enumerate(lines):
            d.text((left, y + h + 34 + i * 48), line, font=_inter(36, 700), fill=t.text, anchor="ls")
    h += 48 * len(lines) + 20
    h += _conditions(page, left, y + h, inner, card["groups"], draw)
    if card.get("more_ways"):
        n = card["more_ways"]
        if draw:
            d.text(
                (left, y + h + 34),
                f"OR {n} more {'way' if n == 1 else 'ways'}: on the region page",
                font=_inter(28, 600),
                fill=t.text_2,
                anchor="ls",
            )
        h += 50
    return h + CARD_PAD


def _boxed(page: _Page, x: float, y: float, h: float, paint) -> None:
    """A card's box at (x, y), *h* tall, then its content (*paint*)."""
    t = page.t
    page.draw.rounded_rectangle(
        (x, y, x + COL_W, y + h), radius=20, fill=t.card, outline=t.edge, width=2 if t.edge else 0
    )
    paint()


def render_region_scenarios(
    clazz: int,
    region: int,
    season: int,
    payload: dict,
    stamp: str,
    mode: str,
    theme: str = "dark",
    teams: dict | None = None,
    show_all: int = SHOW_ALL_PAGES,
    capped: int = CAPPED_PAGES,
) -> list[Image.Image]:
    """The region's scenarios, page after page: every way the region can finish (with its chance in
    *mode*, and why tied teams are in their order when that fits), or, before there are full
    scenarios, the results that settle a spot. [] when nothing is left to decide."""
    if not payload.get("remaining_games"):
        return []
    teams = teams or {}
    name = f"{season} Region {region}-{clazz}A"
    if payload.get("scenarios"):
        cards = complete_scenario_cards(payload["scenarios"])
        kind = "scenarios"
        subtitle = f"Scenarios · {len(cards)} {'way' if len(cards) == 1 else 'ways'} the region can finish"
        intro = ""
    else:
        cards = insight_cards(payload.get("key_insights"))
        kind = "insights"
        left = len(payload["remaining_games"])
        subtitle = "What has to happen"
        intro = (
            f"Full scenarios appear once five or fewer region games remain; {left} are left. "
            "Until then, these are results that settle a spot no matter what else happens."
        )
    if not cards:  # nothing to show (no insight settles a spot yet): no image
        return []

    # Measuring draws nothing, so one scratch page serves every card.
    scratch = _Page.new(theme, teams)

    def measure(card: dict, explain: bool) -> float:
        """A card's height."""
        if kind == "scenarios":
            return _scenario_card(scratch, 0, 0, card, mode, explain, False)
        return _insight_card(scratch, 0, 0, card, False)

    content_top = _strip(
        scratch, _header(scratch, name, subtitle, ["1 of 2", f"{MODE_LABELS[mode]} odds"]), payload, mode
    )
    if intro:
        content_top += 40 + 44 * len(_wrap(scratch.draw, intro, _inter(32, 500), SIZE[0] - 2 * PAD))
    content_top += 36
    room = _footer(scratch, stamp) - 20 - content_top

    # Every card at a height that fits a page: a card taller than a page keeps its first ways and says how
    # many more there are (nothing is cut mid-way). Each with its height with and without its explanation.
    items = []
    for card in cards:
        h = measure(card, False)
        while h > room and len(card["groups"]) > 1:
            card = {**card, "groups": card["groups"][:-1], "more_ways": card.get("more_ways", 0) + 1}
            h = measure(card, False)
        h_why = measure(card, True) if kind == "scenarios" and card.get("why") else None
        items.append((card, h, h_why if h_why is not None and h_why <= room else None))

    def pack(explain: list[bool]) -> list[list[list[tuple[dict, bool, float]]]]:
        """Cards in order onto pages of two columns, each into the shorter column it fits, else a new page."""
        pages: list[list[list[tuple[dict, bool, float]]]] = [[[], []]]
        used = [0.0, 0.0]
        for (card, h, h_why), why in zip(items, explain, strict=True):
            height = h_why if why else h
            fits = [c for c in (0, 1) if not used[c] or used[c] + height <= room]
            if not fits:
                pages.append([[], []])
                used = [0.0, 0.0]
                fits = [0, 1]
            col = min(fits, key=lambda c: used[c])
            pages[-1][col].append((card, why, height))
            used[col] += height + COL_GAP
        return pages

    # Explanations go in where they fit without adding a page.
    explain = [False] * len(items)
    count = len(pack(explain))
    for i, (_, _, h_why) in enumerate(items):
        if h_why is not None:
            explain[i] = True
            if len(pack(explain)) > count:
                explain[i] = False
    pages = pack(explain)

    # Up to *show_all* pages, all of them; more than that, the first *capped*, with room at the end of the
    # last for where to see the rest (never a page short of the whole list: then it's shown in full).
    limit = len(pages) if len(pages) <= show_all else capped
    shown_pages = pages[:limit]
    more = sum(len(c) for p in pages[limit:] for c in p)
    if more:
        last = shown_pages[-1]
        while max(sum(h + COL_GAP for _, _, h in col) for col in last) + 90 > room:
            longer = max(last, key=lambda col: sum(h for _, _, h in col))
            longer.pop()
            more += 1
    images = []
    for n, cols in enumerate(shown_pages, start=1):
        page = _Page.new(theme, teams)
        total = len(shown_pages)
        right = [f"{n} of {total}"] if total > 1 else []
        top = _header(page, name, subtitle, [*right, f"{MODE_LABELS[mode]} odds"])
        top = _strip(page, top, payload, mode)
        if intro:
            for line in _wrap(page.draw, intro, _inter(32, 500), SIZE[0] - 2 * PAD):
                top += 44
                page.draw.text((PAD, top + 20), line, font=_inter(32, 500), fill=page.t.text_2, anchor="ls")
            top += 40
        top += 36
        bottom = _footer(page, stamp)
        for c, column in enumerate(cols):
            x = PAD + c * (COL_W + COL_GAP)
            y = top
            for card, explain, h in column:
                if kind == "scenarios":
                    _boxed(
                        page, x, y, h, lambda c=card, x=x, y=y, e=explain: _scenario_card(page, x, y, c, mode, e, True)
                    )
                else:
                    _boxed(page, x, y, h, lambda c=card, x=x, y=y: _insight_card(page, x, y, c, True))
                y += h + COL_GAP
        if n == len(shown_pages) and more:
            page.draw.text(
                (PAD, bottom - 10),
                f"+{more} more at {SITE_HOST}{region_path(clazz, region)}",
                font=_inter(34, 600),
                fill=page.t.text,
                anchor="ls",
            )
        images.append(page.img)
    return images
