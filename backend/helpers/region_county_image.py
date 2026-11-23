"""The Counties pages as images to share: a county's MHSAA schools, its two seasons compared, its every
season, and every county shaded by its schools; and their link previews.

- ``render_county``: a 4:5 page (1080x1350 at 2x) with the county's outline as its mark (as a team's
  helmet), its name and how many schools in how many classes, a map zoomed to the county (its schools
  numbered by region, each school's region shape in its own color, the regions' other schools as
  smaller dots, the county outlined), and its schools by class.
- ``render_county_compared``: the county in two seasons side by side, and what changed between them
  (``region_pages.county_changes``, the page's own list).
- ``render_county_timeline``: the county's map every season on one image, as the class and team
  timelines (``region_timeline_image``'s grid).
- ``render_counties``: every county shaded by how many MHSAA schools it has, as on /maps/counties.
- ``render_county_card`` and ``render_counties_card``: the pages' link previews (1200x630).

Colors are the page's: each of a county's places (a region in a class) in its region's color, or the
next free one when two share a number (``region_pages.county_places``); the shades of the statewide map
mix the site's green into the page, as app.css's .county-shade--N. Pure, like the other share images.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from backend.helpers import region_map
from backend.helpers.region_map_image import (
    CARD,
    CARD_PAD,
    LIST_X,
    MAP_RIGHT,
    PAD,
    SIZE,
    _blend,
    _card,
    _Frame,
    _Page,
    _polygons,
    place,
    region_color,
    seasons_line,
)
from backend.helpers.region_pages import (
    count_shade,
    county_changes,
    county_count,
    county_places,
    county_title,
    schools_count,
)
from backend.helpers.region_timeline_image import WIDTH, _cells, _sizes, cycle_label, grid, span_line
from backend.helpers.share_cards import SITE_HOST, _inter, _nippo, fit

# The site's green (app.css --brand-700 light, --brand-400 dark) and how much of it each shade on the
# statewide map has (.county-shade--1..4; 0 is the land's own color).
BRAND = {"light": "#137252", "dark": "#66DDB5"}
SHADE_MIX = (0.0, 0.22, 0.42, 0.66, 1.0)


def shade_color(theme: str, shade: int) -> str:
    """A shade (0-4, ``count_shade``) of the statewide map in *theme*."""
    t = _Page(theme, {}, (1, 1)).t
    if shade == 0:
        return _blend(t.bg, t.text, 0.05)
    return _blend(t.bg, BRAND[theme], SHADE_MIX[shade])


def county_bounds(county: str, aspect: float, pad: float = 0.45) -> tuple[float, float, float, float]:
    """The state-grid box a map of *county* shows: the county with room around it (*pad* of its larger
    side each way), widened or heightened to *aspect* (width / height) about its middle."""
    x0, y0, x1, y1 = region_map.counties()[county].bounds
    side = max(x1 - x0, y1 - y0) * pad
    x0, y0, x1, y1 = x0 - side, y0 - side, x1 + side, y1 + side
    cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    if w / h < aspect:
        w = h * aspect
    else:
        h = w / aspect
    # Moved, where it fits, to stay over Mississippi (a county on the state line isn't left beside an
    # empty neighbor); the county stays in it, its room around it going inland.
    sx0, sy0, sx1, sy1 = region_map.state().bounds
    cx = min(max(cx, sx0 + w / 2), sx1 - w / 2) if w < sx1 - sx0 else (sx0 + sx1) / 2
    cy = min(max(cy, sy0 + h / 2), sy1 - h / 2) if h < sy1 - sy0 else (sy0 + sy1) / 2
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def draw_county_mark(page: _Page, county: str, x: float, mid: float, size: int, color: str | None = None) -> None:
    """The county's outline, *size* pixels square, its left edge at *x* and its middle at *mid*: filled
    in *color* (the site's green by default) and edged as on the page (drawn 4x and scaled down, so it's
    smooth)."""
    geom = region_map.counties()[county]
    k = 4
    big = size * k
    frame = _Frame((big * 0.06, big * 0.06, big * 0.94, big * 0.94), bounds=geom.bounds)
    layer = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    fill = color or BRAND[page.theme]
    edge = _blend(page.t.bg, page.t.text, 0.45)
    for poly in _polygons(geom):
        d.polygon(frame.ring(poly.exterior.coords), fill=fill, outline=edge, width=k)
        for hole in poly.interiors:
            d.polygon(frame.ring(hole.coords), fill=(0, 0, 0, 0))
    small = layer.resize((size, size), Image.LANCZOS)
    page.img.paste(small, (round(x), round(mid - size / 2)), small)


def _place_colors(theme: str, mine: list[dict]) -> dict[str, str]:
    """Each of the county's places ("6-3") its color in *theme*."""
    return {p["key"]: region_color(theme, p["color"]) for p in county_places(mine)}


