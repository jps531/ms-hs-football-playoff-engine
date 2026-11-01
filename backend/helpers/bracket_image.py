"""The whole bracket as one image, to share: one half as a square, or both halves side by side.

Two versions. **Projected odds**: every open spot shows the team the bracket page shows there
(``static_pages.round_picks``: no team in two spots of one round) with its Projected chance of being
there. **Blank**: only what's settled, locked-in teams and results; an open first-round spot shows
the seed that goes there, a later one stays empty. A season that's over is the same either way.

Each in the site's two themes: dark, and light (for print). Teams carry their helmets, drawn in
their colors as the site's ``genericHelmet`` SVG draws them (Pillow can't read SVG, so its shapes
are traced here). A team with an uploaded helmet image would still get the drawn one; none has one
yet.

Pure, like ``share_cards``: it takes the API's ``/bracket/matchups`` games and played results and
returns a Pillow image. ``backend/prefect/share_assets_pipeline.py`` writes the files. The image
says what it shows (the class, the half, the version) and where its numbers are from (the stamp), so
a copy passed around stays honest.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from PIL import Image, ImageDraw

from backend.helpers.color_contrast import contrast_ratio
from backend.helpers.share_cards import (
    BG,
    ODDS_BG,
    ODDS_TEXT,
    RULE,
    SITE_HOST,
    TEXT,
    TEXT_2,
    _inter,
    _nippo,
    _tracked,
    _tracked_width,
    fit,
    format_pct,
    odds_bucket,
)
from backend.helpers.static_pages import (
    HALF_NAMES,
    _game_order,
    initials,
    locked_team,
    occupants,
    position_name,
    projected_champion,
    round_picks,
    settled_host,
    team_colors,
    tree_columns,
    venue_name,
)

SQUARE = (2000, 2000)  # one half
WIDE = (3600, 2025)  # both halves, 16:9
MODE = "projected"  # the odds version is Projected only


@dataclass(frozen=True)
class Theme:
    """The site's color tokens for one theme (nginx/html/static/css/app.css)."""

    bg: str  # --surface-page
    card: str  # --surface-card
    edge: str | None  # a card's border, where the page and the card are the same color
    text: str  # --text-primary
    text_2: str  # --text-secondary
    rule: str  # --border
    line: str  # --connector
    odds: dict[int, str]  # --odds-1..5
    odds_text: str  # --odds-text
    pale_edge: str  # a pale helmet's outline (.mark--pale)


THEMES = {
    "dark": Theme(BG, "#272727", None, TEXT, TEXT_2, RULE, "#7B7A7B", ODDS_BG, ODDS_TEXT, "#FFFFFF"),
    "light": Theme(
        "#FFFFFF",
        "#FFFFFF",
        "#DFDEDF",
        "#272727",
        "#5C5B5C",
        "#DFDEDF",
        "#A4A3A4",
        {1: "#F7F7F7", 2: "#E1F7EF", 3: "#C2EFDF", 4: "#9BE6CD", 5: "#66DDB5"},
        "#272727",
        "#A4A3A4",
    ),
}


# ------------------------------------------------------------- helmets
# The site's generic helmet (components.js genericHelmet, static_pages.generic_helmet) in its 32x28
# viewBox: the shell, its stripe, the facemask and the ear hole.


def _curve(p0, p1, p2, p3, steps: int = 20) -> list[tuple[float, float]]:
    """A cubic Bezier from *p0* to *p3* as points (without *p0*)."""
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        out.append(
            (
                u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
            )
        )
    return out


_SHELL = [
    (2.5, 16.2),
    *_curve((2.5, 16.2), (2.5, 8.2), (8.8, 2.6), (16.4, 2.6)),
    *_curve((16.4, 2.6), (22.4, 2.6), (26.6, 6.2), (27.8, 11.3)),
    (20.2, 12.2),
    (19.2, 19.4),
    (21.4, 22.9),
    *_curve((21.4, 22.9), (18.8, 25.2), (14.6, 26), (10.6, 25.2)),
    *_curve((10.6, 25.2), (5.6, 24.2), (2.5, 20.9), (2.5, 16.2)),
]
_STRIPE = [(5.2, 11.8), *_curve((5.2, 11.8), (7.2, 7.4), (11, 5), (15.6, 4.6))]
_MASK = [[(20, 13), (30.2, 13), (30.2, 22.4), (21.6, 22.4)], [(19.6, 17.8), (30.2, 17.8)], [(25, 13), (25, 22.4)]]
_GREY = "#8C8C8C"


