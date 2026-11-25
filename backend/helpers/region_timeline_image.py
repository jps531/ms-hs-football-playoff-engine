"""The Maps timeline as images to share: a class's regions, or one team's, every season on one image.

- ``render_class_timeline``: a small map of the state for each season of regions, oldest first, its
  regions' shapes and schools in each region's color, captioned with the seasons and how many schools
  and regions the class had.
- ``render_team_timeline``: the same small maps, each with the team's region (its shape, its schools,
  the team ringed) and captioned with where it was. A season before a consolidation shows every school
  merged into the team, each in its own region (``data_helpers.names_in``); a season it wasn't in a
  region says so.

Any number of seasons fit one image: the maps are laid out in a grid whose columns are chosen for the
count (``grid``), the image as tall as its rows need, so a few seasons make a short image and decades of
them a tall one. Pure, like the other share images: plain data in, one Pillow image out. The drawing is
``region_map_image``'s, so these match the other Maps images.
"""

from __future__ import annotations

import math

from PIL import Image

from backend.helpers import region_map
from backend.helpers.region_map_image import PAD, _Frame, _Page, place, region_color
from backend.helpers.region_pages import PLACE_FALLBACK
from backend.helpers.share_cards import _inter, _nippo, fit, smooth_draw

WIDTH = 2160  # 1080 wide at 2x, like the other share images; the height follows the rows
HEADER = 380  # the title and its line, above the grid
FOOTER = 220  # the site's lockup (footer), below it
COL_GAP = 40
ROW_GAP = 64
MAX_CELL = 880  # a map's widest (one or two seasons)
MIN_CELL = 230  # and its narrowest: past this, more rows rather than more columns
TARGET = 1.25  # the shape to aim for (height / width): 4:5, the other share images'


def cycle_label(seasons: list[int]) -> str:
    """ "2027–28" for a two-season cycle, "2026" for one."""
    if len(seasons) > 1:
        return f"{seasons[0]}–{seasons[-1] % 100:02d}"
    return str(seasons[0])


def span_line(cycles: list[dict]) -> str:
    """ "2025 to 2028 seasons" (or "2026 season"), the seasons *cycles* cover."""
    first, last = cycles[0]["seasons"][0], cycles[-1]["seasons"][-1]
    return f"{first} season" if first == last else f"{first} to {last} seasons"


def _state_ratio() -> float:
    """The state's height over its width."""
    x0, y0, x1, y1 = region_map.state().bounds
    return (y1 - y0) / (x1 - x0)


def grid(count: int, caption: float) -> tuple[int, float, int]:
    """The layout for *count* maps, each with *caption* pixels under it: (columns, map width, image
    height). The columns whose image comes nearest 4:5, a part-empty last row counting against them; no
    map narrower than MIN_CELL (beyond that the image grows taller instead)."""
    ratio = _state_ratio()
    inner = WIDTH - 2 * PAD
    best = None
    for cols in range(1, count + 1):
        cell = min(MAX_CELL, (inner - (cols - 1) * COL_GAP) / cols)
        if cell < MIN_CELL and cols > 1:
            break
        rows = math.ceil(count / cols)
        height = HEADER + rows * (cell * ratio + caption) + (rows - 1) * ROW_GAP + FOOTER
        empty = rows * cols - count
        score = abs(math.log(height / WIDTH / TARGET)) + 0.6 * empty / cols
        if best is None or score < best[0]:
            best = (score, cols, cell, round(height))
    _, cols, cell, height = best
    return cols, cell, height


def _cells(page: _Page, cycles: list[dict], caption: float, draw_cell) -> None:
    """Lay *cycles* out in the grid, centered, and draw each with *draw_cell(cycle, x, y, width, map_h)*."""
    cols, cell, _ = grid(len(cycles), caption)
    map_h = cell * _state_ratio()
    used = cols * cell + (cols - 1) * COL_GAP
    left = (WIDTH - used) / 2
    for i, cycle in enumerate(cycles):
        row, col = divmod(i, cols)
        x = left + col * (cell + COL_GAP)
        y = HEADER + row * (map_h + caption + ROW_GAP)
        draw_cell(cycle, x, y, cell, map_h)