def county_map(
    theme: str, county: str, schools: list[dict], size: tuple[int, int], label_size: int, big: float, small: float
) -> Image.Image:
    """The county's map, *size* pixels: zoomed to it, its schools' regions (their shapes from *schools*,
    every school in those classes), their schools as dots (the county's numbered and named, the others
    smaller), and the county outlined."""
    page = _Page(theme, {}, size)
    mine = [s for s in schools if s.get("county") == county]
    colors = _place_colors(theme, mine)

    def key(s: dict) -> str:
        return f"{s['class']}-{s['region']}"

    fills = []
    for c in sorted({s["class"] for s in mine}, reverse=True):
        shapes = region_map.region_shapes([s for s in schools if s["class"] == c and s["x"] is not None])
        for g, shape in shapes.items():
            if f"{c}-{g}" in colors:
                fills.append((shape, colors[f"{c}-{g}"]))
    shown = [s for s in schools if key(s) in colors and s["x"] is not None]
    away = [s for s in shown if s.get("county") != county]
    own = sorted((s for s in shown if s.get("county") == county), key=lambda s: s["school"].lower())
    dots = [(s["x"], s["y"], colors[key(s)], "", small) for s in away]
    dots += [(s["x"], s["y"], colors[key(s)], str(s["region"]), big) for s in own]
    labels = [(s["school"], len(away) + i) for i, s in enumerate(own)] if label_size else []
    frame = _Frame((0, 0, *size), bounds=county_bounds(county, size[0] / size[1]))
    line = 3 if size[0] >= 600 else 2
    page.map(
        frame,
        fills,
        dots,
        labels,
        label_size=label_size or 34,
        line=line,
        outlines=[(region_map.counties()[county], page.t.text, line * 2)],
    )
    return page.img


def _header(page: _Page, county: str, line: str) -> None:
    """The county's mark and name, and *line* under them."""
    d, t = page.d, page.t
    draw_county_mark(page, county, PAD, PAD + 62, 128)
    title = county_title(county)
    d.text(
        (PAD + 160, PAD + 104),
        fit(d, title, _nippo(124), SIZE[0] - 2 * PAD - 160),
        font=_nippo(124),
        fill=t.text,
        anchor="ls",
    )
    d.text((PAD, PAD + 196), line, font=_inter(42, 500), fill=t.text_2, anchor="ls")


def _chip(page: _Page, x: float, mid: float, color: str, number: int, size: int = 46) -> None:
    """A region's number in its color, as the page's region chips."""
    page.d.ellipse((x, mid - size / 2, x + size, mid + size / 2), fill=color)
    page.d.text((x + size / 2, mid + 1), str(number), font=_inter(round(size * 0.55), 700), fill="#FFFFFF", anchor="mm")


