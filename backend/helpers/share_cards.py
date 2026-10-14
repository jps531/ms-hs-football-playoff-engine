"""Share cards: the link-preview image and meta tags for region and class pages.

When someone pastes a region link into iMessage or Facebook, the preview
should be that region's own card: its name, its headline sentence, the top of
its standings with playoff odds, and what data it reflects ("Through Week 8 ·
Oct 24 · Projected"), baked into the image so a card can't mislead days later.

Everything here is pure: it takes the same JSON the site's API serves and
returns text or a Pillow image. ``backend/prefect/share_assets_pipeline.py``
fetches the data and writes the files; nginx splices the meta tags into the
app's ``index.html`` (see ``nginx/nginx.conf``).

Formatting mirrors the site's JavaScript (``nginx/html/static/js/format.js``)
so a card says exactly what the page says.
"""

from __future__ import annotations

import html
import math
from collections.abc import Iterable
from datetime import date
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SITE_NAME = "Mississippi High School Football"
SITE_HOST = "mshsfootball.com"

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
NIPPO = FONT_DIR / "Nippo-Bold.otf"
INTER = FONT_DIR / "inter-latin-wght-normal.woff2"

WIDTH, HEIGHT = 1200, 630
PAD = 64

# Dark theme tokens from nginx/html/static/css/app.css.
BG = "#161616"  # --surface-page (neutral-950)
TEXT = "#F7F7F7"  # --text-primary (neutral-50)
TEXT_2 = "#A4A3A4"  # --text-secondary (neutral-400)
RULE = "#393939"  # --border (neutral-800)
ODDS_BG = {1: "#393939", 2: "#07291D", 3: "#0D4632", 4: "#0F5B41", 5: "#137252"}  # --odds-1..5
ODDS_TEXT = "#F2FBF8"  # --odds-text (brand-50)

_EPS = 1e-9
DESCRIPTION_LIMIT = 155


# ------------------------------------------------------------------ text


def format_pct(p: float | None) -> str:
    """Percent as the site shows it: "0%", "<1%", "37%", ">99%", "100%"."""
    if p is None:
        return "—"
    if p <= _EPS:
        return "0%"
    if p >= 1 - _EPS:
        return "100%"
    rounded = math.floor(p * 100 + 0.5)  # JavaScript's Math.round: halves go up
    if rounded < 1:
        return "<1%"
    if rounded > 99:
        return ">99%"
    return f"{rounded}%"


def odds_bucket(p: float | None) -> int:
    """Odds-ramp slot 1-5, bucketed on the displayed value (so "79%" stays out of the 80s color)."""
    text = format_pct(p)
    if text in ("—", "<1%"):
        shown = 0
    elif text == ">99%":
        shown = 99
    else:
        shown = int(text.rstrip("%"))
    return 5 if shown >= 80 else shown // 20 + 1


def short_date(d: date) -> str:
    """ "Oct 9"."""
    return f"{d:%b} {d.day}"


def record_text(wins: int, losses: int, ties: int = 0) -> str:
    """ "6–1" or "6–1–1"."""
    return f"{wins}–{losses}–{ties}" if ties else f"{wins}–{losses}"


def odds_mode(teams: Iterable[dict]) -> str:
    """ "projected" when Elo-weighted odds exist (the site's default), else "tossup"."""
    return "projected" if any((t["odds"].get("p_playoffs_weighted") or 0) > 0 for t in teams) else "tossup"


def mode_odds(team: dict, key: str, mode: str) -> float:
    """One of a team's odds (``p1``..``p4``, ``p_playoffs``) in the odds mode."""
    odds = team["odds"]
    return (odds.get(f"{key}_weighted") or 0.0) if mode == "projected" else odds[key]