@cache
def helmet(shell: str, stripe: str, size: int, pale_edge: str) -> Image.Image:
    """A team's helmet in its colors, *size* px square (RGBA), drawn 4x and scaled down for smooth edges.

    The shell is outlined in white, or in *pale_edge* when it's too pale to show against white.
    """
    big = size * 4
    k = big / 32
    dy = (big - 28 * k) / 2
    pt = lambda p: (p[0] * k, p[1] * k + dy)  # noqa: E731
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    def stroke(points, color, width):
        """A line with round ends and joints, as the SVG's stroke-linecap/linejoin round."""
        pts = [pt(p) for p in points]
        draw.line(pts, fill=color, width=round(width * k), joint="curve")
        r = width * k / 2
        for x, y in (pts[0], pts[-1]):
            draw.ellipse((x - r, y - r, x + r, y + r), fill=color)

    for part in _MASK:
        stroke(part, _GREY, 1.7)
    edge = pale_edge if contrast_ratio(shell, "#FFFFFF") < 1.6 else "#FFFFFF"
    shape = [pt(p) for p in _SHELL]
    draw.line(
        [*shape, shape[0]], fill=edge, width=round(1.5 * k), joint="curve"
    )  # under the fill: its outer half shows
    draw.polygon(shape, fill=shell)
    stroke(_STRIPE, stripe, 1.8)
    cx, cy = pt((12.4, 16.4))
    r = 1.6 * k
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_GREY)
    return img.resize((size, size), Image.LANCZOS)


# ------------------------------------------------------------- the trophy
# The state championship trophy (components.js TROPHY_SHAPES, static_pages.TROPHY_SHAPES) in its
# 40x56 viewBox, shape for shape and in the same order.
_FOOT = [
    (12.5, 40.5),
    *_curve((12.5, 40.5), (13.5, 37.6), (16.6, 36.8), (18.4, 36.6)),
    (21.6, 36.6),
    *_curve((21.6, 36.6), (23.4, 36.8), (26.5, 37.6), (27.5, 40.5)),
]
_HIGHLIGHT = [(12.6, 8.5), *_curve((12.6, 8.5), (11.4, 11.6), (11.2, 16.4), (12.4, 20.4))]
_LACES = [((18.2, 5.4), (21.8, 5.4)), ((18, 7.6), (22, 7.6)), ((18, 9.8), (22, 9.8)), ((18.2, 12), (21.8, 12))]
_PLAQUE_LINES = [((15, 44.6), (25, 44.6)), ((13.5, 46), (26.5, 46)), ((16, 47.4), (24, 47.4))]