def render_county(county: str, seasons: list[int], schools: list[dict], theme: str) -> list[Image.Image]:
    """*county*'s MHSAA schools in *seasons* (*schools*: every school in the classes its schools are in,
    each {school, class, region, county, x, y}): its mark and name, its map and its schools by class.
    Nothing for a county with no school."""
    mine = [s for s in schools if s.get("county") == county]
    if not mine:
        return []
    page = _Page(theme, {})
    _header(page, county, f"{county_count(mine)}, {seasons_line(seasons)}")
    top, bottom = PAD + 290, SIZE[1] - PAD - 110
    box = (PAD - 20, top, MAP_RIGHT, bottom)
    page.img.paste(county_map(theme, county, schools, (box[2] - box[0], box[3] - box[1]), 32, 22, 11), box[:2])
    page.d = ImageDraw.Draw(page.img)
    d, t = page.d, page.t
    colors = _place_colors(theme, mine)
    classes = sorted({s["class"] for s in mine}, reverse=True)
    # Room for every class's heading and every school's two lines; tighter rows when it's a crowd.
    row = min(104, (bottom - top - 30 - 90 * len(classes)) / len(mine))
    y = top + 30
    width = SIZE[0] - PAD - LIST_X - 64
    for c in classes:
        page.label(LIST_X, y + 34, f"Class {c}A")
        y += 90
        for s in sorted((s for s in mine if s["class"] == c), key=lambda s: (s["region"], s["school"].lower())):
            _chip(page, LIST_X, y + row * 0.32, colors[f"{c}-{s['region']}"], s["region"])
            name = fit(d, s["school"], _inter(40, 600), width)
            d.text((LIST_X + 64, y + row * 0.32 + 14), name, font=_inter(40, 600), fill=t.text, anchor="ls")
            where = f"{place(s)}" + (f" · {s['city']}" if s.get("city") else "")
            d.text(
                (LIST_X + 64, y + row * 0.32 + 56),
                fit(d, where, _inter(32, 500), width),
                font=_inter(32, 500),
                fill=t.text_2,
                anchor="ls",
            )
            y += row
        y += 10
    page.footer()
    return [page.img]