def _header(page: _Page, title: str, line: str, x: float = PAD) -> None:
    d, t = page.d, page.t
    d.text((x, PAD + 104), fit(d, title, _nippo(124), WIDTH - PAD - x), font=_nippo(124), fill=t.text, anchor="ls")
    d.text((PAD, PAD + 176), line, font=_inter(42, 500), fill=t.text_2, anchor="ls")


def _sizes(cell: float) -> tuple[int, int, int]:
    """The caption's type sizes for a map *cell* wide: (seasons, details, line height)."""
    big = max(30, min(48, round(cell / 7)))
    small = max(26, min(38, round(cell / 9)))
    return big, small, round(small * 1.35)


def render_class_timeline(clazz: int, cycles: list[dict], theme: str) -> list[Image.Image]:
    """Class *clazz*'s regions over time: *cycles* oldest first, each {seasons, schools} (the class's
    schools those seasons: {school, class, region, x, y})."""
    cycles = [c for c in cycles if any(s["class"] == clazz for s in c["schools"])]
    if not cycles:
        return []

    def counts(cycle: dict) -> tuple[str, str]:
        rows = [s for s in cycle["schools"] if s["class"] == clazz]
        return f"{len(rows)} schools", f"{len({s['region'] for s in rows})} regions"

    probe = Image.new("RGB", (1, 1))
    probe_cell = grid(len(cycles), 120)[1]
    probe_big, probe_small, probe_line = _sizes(probe_cell)
    measure = smooth_draw(probe)
    widest = max(measure.textlength(", ".join(counts(c)), font=_inter(probe_small, 500)) for c in cycles)
    stacked = widest > probe_cell  # "36 schools" over "8 regions" when the two don't fit on a line
    caption = 24 + probe_big + 12 + probe_line * (2 if stacked else 1)
    _, cell, height = grid(len(cycles), caption)
    page = _Page(theme, {}, (WIDTH, height))
    _header(page, f"Class {clazz}A Football Regions", f"Every season’s regions, {span_line(cycles)}")
    big, small, line_h = _sizes(cell)

    def draw_cell(cycle: dict, x: float, y: float, width: float, map_h: float) -> None:
        rows = [s for s in cycle["schools"] if s["class"] == clazz]
        on_map = [s for s in rows if s["x"] is not None]
        shapes = region_map.region_shapes(on_map)
        r = max(4.0, width / 70)
        page.map(
            _Frame((x, y, x + width, y + map_h)),
            [(shapes[g], region_color(theme, g)) for g in sorted(shapes)],
            [
                (s["x"], s["y"], region_color(theme, s["region"]), str(s["region"]) if r >= 14 else "", r)
                for s in on_map
            ],
            line=3 if width >= 500 else 2,
        )
        d = page.d
        base = y + map_h + 24 + big
        d.text((x, base), cycle_label(cycle["seasons"]), font=_nippo(big), fill=page.t.text, anchor="ls")
        lines = counts(cycle) if stacked else [", ".join(counts(cycle))]
        for k, what in enumerate(lines):
            d.text((x, base + 12 + line_h * (0.8 + k)), what, font=_inter(small, 500), fill=page.t.text_2, anchor="ls")

    _cells(page, cycles, caption, draw_cell)
    page.footer()
    return [page.img]


