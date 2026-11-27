"""Schools' past looks (mascot and colors by season) come from backend/data/school_looks.csv, checked
before they're loaded; /teams gives a season's look, and no logo a school didn't use then."""

import pytest

from backend.helpers.region_files import REGIONS_DIR, read_cycle
from backend.helpers.school_looks import LOOKS_PATH, look_for, problems, read_looks


def _write(tmp_path, lines):
    """A looks file of *lines* under *tmp_path*."""
    path = tmp_path / "school_looks.csv"
    path.write_text(
        "school,first_season,last_season,mascot,primary_color,secondary_color,primary_color_hex,"
        "secondary_color_hex,approximate,note\n" + "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return path


def test_the_file_passes_its_own_checks():
    """Every look is a school the region files know, with good colors and no overlapping spans."""
    known = {row["school"] for f in REGIONS_DIR.glob("*.csv") for row in read_cycle(f)}
    looks = read_looks(LOOKS_PATH)
    assert looks and problems(looks, known) == []


def test_shaw_was_the_hawks_through_2019():
    """Shaw's look through 2019: the Hawks, green and gold (standard shades, so approximate); from 2020
    no line covers it, so its look now (the Warriors) holds."""
    looks = read_looks(LOOKS_PATH)
    hawks = look_for(looks, "Shaw", 2017)
    assert (hawks["mascot"], hawks["primary_color"], hawks["secondary_color"]) == ("Hawks", "Green", "Gold")
    assert hawks["approximate"] and hawks["first_season"] is None and hawks["last_season"] == 2019
    assert look_for(looks, "Shaw", 2020) is None


def test_a_file_reads_blanks_as_none_and_says_where_it_is_wrong(tmp_path):
    (look,) = read_looks(_write(tmp_path, ["A,2015,,Eagles,Blue,,#0000FF,,no,"]))
    assert look["first_season"] == 2015 and look["last_season"] is None and look["secondary_color"] is None
    assert look["approximate"] is False and look["note"] is None
    with pytest.raises(ValueError, match="line 2"):
        read_looks(_write(tmp_path, ["A,soon,,Eagles,Blue,,#0000FF,,no,"]))
    with pytest.raises(ValueError, match="approximate"):
        read_looks(_write(tmp_path, ["A,,,Eagles,Blue,,#0000FF,,maybe,"]))
    bad = tmp_path / "x.csv"
    bad.write_text("school,mascot\nA,Eagles\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        read_looks(bad)


def test_each_problem_is_named(tmp_path):
    """An unknown school, a span ending before it starts, a bad color and two overlapping looks."""
    looks = read_looks(
        _write(
            tmp_path,
            [
                "Nowhere,,2019,Hawks,Green,Gold,#00843D,#FFC72C,yes,",
                "A,2020,2018,Eagles,Blue,White,#0000FF,#FFFFFF,no,",
                "B,,2010,Owls,Red,White,red,\"#FFFFFF, #000000\",no,",
                "B,2009,2012,Owls,Red,White,#FF0000,#FFFFFF,no,",
            ],
        )
    )
    out = problems(looks, {"A", "B"})
    assert out == [
        "Nowhere isn't a school the site knows: use its name on the site (its name now).",
        "A's look from 2020 ends in 2018, before it starts.",
        "B's primary_color_hex is 'red', not a color like #00843D.",
        "B has two looks whose seasons overlap.",
    ]
