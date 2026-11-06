"""A cycle's regions as images to share: a class's map, a team's region, and a team's two regions.

Each is a 4:5 portrait page (1080x1350, drawn at twice that) in the site's two themes:

- ``render_class_regions``: the class's schools on a map of the state, each a dot with its region's
  number, every region's soft shape, and the schools listed by region.
- ``render_team_region``: one team's region on the map, its schools labeled, with its New Region
  Members (and those Still in the Region) and, when its region changed, its Former Region Members.
- ``render_team_regions_compared``: the team's region in the season before the cycle and in the cycle,
  side by side, each with its members and where they are in the other season.

Like the other share images it's pure: plain data in (each school's name, class, region and projected
point, from ``region_map``), Pillow images out. The map, the projection and the shapes are
``region_map``'s, so the images and the Regions page show the same thing.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from backend.helpers import region_map
from backend.helpers.bracket_image import THEMES, Theme, helmet
from backend.helpers.data_helpers import SCHOOL_SUCCESSORS
from backend.helpers.region_files import cycle_start
from backend.helpers.share_cards import SITE_HOST, _inter, _nippo, _tracked, fit
from backend.helpers.static_pages import initials, team_colors

SIZE = (2160, 2700)  # 1080x1350 at 2x
PAD = 104
MAP_RIGHT = 1240  # the map's box ends here; the lists start at LIST_X
LIST_X = 1300

# Each region's color, in region order, per theme: the site's categorical palette (app.css
# --region-1..8), checked for color-blind separation between neighbors (regions are numbered roughly
# north to south, so neighbors on the map are neighbors here) and paired with the region's number on
# every dot, so no color has to be told apart alone.
REGION_COLORS = {
    "light": ("#2A78D6", "#EB6834", "#1BAF7A", "#EDA100", "#E87BA4", "#008300", "#6250D6", "#E34948"),
    "dark": ("#3987E5", "#D95926", "#199E70", "#C98500", "#D55181", "#008300", "#9085E9", "#E66767"),
}


def region_color(theme: str, region: int) -> str:
    """Region *region*'s color in *theme*."""
    colors = REGION_COLORS[theme]
    return colors[(region - 1) % len(colors)]


def cycle_name(first: int) -> str:
    """ "2027–29" for the cycle that starts in 2027."""
    return f"{first}–{(first + 2) % 100:02d}"


def seasons_words(seasons: list[int]) -> str:
    """ "2027 and 2028", or "2026"."""
    return " and ".join(str(s) for s in seasons)


def seasons_line(seasons: list[int]) -> str:
    """ "2027 and 2028 seasons", or "2026 season"."""
    return seasons_words(seasons) + (" seasons" if len(seasons) > 1 else " season")


def place(school: dict | None) -> str:
    """ "Region 2-5A" for a school's row (the site's {region}-{class}A)."""
    return f"Region {school['region']}-{school['class']}A" if school else ""


def short_place(school: dict | None) -> str:
    """ "2-5A" for a school's row."""
    return f"{school['region']}-{school['class']}A" if school else ""


def change_line(now: dict, before: dict | None, prior_season: int) -> str:
    """How a team's place changed from *prior_season* (its row then, or None): "Moved up from Region 4-4A"."""
    if before is None:
        old = next(
            (o for o, new, start in SCHOOL_SUCCESSORS if new == now["school"] and start == prior_season + 1), None
        )
        if old:
            return f"New school in {prior_season + 1}, on {old}’s campus"
        return f"Not in a region in {prior_season}"
    if before["class"] != now["class"]:
        way = "up" if now["class"] > before["class"] else "down"
        return f"Moved {way} from {place(before)}"
    if before["region"] != now["region"]:
        return f"Moved from {place(before)}"
    return f"Also {place(now)} in {prior_season}"


# ----------------------------------------------------------------- drawing