@cache
def trophy(height: int) -> Image.Image:
    """The state championship trophy, *height* px tall (RGBA), drawn 4x and scaled down for smooth edges."""
    k = height * 4 / 56
    img = Image.new("RGBA", (round(40 * k), round(56 * k)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pt = lambda p: (p[0] * k, p[1] * k)  # noqa: E731

    def rect(x, y, w, h, r, color):
        draw.rounded_rectangle((x * k, y * k, (x + w) * k, (y + h) * k), radius=r * k, fill=color)

    def ellipse(cx, cy, rx, ry, color):
        draw.ellipse(((cx - rx) * k, (cy - ry) * k, (cx + rx) * k, (cy + ry) * k), fill=color)

    def stroke(points, color, width):
        """A line with round ends, as the SVG's stroke-linecap round."""
        pts = [pt(p) for p in points]
        draw.line(pts, fill=color, width=round(width * k), joint="curve")
        r = width * k / 2
        for x, y in (pts[0], pts[-1]):
            draw.ellipse((x - r, y - r, x + r, y + r), fill=color)

    rect(5.5, 50, 29, 4.5, 1, "#6B4426")
    rect(8, 40.5, 24, 10.5, 1, "#8A5A33")
    rect(10.5, 42.6, 19, 6.6, 0.6, "#1F1F1F")
    for line in _PLAQUE_LINES:
        stroke(line, "#C9A33A", 0.7)
    draw.polygon([pt(p) for p in _FOOT], fill="#C8961C")
    rect(18.3, 31, 3.4, 6, 0, "#C8961C")
    draw.polygon([pt(p) for p in [(15, 27.6), (25, 27.6), (23, 31.4), (17, 31.4)]], fill="#D9A520")
    ellipse(20, 28, 5, 1, "#A87A12")
    ellipse(20, 15, 11, 13.6, "#D9A520")
    stroke(_HIGHLIGHT, "#F3D27A", 1.6)
    stroke([(20, 2.6), (20, 27.4)], "#A87A12", 0.9)
    for line in _LACES:
        stroke(line, "#A87A12", 1.2)
    return img.resize((round(img.width / 4), height), Image.LANCZOS)


def is_final(games: list[dict], results: dict) -> bool:
    """Every game, the championship included, has been played."""
    return bool(games) and all(g["id"] in results for g in games)


def picks_for(games: list[dict], results: dict) -> dict[str, str]:
    """The team each open spot shows, the bracket page's way (``round_picks`` over every round)."""
    picks: dict[str, str] = {}
    for col in tree_columns(games):
        picks.update(round_picks(col, MODE, results))
    return picks


def slot(game: dict, key: str, results: dict, seeds: dict, picks: dict, blank: bool) -> dict:
    """What one side of a game shows: {"name", "sub", "pct", "score", "kind"}.

    ``kind`` is "won" or "lost" (a played game, with its score), "locked" (a team sure to be there,
    with its seed), "bye", "pick" (Projected: a team that could be there, with its chance), "open"
    (blank: the seed that goes there in the first round, else nothing) or "empty" (no team can).
    """
    side = game[f"side_{key}"]
    view = {"name": "", "sub": "", "pct": None, "score": None, "kind": "open"}
    result = results.get(game["id"])
    if result:
        team = locked_team(side) or (result["winner"] if key == "a" else result["loser"])
        won = team == result["winner"]
        score = result.get("winner_score") if won else result.get("loser_score")
        return {**view, "name": team or "", "score": score, "kind": "won" if won else "lost"}
    locked = locked_team(side)
    if locked:
        seed = seeds.get(locked)
        return {**view, "name": locked, "sub": position_name(*seed) if seed else "", "kind": "locked"}
    if side.get("bye"):
        return {**view, "name": "BYE", "kind": "bye"}
    feeders = side.get("feeders") or []
    first = len(feeders) == 1
    if blank:
        return {**view, "name": position_name(feeders[0]["region"], feeders[0]["seed"]) if first else ""}
    listed = occupants(side, MODE)
    if not listed:
        return {**view, "name": "No team can get here", "kind": "empty"}
    pick = picks.get(f"{game['id']}:{key}")
    shown = next((o for o in listed if o["team"] == pick), listed[0])
    if first:
        sub = position_name(feeders[0]["region"], feeders[0]["seed"])
    else:
        sub = f"+{len(listed) - 1} more" if len(listed) > 1 else ""
    return {**view, "name": shown["team"], "sub": sub, "pct": shown["p"], "kind": "pick"}


def _half_rounds(games: list[dict], half: str) -> list[list[dict]]:
    """One half's rounds, first to last, each its games in bracket order (ids "{half}-{round}-{game}")."""
    rounds: dict[int, list[tuple[int, dict]]] = {}
    for g in games:
        parts = g["id"].split("-")
        if parts[0] == half and len(parts) == 3:
            rounds.setdefault(int(parts[1]), []).append((int(parts[2]), g))
    return [[g for _, g in sorted(rounds[k], key=lambda x: x[0])] for k in sorted(rounds)]


def _centers(rounds: list[list[dict]], top: float, height: float) -> list[list[float]]:
    """Each game's vertical center: the first round evenly spaced, each later game between the two feeding it."""
    if not rounds:
        return []
    pitch = height / len(rounds[0])
    centers = [[top + pitch * (i + 0.5) for i in range(len(rounds[0]))]]
    for k in range(1, len(rounds)):
        prev = centers[-1]
        centers.append([(prev[2 * i] + prev[min(2 * i + 1, len(prev) - 1)]) / 2 for i in range(len(rounds[k]))])
    return centers


class _Painter:
    """Draws cards and lines at one scale, in one theme."""

    def __init__(self, img: Image.Image, card_w: float, row_h: float, theme: Theme, teams: dict):
        self.img = img
        self.draw = ImageDraw.Draw(img)
        self.theme = theme
        self.teams = teams
        self.mark = round(row_h * 0.62)
        self.w = card_w
        self.row_h = row_h
        self.h = 2 * row_h + 6
        self.name = _inter(round(row_h * 0.44), 600)
        self.name_light = _inter(round(row_h * 0.44), 400)
        self.sub = _inter(round(row_h * 0.3), 400)
        self.pill = _inter(round(row_h * 0.34), 600)

    def card(self, game: dict, x: float, cy: float, rows: list[dict]) -> None:
        """A game's card, its left edge at *x*, centered on *cy*: one row per side, home team last."""
        top = cy - self.h / 2
        t = self.theme
        self.draw.rounded_rectangle((x, top, x + self.w, top + self.h), radius=10, fill=t.card, outline=t.edge, width=2)
        self.draw.line((x + 12, cy, x + self.w - 12, cy), fill=t.rule, width=2)
        for i, view in enumerate(rows):
            self._row(view, x, top + 3 + i * self.row_h)

    def _mark(self, team: str, x: float, mid: float) -> None:
        """A team's helmet in its colors; its initials when it has no colors."""
        t = self.theme
        colors = team_colors(self.teams.get(team))
        top = round(mid - self.mark / 2)
        if colors:
            icon = helmet(colors[0], colors[1], self.mark, t.pale_edge)
            self.img.paste(icon, (round(x), top), icon)
            return
        self.draw.rounded_rectangle((x, top, x + self.mark, top + self.mark), radius=self.mark / 2, fill=t.rule)
        font = _inter(round(self.mark * 0.4), 600)
        self.draw.text((x + self.mark / 2, mid), initials(team), font=font, fill=t.text_2, anchor="mm")

    def _row(self, view: dict, x: float, top: float) -> None:
        """One side: its helmet and name (and seed or position under it), then its score or chance on the right."""
        t = self.theme
        pad = 16
        right = x + self.w - pad
        mid = top + self.row_h / 2
        value_w = 0.0
        if view["kind"] in ("won", "lost", "locked", "pick") and view["name"]:
            self._mark(view["name"], x + pad, mid)
            x += self.mark + 10
        if view["score"] is not None:
            font = self.name if view["kind"] == "won" else self.name_light
            text = str(view["score"])
            self.draw.text(
                (right, mid), text, font=font, fill=t.text if view["kind"] == "won" else t.text_2, anchor="rm"
            )
            value_w = self.draw.textlength(text, font=font) + 12
        elif view["pct"] is not None:
            pill_w = self.row_h * 1.35
            pill_h = self.row_h * 0.62
            box = (right - pill_w, mid - pill_h / 2, right, mid + pill_h / 2)
            self.draw.rounded_rectangle(box, radius=6, fill=t.odds[odds_bucket(view["pct"])])
            self.draw.text((right - 10, mid), format_pct(view["pct"]), font=self.pill, fill=t.odds_text, anchor="rm")
            value_w = pill_w + 12
        width = right - (x + pad) - value_w
        muted = view["kind"] in ("open", "empty", "bye", "lost")
        font = self.name_light if view["kind"] in ("open", "empty", "lost") else self.name
        # A long name steps down in size (twice at most) before it's ever cut short.
        weight = 400 if font is self.name_light else 600
        for scale in (0.86, 0.74):
            if self.draw.textlength(view["name"], font=font) <= width:
                break
            font = _inter(round(self.name.size * scale), weight)
        if view["sub"]:
            self.draw.text(
                (x + pad, mid - 2),
                fit(self.draw, view["name"], font, width),
                font=font,
                fill=t.text_2 if muted else t.text,
                anchor="ls",
            )
            self.draw.text(
                (x + pad, mid + 4),
                fit(self.draw, view["sub"], self.sub, width),
                font=self.sub,
                fill=t.text_2,
                anchor="lt",
            )
        elif view["name"]:
            self.draw.text(
                (x + pad, mid),
                fit(self.draw, view["name"], font, width),
                font=font,
                fill=t.text_2 if muted else t.text,
                anchor="lm",
            )

    def join(self, x_from: float, y_from: float, x_to: float, y_to: float) -> None:
        """An elbow from one card's edge to the next round's card: across, up or down, across."""
        mid = (x_from + x_to) / 2
        self.draw.line(
            [(x_from, y_from), (mid, y_from), (mid, y_to), (x_to, y_to)], fill=self.theme.line, width=3, joint="curve"
        )


def _rows(game: dict, results: dict, seeds: dict, picks: dict, blank: bool) -> list[dict]:
    """Both sides of a game, top to bottom as the bracket page orders them (home team last)."""
    order, _ = _game_order(game, settled_host(game, MODE))
    return [slot(game, k, results, seeds, picks, blank) for k in order]


def _header(draw, t: Theme, pad: int, title: str, subtitle: str) -> float:
    """Title and subtitle (none when it's ""); returns where the bracket may start."""
    draw.text((pad, pad + 70), title, font=_nippo(88), fill=t.text, anchor="ls")
    if not subtitle:
        return pad + 132
    draw.text((pad, pad + 128), subtitle, font=_inter(36, 500), fill=t.text_2, anchor="ls")
    return pad + 190


def _footer(draw, t: Theme, size: tuple[int, int], pad: int, stamp: str) -> float:
    """The stamp and the site's address along the bottom; returns where the bracket must end."""
    width, height = size
    base = height - pad + 4
    _tracked(draw, (pad, base), stamp.upper(), _inter(26, 600), t.text_2, 2)
    draw.text((width - pad, base), SITE_HOST, font=_inter(34, 600), fill=t.text, anchor="rs")
    return height - pad - 60


def _label(draw, t: Theme, name: str, x: float, width: float, base: float, font) -> None:
    """A round's name over its column, letter-spaced and centered."""
    text = name.upper()
    _tracked(draw, (x + (width - _tracked_width(draw, text, font, 1.5)) / 2, base), text, font, t.text_2, 1.5)


def _subtitle(final: bool, blank: bool) -> str:
    """What the image shows, where it needs saying: the Projected odds, which pick one team for each open
    spot. A blank or finished bracket needs none (the footer has the season and "Final")."""
    if final or blank:
        return ""
    return "Projected odds · Each open spot shows one team that could be there, and their chance"


# The trophy over a finished season's championship game, in px.
TROPHY_H = 260


def _projected_champion(draw, t: Theme, champ: dict, x: float, room: float, y: float, card_w: float) -> None:
    """The projected champion, centered under the championship card at baseline *y*: "Projected champion"
    over "Winona · 22%"."""
    label_font, team_font = _inter(24, 500), _inter(30, 600)
    label = "Projected champion"
    draw.text(
        (x + (card_w - draw.textlength(label, font=label_font)) / 2, y),
        label,
        font=label_font,
        fill=t.text_2,
        anchor="ls",
    )
    pct = f" · {format_pct(champ['p'])}"
    name = fit(draw, champ["team"], team_font, room - draw.textlength(pct, font=team_font))
    width = draw.textlength(name + pct, font=team_font)
    left = x + (card_w - width) / 2
    draw.text((left, y + 40), name, font=team_font, fill=t.text, anchor="ls")
    draw.text((left + draw.textlength(name, font=team_font), y + 40), pct, font=team_font, fill=t.text_2, anchor="ls")


def render_bracket_image(
    clazz: int,
    season: int,
    games: list[dict],
    results: dict,
    seeds: dict,
    view: str,
    blank: bool,
    stamp: str,
    teams: dict | None = None,
    theme: str = "dark",
    venue: dict | None = None,
) -> Image.Image:
    """The bracket image: *view* "N" or "S" (that half, square) or "all" (both halves, wide), in
    *theme* "dark" or "light".

    *results* are played games by id (``static_pages.layout_results``); *seeds* each locked-in team's
    (region, seed) (``static_pages.locked_seeds``); *stamp* where the numbers are from; *teams* the
    API's teams by school, for their helmets; *venue* the class's championship venue (the API's
    ``/championships`` location), named under the championship game when it's on record.
    """
    t = THEMES[theme]
    final = is_final(games, results)
    blank = blank or final
    picks = {} if blank else picks_for(games, results)
    size = WIDE if view == "all" else SQUARE
    pad = 72
    img = Image.new("RGB", size, t.bg)
    draw = ImageDraw.Draw(img)
    title = f"{season} Class {clazz}A Bracket" + ("" if view == "all" else f" · {HALF_NAMES.get(view, view)}")
    top = _header(draw, t, pad, title, _subtitle(final, blank))
    bottom = _footer(draw, t, size, pad, stamp)
    labels_h = 44
    body_top, body_h = top + labels_h, bottom - top - labels_h

    halves = ["N", "S"] if view == "all" else [view]
    rounds = {h: _half_rounds(games, h) for h in halves}
    depth = max((len(r) for r in rounds.values()), default=0)
    if not depth:
        return img
    final_game = next((g for g in games if g["id"] == "final"), None) if view == "all" else None
    cols = depth * len(halves) + (1 if final_game else 0)
    gap = 56
    card_w = (size[0] - 2 * pad - gap * (cols - 1)) / cols
    first = max(len(r[0]) for r in rounds.values() if r)
    row_h = min(64.0, body_h / first * 0.4)
    paint = _Painter(img, card_w, row_h, t, teams or {})
    label_font = _inter(24, 600)

    def column_x(h: str, k: int) -> float:
        """Left edge of round *k*'s column: the north half reads left to right, the south half (wide) right to left."""
        index = k if h == halves[0] else cols - 1 - k
        return pad + index * (card_w + gap)

    sf_centers = []
    for h in halves:
        rs = rounds[h]
        centers = _centers(rs, body_top, body_h)
        mirrored = view == "all" and h == "S"
        for k, games_k in enumerate(rs):
            x = column_x(h, k)
            _label(draw, t, games_k[0]["round"], x, card_w, top + 30, label_font)
            for i, g in enumerate(games_k):
                paint.card(g, x, centers[k][i], _rows(g, results, seeds, picks, blank))
                if k + 1 < len(rs):
                    target = centers[k + 1][i // 2]
                    if mirrored:
                        paint.join(x, centers[k][i], column_x(h, k + 1) + card_w, target)
                    else:
                        paint.join(x + card_w, centers[k][i], column_x(h, k + 1), target)
        if rs:
            sf_centers.append((h, column_x(h, len(rs) - 1), centers[-1][0]))
    if final_game:
        x = pad + depth * (card_w + gap)
        cy = sum(c for _, _, c in sf_centers) / len(sf_centers)
        _label(draw, t, final_game["round"], x, card_w, top + 30, label_font)
        paint.card(final_game, x, cy, _rows(final_game, results, seeds, picks, blank))
        for h, sx, sy in sf_centers:
            if h == "S":
                paint.join(sx, sy, x + card_w, cy)
            else:
                paint.join(sx + card_w, sy, x, cy)
        # Under the card: where it's played, then the champion (or, in the projected image, the
        # projected one), each line centered on the card.
        base = cy + paint.h / 2
        where = venue_name(venue)
        if where:
            font = _inter(24, 500)
            text = fit(draw, where, font, card_w + gap)
            draw.text(
                (x + (card_w - draw.textlength(text, font=font)) / 2, base + 42),
                text,
                font=font,
                fill=t.text_2,
                anchor="ls",
            )
            base += 40
        champion = (results.get("final") or {}).get("winner")
        if champion:
            cup = trophy(TROPHY_H)
            img.paste(cup, (round(x + (card_w - cup.width) / 2), round(cy - paint.h / 2 - 32 - cup.height)), cup)
            font = _inter(30, 600)
            text = fit(draw, f"Champion: {champion}", font, card_w + gap)
            tw = draw.textlength(text, font=font)
            draw.text((x + (card_w - tw) / 2, base + 50), text, font=font, fill=t.text, anchor="ls")
        elif not blank and (champ := projected_champion(final_game, None)):
            _projected_champion(draw, t, champ, x, card_w + gap, base + 50, card_w)
    return img
