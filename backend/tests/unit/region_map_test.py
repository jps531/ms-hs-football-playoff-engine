"""The region maps: the Census county lines, projected; schools in the right county; region shapes
with straight sides that never overlap and hold their own schools; and the images drawn from them."""

import pytest
from shapely.geometry import Point

from backend.helpers import region_map as rm
from backend.helpers import region_map_image as ri

# ----------------------------------------------------------------- the map


def test_the_map_is_mississippis_82_counties():
    """All 82, merged into a state of about Mississippi's size (121,500 km² of land, 125,400 with water;
    the 1:500,000 file trims the shoreline)."""
    assert len(rm.counties()) == 82
    assert {"Hinds", "DeSoto", "Harrison", "Tishomingo", "Wilkinson"} <= set(rm.counties())
    assert 121_000 < rm.state().area / 1e6 < 125_500
    assert rm.source().startswith("U.S. Census Bureau, 2023")


@pytest.mark.parametrize(
    ("lat", "lon", "county"),
    [
        (32.3034, -90.1821, "Hinds"),  # the State Capitol, Jackson
        (34.2576, -88.7034, "Lee"),  # Tupelo
        (30.3960, -88.8853, "Harrison"),  # Biloxi
        (33.4101, -91.0618, "Washington"),  # Greenville
        (31.3271, -89.2903, "Forrest"),  # Hattiesburg
        (34.9620, -89.9973, "DeSoto"),  # Southaven
        (35.1495, -90.0490, None),  # Memphis, Tennessee
        (30.6954, -88.0399, None),  # Mobile, Alabama
    ],
)
def test_a_point_lands_in_its_county(lat, lon, county):
    """Known places, projected the same way as schools, fall in their counties (or outside the state)."""
    assert rm.county_of(*rm.project(lat, lon)) == county


def test_the_projection_keeps_distances():
    """Mississippi TM is true to scale here: Jackson to Tupelo on the grid matches the distance on the
    ground (the geodesic on the WGS84 ellipsoid, about 257 km) to within 0.05%."""
    from pyproj import Geod

    (lat0, lon0), (lat1, lon1) = (32.2988, -90.1848), (34.2576, -88.7034)
    (x0, y0), (x1, y1) = rm.project(lat0, lon0), rm.project(lat1, lon1)
    ground = Geod(ellps="WGS84").inv(lon0, lat0, lon1, lat1)[2]
    grid = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    assert 255_000 < ground < 260_000
    assert abs(grid - ground) / ground < 0.0005


# ----------------------------------------------------------------- region shapes


def _schools(spec):
    """Schools at projected points: {region: [(lat, lon), ...]}."""
    out = []
    for region, places in spec.items():
        for i, (lat, lon) in enumerate(places):
            x, y = rm.project(lat, lon)
            out.append({"school": f"R{region}-{i}", "region": region, "x": x, "y": y})
    return out


# Two regions whose padded hulls would overlap around Jackson (like 7A's Regions 2 and 3).
NEIGHBORS = _schools(
    {
        2: [
            (32.33, -90.32),
            (32.43, -90.13),
            (32.42, -90.25),
            (33.45, -88.82),
        ],  # Clinton, Madison, Ridgeland, Starkville
        3: [
            (32.27, -89.99),
            (32.31, -89.88),
            (32.36, -88.70),
            (31.33, -89.29),
        ],  # Pearl, Brandon, Meridian, Hattiesburg
    }
)


def test_neighboring_regions_never_overlap_and_hold_their_own_schools():
    """Each school is inside its own region's shape and outside every other one's."""
    tangled = []
    shapes = rm.region_shapes(NEIGHBORS, tangled)
    assert tangled == []
    assert shapes[2].intersection(shapes[3]).area == 0
    assert shapes[2].distance(shapes[3]) >= rm.GAP_KM * 1000 * 0.99
    for s in NEIGHBORS:
        p = Point(s["x"], s["y"])
        assert shapes[s["region"]].contains(p)
        assert not shapes[5 - s["region"]].intersects(p)


def test_shapes_have_straight_sides():
    """A shape cut by straight lines stays convex: it's (nearly) its own convex hull."""
    for shape in rm.region_shapes(NEIGHBORS).values():
        assert shape.area / shape.convex_hull.area > 0.995


def test_the_widest_line_between_two_sets():
    """Two clusters 10 km apart along x: the line is x = 5 km, with a 10 km gap; interleaved sets have none."""
    nx, ny, c, gap = rm.separator([(0, 0), (0, 1000)], [(10_000, 0), (10_000, 1000)])
    assert (round(nx, 6), round(ny, 6), round(c), round(gap)) == (1, 0, 5000, 10_000)
    assert rm.separator([(0, 0), (10, 10)], [(10, 0), (0, 10)])[3] <= 0


def test_interleaved_regions_still_dont_overlap():
    """Schools no straight line separates (an X) are split by nearest school instead, and reported."""
    schools = _schools({1: [(32.0, -90.0), (32.6, -89.4)], 2: [(32.0, -89.4), (32.6, -90.0)]})
    tangled = []
    shapes = rm.region_shapes(schools, tangled)
    assert tangled == [(1, 2)]
    assert shapes[1].intersection(shapes[2]).area == 0
    assert all(shapes[s["region"]].contains(Point(s["x"], s["y"])) for s in schools)


def test_the_pages_map_data():
    """The page's SVG: the state's size in 100 m units, and every county with a spot for its name."""
    base = rm.base_map()
    assert 3000 < base["width"] < 3600 and 5000 < base["height"] < 5700
    assert len(base["counties"]) == 82 and base["state"].startswith("M")
    hinds = next(c for c in base["counties"] if c["name"] == "Hinds")
    assert 0 < hinds["label"][0] < base["width"] and 0 < hinds["label"][1] < base["height"]