def render_county_compared(county: str, older: dict, newer: dict, theme: str) -> list[Image.Image]:
    """*county* in two seasons side by side (*older* and *newer*: {label, seasons, schools}, as
    ``render_county`` takes them), and what changed: its schools new to it, gone and changed. Nothing
    when it had no school in either."""
    a = {"label": older["label"], "season": older["seasons"][0], "schools": older["schools"]}
    b = {"label": newer["label"], "season": newer["seasons"][0], "schools": newer["schools"]}
    changes = county_changes(a, b, county)
    mine = [[s for s in x["schools"] if s.get("county") == county] for x in (older, newer)]
    if changes is None or not any(mine):
        return []
    page = _Page(theme, {})
    _header(page, county, f"{older['label']} vs. {newer['label']}")
    d, t = page.d, page.t
    gap = 60
    w = round((SIZE[0] - 2 * PAD - gap) / 2)
    top = PAD + 260
    groups = changes["groups"]
    # The maps as tall as the list under them leaves room for (its headings and rows, 52px each).
    lines = sum(len(groups[k]) + 1 for k in ("in", "out", "moved") if groups[k]) or 1
    map_h = max(900, min(1500, SIZE[1] - PAD - 110 - (top + 130) - 80 - lines * 56 - 40))
    for i, (side, rows) in enumerate(zip((older, newer), mine, strict=True)):
        x0 = PAD + i * (w + gap)
        d.text((x0, top + 50), side["label"], font=_nippo(60), fill=t.text, anchor="ls")
        d.text((x0, top + 100), schools_count(len(rows)), font=_inter(36, 500), fill=t.text_2, anchor="ls")
        if rows:
            page.img.paste(county_map(theme, county, side["schools"], (w, map_h), 28, 17, 9), (x0, top + 130))
        else:
            d.text((x0, top + 200), "No MHSAA school", font=_inter(36, 500), fill=t.text_2, anchor="ls")
    page.d = ImageDraw.Draw(page.img)
    d = page.d
    detail = {
        "in": lambda r: f"{place(r['newer'])} · {r['note']}",
        "out": lambda r: f"{place(r['older'])} in {older['label']} · {r['note']}",
        "moved": lambda r: f"{place(r['older'])} to {place(r['newer'])}",  # (the fonts have no arrow)
    }
    titles = {"in": f"In {newer['label']} only", "out": f"In {older['label']} only", "moved": "Changed class or region"}
    y = top + 130 + map_h + 80
    bottom = SIZE[1] - PAD - 110
    shown = [(k, r) for k in ("in", "out", "moved") for r in groups[k]]
    if not shown:
        d.text(
            (PAD, y),
            "Nothing changed: every school is in the same class and region in both.",
            font=_inter(36, 500),
            fill=t.text_2,
            anchor="ls",
        )
    room = int((bottom - y) // 52) - sum(1 for k in ("in", "out", "moved") if groups[k])
    left = len(shown)
    for k in ("in", "out", "moved"):
        if not groups[k] or room <= 0:
            continue
        page.label(PAD, y, f"{titles[k]} ({len(groups[k])})")
        y += 58
        for r in groups[k]:
            if room <= 1 and left > 1:
                d.text((PAD, y), f"and {left} more", font=_inter(32, 500), fill=t.text_2, anchor="ls")
                y += 52
                room = 0
                break
            name_w = d.textlength(r["school"], font=_inter(36, 600))
            d.text((PAD, y), r["school"], font=_inter(36, 600), fill=t.text, anchor="ls")
            room_for = SIZE[0] - 2 * PAD - name_w - 30
            d.text(
                (PAD + name_w + 24, y),
                fit(d, detail[k](r), _inter(32, 500), room_for),
                font=_inter(32, 500),
                fill=t.text_2,
                anchor="ls",
            )
            y += 52
            room -= 1
            left -= 1
        y += 20
    page.footer()
    return [page.img]


def render_county_timeline(county: str, cycles: list[dict], theme: str) -> list[Image.Image]:
    """*county*'s map every season (*cycles*: [{seasons, schools}], oldest first, *schools* as
    ``render_county`` takes them) on one image, in the class and team timelines' grid. The seasons
    before its first school and after its last are left out; nothing for a county that never had one."""
    have = [i for i, c in enumerate(cycles) if any(s.get("county") == county for s in c["schools"])]
    if not have:
        return []
    cycles = cycles[have[0] : have[-1] + 1]
    probe_big, _, probe_line = _sizes(grid(len(cycles), 120)[1])
    caption = 24 + probe_big + 12 + probe_line
    _, cell, height = grid(len(cycles), caption)
    page = _Page(theme, {}, (WIDTH, height))
    d, t = page.d, page.t
    draw_county_mark(page, county, PAD, PAD + 62, 128)
    d.text(
        (PAD + 160, PAD + 104),
        fit(d, county_title(county), _nippo(124), WIDTH - 2 * PAD - 160),
        font=_nippo(124),
        fill=t.text,
        anchor="ls",
    )
    d.text(
        (PAD, PAD + 176),
        f"Its MHSAA schools every season, {span_line(cycles)}",
        font=_inter(42, 500),
        fill=t.text_2,
        anchor="ls",
    )
    big, small, line_h = _sizes(cell)

    def draw_cell(cycle: dict, x: float, y: float, width: float, map_h: float) -> None:
        mine = [s for s in cycle["schools"] if s.get("county") == county]
        size = (round(width), round(map_h))
        if mine:
            r = max(6.0, width / 34)
            page.img.paste(county_map(theme, county, cycle["schools"], size, 0, r, r * 0.55), (round(x), round(y)))
        else:
            ImageDraw.Draw(page.img).rectangle((x, y, x + width, y + map_h), outline=t.rule, width=2)
        dd = ImageDraw.Draw(page.img)
        base = y + map_h + 24 + big
        dd.text((x, base), cycle_label(cycle["seasons"]), font=_nippo(big), fill=t.text, anchor="ls")
        dd.text(
            (x, base + 12 + line_h * 0.8), schools_count(len(mine)), font=_inter(small, 500), fill=t.text_2, anchor="ls"
        )

    _cells(page, cycles, caption, draw_cell)
    page.d = ImageDraw.Draw(page.img)
    page.footer()
    return [page.img]


def _counties_map(page: _Page, frame: _Frame, counts: dict[str, int]) -> None:
    """Every county filled in its shade (by its count of MHSAA schools), the state outlined."""
    t = page.t
    for name, geom in region_map.counties().items():
        fill = shade_color(page.theme, count_shade(counts.get(name, 0)))
        for poly in _polygons(geom):
            page.d.polygon(frame.ring(poly.exterior.coords), fill=fill, outline=t.bg, width=2)
    for poly in _polygons(region_map.state()):
        page.d.line(frame.ring(poly.exterior.coords), fill=_blend(t.bg, t.text, 0.6), width=4, joint="curve")


SHADE_LABELS = ("None", "1", "2", "3–4", "5 or more")


def render_counties(seasons: list[int], counts: dict[str, int], theme: str) -> list[Image.Image]:
    """Every county shaded by how many MHSAA schools it has in *seasons* (*counts*: by county name), with
    the shades' key, and the counties with the most."""
    page = _Page(theme, {})
    d, t = page.d, page.t
    d.text((PAD, PAD + 104), "MHSAA Schools by County", font=_nippo(112), fill=t.text, anchor="ls")
    d.text((PAD, PAD + 176), seasons_line(seasons), font=_inter(42, 500), fill=t.text_2, anchor="ls")
    top, bottom = PAD + 250, SIZE[1] - PAD - 260
    _counties_map(page, _Frame((PAD - 20, top, MAP_RIGHT + 80, bottom)), counts)
    # The key, along the bottom.
    y = bottom + 90
    d.text((PAD, y), "MHSAA schools in the county:", font=_inter(36, 500), fill=t.text_2, anchor="ls")
    x = PAD
    for shade, label in enumerate(SHADE_LABELS):
        y2 = y + 70
        d.rounded_rectangle(
            (x, y2 - 34, x + 40, y2 + 6), radius=6, fill=shade_color(theme, shade), outline=t.rule, width=2
        )
        d.text((x + 56, y2), label, font=_inter(36, 500), fill=t.text, anchor="ls")
        x += 56 + d.textlength(label, font=_inter(36, 500)) + 48
    # The most schools, on the right.
    most = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))[:12]
    lx = MAP_RIGHT + 160
    yy = top + 40
    page.label(lx, yy, "The most")
    yy += 76
    for name, n in most:
        d.text((lx, yy), name, font=_inter(40, 600), fill=t.text, anchor="ls")
        d.text((SIZE[0] - PAD, yy), str(n), font=_inter(40, 600), fill=t.text_2, anchor="rs")
        yy += 64
    page.footer()
    return [page.img]