def provenance(as_of: date | None, dates: list[dict], mode: str, today: date) -> str:
    """What a card reflects, as the page's controls say it: "Through Week 8 · Oct 24 · Projected".

    Mirrors the site: weeks come from the season's game dates before today;
    the week shown is the newest one the snapshot reaches; and when the
    snapshot predates that week's last games it says "Latest update" instead
    of implying the week's date.
    """
    weeks: dict[int, dict] = {}
    for d in dates:
        if d.get("kind") != "games":
            continue
        day = date.fromisoformat(d["date"]) if isinstance(d["date"], str) else d["date"]
        if day >= today:
            continue
        w = weeks.setdefault(
            d["week"], {"label": d.get("description") or f"Week {d['week']}", "first": day, "last": day}
        )
        w["first"] = min(w["first"], day)
        w["last"] = max(w["last"], day)
    ordered = [weeks[k] for k in sorted(weeks)]
    if as_of is not None:
        ordered = [w for w in ordered if w["first"] <= as_of]
    parts: list[str] = []
    if ordered:
        shown = ordered[-1]
        parts.append(f"Through {shown['label']}")
        if as_of is not None and as_of < shown["last"]:
            parts.append(f"Latest update {short_date(as_of)}")
        else:
            parts.append(short_date(shown["last"]))
    elif as_of is not None:
        parts.append(f"Updated {short_date(as_of)}")
    parts.append("Projected" if mode == "projected" else "Toss-up")
    return " · ".join(parts)


def region_title(clazz: int, region: int) -> str:
    """The region page's title, as the app sets it."""
    return f"Region {region}-{clazz}A playoff race — {SITE_NAME}"


def class_title(clazz: int) -> str:
    """The class page's title, as the app sets it."""
    return f"Class {clazz}A playoff races — {SITE_NAME}"


def class_description(clazz: int) -> str:
    """A class page's description."""
    return f"Every Class {clazz}A region race in Mississippi: who’s in, who’s out, and what has to happen next."


def description(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    """The headline sentence, cut at a word boundary to about *limit* characters."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:—–-")
    return f"{cut}…"


def meta_tags(title: str, desc: str, image_url: str, page_url: str) -> str:
    """The page's <title>, description, Open Graph and Twitter tags, ready to splice into <head>."""
    t, d, img, url = (html.escape(v, quote=True) for v in (title, desc, image_url, page_url))
    return "\n".join(
        [
            f"<title>{t}</title>",
            f'<meta name="description" content="{d}">',
            f'<meta property="og:site_name" content="{html.escape(SITE_NAME)}">',
            '<meta property="og:type" content="website">',
            f'<meta property="og:title" content="{t}">',
            f'<meta property="og:description" content="{d}">',
            f'<meta property="og:url" content="{url}">',
            f'<meta property="og:image" content="{img}">',
            f'<meta property="og:image:width" content="{WIDTH}">',
            f'<meta property="og:image:height" content="{HEIGHT}">',
            '<meta name="twitter:card" content="summary_large_image">',
            f'<link rel="canonical" href="{url}">',
            "",
        ]
    )


# ----------------------------------------------------------------- drawing


@cache
def _inter(size: int, weight: int) -> ImageFont.FreeTypeFont:
    """Inter at *size* px and a weight from its variable axis (400 regular, 600 semibold)."""
    font = ImageFont.truetype(str(INTER), size)
    font.set_variation_by_axes([weight])
    return font


@cache
def _nippo(size: int) -> ImageFont.FreeTypeFont:
    """Nippo Bold at *size* px, for titles."""
    return ImageFont.truetype(str(NIPPO), size)


def fit(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: float) -> str:
    """*text* as it fits on one line in *width*, ending in "…" when cut."""
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(f"{text}…", font=font) > width:
        text = text[:-1]
    return f"{text.rstrip()}…"


def wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: float, max_lines: int) -> list[str]:
    """*text* wrapped at word boundaries into at most *max_lines* lines; the last ends in "…" if cut."""
    lines: list[str] = []
    words = text.split()
    i = 0
    while i < len(words) and len(lines) < max_lines:
        line = words[i]
        i += 1
        while i < len(words) and draw.textlength(f"{line} {words[i]}", font=font) <= width:
            line = f"{line} {words[i]}"
            i += 1
        lines.append(line)
    if i < len(words) and lines:
        lines[-1] = fit(draw, f"{lines[-1]} {' '.join(words[i:])}", font, width)
    return [fit(draw, line, font, width) for line in lines]


