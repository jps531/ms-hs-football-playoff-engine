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
import logging
import math
import re
import unicodedata
from collections.abc import Iterable
from datetime import date
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from backend.helpers.certainty import CERTAIN_EPS

SITE_NAME = "Mississippi High School Football"
SITE_TITLE = "Mississippi High School Football Playoff Races"
SITE_DESCRIPTION = (
    "Scenarios and odds for every MHSAA high school football region race, and an outlook for every playoff game."
)
SITE_HOST = "mshsfootball.com"

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
# Nippo's license covers this site's own use, not copies in a public repository,
# so the file isn't committed (backend/assets/fonts/README.md says where it comes from).
NIPPO = FONT_DIR / "Nippo-Bold.otf"
INTER = FONT_DIR / "inter-latin-wght-normal.woff2"
# The site's helmet (nginx/html/static/helmet.webp, the front page's), for the footer's lockup.
HELMET_ART = FONT_DIR.parent / "helmet.webp"
# The URL in the footer's lockup: the site's link green in each theme (--brand-400 dark, --brand-600 light).
BRAND_GREEN = {"dark": "#66DDB5", "light": "#198C65"}

_log = logging.getLogger(__name__)

WIDTH, HEIGHT = 1200, 630
PAD = 64

# Dark theme tokens from nginx/html/static/css/app.css.
BG = "#161616"  # --surface-page (neutral-950)
TEXT = "#F7F7F7"  # --text-primary (neutral-50)
TEXT_2 = "#A4A3A4"  # --text-secondary (neutral-400)
RULE = "#393939"  # a rule (neutral-800; the site's dark --border is a step lighter, neutral-700)
ODDS_BG = {1: "#393939", 2: "#07291D", 3: "#0D4632", 4: "#0F5B41", 5: "#137252"}  # --odds-1..5
ODDS_TEXT = "#F2FBF8"  # --odds-text (brand-50)

_EPS = CERTAIN_EPS  # 0% and 100% only for certainties (backend.helpers.certainty)
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


def provenance(as_of: date | None, dates: list[dict], mode: str | None, today: date) -> str:
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
    if mode:  # None where nothing shown has odds, so the mode would say nothing
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
    return f"Every MHSAA Class {clazz}A region race."


