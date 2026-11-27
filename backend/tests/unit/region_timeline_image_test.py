"""The Timeline view's images: a class's regions, and a team's, every season on one image."""

import pytest

from backend.helpers import region_map as rm
from backend.helpers import region_map_image as rmi
from backend.helpers import region_timeline_image as rt


def _row(school, clazz, region, lat, lon):
    """A school's row at a latitude and longitude, projected."""
    x, y = rm.project(lat, lon)
    return {"school": school, "class": clazz, "region": region, "x": x, "y": y}


WALNUT, FALKNER = (34.9487, -88.9054), (34.8473, -88.9311)
S25 = [
    _row("Walnut", 2, 1, *WALNUT),
    _row("Falkner", 1, 2, *FALKNER),
    _row("Biggersville", 1, 2, 34.8981, -88.5598),
    _row("Ashland", 2, 1, 34.8329, -89.1776),
]
S27 = [
    _row("North Tippah", 3, 2, *WALNUT),
    _row("Ashland", 3, 2, 34.8329, -89.1776),
    _row("Biggersville", 1, 2, 34.8981, -88.5598),
]


def _cycle(seasons, rows, mine):
    """A team's season: its rows (by name) and its regions' schools."""
    places = {(r["class"], r["region"]) for r in rows if r["school"] in mine}
    return {
        "seasons": seasons,
        "rows": [r for r in rows if r["school"] in mine],
        "schools": [r for r in rows if (r["class"], r["region"]) in places],
    }


def test_the_grid_fits_any_number_of_seasons():
    """A few seasons make a row; decades of them more rows, no map narrower than MIN_CELL, and the image
    as tall as its rows need."""
    one, three, many = rt.grid(1, 100), rt.grid(3, 100), rt.grid(40, 100)
    assert one[0] == 1 and one[1] == rt.MAX_CELL
    assert three[0] == 3  # one row, not two with a gap
    assert many[1] >= rt.MIN_CELL and many[0] * many[1] <= rt.WIDTH
    assert many[2] > three[2]


def test_cycle_and_span_words():
    """How the images name a season of regions and the seasons they cover."""
    assert (rt.cycle_label([2027, 2028]), rt.cycle_label([2026]), rt.cycle_label([1999, 2000])) == (
        "2027–28",
        "2026",
        "1999–00",
    )
    assert rt.span_line([{"seasons": [1990]}, {"seasons": [2027, 2028]}]) == "1990 to 2028 seasons"
    assert rt.span_line([{"seasons": [2026]}]) == "2026 season"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_class_over_the_seasons(theme):
    """One image, the site's width; seasons without the class are left out, and a class in none draws
    nothing."""
    cycles = [{"seasons": [2025, 2026], "schools": S25}, {"seasons": [2027, 2028], "schools": S27}]
    pages = rt.render_class_timeline(1, cycles, theme)
    assert len(pages) == 1 and pages[0].size[0] == rt.WIDTH
    assert rt.render_class_timeline(7, cycles, theme) == []


def test_a_class_over_decades_still_one_image():
    """Twenty seasons of regions: one image, taller than wide, no wider than the site's."""
    cycles = [{"seasons": [y, y + 1], "schools": S25} for y in range(1989, 2029, 2)]
    (page,) = rt.render_class_timeline(1, cycles, "light")
    assert page.size[0] == rt.WIDTH and page.size[1] > page.size[0]


def test_a_team_over_the_seasons_before_and_after_a_consolidation():
    """North Tippah before 2027 is Walnut and Falkner, each in its region; its seasons before any region
    are left out, and one between with none still drawn."""
    cycles = [
        {"seasons": [2021, 2022], "rows": [], "schools": []},  # before: left out
        _cycle([2023, 2024], S25, {"Walnut"}),
        {"seasons": [2025], "rows": [], "schools": []},  # between: "Not in a region"
        _cycle([2026], S25, {"Walnut", "Falkner"}),
        _cycle([2027, 2028], S27, {"North Tippah"}),
    ]
    pages = rt.render_team_timeline("North Tippah", cycles, {}, "dark")
    assert len(pages) == 1 and pages[0].size[0] == rt.WIDTH
    assert rt.render_team_timeline("North Tippah", [{"seasons": [2025], "rows": [], "schools": []}], {}, "dark") == []


def test_two_places_never_share_a_color():
    """Schools merged later, in regions of the same number in different classes, get different colors;
    one region keeps its own."""
    rows = [{"class": 4, "region": 5}, {"class": 1, "region": 5}, {"class": 4, "region": 5}]
    colors = rt._place_colors("light", rows)
    assert colors[4, 5] == rmi.region_color("light", 5)
    assert colors[1, 5] != colors[4, 5] and len(colors) == 2


def test_a_timeline_with_an_independent_season():
    """A team that was an independent one season: its map has just its own dashed dot, its line says
    "1A Independent"; the class's timeline counts only the regions."""
    x, y = rm.project(34.61371, -89.19164)
    a, b = rm.project(34.8329, -89.1745)
    hickory = {"school": "Hickory Flat", "class": 1, "region": None, "x": x, "y": y}
    ashland = {"school": "Ashland", "class": 1, "region": 1, "x": a, "y": b}
    cycles = [{"seasons": [2017], "rows": [hickory], "schools": [hickory]}]
    assert len(rt.render_team_timeline("Hickory Flat", cycles, {}, "light")) == 1
    assert rt._place_colors("light", [hickory]) == {(1, None): rmi.INDEPENDENT}
    assert len(rt.render_class_timeline(1, [{"seasons": [2017], "schools": [ashland, hickory]}], "dark")) == 1