def render_county_card(county: str, seasons: list[int], schools: list[dict]) -> list[Image.Image]:
    """A county page's link preview: its mark and name, its schools' count, and its map. Nothing for a
    county with no school (its page keeps the site's card)."""
    mine = [s for s in schools if s.get("county") == county]
    if not mine:
        return []
    page = _Page("dark", {}, CARD)
    d, t = page.d, page.t
    width = CARD[0] - 2 * CARD_PAD - 900
    draw_county_mark(page, county, CARD_PAD, CARD_PAD + 80, 160)
    d.text(
        (CARD_PAD, CARD_PAD + 330),
        fit(d, county_title(county), _nippo(120), width),
        font=_nippo(120),
        fill=t.text,
        anchor="ls",
    )
    d.text((CARD_PAD, CARD_PAD + 440), county_count(mine), font=_inter(58, 600), fill=t.text, anchor="ls")
    d.text((CARD_PAD, CARD_PAD + 520), seasons_line(seasons), font=_inter(50, 500), fill=t.text_2, anchor="ls")
    box = (CARD[0] - CARD_PAD - 760, 70, CARD[0] - CARD_PAD + 20, CARD[1] - 70)
    page.img.paste(county_map("dark", county, schools, (box[2] - box[0], box[3] - box[1]), 34, 22, 11), box[:2])
    page.d = ImageDraw.Draw(page.img)
    page.d.text((CARD_PAD, CARD[1] - CARD_PAD + 16), SITE_HOST, font=_inter(52, 600), fill=t.text, anchor="ls")
    return _card(page)


def render_counties_card(seasons: list[int], counts: dict[str, int]) -> list[Image.Image]:
    """The statewide page's link preview: its title and seasons, and every county shaded."""
    page = _Page("dark", {}, CARD)
    d, t = page.d, page.t
    d.text((CARD_PAD, CARD_PAD + 140), "MHSAA Schools", font=_nippo(140), fill=t.text, anchor="ls")
    d.text((CARD_PAD, CARD_PAD + 290), "by County", font=_nippo(140), fill=t.text, anchor="ls")
    d.text((CARD_PAD, CARD_PAD + 400), seasons_line(seasons), font=_inter(56, 600), fill=t.text_2, anchor="ls")
    _counties_map(page, _Frame((CARD[0] - CARD_PAD - 760, 70, CARD[0] - CARD_PAD + 20, CARD[1] - 70)), counts)
    d.text((CARD_PAD, CARD[1] - CARD_PAD + 16), SITE_HOST, font=_inter(52, 600), fill=t.text, anchor="ls")
    return _card(page)