def description(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    """The headline sentence, cut at a word boundary to about *limit* characters."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:—–-")
    return f"{cut}…"


def meta_tags(title: str, desc: str, image_url: str, page_url: str, extra: str = "", *, image_alt: str) -> str:
    """The page's <title>, description, Open Graph and Twitter tags, ready to splice into <head>.

    *image_alt* says what the card image shows, for anyone who can't see it. *extra* is appended as
    is: the page's structured data (``static_pages.json_ld`` blocks).
    """
    t, d, img, url, alt = (html.escape(v, quote=True) for v in (title, desc, image_url, page_url, image_alt))
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
            f'<meta property="og:image:alt" content="{alt}">',
            '<meta name="twitter:card" content="summary_large_image">',
            f'<meta name="twitter:image:alt" content="{alt}">',
            f'<link rel="canonical" href="{url}">',
            *([extra] if extra else []),
            "",
        ]
    )


# What each card shows, as its image's alt text (``meta_tags``' *image_alt*).

SITE_CARD_ALT = f"{SITE_NAME}: {SITE_DESCRIPTION}"


def class_card_alt(clazz: int) -> str:
    """The class card (``render_class_card``)."""
    return (
        f"Class {clazz}A: the team on top in each region race, with its region record and its chance to win the region."
    )


def region_card_alt(clazz: int, region: int) -> str:
    """The region card (``render_region_card``)."""
    return (
        f"Region {region}-{clazz}A standings, with the teams' region records and their chances of finishing "
        "first through fourth and of making the playoffs."
    )


def team_card_alt(team: dict, clazz: int, region: int, mode: str) -> str:
    """A team's card on its region page (``render_team_card``): the round chances only when it shows them."""
    rounds = ", and its chance of reaching each playoff round" if playoff_path(team, mode, clazz) else ""
    return (
        f"{team['school']}, Region {region}-{clazz}A: its records and its chances of each seed and of making "
        f"the playoffs{rounds}."
    )


def bracket_card_alt(clazz: int, season: int, picture: bool) -> str:
    """A bracket page's card: the whole bracket in miniature (*picture*), or its favorites' table."""
    if picture:
        return f"The {season} Class {clazz}A playoff bracket."
    return (
        f"The Class {clazz}A bracket's favorites and their chances of reaching the semifinals and the "
        "championship game, and of winning it."
    )


def team_bracket_card_alt(team: str, clazz: int) -> str:
    """A team's card on the bracket page (``render_team_bracket_card``)."""
    return f"{team}'s road through the Class {clazz}A playoff bracket, round by round."


# ----------------------------------------------------------------- drawing


# How much larger text is drawn before it's scaled down to size (SmoothDraw).
_SUPERSAMPLE = 4
# Each font _inter and _nippo make, by id: how to make it again at another size.
_REMAKE: dict[int, tuple] = {}


@cache
def _inter(size: int, weight: int) -> ImageFont.FreeTypeFont:
    """Inter at *size* px and a weight from its variable axis (400 regular, 600 semibold)."""
    font = ImageFont.truetype(str(INTER), size)
    font.set_variation_by_axes([weight])
    _REMAKE[id(font)] = (_inter, size, (weight,))
    return font


@cache
def _nippo(size: int) -> ImageFont.FreeTypeFont:
    """Nippo Bold at *size* px, for titles; Inter Bold when the Nippo file isn't installed (tests, CI)."""
    if NIPPO.exists():
        font = ImageFont.truetype(str(NIPPO), size)
        _REMAKE[id(font)] = (_nippo, size, ())
        return font
    _log.warning("%s not found: drawing titles in Inter Bold (see backend/assets/fonts/README.md)", NIPPO)
    return _inter(size, 700)


def _larger(font) -> ImageFont.FreeTypeFont | None:
    """*font* at _SUPERSAMPLE times its size, when it's one of ours."""
    made = _REMAKE.get(id(font))
    return made[0](made[1] * _SUPERSAMPLE, *made[2]) if made else None


_PLAIN = ImageDraw.Draw


class SmoothDraw(ImageDraw.ImageDraw):
    """ImageDraw whose text is drawn at _SUPERSAMPLE times its size and scaled down into place.

    Drawn at size, FreeType fits each letter to the pixel grid and Pillow puts each one on a whole
    pixel, so at the sizes these images use the gaps between letters come out uneven ("Kosci usko").
    Drawn larger, the letters sit within a quarter of a pixel of where the font puts them. Text is
    measured the same way, so what's laid out is what's drawn."""

    def __init__(self, img: Image.Image):
        super().__init__(img)
        self._img = img

    def textlength(self, text, font=None, *args, **kwargs):
        big = _larger(font)
        if big is None or args or kwargs:
            return super().textlength(text, font, *args, **kwargs)
        return super().textlength(text, big) / _SUPERSAMPLE

    def text(self, xy, text, fill=None, font=None, anchor=None, *args, **kwargs):
        big = _larger(font)
        if big is None or fill is None or args or kwargs or not text or "\n" in text:
            return super().text(xy, text, fill, font, anchor, *args, **kwargs)
        k = _SUPERSAMPLE
        x, y = xy[0] * k, xy[1] * k
        left, top, right, bottom = big.getbbox(text, anchor=anchor)
        ox, oy = math.floor((x + left) / k) * k, math.floor((y + top) / k) * k
        w = math.ceil((x + right - ox) / k + 1) * k
        h = math.ceil((y + bottom - oy) / k + 1) * k
        mask = Image.new("L", (w, h), 0)
        _PLAIN(mask).text((x - ox, y - oy), text, fill=255, font=big, anchor=anchor)
        mask = mask.resize((w // k, h // k), Image.BOX)
        self._img.paste(fill, (ox // k, oy // k, ox // k + w // k, oy // k + h // k), mask)


def smooth_draw(img: Image.Image) -> SmoothDraw:
    """A SmoothDraw on *img*."""
    return SmoothDraw(img)


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


def _tracked_width(draw: ImageDraw.ImageDraw, text: str, font, tracking: float) -> float:
    """Width of *text* drawn by ``_tracked``."""
    return draw.textlength(text, font=font) + tracking * max(0, len(text) - 1)


def _tracked(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font, fill, tracking: float, anchor="ls"):
    """Small caps-style label with letter spacing (Pillow has none built in). Left or right anchored.

    Each letter goes where the whole line would put it (its kerning with the letters before it kept),
    then *tracking* further along for each letter before it: drawn one at a time, the pairs the font
    kerns ("AV", "TA") would otherwise sit too far apart."""
    total = _tracked_width(draw, text, font, tracking)
    x, y = xy
    if anchor[0] == "r":
        x -= total
    for i, ch in enumerate(text):
        if not ch.isspace():
            at = x + draw.textlength(text[:i], font=font) + tracking * i
            draw.text((at, y), ch, font=font, fill=fill, anchor="l" + anchor[1])


@cache
def _helmet_art(height: int) -> Image.Image:
    """The site's helmet, *height* px tall."""
    art = Image.open(HELMET_ART).convert("RGBA")
    art = art.crop(art.getbbox())
    return art.resize((round(art.width * height / art.height), height), Image.LANCZOS)


def stamp_line(stamp: str) -> str:
    """A footer's provenance, its odds mode said in full: "… · Projected" → "… · Projected odds"."""
    for mode in ("Projected", "Toss-up"):
        if stamp.endswith(f" · {mode}") or stamp == mode:
            return f"{stamp} odds"
    return stamp


def theme_name(t) -> str:
    """ "dark" or "light": which of marks.THEMES *t* is."""
    return "dark" if t.text == TEXT else "light"


def brand_lockup(
    img: Image.Image, theme: str, edge: float, base: float, size: int, align: str = "right"
) -> tuple[float, float]:
    """The site's helmet, name and address, its right side at *edge* (or with *align* "left", its left
    side), the address's baseline at *base*; *size* is the name's font size. Returns the lockup's left
    edge and its top."""
    draw = smooth_draw(img)
    name_font, host_font = _nippo(size), _nippo(round(size * 0.8))
    name_base = base - round(size * 1.08)
    width = max(draw.textlength(SITE_NAME, font=name_font), draw.textlength(SITE_HOST, font=host_font))
    top = name_base - round(size * 0.78)  # the name's cap height
    art = _helmet_art(round((base - top) * 1.12))
    gap = round(size * 0.45)
    x = edge - width if align == "right" else edge + art.width + gap
    left = x - gap - art.width
    img.paste(art, (round(left), round((top + base) / 2 - art.height / 2)), art)
    text = TEXT if theme == "dark" else "#272727"
    draw.text((x, name_base), SITE_NAME, font=name_font, fill=text, anchor="ls")
    draw.text((x, base), SITE_HOST, font=host_font, fill=BRAND_GREEN[theme], anchor="ls")
    return left, top


def brand_footer(img: Image.Image, theme: str, pad: float, stamp: str, size: int, stamp_size: int, color: str) -> float:
    """The footer along the bottom of *img*: the provenance *stamp* (if any) at the left in Nippo
    capitals, the site's lockup at the right (``brand_lockup``, its name at *size*). Returns the top of
    the footer: where what's above it must end."""
    w, h = img.size
    base = h - pad
    left, top = brand_lockup(img, theme, w - pad, base, size)
    if stamp:
        draw = smooth_draw(img)
        text = stamp_line(stamp).upper()
        tracking = stamp_size * 0.08
        font = _nippo(stamp_size)
        while _tracked_width(draw, text, font, tracking) > left - pad - size and font.size > 10:
            font = _nippo(font.size - 1)
        _tracked(draw, (pad, (top + base) / 2), text, font, color, tracking, anchor="lm")
    return top - round(size * 0.9)


def _breadcrumb(draw: ImageDraw.ImageDraw, x: float, base: float, parts: list[str], size: int) -> None:
    """A trail like the site's breadcrumb ("Class 4A › Region 3-4A"), in Nippo: the places above in the
    link green, the last one plain."""
    font = _nippo(size)
    for i, part in enumerate(parts):
        if i:
            draw.text((x, base), " › ", font=font, fill=TEXT_2, anchor="ls")
            x += draw.textlength(" › ", font=font)
        draw.text((x, base), part, font=font, fill=TEXT_2 if i == len(parts) - 1 else BRAND_GREEN["dark"], anchor="ls")
        x += draw.textlength(part, font=font)


def _school_title(img: Image.Image, draw, base: float, school: str, font, look: dict | None) -> None:
    """A card's school name at *base* in *font*, its helmet (from *look*, its ``/teams`` entry) before it
    when it has colors."""
    from backend.helpers.marks import helmet, team_colors  # marks imports this module

    x = PAD
    colors = team_colors(look)
    if colors:
        size = round(font.size * 0.95)
        icon = helmet(colors[0], colors[1], size, "#FFFFFF")
        img.paste(icon, (x, round(base - font.size * 0.74 / 2 - size / 2)), icon)
        x += size + round(font.size * 0.25)
    draw.text((x, base), fit(draw, school, font, WIDTH - PAD - x), font=font, fill=TEXT, anchor="ls")


def _lock(draw: ImageDraw.ImageDraw, x: float, mid: float, h: float, color: str) -> float:
    """A padlock *h* px tall, its left at *x*, centered on *mid*; returns its width."""
    w = h * 0.78
    body_top = mid - h / 2 + h * 0.42
    shackle = (x + w * 0.2, mid - h / 2, x + w * 0.8, body_top + h * 0.3)
    draw.arc(shackle, 180, 360, fill=color, width=max(2, round(h * 0.12)))
    draw.line(
        (shackle[0] + h * 0.06, body_top - h * 0.12, shackle[0] + h * 0.06, body_top),
        fill=color,
        width=max(2, round(h * 0.12)),
    )
    draw.line(
        (shackle[2] - h * 0.06, body_top - h * 0.12, shackle[2] - h * 0.06, body_top),
        fill=color,
        width=max(2, round(h * 0.12)),
    )
    draw.rounded_rectangle((x, body_top, x + w, mid + h / 2), radius=h * 0.1, fill=color)
    return w


def _odds_pill(
    draw: ImageDraw.ImageDraw,
    right: float,
    middle: float,
    p: float,
    width: float = 118,
    height: float = 44,
    size: int = 27,
) -> None:
    """An odds cell in the ramp, right-aligned at *right*, centered on *middle*."""
    box = (right - width, middle - height / 2, right, middle + height / 2)
    draw.rounded_rectangle(box, radius=7, fill=ODDS_BG[odds_bucket(p)])
    draw.text((right - 12, middle), format_pct(p), font=_inter(size, 600), fill=ODDS_TEXT, anchor="rm")


def _footer(img: Image.Image, stamp: str) -> float:
    """Provenance stamp (left) and the site's lockup (right), along the bottom of a dark card."""
    return brand_footer(img, "dark", PAD - 12, stamp, CARD_LOCKUP, 19, TEXT_2)


# The site's name in a link preview's footer, and the bottom of the area a table may use above it.
CARD_LOCKUP = 21
_TABLE_BOTTOM = HEIGHT - PAD - 48


def _table(
    draw,
    top: float,
    rows: list[tuple[str, str, str, list[float]]],
    record_header: str,
    odds_headers: list[str],
    name_x: float,
    row_h: float = 56,
    pill_widths: list[float] | None = None,
    gap: float = 10,
) -> None:
    """Rows of (label, name, record, [odds...]) under small column headers, odds columns on the right."""
    right = WIDTH - PAD
    widths = pill_widths or [118] * len(odds_headers)
    # Right edge of each odds column, last one flush with the margin.
    rights: list[float] = []
    edge = right
    for w in reversed(widths):
        rights.insert(0, edge)
        edge -= w + gap
    record_right = edge + gap - 32
    small = _nippo(17)
    _tracked(draw, (record_right, top), record_header, small, TEXT_2, 1.6, anchor="rs")
    header_font, tracking = small, 1.6
    if any(_tracked_width(draw, h, small, 1.6) > w + gap - 6 for h, w in zip(odds_headers, widths, strict=True)):
        header_font, tracking = _nippo(15), 0.8
    for col_right, header in zip(rights, odds_headers, strict=True):
        _tracked(draw, (col_right, top), header, header_font, TEXT_2, tracking, anchor="rs")
    pill_h = min(44, row_h - 10)
    pill_size = 27 if min(widths) >= 110 else 23
    name_font = _inter(30 if row_h >= 52 else 28, 600)
    record_font = _inter(27 if row_h >= 52 else 25, 500)
    y = top + 14
    for label, name, record, odds in rows:
        draw.line((PAD, y, right, y), fill=RULE, width=1)
        middle = y + row_h / 2
        draw.text((PAD, middle), label, font=_inter(26, 500), fill=TEXT_2, anchor="lm")
        record_w = draw.textlength(record, font=record_font)
        draw.text(
            (name_x, middle),
            fit(draw, name, name_font, record_right - record_w - 28 - name_x),
            font=name_font,
            fill=TEXT,
            anchor="lm",
        )
        draw.text((record_right, middle), record, font=record_font, fill=TEXT, anchor="rm")
        for col_right, w, p in zip(rights, widths, odds, strict=True):
            _odds_pill(draw, col_right, middle, p, w, pill_h, pill_size)
        y += row_h


def _win_pct(r: dict) -> float | None:
    """Region winning percentage, ties counting half; None with no games played."""
    games = r["region_wins"] + r["region_losses"] + (r.get("region_ties") or 0)
    return (r["region_wins"] + 0.5 * (r.get("region_ties") or 0)) / games if games else None


def display_order(teams: list[dict]) -> list[dict]:
    """Teams in the order the standings table shows them (``displayOrder`` in standings.js).

    Region winning percentage (no games counts as .500), then games over .500,
    then odds of 1st, the playoffs, 2nd, 3rd and 4th (projected when any exist),
    then the API's order (MHSAA tiebreakers).
    """
    weighted = any((t["odds"].get("p_playoffs_weighted") or 0) > 0 for t in teams)
    keys = [f"{k}_weighted" if weighted else k for k in ("p1", "p_playoffs", "p2", "p3", "p4")]

    def key(t: dict) -> tuple:
        """Sort key: larger is earlier, so every part is negated."""
        r = t["record"]
        return (
            -_pct_or_half(t),
            -(r["region_wins"] - r["region_losses"]),
            *(-(t["odds"].get(k) or 0.0) for k in keys),
        )

    return sorted(teams, key=key)  # stable: ties keep the API's order


def standing_positions(ordered: list[dict]) -> list[int]:
    """Positions with ties shared, competition style (``standingPositions`` in standings.js): 1, 1, 1, 4.

    "Tied" means the same region winning percentage, so 2-0 and 1-0 share a position.
    """
    out: list[int] = []
    for i, t in enumerate(ordered):
        tied = i > 0 and _pct_or_half(ordered[i - 1]) == _pct_or_half(t)
        out.append(out[i - 1] if tied else i + 1)
    return out


def position_labels(positions: list[int]) -> list[str]:
    """Positions as the standings show them, a shared one marked as a tie: 1, T-2, T-2, 4
    (``positionLabels`` in standings.js), so a shared number reads as a tie in the standings, not a seed."""
    return [f"T-{p}" if positions.count(p) > 1 else str(p) for p in positions]


def _pct_or_half(t: dict) -> float:
    """Region winning percentage, with a team that hasn't played counting as .500."""
    pct = _win_pct(t["record"])
    return 0.5 if pct is None else pct


def _region_record(t: dict) -> str:
    """A team's region record, "4–0"."""
    r = t["record"]
    return record_text(r["region_wins"], r["region_losses"], r.get("region_ties") or 0)


def render_region_card(clazz: int, region: int, payload: dict, stamp: str, mode: str) -> Image.Image:
    """A region's card: name, headline sentence, the standings with seeding and playoff odds, provenance.

    The table is the page's: same order, same tied positions, 1st-4th and
    playoff odds in the odds ramp. Every team that fits is shown (all of them
    unless a three-line headline leaves room for fewer).

    *payload* is the API's region standings response (``/standings/{class}/{region}``).
    """
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = smooth_draw(img)
    draw.text((PAD, PAD + 58), f"Region {region}-{clazz}A", font=_nippo(76), fill=TEXT, anchor="ls")
    y = PAD + 58 + 12  # clear of the title's descenders ("Region")
    headline = payload.get("headline")
    lines = wrap(draw, headline, _inter(32, 600), WIDTH - 2 * PAD, 3) if headline else []
    for line in lines:
        y += 42
        draw.text((PAD, y), line, font=_inter(32, 600), fill=TEXT, anchor="ls")
    ordered = display_order(payload.get("teams") or [])
    positions = position_labels(standing_positions(ordered))
    top = y + 40
    space = _TABLE_BOTTOM - (top + 14)
    fits = max(1, int(space // 40))
    shown = ordered[:fits]
    row_h = min(52, space / max(1, len(shown)))
    rows = [
        (
            positions[i],
            t["school"],
            _region_record(t),
            [mode_odds(t, k, mode) for k in ("p1", "p2", "p3", "p4", "p_playoffs")],
        )
        for i, t in enumerate(shown)
    ]
    _table(
        draw,
        top,
        rows,
        "REGION",
        ["1ST", "2ND", "3RD", "4TH", "PLAYOFFS"],
        PAD + 56,  # room for a tied position, "T-2"
        row_h,
        [88, 88, 88, 88, 116],
        gap=8,
    )
    _footer(img, stamp)
    return img


def render_class_card(clazz: int, payload: dict, stamp: str, mode: str) -> Image.Image:
    """A class's card: every region's leader and its odds of winning the region.

    *payload* is the API's class standings response (``/standings/{class}``).
    """
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = smooth_draw(img)
    draw.text((PAD, PAD + 58), f"Class {clazz}A", font=_nippo(76), fill=TEXT, anchor="ls")
    regions = sorted(payload.get("regions") or [], key=lambda r: r["region"])
    leaders = [(r["region"], display_order(r["teams"])[0]) for r in regions if r.get("teams")]
    y = PAD + 58
    if len(leaders) <= 4:
        draw.text((PAD, y + 50), "Region leaders", font=_inter(34, 600), fill=TEXT_2, anchor="ls")
        y += 50
    rows = [
        (
            f"R{region}",
            t["school"],
            _region_record(t),
            mode_odds(t, "p1", mode),
        )
        for region, t in leaders[:8]
    ]
    if len(rows) > 4:
        _class_table(draw, y + 40, rows)  # eight regions: two columns of four
    else:
        _table(draw, y + 46, [(*r[:3], [r[3]]) for r in rows], "REGION", ["WINS REGION"], PAD + 56)
    _footer(img, stamp)
    return img


def _class_table(draw, top: float, rows: list[tuple[str, str, str, float]]) -> None:
    """Eight region leaders in two columns of four."""
    small = _nippo(17)
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


# ------------------------------------------------------------------ teams

LOSS = "#F87171"  # a loss's "L" on a dark card: red-400, which reads on it (the site's #B91C1C doesn't)
CLINCHED = "#66DDB5"  # --brand-400, the clinched badge's color in the dark theme

_ROUND_TITLES = {
    "second_round": "Second Round",
    "quarterfinals": "Quarterfinals",
    "semifinals": "Semifinals",
    "finals": "Championship Game",
}


def slugify(name: str) -> str:
    """A team's URL slug, as the site makes it (``slugify`` in routes.js): "D'Iberville" -> "diberville"."""
    text = unicodedata.normalize("NFD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"['’.]", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _certain(p: float | None) -> bool:
    """Whether a probability is a certainty (within float noise of 1)."""
    return p is not None and p >= 1 - _EPS


def playoff_path(team: dict, mode: str, clazz: int) -> list[tuple[str, str, float | None]]:
    """A team's chance of reaching each playoff round: [(key, label, p)], as the page's playoff path.

    5A-7A have no second round. Empty when the snapshot has no bracket odds.
    """
    b = team.get("bracket_odds")
    if not b:
        return []
    w = "_weighted" if mode == "projected" else ""
    rounds = [
        ("second_round", "SECOND ROUND"),
        ("quarterfinals", "QUARTERFINALS"),
        ("semifinals", "SEMIFINALS"),
        ("finals", "CHAMPIONSHIP GAME"),
        ("champion", "CHAMPIONS"),
    ]
    return [(k, label, b.get(f"{k}{w}")) for k, label in rounds if not (k == "second_round" and clazz >= 5)]


def team_status(team: dict, clazz: int) -> tuple[str, str] | None:
    """The page's status badge for a team: (kind, label), e.g. ("clinched", "Clinched #1"); None without one.

    Mirrors ``teamStatuses`` / ``playoffStatus`` in the site's JavaScript.
    """
    odds = team["odds"]
    if _certain(odds.get("p_playoffs")):
        path = playoff_path(team, "tossup", clazz)
        if path:
            if _certain(path[-1][2]):
                return ("champion", "State Champion")
            reached = [k for k, _, p in path[:-1] if _certain(p)]
            keys = [k for k, _, _ in path]
            if reached:
                last = reached[-1]
                nxt = path[keys.index(last) + 1][2]
                if nxt is not None and nxt <= _EPS:
                    return ("eliminated", f"Lost in {_ROUND_TITLES[last]}")
                return ("clinched", f"Advanced to {_ROUND_TITLES[last]}")
            if path[0][2] is not None and path[0][2] <= _EPS:
                return ("eliminated", "Lost in First Round")
    if team.get("eliminated"):
        return ("eliminated", "Eliminated")
    seed = next((s for s in (1, 2, 3, 4) if _certain(odds.get(f"p{s}"))), None)
    if seed:
        return ("clinched", f"Clinched #{seed}")
    if team.get("clinched"):
        return ("clinched", "Clinched")
    return None


def _records(team: dict) -> tuple[str, str]:
    """A team's overall and region records: ("5–1", "1–0")."""
    r = team["record"]
    return record_text(r["wins"], r["losses"], r.get("ties") or 0), _region_record(team)


def team_title(team: dict, clazz: int, region: int) -> str:
    """A team link's title: "Raleigh in the Region 6-3A playoff race — Mississippi High School Football"."""
    return f"{team['school']} in the Region {region}-{clazz}A playoff race — {SITE_NAME}"


def team_description(team: dict, clazz: int, region: int, mode: str) -> str:
    """One line of the team's numbers, for the link preview.

    "Raleigh (5–1, 1–0 in Region 6-3A), Projected odds: 39% to win the region, >99% to make the
    playoffs, 4% to win the state championship." Locked and finished outcomes are stated as facts; a
    line with a percentage names its odds mode up front, where trimming the line can't drop it.
    """
    overall, in_region = _records(team)
    name = f"{team['school']} ({overall}, {in_region} in Region {region}-{clazz}A)"
    status = team_status(team, clazz)
    if status and status[0] == "champion":
        return f"{name}: {clazz}A state champion."
    if status and status[1].startswith("Lost in"):
        return f"{name}: lost in the {status[1].removeprefix('Lost in ').lower()}."
    if status and status[1] == "Eliminated":
        return f"{name}: out of the playoff race."
    odds = team["odds"]
    parts = []
    seed = next((s for s in (1, 2, 3, 4) if _certain(odds.get(f"p{s}"))), None)
    if seed:
        parts.append(f"locked in as the #{seed} seed")
    else:
        p1 = mode_odds(team, "p1", mode)
        if p1 > _EPS:  # a team that can't win the region doesn't lead with "0% to win the region"
            parts.append(f"{format_pct(p1)} to win the region")
        playoffs = mode_odds(team, "p_playoffs", mode)
        parts.append("in the playoffs" if _certain(playoffs) else f"{format_pct(playoffs)} to make the playoffs")
    path = playoff_path(team, mode, clazz)
    if path and path[-1][2] is not None:
        parts.append(f"{format_pct(path[-1][2])} to win the state championship")
    if any("%" in p for p in parts):
        name = f"{name}, {_mode_name(mode)}"
    if len(parts) > 1:
        return f"{name}: {', '.join(parts[:-1])}, {parts[-1]}."
    return f"{name}: {parts[0]}."


def _mode_name(mode: str) -> str:
    """The odds mode, as a preview names it."""
    return "Projected odds" if mode == "projected" else "Toss-up odds"


def _pill_row(draw: ImageDraw.ImageDraw, top: float, label: str, cells: list[tuple[str, float | None]]) -> None:
    """A section of large odds cells spanning the card: its title in Nippo, column headers, pills.

    *top* is the title's baseline; the row ends about 95px below it.
    """
    small = _nippo(17)
    draw.text((PAD, top), label, font=_nippo(30), fill=TEXT, anchor="ls")
    gap = 14
    width = (WIDTH - 2 * PAD - gap * (len(cells) - 1)) / len(cells)
    # Full round names ("CHAMPIONSHIP GAME") over five columns: step the
    # headers down a size rather than abbreviate them.
    header_font, tracking = small, 1.6
    if max(_tracked_width(draw, h, small, 1.6) for h, _ in cells) > width - 16:
        header_font, tracking = _nippo(15), 0.8
    for i, (header, p) in enumerate(cells):
        right = PAD + (i + 1) * width + i * gap
        _tracked(draw, (right, top + 34), header, header_font, TEXT_2, tracking, anchor="rs")
        if p is None:
            continue
        _odds_pill(draw, right, top + 34 + 36, p, width, 50, 30)


def render_team_card(
    clazz: int, region: int, team: dict, stamp: str, mode: str, look: dict | None = None
) -> Image.Image:
    """A team's card: name (and helmet, from *look*, its ``/teams`` entry), records and status, seeding odds,
    and its odds of reaching each playoff round.

    *team* is one entry of the API's region standings response.
    """
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = smooth_draw(img)
    _breadcrumb(draw, PAD, PAD + 18, [f"Class {clazz}A", f"Region {region}-{clazz}A"], 22)
    _school_title(img, draw, PAD + 104, team["school"], _nippo(76), look)
    overall, in_region = _records(team)
    line_font = _inter(30, 600)
    x = PAD
    y = PAD + 146
    for text, color in [(f"{overall} overall", TEXT), (" · ", TEXT_2), (f"{in_region} in region", TEXT)]:
        draw.text((x, y), text, font=line_font, fill=color, anchor="ls")
        x += draw.textlength(text, font=line_font)
    status = team_status(team, clazz)
    if status:
        draw.text((x, y), " · ", font=line_font, fill=TEXT_2, anchor="ls")
        x += draw.textlength(" · ", font=line_font)
        draw.text(
            (x, y), status[1], font=line_font, fill=CLINCHED if status[0] != "eliminated" else TEXT_2, anchor="ls"
        )
    _pill_row(
        draw,
        PAD + 206,
        "Seeding odds",
        [
            (h, mode_odds(team, k, mode))
            for h, k in zip(
                ("1ST", "2ND", "3RD", "4TH", "MAKES PLAYOFFS"), ("p1", "p2", "p3", "p4", "p_playoffs"), strict=True
            )
        ],
    )
    path = playoff_path(team, mode, clazz)
    if path:
        _pill_row(draw, PAD + 340, "Chance of reaching each round", [(label, p) for _, label, p in path])
    _footer(img, stamp)
    return img


# ---------------------------------------------------------------- brackets


def bracket_title(clazz: int, season: int | None = None) -> str:
    """The bracket page's title, as the app sets it; with *season*, for a link to that season's bracket."""
    return f"{f'{season} ' if season else ''}Class {clazz}A playoff bracket — {SITE_NAME}"


def _bracket_odds(team: dict, key: str, mode: str) -> float:
    """One of a team's round-reach odds (``semifinals``, ``finals``, ``champion``) in the odds mode."""
    b = team.get("bracket_odds") or {}
    w = b.get(f"{key}_weighted")
    return (w if mode == "projected" and w is not None else b.get(key)) or 0.0


def bracket_favorites(teams: list[dict], mode: str) -> list[dict]:
    """Playoff teams, likeliest champion first (then likeliest to reach the final, then the semifinals)."""
    alive = [t for t in teams if t.get("bracket_odds") and mode_odds(t, "p_playoffs", mode) > _EPS]
    return sorted(
        alive,
        key=lambda t: tuple(-_bracket_odds(t, k, mode) for k in ("champion", "finals", "semifinals")),
    )


def bracket_description(clazz: int, favorites: list[dict], mode: str) -> str:
    """The bracket's link-preview line: the favorites' title odds, or the champion once there is one."""
    if favorites and _certain(_bracket_odds(favorites[0], "champion", "tossup")):
        return f"{favorites[0]['school']} won the Class {clazz}A state championship."
    if not favorites:
        return f"Who might play whom in the Class {clazz}A playoffs, and where."
    top = favorites[0]
    text = (
        f"{_mode_name(mode)}: {top['school']} leads the Class {clazz}A bracket at "
        f"{format_pct(_bracket_odds(top, 'champion', mode))} to win the state championship"
    )
    chasers = [f"{t['school']} ({format_pct(_bracket_odds(t, 'champion', mode))})" for t in favorites[1:3]]
    if chasers:
        text += f", ahead of {' and '.join(chasers)}"
    return f"{text}."


def past_bracket_description(clazz: int, season: int, results: dict) -> str:
    """A past season's bracket link preview line: who won it, from the final's result."""
    winner = (results.get("final") or {}).get("winner")
    if winner:
        return f"{winner} won the {season} Class {clazz}A state championship."
    return f"The {season} Class {clazz}A playoff bracket."


def _pick(obj: dict, key: str, mode: str) -> float | None:
    """A matchups-payload value in the odds mode, falling back to Toss-up (``pick`` in bracket.js)."""
    w = obj.get(f"{key}_weighted")
    return w if mode == "projected" and w is not None else obj.get(key)


def team_road(games: list[dict], team: str, mode: str, results: dict | None = None) -> list[dict]:
    """A team's road through the bracket, one entry per round it played or can still reach.

    From the bracket matchups payload (``/bracket/matchups``), as the bracket
    page computes it: for each round, the chance the team plays in it (from
    either side of any game), its likeliest opponent there with the chance of
    that exact game and of facing them if the team gets there, and who'd host:
    ``{round, reach, opponent, p_matchup, p_if_there, hosts, p_team_hosts}``
    where hosts is "team", "opponent", "split" or "neutral", and ``set`` when that game is sure to be
    the one (both its teams in it, not yet played). A round the team has played (in
    *results*, played games by id: ``static_pages.layout_results``) has ``played``: ``{won, opponent,
    score_for, score_against}`` (the scores None when not on record) in place of the odds.
    """
    played_in: dict[str, dict] = {}
    for g in games:
        r = (results or {}).get(g["id"])
        if r and team in (r["winner"], r["loser"]):
            won = r["winner"] == team
            played_in[g["round"]] = {
                "won": won,
                "opponent": r["loser"] if won else r["winner"],
                "score_for": r["winner_score"] if won else r["loser_score"],
                "score_against": r["loser_score"] if won else r["winner_score"],
            }
    by_round: dict[str, dict] = {}
    order: list[str] = []
    for g in games:
        name = g["round"]
        if name not in by_round:
            by_round[name] = {"reach": 0.0, "opponents": {}}
            order.append(name)
        entry = by_round[name]
        for side in (g["side_a"], g["side_b"]):
            o = next((x for x in side["occupants"] if x["team"] == team), None)
            if o:
                entry["reach"] += _pick(o, "p_reach", mode) or 0.0
        for m in g.get("matchups") or []:
            if team not in (m["team_a"], m["team_b"]):
                continue
            p = _pick(m, "p_matchup", mode) or 0.0
            host_a = _pick(m, "p_host_a", mode)
            opponent = m["team_b"] if m["team_a"] == team else m["team_a"]
            row = entry["opponents"].setdefault(opponent, {"p": 0.0, "host": 0.0, "neutral": False})
            row["p"] += p
            if host_a is None:
                row["neutral"] = True
            else:
                row["host"] += p * (host_a if m["team_a"] == team else 1 - host_a)
    road = []
    for name in order:
        entry = by_round[name]
        if name in played_in:
            road.append(
                {
                    "round": name,
                    "reach": 1.0,
                    "opponent": played_in[name]["opponent"],
                    "p_matchup": None,
                    "p_if_there": None,
                    "hosts": None,
                    "p_team_hosts": None,
                    "played": played_in[name],
                }
            )
            if not played_in[name]["won"]:
                break  # out: no round after a loss
            continue
        reach = min(1.0, entry["reach"])
        if reach <= _EPS:
            continue
        step = {
            "round": name,
            "reach": reach,
            "opponent": None,
            "p_matchup": None,
            "p_if_there": None,
            "hosts": None,
            "p_team_hosts": None,
            "played": None,
            "set": False,
        }
        if entry["opponents"]:
            opponent, row = max(entry["opponents"].items(), key=lambda kv: (kv[1]["p"], kv[0]))
            p_hosts = None if row["neutral"] else row["host"] / row["p"] if row["p"] > _EPS else None
            if p_hosts is None:
                hosts = "neutral"
            elif p_hosts >= 1 - _EPS:  # the host only when it's certain; anything short of it is a split
                hosts = "team"
            elif p_hosts <= _EPS:
                hosts = "opponent"
            else:
                hosts = "split"
            step.update(
                opponent=opponent, p_matchup=row["p"], p_if_there=row["p"] / reach, hosts=hosts, p_team_hosts=p_hosts
            )
            # Both teams in it and not yet played: the game is set, not likely.
            step["set"] = reach >= 1 - _EPS and row["p"] >= 1 - _EPS
        road.append(step)
    return road


def team_bracket_title(team: str, clazz: int) -> str:
    """A team link on the bracket page: "Raleigh's path in the Class 3A bracket — …"."""
    return f"{team}’s path in the Class {clazz}A bracket — {SITE_NAME}"


def _result_text(step: dict) -> str:
    """A round played, in a line of them: "W 49–0 vs Amory", "L 26–35 to Kosciusko" (the score, opponent
    left out when not on record)."""
    played = step["played"]
    parts = ["W" if played["won"] else "L"]
    if played["score_for"] is not None and played["score_against"] is not None:
        parts.append(f"{played['score_for']}–{played['score_against']}")
    if played["opponent"]:
        parts.append(f"{'vs' if played['won'] else 'to'} {played['opponent']}")
    return " ".join(parts)


def team_bracket_description(team: str, road: list[dict], champion: float | None, mode: str) -> str:
    """ "Raleigh's likeliest opponents (Projected): First Round vs Tylertown, Second Round at Hazlehurst, …;
    4% to win…", after the rounds it's played: "Raleigh beat Tylertown 28–14 in the First Round; …"."""
    results = []
    out = False
    for step in road:
        played = step.get("played")
        if not played:
            continue
        out = out or not played["won"]
        score = (
            f" {played['score_for']}–{played['score_against']}"
            if played["score_for"] is not None and played["score_against"] is not None
            else ""
        )
        if played["opponent"]:
            results.append(
                f"{'beat' if played['won'] else 'lost to'} {played['opponent']}{score} in the {step['round']}"
            )
        else:
            results.append(f"{'won' if played['won'] else 'lost'}{score} in the {step['round']}")
    nxt = None
    stops = []
    for step in road:
        if step.get("played") or not step["opponent"]:
            continue
        joiner = "at" if step["hosts"] == "opponent" else "vs"
        if step.get("set"):
            nxt = f"next game: {step['round']} {joiner} {step['opponent']}"
        elif step["round"] != "Championship Game":
            stops.append(f"{step['round']} {joiner} {step['opponent']}")
    label = "Projected" if mode == "projected" else "Toss-up"
    parts = []
    if results:
        listed = results[0] if len(results) == 1 else f"{', '.join(results[:-1])} and {results[-1]}"
        parts.append(f"{team} {listed}")
    if nxt:
        parts.append(nxt if results else f"{team}’s {nxt}")
    if stops:
        opponents = "likeliest opponent" + ("s" if len(stops) > 1 else "")
        parts.append(f"{opponents if results or nxt else f'{team}’s {opponents}'} ({label}): {', '.join(stops[:3])}")
    elif not results and not nxt:
        parts.append(f"{team}’s road through the bracket ({label})")
    if champion is not None and not out:
        parts.append(f"{format_pct(champion)} to win the state championship")
    return f"{'; '.join(parts)}."


def render_bracket_card(
    clazz: int, favorites: list[dict], regions: dict[str, int], stamp: str, mode: str
) -> Image.Image:
    """A class bracket's card: the favorites and their odds of reaching the semifinals, the final, and winning it all.

    *regions* maps each school to its region, for the sub-label.
    """
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = smooth_draw(img)
    draw.text((PAD, PAD + 58), f"Class {clazz}A Bracket", font=_nippo(76), fill=TEXT, anchor="ls")
    champion = favorites[0] if favorites and _certain(_bracket_odds(favorites[0], "champion", "tossup")) else None
    line = f"{champion['school']} won the state championship" if champion else "Who’s likeliest to win it all"
    draw.text((PAD, PAD + 108), line, font=_inter(32, 600), fill=TEXT_2, anchor="ls")
    rows = [
        (
            str(i + 1),
            t["school"],
            f"Region {regions.get(t['school'], '?')}",
            [_bracket_odds(t, k, mode) for k in ("semifinals", "finals", "champion")],
        )
        for i, t in enumerate(favorites[:6])
    ]
    top = PAD + 108 + 46
    row_h = min(52, (_TABLE_BOTTOM - (top + 14)) / max(1, len(rows)))
    _table(
        draw,
        top,
        rows,
        "",
        ["REACH SEMIFINALS", "REACH CHAMPIONSHIP", "WIN CHAMPIONSHIP"],
        PAD + 44,
        row_h,
        [176, 176, 176],
        gap=16,
    )
    _footer(img, stamp)
    return img


def render_team_bracket_card(
    clazz: int,
    region: int | None,
    team: dict,
    road: list[dict],
    stamp: str,
    mode: str,
    venue: dict | None = None,
    look: dict | None = None,
) -> Image.Image:
    """A team's road through the bracket: each round played, its result; each round to come, its chance,
    likeliest opponent with the chance it's them if the team gets there, and who'd host, or for the
    championship game where it's played (*venue*, the API's ``/championships`` location, when it's on
    record)."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = smooth_draw(img)
    kicker = f"CLASS {clazz}A BRACKET" + (f" · REGION {region}-{clazz}A" if region else "")
    _tracked(draw, (PAD, PAD + 14), kicker, _nippo(19), TEXT_2, 2)
    _school_title(img, draw, PAD + 84, team["school"], _nippo(64), look)
    status = team_status(team, clazz)
    champion = _bracket_odds(team, "champion", mode) if team.get("bracket_odds") else None
    parts = [(status[1], CLINCHED if status[0] != "eliminated" else TEXT_2)] if status else []
    if champion is not None and not (status and status[0] in ("champion", "eliminated")):
        parts.append((f"{format_pct(champion)} to win the state championship", TEXT))
    x, y = PAD, PAD + 126
    line_font = _inter(28, 600)
    for i, (text, color) in enumerate(parts):
        if i:
            draw.text((x, y), " · ", font=line_font, fill=TEXT_2, anchor="ls")
            x += draw.textlength(" · ", font=line_font)
        draw.text((x, y), text, font=line_font, fill=color, anchor="ls")
        x += draw.textlength(text, font=line_font)

    small = _nippo(17)
    top = PAD + 174
    right = WIDTH - PAD
    pill_w = 110
    reach_right = PAD + 272 + pill_w  # room for "Championship Game"
    opp_x = reach_right + 36
    # Rounds played show their result; rounds to come, odds. With both, the results go on a line of their
    # own above the table, so each of its columns holds one kind of number.
    played = [step for step in road if step.get("played")]
    future = [step for step in road if not step.get("played")]
    to_come = bool(future)
    if played and future:
        line = " · ".join(_result_text(step) for step in played)
        draw.text(
            (PAD, top - 4),
            fit(draw, line, _inter(22, 500), right - PAD),
            font=_inter(22, 500),
            fill=TEXT_2,
            anchor="ls",
        )
        top += 44
    steps = (future or played)[:5]
    _tracked(draw, (reach_right, top), "CHANCE TO PLAY" if to_come else "RESULT", small, TEXT_2, 1.6, anchor="rs")
    _tracked(draw, (opp_x, top), "LIKELIEST OPPONENT" if to_come else "OPPONENT", small, TEXT_2, 1.6)
    _tracked(draw, (right, top), "CHANCE IT’S THEM" if to_come else "SCORE", small, TEXT_2, 1.6, anchor="rs")
    row_h = min(68, (_TABLE_BOTTOM - (top + 14)) / max(1, len(steps)))
    pill_h = min(44, row_h - 16)
    y = top + 14
    for step in steps:
        draw.line((PAD, y, right, y), fill=RULE, width=1)
        middle = y + row_h / 2
        draw.text((PAD, middle), step["round"], font=_inter(25, 600), fill=TEXT, anchor="lm")
        if played := step.get("played"):
            won = played["won"]
            draw.text(
                (reach_right - 12, middle),
                "W" if won else "L",
                font=_inter(30, 700),
                fill=CLINCHED if won else LOSS,
                anchor="rm",
            )
            opponent = played["opponent"]
            if opponent:
                lead = "Beat" if won else "Lost to"
                lead_font = _inter(21, 500)
                draw.text((opp_x, middle), lead, font=lead_font, fill=TEXT_2, anchor="lm")
                name_x = opp_x + draw.textlength(lead, font=lead_font) + 10
                opp_font = _inter(26, 600)
                draw.text(
                    (name_x, middle),
                    fit(draw, opponent, opp_font, right - pill_w - 32 - name_x),
                    font=opp_font,
                    fill=TEXT,
                    anchor="lm",
                )
            else:
                draw.text((opp_x, middle), "Won" if won else "Lost", font=_inter(26, 600), fill=TEXT, anchor="lm")
            if played["score_for"] is not None and played["score_against"] is not None:
                score = f"{played['score_for']}–{played['score_against']}"
                draw.text((right - 12, middle), score, font=_inter(26, 600), fill=TEXT, anchor="rm")
            y += row_h
            continue
        if step.get("set"):
            # Set: both teams in it. A lock, as the bracket page marks a locked-in team.
            font = _inter(26, 700)
            draw.text((reach_right - 12, middle), "Next", font=font, fill=TEXT, anchor="rm")
            _lock(draw, reach_right - 12 - draw.textlength("Next", font=font) - 30, middle, 24, CLINCHED)
        else:
            _odds_pill(draw, reach_right, middle, step["reach"], pill_w, pill_h, 26)
        if step["opponent"]:
            joiner = "at" if step["hosts"] == "opponent" else "vs"
            where = {
                "team": "Home",
                "opponent": "Away",
                "neutral": (venue or {}).get("name") or "Neutral site",
                "split": (
                    f"{format_pct(step['p_team_hosts'])} chance at home"
                    if step["p_team_hosts"] >= 0.5
                    else f"{format_pct(1 - step['p_team_hosts'])} chance away"
                )
                if step["p_team_hosts"] is not None
                else "",
            }[step["hosts"]]
            joiner_font = _inter(21, 500)
            draw.text((opp_x, middle - 12), joiner, font=joiner_font, fill=TEXT_2, anchor="lm")
            name_x = opp_x + draw.textlength(joiner, font=joiner_font) + 10
            opp_font = _inter(26, 600)
            opp_name = fit(draw, step["opponent"], opp_font, right - pill_w - 32 - name_x)
            draw.text((name_x, middle - 12), opp_name, font=opp_font, fill=TEXT, anchor="lm")
            draw.text((opp_x, middle + 17), where, font=_inter(19, 500), fill=TEXT_2, anchor="lm")
            if not step.get("set"):
                _odds_pill(draw, right, middle, step["p_if_there"], pill_w, pill_h, 26)
        else:
            # Every pairing here is under the API's 0.5% listing floor.
            draw.text((opp_x, middle - 12), "Many possible opponents", font=_inter(24, 600), fill=TEXT_2, anchor="lm")
            draw.text((opp_x, middle + 17), "Each under 0.5%", font=_inter(19, 500), fill=TEXT_2, anchor="lm")
        y += row_h
    _footer(img, stamp)
    return img


def render_site_card() -> Image.Image:
    """The fallback card for pages without their own, laid out like the front page's top: "Welcome to"
    over the site's name in capitals and what it does, its helmet at the right, its address below."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = smooth_draw(img)
    art = _helmet_art(380)
    img.paste(art, (WIDTH - PAD + 20 - art.width, (HEIGHT - art.height) // 2 - 10), art)
    room = WIDTH - 2 * PAD - art.width + 10
    _tracked(draw, (PAD, PAD + 30), "WELCOME TO", _nippo(24), TEXT, 1.5)
    title = _nippo(64)
    y = PAD + 100
    for line in wrap(draw, SITE_NAME.upper(), title, room, 3):
        draw.text((PAD, y), line, font=title, fill=TEXT, anchor="ls")
        y += 68
    body = _inter(27, 500)
    y += 6
    for line in wrap(draw, SITE_DESCRIPTION, body, room - 20, 3):
        draw.text((PAD, y), line, font=body, fill=TEXT_2, anchor="ls")
        y += 38
    draw.text((PAD, HEIGHT - PAD + 8), SITE_HOST, font=_nippo(30), fill=BRAND_GREEN["dark"], anchor="ls")
    return img