def _blend(a: str, b: str, t: float) -> str:
    """Color *a* mixed toward *b* by *t* (0..1)."""
    pa = [int(a[i : i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(pa, pb, strict=True))


class _Frame:
    """State-grid meters to pixels in a box: north up, one scale for x and y, centered."""

    def __init__(self, box: tuple[float, float, float, float]):
        x0, y0, x1, y1 = box
        bx0, by0, bx1, by1 = region_map.state().bounds
        self.s = min((x1 - x0) / (bx1 - bx0), (y1 - y0) / (by1 - by0))
        w, h = (bx1 - bx0) * self.s, (by1 - by0) * self.s
        self.ox, self.oy = x0 + (x1 - x0 - w) / 2, y0 + (y1 - y0 - h) / 2
        self.bx0, self.by1 = bx0, by1
        self.x0, self.x1 = x0, x1

    def __call__(self, x: float, y: float) -> tuple[float, float]:
        return self.ox + (x - self.bx0) * self.s, self.oy + (self.by1 - y) * self.s

    def ring(self, coords) -> list[tuple[float, float]]:
        """A ring of state-grid points, as pixels."""
        return [self(x, y) for x, y, *_ in coords]


def _polygons(geom):
    """The polygons of a shapely geometry."""
    return [g for g in getattr(geom, "geoms", [geom]) if g.geom_type == "Polygon" and not g.is_empty]


def _spread(points: list[list[float]], radii: list[float], gap: float = 6, rounds: int = 200) -> None:
    """Push overlapping dots apart, in place, until none overlap (or *rounds* run out)."""
    for _ in range(rounds):
        moved = False
        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                need = radii[i] + radii[j] + gap
                dx, dy = points[j][0] - points[i][0], points[j][1] - points[i][1]
                dist = (dx * dx + dy * dy) ** 0.5
                if dist >= need:
                    continue
                ux, uy = (dx / dist, dy / dist) if dist > 0.01 else (1.0, 0.0)
                push = (need - dist) / 2
                points[i][0] -= ux * push
                points[i][1] -= uy * push
                points[j][0] += ux * push
                points[j][1] += uy * push
                moved = True
        if not moved:
            return


class _Page:
    """One page being drawn."""

    def __init__(self, theme: str, teams: dict, size: tuple[int, int] = SIZE):
        self.theme = theme
        self.t: Theme = THEMES[theme]
        self.size = size
        self.img = Image.new("RGB", size, self.t.bg)
        self.d = ImageDraw.Draw(self.img)
        self.teams = teams

    def mark(self, school: str, x: float, mid: float, size: int) -> None:
        """A team's helmet in its colors, or its initials in a circle when it has none."""
        colors = team_colors(self.teams.get(school))
        if colors:
            icon = helmet(colors[0], colors[1], size, self.t.pale_edge)
            self.img.paste(icon, (round(x), round(mid - size / 2)), icon)
            return
        self.d.rounded_rectangle((x, mid - size / 2, x + size, mid + size / 2), radius=size / 2, fill=self.t.rule)
        font = _inter(round(size * 0.4), 600)
        self.d.text((x + size / 2, mid), initials(school), font=font, fill=self.t.text_2, anchor="mm")

    def footer(self, stamp: str) -> None:
        """The stamp and the site's address along the bottom."""
        base = self.size[1] - PAD + 8
        _tracked(self.d, (PAD, base), stamp.upper(), _inter(28, 600), self.t.text_2, 2)
        self.d.text((self.size[0] - PAD, base), SITE_HOST, font=_inter(44, 600), fill=self.t.text, anchor="rs")

    def label(self, x: float, base: float, text: str, anchor: str = "ls") -> None:
        """A small letter-spaced heading ("NEW REGION MEMBERS")."""
        _tracked(self.d, (x, base), text.upper(), _nippo(34), self.t.text_2, 2, anchor=anchor)

    def map(
        self,
        frame: _Frame,
        fills: list[tuple[object, str]],
        dots: list[tuple[float, float, str, str, float]],
        labels: list[tuple[str, int]] = (),
        focus: int | None = None,
        label_size: int = 34,
    ) -> None:
        """The state, its counties and the region shapes (*fills*: [(geometry, color)]), then the *dots*
        ([(x, y, color, text, radius)] in state-grid meters), then *labels* ([(text, dot index)]). A dot
        pushed off its spot to stay readable gets a hairline back to a small mark at the true spot."""
        t = self.t
        land = _blend(t.bg, t.text, 0.05)
        for poly in _polygons(region_map.state()):
            self.d.polygon(frame.ring(poly.exterior.coords), fill=land)
        over = Image.new("RGBA", self.size, (0, 0, 0, 0))
        for geom, color in fills:
            for poly in _polygons(geom):
                mask = Image.new("L", self.size, 0)
                md = ImageDraw.Draw(mask)
                md.polygon(frame.ring(poly.exterior.coords), fill=0x38)
                for hole in poly.interiors:
                    md.polygon(frame.ring(hole.coords), fill=0)
                layer = Image.new("RGBA", self.size, color)
                layer.putalpha(mask)
                over = Image.alpha_composite(over, layer)
                od = ImageDraw.Draw(over)
                for ring in [poly.exterior, *poly.interiors]:
                    od.line(frame.ring(ring.coords), fill=color + "C0", width=3, joint="curve")
        self.img.paste(Image.alpha_composite(self.img.convert("RGBA"), over).convert("RGB"))
        self.d = ImageDraw.Draw(self.img)
        county_line = _blend(t.bg, t.text, 0.22)
        for geom in region_map.counties().values():
            for poly in _polygons(geom):
                self.d.line(frame.ring(poly.exterior.coords), fill=county_line, width=2, joint="curve")
        for poly in _polygons(region_map.state()):
            self.d.line(frame.ring(poly.exterior.coords), fill=_blend(t.bg, t.text, 0.6), width=5, joint="curve")

        true = [frame(x, y) for x, y, *_ in dots]
        spots = [list(p) for p in true]
        _spread(spots, [r for *_, r in dots])
        for (px, py), (tx, ty) in zip(spots, true, strict=True):
            if abs(px - tx) + abs(py - ty) > 4:
                self.d.line((tx, ty, px, py), fill=t.text_2, width=2)
                self.d.ellipse((tx - 5, ty - 5, tx + 5, ty + 5), fill=t.text)
        for i, ((px, py), (_, _, color, text, r)) in enumerate(zip(spots, dots, strict=True)):
            ring = 6 if focus == i else 3
            self.d.ellipse(
                (px - r - ring, py - r - ring, px + r + ring, py + r + ring), fill=t.text if focus == i else t.bg
            )
            self.d.ellipse((px - r, py - r, px + r, py + r), fill=color)
            if text:
                self.d.text((px, py + 1), text, font=_inter(round(r * 1.15), 700), fill="#FFFFFF", anchor="mm")
        self._labels(frame, spots, dots, labels, label_size)

    def _labels(self, frame: _Frame, spots, dots, labels, size: int) -> None:
        """Each label beside its dot, at the first of eight spots around it that's clear of the other
        dots and labels (to the right if none is)."""
        font = _inter(size, 600)
        placed: list[tuple[float, float, float, float]] = []
        for text, i in labels:
            px, py = spots[i]
            r = dots[i][4]
            w, h, g = self.d.textlength(text, font=font), size + 6, r + 14
            options = [
                (px + g, py - h / 2),
                (px - g - w, py - h / 2),
                (px - w / 2, py - g - h),
                (px - w / 2, py + g),
                (px + g * 0.7, py - g - h * 0.6),
                (px + g * 0.7, py + g * 0.6 - h * 0.4),
                (px - g * 0.7 - w, py - g - h * 0.6),
                (px - g * 0.7 - w, py + g * 0.6 - h * 0.4),
            ]

            def clear(x: float, y: float) -> bool:
                """Is a label at (x, y) inside the map and clear of the dots and labels drawn so far?"""
                box = (x - 6, y - 4, x + w + 6, y + h + 4)
                if box[0] < frame.x0 - 10 or box[2] > frame.x1 + 40:
                    return False
                if any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in placed):
                    return False
                for (qx, qy), dot in zip(spots, dots, strict=True):
                    cx, cy = min(max(qx, box[0]), box[2]), min(max(qy, box[1]), box[3])
                    if (cx - qx) ** 2 + (cy - qy) ** 2 < (dot[4] + 4) ** 2:
                        return False
                return True

            x, y = next((o for o in options if clear(*o)), options[0])
            placed.append((x - 6, y - 4, x + w + 6, y + h + 4))
            self.d.text(
                (x, y + h / 2), text, font=font, fill=self.t.text, anchor="lm", stroke_width=6, stroke_fill=self.t.bg
            )


def _absent(school: str, first: int, short: bool = False) -> str:
    """What a school in the cycle that starts in *first* was the season before, when it had no region:
    a new school (a successor), or "Not in a region in 2026"."""
    if any(new == school and start == first for _, new, start in SCHOOL_SUCCESSORS):
        return "New school" if short else f"New school in {first}"
    return f"Not in a region in {first - 1}"


def _class_rows(schools: list[dict], clazz: int) -> list[dict]:
    """A class's schools, by region and name."""
    return sorted((s for s in schools if s["class"] == clazz), key=lambda s: (s["region"], s["school"].lower()))


def _members(schools: list[dict], at: dict, but: str) -> list[dict]:
    """The schools in *at*'s class and region, other than *but*, by name."""
    return sorted(
        (s for s in schools if (s["class"], s["region"]) == (at["class"], at["region"]) and s["school"] != but),
        key=lambda s: s["school"].lower(),
    )


def _region_map(page: _Page, frame: _Frame, rows: list[dict], school: str, label_size: int, big: float, small: float):
    """*school*'s region in its class (*rows*): its shape, its schools labeled and the team ringed, the
    class's other schools in gray."""
    me = next(s for s in rows if s["school"] == school)
    rows = [s for s in rows if s["x"] is not None]  # a school with no place on the map gets no dot
    color = region_color(page.theme, me["region"])
    group = sorted((s for s in rows if s["region"] == me["region"]), key=lambda s: s["school"].lower())
    others = [s for s in rows if s["region"] != me["region"]]
    muted = _blend(page.t.bg, page.t.text, 0.3)
    dots = [(s["x"], s["y"], muted, "", small) for s in others] + [(s["x"], s["y"], color, "", big) for s in group]
    first = len(others)
    shapes = region_map.region_shapes(rows)
    names = [s["school"] for s in group]
    page.map(
        frame,
        [(shapes[me["region"]], color)] if me["region"] in shapes else [],
        dots,
        [(s["school"], first + k) for k, s in enumerate(group)] if label_size else [],
        first + names.index(school) if school in names else None,
        label_size or 34,
    )


def render_class_regions(clazz: int, seasons: list[int], schools: list[dict], theme: str) -> list[Image.Image]:
    """Class *clazz*'s regions in the cycle that starts in *first*: the map and the schools by region.
    *schools* is the cycle's every school ({school, class, region, x, y})."""
    first = seasons[0]
    rows = _class_rows(schools, clazz)
    if not rows:
        return []
    page = _Page(theme, {})
    d, t = page.d, page.t
    d.text((PAD, PAD + 104), f"{clazz}A Football Regions", font=_nippo(124), fill=t.text, anchor="ls")
    d.text((PAD, PAD + 176), seasons_line(seasons), font=_inter(42, 500), fill=t.text_2, anchor="ls")
    regions = sorted({s["region"] for s in rows})
    top, bottom = PAD + 250, SIZE[1] - PAD - 110
    on_map = [s for s in rows if s["x"] is not None]  # a school with no place on the map is only listed
    shapes = region_map.region_shapes(on_map)
    page.map(
        _Frame((PAD - 20, top, MAP_RIGHT, bottom)),
        [(shapes[g], region_color(theme, g)) for g in sorted(shapes)],
        [(s["x"], s["y"], region_color(theme, s["region"]), str(s["region"]), 26) for s in on_map],
    )
    d = page.d
    y, width = top + 10, SIZE[0] - PAD - LIST_X - 80
    compact = len(regions) > 4  # eight regions: names run on, "Ashland · Biggersville · …"
    for g in regions:
        d.ellipse((LIST_X, y, LIST_X + 56, y + 56), fill=region_color(theme, g))
        d.text((LIST_X + 28, y + 29), str(g), font=_inter(34, 700), fill="#FFFFFF", anchor="mm")
        d.text((LIST_X + 80, y + 48), f"Region {g}", font=_nippo(52), fill=t.text, anchor="ls")
        y += 96
        names = [s["school"] for s in rows if s["region"] == g]
        if compact:
            font, lines, line = _inter(36, 500), [], ""
            for name in names:
                trial = f"{line} · {name}" if line else name
                if line and d.textlength(trial, font=font) > width:
                    lines.append(line)
                    line = name
                else:
                    line = trial
            lines.append(line)
            for text in lines:
                d.text((LIST_X + 80, y), fit(d, text, font, width), font=font, fill=t.text, anchor="ls")
                y += 52
            y += 30
        else:
            font = _inter(38, 500)
            for name in names:
                d.text((LIST_X + 80, y), fit(d, name, font, width), font=font, fill=t.text, anchor="ls")
                y += 66
            y += 34
    page.footer(f"MHSAA {cycle_name(first)} regions")
    return [page.img]


def render_team_region(
    school: str, seasons: list[int], schools: list[dict], prior: list[dict], teams: dict, theme: str
) -> list[Image.Image]:
    """*school*'s region in the cycle that starts in *first* (*schools*), against the season before
    (*prior*: that season's schools, empty when there's none): the map, its New Region Members and those
    Still in the Region, and its Former Region Members when its region changed."""
    first = seasons[0]
    me = next((s for s in schools if s["school"] == school), None)
    if me is None:
        return []
    prior_by = {s["school"]: s for s in prior}
    before = prior_by.get(school)
    page = _Page(theme, teams)
    d, t = page.d, page.t
    page.mark(school, PAD, PAD + 62, 128)
    d.text(
        (PAD + 160, PAD + 104),
        fit(d, school, _nippo(124), SIZE[0] - 2 * PAD - 160),
        font=_nippo(124),
        fill=t.text,
        anchor="ls",
    )
    d.text((PAD, PAD + 196), f"{place(me)} in {seasons_words(seasons)}", font=_nippo(52), fill=t.text, anchor="ls")
    if prior:
        d.text((PAD, PAD + 256), change_line(me, before, first - 1), font=_inter(40, 500), fill=t.text_2, anchor="ls")
    top, bottom = PAD + 330, SIZE[1] - PAD - 110
    _region_map(page, _Frame((PAD - 20, top, MAP_RIGHT, bottom)), _class_rows(schools, me["class"]), school, 34, 24, 12)

    d = page.d
    mates = _members(schools, me, school)
    old = {s["school"] for s in _members(prior, before, school)} if before else set()
    new = [s for s in mates if s["school"] not in old] if prior else mates
    kept = [s for s in mates if s["school"] in old]
    y = top + 30

    def block(title: str, rows: list[dict], y: float) -> float:
        """A titled list of schools, each with its helmet and where it was; returns where the next goes."""
        page.label(LIST_X, y, title)
        y += 70
        for s in rows:
            page.mark(s["school"], LIST_X, y - 14, 64)
            d.text(
                (LIST_X + 88, y),
                fit(d, s["school"], _inter(42, 600), SIZE[0] - PAD - LIST_X - 88),
                font=_inter(42, 600),
                fill=t.text,
                anchor="ls",
            )
            if prior:
                was = prior_by.get(s["school"])
                note = f"{place(was)} in {first - 1}" if was else _absent(s["school"], first)
                d.text((LIST_X + 88, y + 50), note, font=_inter(32, 500), fill=t.text_2, anchor="ls")
            y += 130 if prior else 96
        return y + 30

    if new:
        y = block("New Region Members" if prior else "Region Members", new, y)
    if kept:
        y = block("Still in the Region", kept, y)
    moved = before and (before["class"], before["region"]) != (me["class"], me["region"])
    former = (
        [s for s in _members(prior, before, school) if s["school"] not in {m["school"] for m in mates}] if moved else []
    )
    if former:
        now_by = {s["school"]: s for s in schools}
        page.label(LIST_X, y, "Former Region Members")
        d.text((LIST_X, y + 56), f"{place(before)} in {first - 1}", font=_inter(32, 500), fill=t.text_2, anchor="ls")
        y += 118
        for s in former:
            now = now_by.get(s["school"])
            d.text(
                (LIST_X, y),
                fit(d, s["school"], _inter(38, 500), SIZE[0] - PAD - LIST_X - 200),
                font=_inter(38, 500),
                fill=t.text,
                anchor="ls",
            )
            note = short_place(now) if now else f"Not on the {cycle_name(first)} list"
            d.text((SIZE[0] - PAD, y), note, font=_inter(32, 500), fill=t.text_2, anchor="rs")
            y += 58
            if y > bottom:
                break
    page.footer(f"MHSAA {cycle_name(first)} regions")
    return [page.img]


def render_team_regions_compared(
    school: str, seasons: list[int], schools: list[dict], prior: list[dict], teams: dict, theme: str
) -> list[Image.Image]:
    """*school*'s region in the season before the cycle (*prior*) and in the cycle that starts in *first*
    (*schools*), side by side; nothing when it had no region the season before."""
    first = seasons[0]
    now = next((s for s in schools if s["school"] == school), None)
    before = next((s for s in prior if s["school"] == school), None)
    if now is None or before is None:
        return []
    page = _Page(theme, teams)
    d, t = page.d, page.t
    page.mark(school, PAD, PAD + 62, 128)
    d.text(
        (PAD + 160, PAD + 104),
        fit(d, school, _nippo(124), SIZE[0] - 2 * PAD - 160),
        font=_nippo(124),
        fill=t.text,
        anchor="ls",
    )
    d.text((PAD, PAD + 184), f"{first - 1} region vs. {first} region", font=_inter(46, 600), fill=t.text_2, anchor="ls")
    gap = 60
    w = (SIZE[0] - 2 * PAD - gap) / 2
    top = PAD + 260
    bx0, by0, bx1, by1 = region_map.state().bounds
    bottom = top + 140 + w * (by1 - by0) / (bx1 - bx0)
    panels = (
        (PAD, before, prior, schools, f"{first - 1}", f"IN {first}", f"Not on the {cycle_name(first)} list"),
        (
            PAD + w + gap,
            now,
            schools,
            prior,
            seasons_words(seasons),
            f"IN {first - 1}",
            f"Not in a region in {first - 1}",
        ),
    )
    for x0, row, these, other, when, column, missing in panels:
        d.text((x0, top + 50), place(row), font=_nippo(60), fill=t.text, anchor="ls")
        d.text((x0, top + 100), when, font=_inter(36, 500), fill=t.text_2, anchor="ls")
        _region_map(page, _Frame((x0, top + 140, x0 + w, bottom)), _class_rows(these, row["class"]), school, 28, 18, 9)
        d = page.d
        y = bottom + 70
        page.label(x0, y, f"{when.split()[0]} Region Members")
        page.label(x0 + w, y, column, anchor="rs")
        y += 58
        other_by = {s["school"]: s for s in other}
        theirs = next(s for s in other if s["school"] == school)
        for s in _members(these, row, school):
            o = other_by.get(s["school"])
            if o and (o["class"], o["region"]) == (theirs["class"], theirs["region"]):
                note = "Still in region"
            elif o:
                note = short_place(o)
            elif other is prior:
                note = _absent(s["school"], first, short=True)
            else:
                note = missing
            d.text(
                (x0, y), fit(d, s["school"], _inter(36, 600), w - 220), font=_inter(36, 600), fill=t.text, anchor="ls"
            )
            d.text((x0 + w, y), note, font=_inter(30, 500), fill=t.text_2, anchor="rs")
            y += 50
            if y > SIZE[1] - PAD - 110:
                break
    page.footer(f"MHSAA {cycle_name(cycle_start(first - 1))} and {cycle_name(first)} regions")
    return [page.img]


# ----------------------------------------------------------------- link previews

CARD = (2400, 1260)  # the site's 1200x630 link preview, drawn at 2x and scaled down
CARD_PAD = 128


def _card_map(page: _Page) -> _Frame:
    """The preview's map box, on the right."""
    return _Frame((CARD[0] - CARD_PAD - 760, 70, CARD[0] - CARD_PAD + 20, CARD[1] - 70))


def _card(page: _Page) -> list[Image.Image]:
    """The preview at its published size (as a one-page image, like the other renderers)."""
    return [page.img.resize((CARD[0] // 2, CARD[1] // 2), Image.LANCZOS)]


def _card_lines(page: _Page, x: float, y: float, text: str, size: int, width: float, lines: int) -> float:
    """*text* wrapped into at most *lines* lines at *y*; returns where the next line goes."""
    font, out, line = _inter(size, 500), [], ""
    for word in text.split():
        trial = f"{line} {word}" if line else word
        if line and page.d.textlength(trial, font=font) > width:
            out.append(line)
            line = word
        else:
            line = trial
    out.append(line)
    for text_line in out[:lines]:
        page.d.text((x, y), fit(page.d, text_line, font, width), font=font, fill=page.t.text_2, anchor="ls")
        y += size * 1.45
    return y


def render_class_regions_card(clazz: int, seasons: list[int], schools: list[dict]) -> list[Image.Image]:
    """Class *clazz*'s Regions page preview: the title, its seasons, and the map with every region."""
    rows = [s for s in _class_rows(schools, clazz) if s["x"] is not None]
    if not rows:
        return []
    page = _Page("dark", {}, CARD)
    d, t = page.d, page.t
    d.text((CARD_PAD, CARD_PAD + 120), f"Class {clazz}A", font=_nippo(152), fill=t.text, anchor="ls")
    d.text((CARD_PAD, CARD_PAD + 270), "Football Regions", font=_nippo(152), fill=t.text, anchor="ls")
    d.text((CARD_PAD, CARD_PAD + 380), seasons_line(seasons), font=_inter(60, 600), fill=t.text_2, anchor="ls")
    regions = sorted({s["region"] for s in rows})
    x, y = CARD_PAD, CARD_PAD + 500
    for g in regions:
        d.ellipse((x, y, x + 72, y + 72), fill=region_color("dark", g))
        d.text((x + 36, y + 37), str(g), font=_inter(44, 700), fill="#FFFFFF", anchor="mm")
        x += 96
    shapes = region_map.region_shapes(rows)
    page.map(
        _card_map(page),
        [(shapes[g], region_color("dark", g)) for g in regions],
        [(s["x"], s["y"], region_color("dark", s["region"]), "", 14) for s in rows],
    )
    page.d.text((CARD_PAD, CARD[1] - CARD_PAD + 16), SITE_HOST, font=_inter(52, 600), fill=t.text, anchor="ls")
    return _card(page)


def render_team_region_card(
    school: str, seasons: list[int], schools: list[dict], prior: list[dict], teams: dict
) -> list[Image.Image]:
    """A team's Regions page preview: its name, its region, how it changed, and the map."""
    first = seasons[0]
    me = next((s for s in schools if s["school"] == school), None)
    if me is None or me["x"] is None:
        return []  # no place on the map
    before = next((s for s in prior if s["school"] == school), None)
    page = _Page("dark", teams, CARD)
    d, t = page.d, page.t
    page.mark(school, CARD_PAD, CARD_PAD + 70, 150)
    width = CARD[0] - 2 * CARD_PAD - 900
    d.text((CARD_PAD, CARD_PAD + 300), fit(d, school, _nippo(132), width), font=_nippo(132), fill=t.text, anchor="ls")
    d.text(
        (CARD_PAD, CARD_PAD + 410),
        f"{place(me)} in {seasons_words(seasons)}",
        font=_inter(60, 600),
        fill=t.text,
        anchor="ls",
    )
    y = CARD_PAD + 500
    if prior:
        y = _card_lines(page, CARD_PAD, y, change_line(me, before, first - 1), 50, width, 2)
    old = {s["school"] for s in _members(prior, before, school)} if before else set()
    new = [s["school"] for s in _members(schools, me, school) if s["school"] not in old]
    if new and prior:
        _card_lines(page, CARD_PAD, y + 20, "New Region Members: " + ", ".join(new), 44, width, 3)
    rows = [s for s in _class_rows(schools, me["class"]) if s["x"] is not None]
    _region_map(page, _card_map(page), rows, school, 0, 16, 8)
    page.d.text((CARD_PAD, CARD[1] - CARD_PAD + 16), SITE_HOST, font=_inter(52, 600), fill=t.text, anchor="ls")
    return _card(page)
