"""Mississippi on a map: its counties, where each school is, and a soft shape for each region.

Everything is projected once, with PROJ (pyproj), into NAD83 / Mississippi Transverse Mercator
(EPSG:3814), the state's own statewide grid, in meters: the county lines from the Census Bureau's
cartographic boundary file (``backend/data/geo/mississippi_counties.geojson``, NAD83) and each
school's latitude and longitude (WGS84). The share images (``region_map_image``) and the Regions page
(``regions.js``, from ``map_payload``) draw the same projected shapes, so they can't disagree.

A region's shape is drawn around its schools; MHSAA draws no boundaries, so it isn't one. It's the
schools' convex hull, padded by ``PAD_KM``; where two regions' shapes would touch, both are cut by one
straight line, the one with the widest gap between the two regions' schools, leaving ``GAP_KM``
between them. Cutting a convex shape with straight lines keeps it convex, so every side is straight
and no school is ever inside another region's shape. Should no straight line separate two regions'
schools, that pair is split by nearest school instead (``region_shapes`` reports it).
"""

from __future__ import annotations

import json
import math
from functools import cache
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely import voronoi_polygons
from shapely.geometry import MultiPoint, Point, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

COUNTIES_PATH = Path(__file__).resolve().parents[1] / "data" / "geo" / "mississippi_counties.geojson"
CRS = "EPSG:3814"  # NAD83 / Mississippi TM
PAD_KM = 9  # how far a region's shape reaches past its outermost schools
GAP_KM = 1.5  # the space left between two regions' shapes
SVG_UNIT = 100  # meters per unit in the Regions page's SVG (map_payload)
_FAR = 2_000_000  # meters: "infinitely" far, for half-planes


@cache
def _from_nad83() -> Transformer:
    """NAD83 longitude/latitude (the Census file) to the state grid."""
    return Transformer.from_crs("EPSG:4269", CRS, always_xy=True)


@cache
def _from_wgs84() -> Transformer:
    """WGS84 longitude/latitude (a school's coordinates) to the state grid."""
    return Transformer.from_crs("EPSG:4326", CRS, always_xy=True)


@cache
def counties() -> dict[str, BaseGeometry]:
    """Each county's outline, projected, by name ("Hinds")."""
    doc = json.loads(COUNTIES_PATH.read_text(encoding="utf-8"))
    tf = _from_nad83()

    def to_grid(coords: np.ndarray) -> np.ndarray:
        """Longitude/latitude pairs to state-grid meters."""
        x, y = tf.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])

    return {f["properties"]["name"]: shapely.transform(shape(f["geometry"]), to_grid) for f in doc["features"]}


@cache
def state() -> BaseGeometry:
    """Mississippi's outline: its counties, merged."""
    return unary_union(list(counties().values()))


def source() -> str:
    """Where the county lines come from, for a page's credits."""
    return json.loads(COUNTIES_PATH.read_text(encoding="utf-8"))["source"]


def project(latitude: float, longitude: float) -> tuple[float, float]:
    """A school's (x, y) on the state grid, in meters."""
    return _from_wgs84().transform(longitude, latitude)


def county_of(x: float, y: float) -> str | None:
    """The county a projected point is in, or None outside the state."""
    p = Point(x, y)
    return next((name for name, g in counties().items() if g.covers(p)), None)


# ----------------------------------------------------------------- region shapes


def separator(a: list[tuple[float, float]], b: list[tuple[float, float]], steps: int = 1440):
    """The straight line with the widest gap between point sets *a* and *b*: (nx, ny, c, gap), with
    *a* where nx*x + ny*y < c and *b* past it. *gap* is the space between them across the line, in
    meters; it's 0 or less when no straight line separates them. Searched over *steps* directions."""
    best = None
    for k in range(steps):
        t = 2 * math.pi * k / steps
        nx, ny = math.cos(t), math.sin(t)
        hi = max(nx * x + ny * y for x, y in a)
        lo = min(nx * x + ny * y for x, y in b)
        if best is None or lo - hi > best[3]:
            best = (nx, ny, (hi + lo) / 2, lo - hi)
    return best