# ----------------------------------------------------------------- the images


def _row(school, clazz, region, lat, lon):
    """A school's row at a latitude and longitude, projected."""
    x, y = rm.project(lat, lon)
    return {"school": school, "class": clazz, "region": region, "x": x, "y": y}


S27 = [
    _row("Greenwood", 5, 2, 33.5162, -90.1795),
    _row("Greenville", 5, 2, 33.4101, -91.0618),
    _row("Leake", 5, 2, 32.7726, -89.5370),
    _row("Brookhaven", 5, 3, 31.5791, -90.4407),
    _row("Natchez", 5, 3, 31.5604, -91.4032),
    _row("Vicksburg", 5, 3, 32.3526, -90.8779),
    _row("North Tippah", 3, 2, 34.9487, -88.9054),
]
S26 = [
    _row("Greenwood", 4, 4, 33.5162, -90.1795),
    _row("Yazoo City", 4, 4, 32.8551, -90.4056),
    _row("Greenville", 6, 2, 33.4101, -91.0618),
    _row("Leake", 5, 2, 32.7726, -89.5370),
    _row("Brookhaven", 5, 3, 31.5791, -90.4407),
    _row("Natchez", 5, 3, 31.5604, -91.4032),
    _row("Vicksburg", 5, 2, 32.3526, -90.8779),
    _row("Walnut", 2, 1, 34.9487, -88.9054),
]


def test_how_a_teams_place_changed():
    """Up or down a class, a new region, the same one, or a new school on an old one's campus."""
    by26 = {s["school"]: s for s in S26}
    by27 = {s["school"]: s for s in S27}
    assert ri.change_line(by27["Greenwood"], by26["Greenwood"], 2026) == "Moved up from Region 4-4A"
    assert ri.change_line(by27["Greenville"], by26["Greenville"], 2026) == "Moved down from Region 2-6A"
    assert ri.change_line(by27["Vicksburg"], by26["Vicksburg"], 2026) == "Moved from Region 2-5A"
    assert ri.change_line(by27["Leake"], by26["Leake"], 2026) == "Also Region 2-5A in 2026"
    assert ri.change_line(by27["North Tippah"], None, 2026) == "New school in 2027, on Walnut’s campus"
    assert ri._absent("North Tippah", 2027) == "New school in 2027"
    assert ri._absent("Somewhere", 2027) == "Not in a region in 2026"


def test_cycle_words():
    """The cycle and its seasons, as the images name them."""
    assert (ri.cycle_name(2027), ri.cycle_name(2099), ri.seasons_line([2027, 2028])) == (
        "2027–29",
        "2099–01",
        "2027 and 2028 seasons",
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_each_image_draws_a_page(theme):
    """The class map, the team's region and the comparison each draw one 1080x1350 page at 2x."""
    teams = {"Greenwood": {"color_variants": {"primary": {"raw": "#800000"}}, "secondary_color_hex": "#FFFFFF"}}
    pages = [
        ri.render_class_regions(5, [2027, 2028], S27, theme),
        ri.render_team_region("Greenwood", [2027, 2028], S27, S26, teams, theme),
        ri.render_team_region("North Tippah", [2027, 2028], S27, S26, teams, theme),
        ri.render_team_regions_compared("Greenwood", [2027, 2028], S27, S26, teams, theme),
    ]
    assert all(len(p) == 1 and p[0].size == ri.SIZE for p in pages)


def test_the_link_previews_are_the_sites_size():
    """The class's and the team's previews are 1200x630, like the site's other link previews."""
    assert [p.size for p in ri.render_class_regions_card(5, [2027, 2028], S27)] == [(1200, 630)]
    assert [p.size for p in ri.render_team_region_card("Greenwood", [2027, 2028], S27, S26, {})] == [(1200, 630)]
    assert ri.render_class_regions_card(7, [2027, 2028], S27) == []


def test_a_school_with_no_place_on_the_map_is_still_listed():
    """No coordinates: no dot, but the images still draw (and the class still has its other dots)."""
    unplaced = [*S27, {"school": "Nowhere", "class": 5, "region": 2, "x": None, "y": None}]
    assert ri.render_class_regions(5, [2027], unplaced, "light")
    assert ri.render_team_region("Nowhere", [2027], unplaced, S26, {}, "light")
    assert ri.render_team_region_card("Nowhere", [2027], unplaced, S26, {}) == []


def test_nothing_to_draw_draws_nothing():
    """No schools in the class, a team not in the cycle, or no region the season before: no image."""
    assert ri.render_class_regions(7, [2027, 2028], S27, "light") == []
    assert ri.render_team_region("Nobody", [2027, 2028], S27, S26, {}, "light") == []
    assert ri.render_team_regions_compared("North Tippah", [2027, 2028], S27, S26, {}, "light") == []


def test_region_colors_are_the_pages():
    """The images' region colors are the page's (app.css --region-N, light then dark)."""
    import re
    from pathlib import Path

    css = (Path(__file__).resolve().parents[3] / "nginx" / "html" / "static" / "css" / "app.css").read_text()
    for theme, block in (("light", css.split("--region-1:", 1)[1]), ("dark", css.split("--region-1:", 2)[2])):
        found = re.findall(r"--region-(\d):\s*(#[0-9A-Fa-f]{6})", "--region-1:" + block)[:8]
        assert [c.upper() for _, c in found] == list(ri.REGION_COLORS[theme]), theme
