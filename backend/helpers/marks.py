"""What every image to share draws a team with: its helmet in its colors (or its initials), in the
site's two themes.

Kept apart from the pages' and images' own code (``static_pages``, ``bracket_image``), which import
from here, so that an image is redrawn only when the code it draws with changes
(``image_jobs.code_fingerprint``): a change to the page wording doesn't redraw the region maps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache

from PIL import Image, ImageDraw

from backend.helpers.color_contrast import contrast_ratio
from backend.helpers.share_cards import BG, ODDS_BG, ODDS_TEXT, RULE, TEXT, TEXT_2

DROPPED_WORDS = {"county", "high", "school", "academy"}  # as format.js's initials()
_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


def initials(name: str) -> str:
    """Fallback initials, as the app makes them: first letters of up to two significant words."""
    words = [w for w in re.split(r"[\s\-/]+", name) if w]
    significant = [w for w in words if w.lower() not in DROPPED_WORDS]
    return "".join(w[0].upper() for w in (significant or words)[:2])


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