def _half_plane(nx: float, ny: float, c: float) -> Polygon:
    """Everything where nx*x + ny*y <= c (within ``_FAR``)."""
    px, py = nx * c, ny * c
    tx, ty = -ny, nx
    return Polygon(
        [
            (px + tx * _FAR, py + ty * _FAR),
            (px - tx * _FAR, py - ty * _FAR),
            (px - tx * _FAR - nx * _FAR, py - ty * _FAR - ny * _FAR),
            (px + tx * _FAR - nx * _FAR, py + ty * _FAR - ny * _FAR),
        ]
    )


def region_shapes(schools: list[dict], tangled: list | None = None) -> dict[int, BaseGeometry]:
    """Each region's shape for one class's *schools* ({x, y, region}), inside the state. Pairs of
    regions no straight line separates are appended to *tangled* (and split by nearest school)."""
    groups: dict[int, list[tuple[float, float]]] = {}
    for s in schools:
        groups.setdefault(s["region"], []).append((s["x"], s["y"]))
    wraps = {g: MultiPoint(p).convex_hull.buffer(PAD_KM * 1000, quad_segs=24) for g, p in groups.items()}
    shapes = dict(wraps)
    knotted = []
    regions = sorted(groups)
    for i, g in enumerate(regions):
        for h in regions[i + 1 :]:
            if not wraps[g].intersects(wraps[h]):
                continue
            nx, ny, c, gap = separator(groups[g], groups[h])
            if gap <= GAP_KM * 1000:
                knotted.append((g, h))
                continue
            shapes[g] = shapes[g].intersection(_half_plane(nx, ny, c - GAP_KM * 500))
            shapes[h] = shapes[h].intersection(_half_plane(-nx, -ny, -c - GAP_KM * 500))
    if knotted:
        cells = voronoi_polygons(MultiPoint([(s["x"], s["y"]) for s in schools]), extend_to=state().envelope)
        near: dict[int, list] = {g: [] for g in regions}
        for cell in cells.geoms:
            owner = next((s for s in schools if cell.covers(Point(s["x"], s["y"]))), None)
            if owner:
                near[owner["region"]].append(cell)
        for g, h in knotted:
            shapes[g] = shapes[g].difference(unary_union(near[h]).buffer(GAP_KM * 500))
            shapes[h] = shapes[h].difference(unary_union(near[g]).buffer(GAP_KM * 500))
        if tangled is not None:
            tangled.extend(knotted)
    return {g: s.intersection(state()) for g, s in shapes.items()}


# ----------------------------------------------------------------- the Regions page's data


def svg_point(x: float, y: float) -> tuple[float, float]:
    """State-grid meters to the page's SVG units: from the state's top-left corner, y down."""
    x0, _, _, y1 = state().bounds
    return (x - x0) / SVG_UNIT, (y1 - y) / SVG_UNIT


def svg_path(geom: BaseGeometry) -> str:
    """*geom* as SVG path data in the page's units (holes included; draw with fill-rule evenodd)."""
    out = []
    for poly in getattr(geom, "geoms", [geom]):
        if poly.is_empty or poly.geom_type != "Polygon":
            continue
        for ring in [poly.exterior, *poly.interiors]:
            pts = [svg_point(x, y) for x, y in ring.coords]
            out.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
    return "".join(out)


def base_map() -> dict:
    """The page's map without schools: its size, the state outline, and each county with a spot for
    its name. It doesn't change from season to season."""
    x0, y0, x1, y1 = state().bounds
    return {
        "width": round((x1 - x0) / SVG_UNIT, 1),
        "height": round((y1 - y0) / SVG_UNIT, 1),
        "state": svg_path(state()),
        "counties": [
            {
                "name": name,
                "d": svg_path(g),
                "label": [round(v, 1) for v in svg_point(*g.representative_point().coords[0])],
            }
            for name, g in sorted(counties().items())
        ],
        "source": source(),
    }
