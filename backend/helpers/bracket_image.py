"""The whole bracket as one image, to share: one half as a square, or both halves side by side.

Two versions. **Projected odds**: every open spot shows the team the bracket page shows there
(``static_pages.round_picks``: no team in two spots of one round) with its Projected chance of being
there. **Blank**: only what's settled, locked-in teams and results; an open first-round spot shows
the seed that goes there, a later one stays empty. A season that's over is the same either way.

Pure, like ``share_cards``: it takes the API's ``/bracket/matchups`` games and played results and
returns a Pillow image. ``backend/prefect/share_assets_pipeline.py`` writes the files. The image
says what it shows (the class, the half, the version) and where its numbers are from (the stamp), so
a copy passed around stays honest.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

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
    locked_team,
    occupants,
    position_name,
    round_picks,
    settled_host,
    tree_columns,
)

SQUARE = (2000, 2000)  # one half
WIDE = (3600, 2025)  # both halves, 16:9
CARD = "#272727"  # --surface-card, dark (neutral-900)
LINE = "#7B7A7B"  # --connector, dark (neutral-500)
MODE = "projected"  # the odds version is Projected only


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
    """Draws cards and lines at one scale."""

    def __init__(self, draw: ImageDraw.ImageDraw, card_w: float, row_h: float):
        self.draw = draw
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
        self.draw.rounded_rectangle((x, top, x + self.w, top + self.h), radius=10, fill=CARD)
        self.draw.line((x + 12, cy, x + self.w - 12, cy), fill=RULE, width=2)
        for i, view in enumerate(rows):
            self._row(view, x, top + 3 + i * self.row_h)

    def _row(self, view: dict, x: float, top: float) -> None:
        """One side: its name (and seed or position under it), then its score or chance on the right."""
        pad = 16
        right = x + self.w - pad
        mid = top + self.row_h / 2
        value_w = 0.0
        if view["score"] is not None:
            font = self.name if view["kind"] == "won" else self.name_light
            text = str(view["score"])
            self.draw.text((right, mid), text, font=font, fill=TEXT if view["kind"] == "won" else TEXT_2, anchor="rm")
            value_w = self.draw.textlength(text, font=font) + 12
        elif view["pct"] is not None:
            pill_w = self.row_h * 1.35
            pill_h = self.row_h * 0.62
            box = (right - pill_w, mid - pill_h / 2, right, mid + pill_h / 2)
            self.draw.rounded_rectangle(box, radius=6, fill=ODDS_BG[odds_bucket(view["pct"])])
            self.draw.text((right - 10, mid), format_pct(view["pct"]), font=self.pill, fill=ODDS_TEXT, anchor="rm")
            value_w = pill_w + 12
        width = self.w - 2 * pad - value_w
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
                fill=TEXT_2 if muted else TEXT,
                anchor="ls",
            )
            self.draw.text(
                (x + pad, mid + 4),
                fit(self.draw, view["sub"], self.sub, width),
                font=self.sub,
                fill=TEXT_2,
                anchor="lt",
            )
        elif view["name"]:
            self.draw.text(
                (x + pad, mid),
                fit(self.draw, view["name"], font, width),
                font=font,
                fill=TEXT_2 if muted else TEXT,
                anchor="lm",
            )

    def join(self, x_from: float, y_from: float, x_to: float, y_to: float) -> None:
        """An elbow from one card's edge to the next round's card: across, up or down, across."""
        mid = (x_from + x_to) / 2
        self.draw.line([(x_from, y_from), (mid, y_from), (mid, y_to), (x_to, y_to)], fill=LINE, width=3, joint="curve")


def _rows(game: dict, results: dict, seeds: dict, picks: dict, blank: bool) -> list[dict]:
    """Both sides of a game, top to bottom as the bracket page orders them (home team last)."""
    order, _ = _game_order(game, settled_host(game, MODE))
    return [slot(game, k, results, seeds, picks, blank) for k in order]


def _header(draw, size: tuple[int, int], pad: int, title: str, subtitle: str) -> float:
    """Title and subtitle; returns where the bracket may start."""
    draw.text((pad, pad + 70), title, font=_nippo(88), fill=TEXT, anchor="ls")
    draw.text((pad, pad + 128), subtitle, font=_inter(36, 500), fill=TEXT_2, anchor="ls")
    return pad + 190


def _footer(draw, size: tuple[int, int], pad: int, stamp: str) -> float:
    """The stamp and the site's address along the bottom; returns where the bracket must end."""
    width, height = size
    base = height - pad + 4
    _tracked(draw, (pad, base), stamp.upper(), _inter(26, 600), TEXT_2, 2)
    draw.text((width - pad, base), SITE_HOST, font=_inter(34, 600), fill=TEXT, anchor="rs")
    return height - pad - 60


def _label(draw, name: str, x: float, width: float, base: float, font) -> None:
    """A round's name over its column, letter-spaced and centered."""
    text = name.upper()
    _tracked(draw, (x + (width - _tracked_width(draw, text, font, 1.5)) / 2, base), text, font, TEXT_2, 1.5)


def _subtitle(final: bool, blank: bool, season: int) -> str:
    """What the image shows."""
    if final:
        return f"{season} season · Final"
    if blank:
        return "Teams and results so far · open first-round spots show the seed that goes there"
    return "Projected odds · each open spot shows one team that could be there, and its chance"


def render_bracket_image(
    clazz: int,
    season: int,
    games: list[dict],
    results: dict,
    seeds: dict,
    view: str,
    blank: bool,
    stamp: str,
) -> Image.Image:
    """The bracket image: *view* "N" or "S" (that half, square) or "all" (both halves, wide).

    *results* are played games by id (``static_pages.layout_results``); *seeds* each locked-in team's
    (region, seed) (``static_pages.locked_seeds``); *stamp* where the numbers are from.
    """
    final = is_final(games, results)
    blank = blank or final
    picks = {} if blank else picks_for(games, results)
    size = WIDE if view == "all" else SQUARE
    pad = 72
    img = Image.new("RGB", size, BG)
    draw = ImageDraw.Draw(img)
    title = f"Class {clazz}A Bracket" + ("" if view == "all" else f" · {HALF_NAMES.get(view, view)}")
    top = _header(draw, size, pad, title, _subtitle(final, blank, season))
    bottom = _footer(draw, size, pad, stamp)
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
    paint = _Painter(draw, card_w, row_h)
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
            _label(draw, games_k[0]["round"], x, card_w, top + 30, label_font)
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
        _label(draw, final_game["round"], x, card_w, top + 30, label_font)
        paint.card(final_game, x, cy, _rows(final_game, results, seeds, picks, blank))
        for h, sx, sy in sf_centers:
            if h == "S":
                paint.join(sx, sy, x + card_w, cy)
            else:
                paint.join(sx + card_w, sy, x, cy)
        champion = (results.get("final") or {}).get("winner")
        if champion:
            font = _inter(30, 600)
            text = fit(draw, f"Champion: {champion}", font, card_w + gap)
            tw = draw.textlength(text, font=font)
            draw.text((x + (card_w - tw) / 2, cy + paint.h / 2 + 50), text, font=font, fill=TEXT, anchor="ls")
    return img
