"""The Counties pages' share images: a county's, its two seasons compared, its every season, every county
shaded, and the link previews."""

import pytest

from backend.helpers import region_county_image as rc
from backend.helpers import region_map as rm
from backend.helpers import region_map_image as rmi
from backend.helpers import region_pages as rp


def _row(school, clazz, region, lat, lon):
    """A school's row at a latitude and longitude, projected, with its county."""
    x, y = rm.project(lat, lon)
    return {
        "school": school,
        "class": clazz,
        "region": region,
        "x": x,
        "y": y,
        "county": rm.county_of(x, y),
        "city": "",
    }


WALNUT, FALKNER, RIPLEY = (34.9487, -88.9054), (34.8473, -88.9311), (34.7298, -88.9509)
S26 = [
    _row("Walnut", 2, 1, *WALNUT),
    _row("Falkner", 1, 2, *FALKNER),
    _row("Ripley", 4, 3, *RIPLEY),
    _row("Biggersville", 1, 2, 34.8981, -88.5598),
    _row("Ashland", 2, 1, 34.8329, -89.1776),
    _row("Kossuth", 4, 3, 34.8740, -88.6487),
]
S27 = [
    _row("North Tippah", 3, 2, *WALNUT),
    _row("Ripley", 3, 1, *RIPLEY),
    _row("Ashland", 3, 2, 34.8329, -89.1776),
    _row("Kossuth", 3, 1, 34.8740, -88.6487),
]


def test_the_rows_are_in_tippah():
    assert {r["county"] for r in S26 if r["school"] in ("Walnut", "Falkner", "Ripley")} == {"Tippah"}


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_countys_images_are_the_sites_sizes(theme):
    """The county's own, its two seasons and its every season: one page each, 1080 wide at 2x."""
    older = {"label": "2026", "seasons": [2026], "schools": S26}
    newer = {"label": "2027 and 2028", "seasons": [2027, 2028], "schools": S27}
    pages = [
        rc.render_county("Tippah", [2027, 2028], S27, theme),
        rc.render_county_compared("Tippah", older, newer, theme),
    ]
    assert all(len(p) == 1 and p[0].size == rmi.SIZE for p in pages)
    (timeline,) = rc.render_county_timeline(
        "Tippah", [{"seasons": [2026], "schools": S26}, {"seasons": [2027, 2028], "schools": S27}], theme
    )
    assert timeline.size[0] == rmi.SIZE[0]
    (state,) = rc.render_counties([2027, 2028], {"Tippah": 2, "Hinds": 9}, theme)
    assert state.size == rmi.SIZE


def test_the_link_previews_are_the_sites_size():
    assert [p.size for p in rc.render_county_card("Tippah", [2027, 2028], S27)] == [(1200, 630)]
    assert [p.size for p in rc.render_counties_card([2027, 2028], {"Tippah": 2})] == [(1200, 630)]


def test_a_county_with_no_school_has_no_image():
    """Issaquena has no MHSAA school: no image, and no timeline (nor a compare with none either side)."""
    assert rc.render_county("Issaquena", [2027], S27, "light") == []
    assert rc.render_county_card("Issaquena", [2027], S27) == []
    side = {"label": "2027", "seasons": [2027], "schools": S27}
    assert rc.render_county_compared("Issaquena", {**side, "label": "2026", "seasons": [2026]}, side, "light") == []
    assert rc.render_county_timeline("Issaquena", [{"seasons": [2027], "schools": S27}], "light") == []


def test_a_countys_map_stays_over_mississippi():
    """The window around a county on the state line is moved inland, the county still in it, in the
    asked-for shape."""
    sx0, sy0, sx1, sy1 = rm.state().bounds
    cx0, cy0, cx1, cy1 = rm.counties()["Tippah"].bounds
    x0, y0, x1, y1 = rc.county_bounds("Tippah", 0.6)
    assert abs((x1 - x0) / (y1 - y0) - 0.6) < 1e-9
    assert y1 <= sy1 + 1e-6 and x0 <= cx0 and y0 <= cy0 and x1 >= cx1 and y1 >= cy1


def test_the_shades_are_the_pages():
    """None is the land's own color; then more of the site's green, all of it at 5 or more."""
    assert rc.shade_color("light", 4) == rc.BRAND["light"] and rc.shade_color("dark", 4) == rc.BRAND["dark"]
    assert len({rc.shade_color("light", s) for s in range(5)}) == 5


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_pill_reads_at_wcag_aa(theme):
    """Each class's pill, at any tone, in either theme: its ink on its color at 4.5:1 or more, and the
    images draw the same colors the page does."""
    for clazz in range(1, 8):
        for tone in (0, 0.25, 1 / 3, 0.5, 2 / 3, 0.75, 1):
            shade = rp.shade_in(theme, clazz, tone)
            assert rp.contrast(shade["fill"], shade["ink"]) >= 4.5, (clazz, tone, shade)
    mine = [{"school": "A", "class": 7, "region": 3}, {"school": "B", "class": 7, "region": 4}]
    page = rp.county_shades(mine)
    assert rc.place_shades(theme, mine) == {k: (v[theme]["fill"], v[theme]["ink"]) for k, v in page.items()}


def test_the_most_lists_every_county_tied_with_the_last_one_shown():
    """Twelve wanted, but a fifth county with 5 schools is as many as the twelfth, so it's listed too."""
    counts = {"Hinds": 9, "Rankin": 9, "DeSoto": 8, "Harrison": 8, "Jackson": 8, "Forrest": 6, "Lee": 6}
    counts |= {"Madison": 6, "Lauderdale": 5, "Lincoln": 5, "Monroe": 5, "Scott": 5, "Washington": 5}
    counts |= {"Alcorn": 4, "Issaquena": 0}
    most = rc.most_counties(counts, room=30)
    assert len(most) == 13
    assert most[-1] == ("Washington", 5)
    # With room for only twelve, the tie at 5 is left off whole, not cut through.
    assert [n for _, n in rc.most_counties(counts, room=12)] == [9, 9, 8, 8, 8, 6, 6, 6]
    # A county with none is never one of "the most".
    assert rc.most_counties({"A": 1, "B": 0}) == [("A", 1)]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_countys_independent_is_a_gray_pill(theme):
    """A county's independent (no region) gets the neutral "Ind. 1A" pill, on its map and in its list,
    and every county image still draws."""
    indy = {**next(r for r in S27 if r["county"] == "Tippah"), "school": "Indy", "class": 1, "region": None}
    schools = [*S27, indy]
    assert rp.pill_text(indy) == "Ind. 1A" and rp.place_key(indy) == "1-ind"
    assert rc.place_shades(theme, [indy]) == {"1-ind": tuple(rp.INDEPENDENT_SHADE[theme].values())}
    assert all(len(p) == 1 for p in [rc.render_county("Tippah", [2027], schools, theme)])
    older = {"label": "2026", "seasons": [2026], "schools": S26}
    newer = {"label": "2027", "seasons": [2027], "schools": schools}
    assert len(rc.render_county_compared("Tippah", older, newer, theme)) == 1
    assert len(rc.render_county_timeline("Tippah", [older, newer], theme)) == 1