def _tracked(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font, fill, tracking: float, anchor="ls"):
    """Small caps-style label with letter spacing (Pillow has none built in). Left or right anchored."""
    total = sum(draw.textlength(ch, font=font) for ch in text) + tracking * max(0, len(text) - 1)
    x, y = xy
    if anchor[0] == "r":
        x -= total
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor="l" + anchor[1])
        x += draw.textlength(ch, font=font) + tracking


def _odds_pill(draw: ImageDraw.ImageDraw, right: float, middle: float, p: float) -> None:
    """An odds cell in the ramp, right-aligned at *right*, centered on *middle*."""
    w, h = 118, 44
    box = (right - w, middle - h / 2, right, middle + h / 2)
    draw.rounded_rectangle(box, radius=7, fill=ODDS_BG[odds_bucket(p)])
    draw.text((right - 14, middle), format_pct(p), font=_inter(27, 600), fill=ODDS_TEXT, anchor="rm")


def _footer(draw: ImageDraw.ImageDraw, stamp: str) -> None:
    """Provenance stamp (left) and the site's address (right), along the bottom."""
    base = HEIGHT - PAD + 8
    _tracked(draw, (PAD, base), stamp.upper(), _inter(19, 600), TEXT_2, 1.6)
    draw.text((WIDTH - PAD, base), SITE_HOST, font=_inter(24, 600), fill=TEXT, anchor="rs")


def _table(draw, top: float, rows: list[tuple[str, str, str, float]], headers: tuple[str, str], name_x: float) -> None:
    """Rows of (label, name, record, odds) under small column headers."""
    right = WIDTH - PAD
    record_right = right - 118 - 40
    small = _inter(17, 600)
    _tracked(draw, (record_right, top), headers[0], small, TEXT_2, 1.6, anchor="rs")
    _tracked(draw, (right, top), headers[1], small, TEXT_2, 1.6, anchor="rs")
    y = top + 14
    row_h = 56
    for label, name, record, p in rows:
        draw.line((PAD, y, right, y), fill=RULE, width=1)
        middle = y + row_h / 2
        draw.text((PAD, middle), label, font=_inter(26, 500), fill=TEXT_2, anchor="lm")
        name_font = _inter(30, 600)
        record_font = _inter(27, 500)
        record_w = draw.textlength(record, font=record_font)
        draw.text(
            (name_x, middle),
            fit(draw, name, name_font, record_right - record_w - 32 - name_x),
            font=name_font,
            fill=TEXT,
            anchor="lm",
        )
        draw.text((record_right, middle), record, font=record_font, fill=TEXT, anchor="rm")
        _odds_pill(draw, right, middle, p)
        y += row_h


def render_region_card(clazz: int, region: int, payload: dict, stamp: str, mode: str) -> Image.Image:
    """A region's card: name, headline sentence, top of the standings with playoff odds, provenance.

    *payload* is the API's region standings response (``/standings/{class}/{region}``).
    """
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    draw.text((PAD, PAD + 58), f"Region {region}-{clazz}A", font=_nippo(76), fill=TEXT, anchor="ls")
    y = PAD + 58 + 24
    headline = payload.get("headline")
    lines = wrap(draw, headline, _inter(34, 600), WIDTH - 2 * PAD, 3) if headline else []
    for line in lines:
        y += 44
        draw.text((PAD, y), line, font=_inter(34, 600), fill=TEXT, anchor="ls")
    teams = payload.get("teams") or []
    count = 4 if len(lines) <= 2 else 3
    rows = [
        (
            str(i + 1),
            t["school"],
            record_text(t["record"]["region_wins"], t["record"]["region_losses"], t["record"].get("region_ties") or 0),
            mode_odds(t, "p_playoffs", mode),
        )
        for i, t in enumerate(teams[:count])
    ]
    _table(draw, y + 46, rows, ("REGION", "PLAYOFFS"), PAD + 44)
    _footer(draw, stamp)
    return img