def render_team_timeline(school: str, cycles: list[dict], teams: dict, theme: str) -> list[Image.Image]:
    """*school*'s regions over time: *cycles* oldest first, each {seasons, rows, schools}: *rows* the
    team's line that season (none: not in a region; several: the schools merged into it, before a
    consolidation), *schools* the schools in those rows' regions. The seasons before its first region
    and after its last are left out; one between with none says so."""
    have = [i for i, c in enumerate(cycles) if c["rows"]]
    if not have:
        return []
    cycles = cycles[have[0] : have[-1] + 1]
    lines = max(2 * len(c["rows"]) if _named(school, c["rows"]) else len(c["rows"]) or 1 for c in cycles)
    probe_big, _, probe_line = _sizes(grid(len(cycles), 120)[1])
    caption = 24 + probe_big + 12 + lines * probe_line
    _, cell, height = grid(len(cycles), caption)
    page = _Page(theme, teams, (WIDTH, height))
    page.mark(school, PAD, PAD + 62, 128)
    _header(page, school, f"Regions, {span_line(cycles)}", PAD + 160)
    big, small, line_h = _sizes(cell)
    t = page.t

    def draw_cell(cycle: dict, x: float, y: float, width: float, map_h: float) -> None:
        mine = cycle["rows"]
        r = max(5.0, width / 48)
        fills, dots, focus = [], [], set()
        colors = _place_colors(theme, mine)
        for me in mine:
            group = [
                s
                for s in cycle["schools"]
                if (s["class"], s["region"]) == (me["class"], me["region"]) and s["x"] is not None
            ]
            color = colors[me["class"], me["region"]]
            shape = region_map.region_shapes(group).get(me["region"])
            if shape is not None:
                fills.append((shape, color))
            for s in group:
                if s["school"] in {m["school"] for m in mine}:
                    focus.add(len(dots))
                dots.append((s["x"], s["y"], color, "", r))
        page.map(_Frame((x, y, x + width, y + map_h)), fills, dots, focus=focus, line=3 if width >= 500 else 2)
        d = page.d
        base = y + map_h + 24 + big
        d.text((x, base), cycle_label(cycle["seasons"]), font=_nippo(big), fill=t.text, anchor="ls")
        y_line = base + 12 + line_h * 0.8
        if not mine:
            d.text((x, y_line), "Not in a region", font=_inter(small, 500), fill=t.text_2, anchor="ls")
            return
        named = _named(school, mine)
        for me in mine:
            if named:  # whose region this is, then the region
                d.text(
                    (x, y_line),
                    fit(d, me["school"], _inter(small, 600), width),
                    font=_inter(small, 600),
                    fill=t.text,
                    anchor="ls",
                )
                y_line += line_h
            chip = round(small * 0.8)
            mid = y_line - small * 0.36
            d.ellipse((x, mid - chip / 2, x + chip, mid + chip / 2), fill=colors[me["class"], me["region"]])
            d.text(
                (x + chip + 10, y_line),
                fit(d, place(me), _inter(small, 500), width - chip - 10),
                font=_inter(small, 500),
                fill=t.text_2 if named else t.text,
                anchor="ls",
            )
            y_line += line_h

    _cells(page, cycles, caption, draw_cell)
    page.footer()
    return [page.img]


def _place_colors(theme: str, rows: list[dict]) -> dict[tuple[int, int], str]:
    """Each of a season's places (class, region) its region's color, but two different places (schools
    merged later, in regions with the same number in different classes) never the same: the second
    takes the first of the Counties pages' fallback colors not in use (region_pages.PLACE_FALLBACK)."""
    out: dict[tuple[int, int], str] = {}
    for r in rows:
        key = (r["class"], r["region"])
        if key in out:
            continue
        color = region_color(theme, r["region"])
        if color in out.values():
            color = next(
                (region_color(theme, c) for c in PLACE_FALLBACK if region_color(theme, c) not in out.values()), color
            )
        out[key] = color
    return out


def _named(school: str, rows: list[dict]) -> bool:
    """Whether a season's caption names its schools: several (before a consolidation), or one under
    another name."""
    return len(rows) > 1 or (len(rows) == 1 and rows[0]["school"] != school)
