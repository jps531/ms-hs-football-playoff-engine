"""A season's regions come from its cycle's checked-in file (backend/data/regions/), checked before
they're loaded; the draft tool reads MHSAA's article in either layout it has used."""

import pytest

from backend.helpers.region_files import (
    REGIONS_DIR,
    assignments_for_season,
    cycle_path,
    cycle_start,
    problems,
    read_cycle,
)
from backend.prefect.regions_data_pipeline import check_season
from backend.tools.draft_regions import draft, parse_tables, site_name, to_csv

# ----------------------------------------------------------------- the files


def test_a_season_reads_its_cycles_file():
    """Cycles start in odd years; an even season reads the cycle that began the year before."""
    assert (cycle_start(2025), cycle_start(2026), cycle_start(2027)) == (2025, 2025, 2027)
    assert cycle_path(2026).name == "2025-27.csv" and cycle_path(2028).name == "2027-29.csv"
    assert cycle_path(2099).name == "2099-01.csv"


def test_a_line_for_one_season_holds_only_then():
    """The 2025-27 file has Leake Central (4A-5) and Leake County (1A-5) for 2025, and Leake (5A-2) for 2026."""
    s25, s26 = assignments_for_season(2025), assignments_for_season(2026)
    assert s25["Leake Central"] == (4, 5) and s25["Leake County"] == (1, 5) and "Leake" not in s25
    assert s26["Leake"] == (5, 2) and "Leake Central" not in s26 and "Leake County" not in s26
    assert s25["Raleigh"] == s26["Raleigh"] == (3, 6)


@pytest.mark.parametrize("path", sorted(REGIONS_DIR.glob("*.csv")), ids=lambda p: p.name)
def test_every_file_passes_its_own_checks(path):
    """Each season of each cycle: every region numbered and big enough, no school twice, and every school
    from the season before (the previous file) accounted for."""
    first = int(path.name[:4])
    known = set()
    for f in sorted(REGIONS_DIR.glob("*.csv")):
        known |= {row["school"] for row in read_cycle(f)}
    for season in (first, first + 1):
        prior_path = cycle_path(season - 1)
        prior = set(assignments_for_season(season - 1, prior_path)) if prior_path.exists() else None
        assert problems(assignments_for_season(season, path), season, known, prior) == [], season


def test_the_2027_cycle_has_north_tippah_and_not_its_old_schools():
    """North Tippah replaces Falkner and Walnut in 2027."""
    s27 = assignments_for_season(2027)
    assert s27["North Tippah"] == (3, 2)
    assert "Walnut" not in s27 and "Falkner" not in s27
    # MHSAA's spellings land on the site's names.
    assert {"O’Bannon", "St. Andrew’s", "Thomas E. Edwards", "Jefferson Davis County"} <= set(s27)