def render_class_card(clazz: int, payload: dict, stamp: str, mode: str) -> Image.Image:
    """A class's card: every region's leader and its odds of winning the region.

    *payload* is the API's class standings response (``/standings/{class}``).
    """
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    draw.text((PAD, PAD + 58), f"Class {clazz}A", font=_nippo(76), fill=TEXT, anchor="ls")
    regions = sorted(payload.get("regions") or [], key=lambda r: r["region"])
    leaders = [(r["region"], r["teams"][0]) for r in regions if r.get("teams")]
    y = PAD + 58
    if len(leaders) <= 4:
        draw.text((PAD, y + 50), "Who leads every region race", font=_inter(34, 600), fill=TEXT_2, anchor="ls")
        y += 50
    rows = [
        (
            f"R{region}",
            t["school"],
            record_text(t["record"]["region_wins"], t["record"]["region_losses"], t["record"].get("region_ties") or 0),
            mode_odds(t, "p1", mode),
        )
        for region, t in leaders[:8]
    ]
    if len(rows) > 4:
        _class_table(draw, y + 40, rows)  # eight regions: two columns of four
    else:
        _table(draw, y + 46, rows, ("REGION", "WINS REGION"), PAD + 56)
    _footer(draw, stamp)
    return img


def _class_table(draw, top: float, rows: list[tuple[str, str, str, float]]) -> None:
    """Eight region leaders in two columns of four."""
    small = _inter(17, 600)
    col_w = (WIDTH - 2 * PAD - 48) / 2
    _tracked(draw, (PAD, top), "REGION LEADERS", small, TEXT_2, 1.6)
    _tracked(draw, (PAD + col_w, top), "WINS REGION", small, TEXT_2, 1.6, anchor="rs")
    _tracked(draw, (WIDTH - PAD, top), "WINS REGION", small, TEXT_2, 1.6, anchor="rs")
    row_h = 74
    for i, (label, name, record, p) in enumerate(rows):
        col, row = divmod(i, 4)
        left = PAD + col * (col_w + 48)
        right = left + col_w
        y = top + 14 + row * row_h
        draw.line((left, y, right, y), fill=RULE, width=1)
        middle = y + row_h / 2
        draw.text((left, middle), label, font=_inter(24, 500), fill=TEXT_2, anchor="lm")
        name_x = left + 52
        name_font = _inter(28, 600)
        draw.text(
            (name_x, middle - 13),
            fit(draw, name, name_font, right - 118 - 24 - name_x),
            font=name_font,
            fill=TEXT,
            anchor="lm",
        )
        draw.text((name_x, middle + 19), f"{record} in region", font=_inter(21, 500), fill=TEXT_2, anchor="lm")
        _odds_pill(draw, right, middle, p)


def render_site_card() -> Image.Image:
    """The fallback card for pages without their own: the site's name and what it does."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    lines = wrap(draw, SITE_NAME, _nippo(84), WIDTH - 2 * PAD, 2)
    y = PAD + 60
    for line in lines:
        draw.text((PAD, y), line, font=_nippo(84), fill=TEXT, anchor="ls")
        y += 92
    for line in wrap(
        draw,
        "Every region race: who’s in, who’s out, and exactly what has to happen next.",
        _inter(36, 600),
        WIDTH - 2 * PAD,
        3,
    ):
        y += 12
        draw.text((PAD, y), line, font=_inter(36, 600), fill=TEXT_2, anchor="ls")
        y += 36
    draw.text((WIDTH - PAD, HEIGHT - PAD + 8), SITE_HOST, font=_inter(24, 600), fill=TEXT, anchor="rs")
    return img
