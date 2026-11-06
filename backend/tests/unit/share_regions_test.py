"""The Regions pages' files: each season's data, the page without JavaScript and its previews, and the
images to share, from ``/teams`` for each season a region file covers."""

import json
from datetime import date

import pytest

import backend.prefect.share_regions as sr
from backend.helpers.region_pages import season_options


def _team(school, clazz, region, lat=33.5, lon=-89.8):
    """A school as ``/teams`` gives it."""
    return {"school": school, "class_": clazz, "region": region, "latitude": lat, "longitude": lon, "city": "Town"}


S26 = [
    _team("Greenwood", 4, 4, 33.5162, -90.1795),
    _team("Yazoo City", 4, 4, 32.8551, -90.4056),
    _team("Leake", 5, 2, 32.7726, -89.5370),
    _team("Walnut", 2, 1, 34.9487, -88.9054),
]
S27 = [
    _team("Greenwood", 5, 2, 33.5162, -90.1795),
    _team("Leake", 5, 2, 32.7726, -89.5370),
    _team("Natchez", 5, 1, 31.5604, -91.4032),
    _team("North Tippah", 3, 2, 34.9487, -88.9054),
    _team("Lost", 5, 1, 35.1495, -90.0490),  # coordinates in Memphis: listed, but no dot
]
TEAMS = {2026: S26, 2027: S27, 2028: S27}


@pytest.fixture
def written(tmp_path, monkeypatch):
    """Run the step on the seasons above, recording the image jobs instead of drawing them."""
    jobs = []

    def draw(out_dir, todo, prune=(), files_out=None):
        """Record the jobs instead of drawing them."""
        jobs.extend(todo)
        return {"drawn": len(todo), "kept": 0, "removed": 0}

    monkeypatch.setattr(sr, "draw_images", draw)

    def fetch(path):
        """The API: each season's schools, and nothing else."""
        if path.startswith("/teams?season="):
            return TEAMS.get(int(path.split("=")[1]), [])
        return None

    def write(path, text):
        """Write a file, making its folder."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    counts, sitemap = sr.write_regions(fetch, tmp_path, "https://example.com", date(2026, 11, 6), [2026, 2025], write)
    return tmp_path, counts, sitemap, jobs


def test_each_season_and_the_choices(written):
    """2027 and 2028 have the same regions, so they're one choice; 2026 is its own."""
    out, counts, _, _ = written
    index = json.loads((out / "regions" / "index.json").read_text())
    assert index["default"] == 2027 and index["current_season"] == 2026
    assert [(o["season"], o["label"]) for o in index["options"]] == [(2027, "2027 and 2028"), (2026, "2026")]
    assert counts["region_maps"] == 2
    assert (out / "regions" / "map.json").exists() and not (out / "regions" / "2028.json").exists()


def test_a_seasons_data(written):
    """Every school with where it was the season before; one with no place in Mississippi has no dot."""
    out, *_ = written
    data = json.loads((out / "regions" / "2027.json").read_text())
    by = {s["school"]: s for s in data["schools"]}
    assert by["Greenwood"]["before"] == {"class": 4, "region": 4} and by["Greenwood"]["x"] is not None
    assert by["North Tippah"]["before"] is None and by["North Tippah"]["successor_of"] == "Walnut"
    assert by["Lost"]["x"] is None and by["Lost"]["county"] is None
    assert data["prior_season"] == 2026 and data["standings_season"] is None  # 2027 has no games yet
    assert set(data["regions"]["5"]) == {"1", "2"} and data["regions"]["5"]["2"]["d"].startswith("M")


def test_the_page_without_javascript_and_its_previews(written):
    """The newest choice's page per class, its preview and each team's, and a sitemap entry."""
    out, _, sitemap, _ = written
    body = (out / "body" / "regions-5.html").read_text()
    assert '<a href="/standings/5a">Class 5A</a>' in body and "Class 5A Regions" in body
    assert "2027 and 2028 seasons · MHSAA 2027–29 regions" in body
    assert "4A-4 in 2026" in body and ">Region 2</h2>" in body  # no standings yet: the heading isn't a link
    meta = (out / "meta" / "regions-5.html").read_text()
    assert "https://example.com/static/og/regions-5.png?v=20261106" in meta
    assert (
        "https://example.com/regions/5a?team=greenwood" in (out / "meta" / "regions-5" / "greenwood.html").read_text()
    )
    assert ("/regions/5a", None, ["https://example.com/static/regions/2027/5a-light.png"]) in sitemap


def test_the_images(written):
    """Each class's map and preview, each team's region and preview, and its two regions compared when it
    had one the season before (North Tippah, new, has none)."""
    *_, jobs = written
    paths = {j.path for j in jobs}
    assert {"regions/2027/5a-light.png", "regions/2027/5a-dark.png", "og/regions-5.png"} <= paths
    assert {"regions/2027/team/greenwood-dark.png", "regions/2027/compare/greenwood-dark.png"} <= paths
    assert "regions/2027/team/north-tippah-light.png" in paths
    assert "regions/2027/compare/north-tippah-light.png" not in paths
    job = next(j for j in jobs if j.path == "regions/2027/team/greenwood-light.png")
    assert {s["school"] for s in job.kwargs["schools"]} == {"Greenwood", "Leake", "Natchez", "Lost"}


def test_seasons_with_different_regions_stay_apart():
    """Two seasons of a cycle are one choice only when every school is in the same place both."""
    a = [{"school": "A", "class": 1, "region": 1}]
    b = [{"school": "A", "class": 1, "region": 2}]
    assert [o["seasons"] for o in season_options({2025: a, 2026: b})] == [[2026], [2025]]
    assert [o["seasons"] for o in season_options({2025: a, 2026: a})] == [[2025, 2026]]
    assert [o["seasons"] for o in season_options({2026: a, 2027: a})] == [[2027], [2026]]  # different cycles