def _write(tmp_path, lines):
    """A 2025-27 file of *lines* under *tmp_path*."""
    path = tmp_path / "2025-27.csv"
    path.write_text("school,class,region,seasons\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_a_bad_file_says_where(tmp_path):
    """A wrong header, a bad line or a school listed twice for a season is an error naming the file."""
    with pytest.raises(ValueError, match="header"):
        bad = tmp_path / "x.csv"
        bad.write_text("school,class\nRaleigh,3\n", encoding="utf-8")
        read_cycle(bad)
    with pytest.raises(ValueError, match="line 2"):
        read_cycle(_write(tmp_path, ["Raleigh,3,six,"]))
    with pytest.raises(ValueError, match="more than once"):
        assignments_for_season(2025, _write(tmp_path, ["Raleigh,3,6,", "Raleigh,3,5,2025"]))


# ----------------------------------------------------------------- the checks


def _season(regions: dict[tuple[int, int], int]) -> dict[str, tuple[int, int]]:
    """A season with *regions* ({(class, region): number of schools}), every school named after its spot."""
    return {f"S{c}-{r}-{i}": (c, r) for (c, r), n in regions.items() for i in range(n)}


FULL = {(c, r): 4 for c in range(1, 8) for r in range(1, (9 if c <= 4 else 5))}


def test_a_well_formed_season_has_no_problems():
    """Seven classes, regions numbered from 1, four schools each, everyone from last season here."""
    season = _season(FULL)
    assert problems(season, 2027, set(season), set(season)) == []


def test_each_problem_is_named():
    """A misspelled name, a small region, a gap in the numbering, a missing school and an empty class."""
    season = _season({**FULL, (3, 2): 2})
    del season["S6-4-0"], season["S6-4-1"], season["S6-4-2"], season["S6-4-3"]  # 6A's region 4 gone…
    season["S6-5-0"] = season["S6-5-1"] = season["S6-5-2"] = (6, 5)  # …and a region 5 instead
    season["Mispelled"] = (1, 1)
    known = set(season) - {"Mispelled"}
    out = problems(season, 2027, known, known | {"Gone"})
    assert any("Mispelled isn't a school the site knows" in p for p in out)
    assert "Region 2-3A has 2 schools." in out
    assert "Class 6A's regions aren't numbered 1 to 4: [1, 2, 3, 5]." in out
    assert any(p.startswith("Gone played in 2026 but isn't in 2027's file") for p in out)
    assert "Class 7A has no schools." in problems({k: v for k, v in season.items() if v[0] != 7}, 2027, known, None)


def test_a_rename_successor_or_closure_accounts_for_last_seasons_school():
    """Leake Central is Leake in 2026; Walnut carries on as North Tippah in 2027; Falkner closed after 2026."""
    s26 = {**_season(FULL), "Leake": (5, 2)}
    assert problems(s26, 2026, set(s26), set(s26) - {"Leake"} | {"Leake Central", "Leake County"}) == []
    s27 = {**_season(FULL), "North Tippah": (3, 2)}
    prior = set(s27) - {"North Tippah"} | {"Walnut", "Falkner"}
    assert problems(s27, 2027, set(s27) - {"North Tippah"}, prior) == []  # North Tippah is new, and allowed


def test_the_loader_also_catches_a_school_active_in_the_database_but_not_in_the_file():
    """A school the database has active for the season but the file doesn't list stops the load."""
    assigned, issues = check_season(2027, known=set(assignments_for_season(2027)), prior=set(), active={"Ghost"})
    assert issues == [
        "Ghost is active in the database for 2027 but not in its file. Add it to the file, or deactivate it "
        "(PATCH /api/v1/admin/school-seasons/Ghost/2027)."
    ]
    assert len(assigned) == 224


# ----------------------------------------------------------------- the draft tool

# MHSAA's 2025-27 layout: one table, "Class 7A" heading rows, then school, class and region.
OLD = """<div class="entry"><table><tbody>
<tr><td>2025-27 Football Regions</td><td></td><td></td></tr>
<tr><td colspan="3">Class 7A</td></tr>
<tr><td>School Name</td><td>Class</td><td>Region</td></tr>
<tr><td>DESOTO CENTRAL HIGH SCHOOL</td><td>7</td><td>1</td></tr>
<tr><td colspan="3">Class 4A</td></tr>
<tr><td>School Name</td><td>Class</td><td>Region</td></tr>
<tr><td>LEAKE CENTRAL HIGH SCHOOL</td><td>5</td><td>2</td></tr>
<tr><td>Jefferson Co High</td><td>4</td><td>7</td></tr>
</tbody></table></div>"""

# The 2027-29 layout (a page embedded in the article): a heading per class, then school and "Region N".
NEW = """<h1>Football Regions</h1>
<h2>Football — 3A (boys)</h2>
<table><tr><th>School</th><th>Region</th></tr>
<tr><td>NORTH TIPPAH HIGH SCHOOL</td><td>Region 2</td></tr>
<tr><td>O'BANNON HIGH SCHOOL</td><td>Region 3</td></tr>
<tr><td>St. Andrews</td><td>Region 6</td></tr>
<tr><td>JDC HIGH SCHOOL</td><td>Region 7</td></tr></table>
<h2>Football — 2A (boys)</h2>
<table><tr><th>School</th><th>Region</th></tr>
<tr><td>THOMAS E. EDWARDS, SR. HIGH SCHOOL</td><td>Region 3</td></tr></table>"""


def test_the_draft_reads_both_layouts_under_the_sites_names():
    """Both MHSAA layouts, with its spellings turned into the site's names."""
    assert parse_tables(OLD) == [
        (7, "DESOTO CENTRAL HIGH SCHOOL", 1),
        (5, "LEAKE CENTRAL HIGH SCHOOL", 2),
        (4, "Jefferson Co High", 7),
    ]
    # The class column wins over the heading; a school renamed for the season gets its new name.
    assert draft([OLD], 2026) == {"DeSoto Central": (7, 1), "Leake": (5, 2), "Jefferson County": (4, 7)}
    assert draft([NEW], 2027) == {
        "North Tippah": (3, 2),
        "O’Bannon": (3, 3),
        "St. Andrew’s": (3, 6),
        "Jefferson Davis County": (3, 7),
        "Thomas E. Edwards": (2, 3),
    }
    assert site_name("ST. ANDREWS", 2027) == "St. Andrew’s"


def test_the_draft_is_a_file_the_loader_reads(tmp_path):
    """The draft is a valid cycle file, sorted by class, region and name."""
    path = tmp_path / "2027-29.csv"
    path.write_text(to_csv(draft([NEW], 2027)), encoding="utf-8")
    assert assignments_for_season(2027, path)["North Tippah"] == (3, 2)
    assert path.read_text(encoding="utf-8").splitlines()[:2] == [
        "school,class,region,seasons",
        "Thomas E. Edwards,2,3,",
    ]
