"""Each season's region assignments, from the checked-in files in ``backend/data/regions/``.

MHSAA assigns classes and regions on a two-year cycle, and each cycle has one file,
``{first}-{last two digits}.csv`` (``2027-29.csv`` for the 2027 and 2028 seasons), one school a line::

    school,class,region,seasons
    Ashland,1,1,
    Leake Central,4,5,2025

``school`` is the site's name for the school. ``seasons`` is blank for every season of the cycle,
or names the one season a line holds for (a school that moved, closed or was renamed mid-cycle).

``assignments_for_season`` gives a season's schools; ``problems`` checks them before anything is
loaded: every name a school the site knows or one the changes in ``data_helpers`` add, no school
twice, every class's regions numbered from 1 with enough teams to play, and every school from the
season before accounted for (still here, renamed, continued by another, or closed).
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from backend.helpers.data_helpers import (
    SCHOOL_CLOSURES,
    SCHOOL_RENAMES,
    SCHOOL_SUCCESSORS,
    school_name_for_season,
)

REGIONS_DIR = Path(__file__).resolve().parents[1] / "data" / "regions"
FIELDS = ["school", "class", "region", "seasons"]
MIN_REGION_TEAMS = 3  # fewer can't make a region (four playoff seeds, one of them a bye at most)


def cycle_start(season: int) -> int:
    """The first season of *season*'s cycle (cycles start in odd years: 2026 is in 2025's)."""
    return season if season % 2 == 1 else season - 1


def cycle_path(season: int) -> Path:
    """The file for *season*'s cycle: ``2025-27.csv`` for 2025 and 2026."""
    first = cycle_start(season)
    return REGIONS_DIR / f"{first}-{(first + 2) % 100:02d}.csv"


def read_cycle(path: Path) -> list[dict]:
    """A cycle file's lines as {school, class, region, seasons}; ``seasons`` is a set (empty: every season)."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != FIELDS:
            raise ValueError(
                f"{path.name}: the header must be {','.join(FIELDS)}, not {','.join(reader.fieldnames or [])}"
            )
        rows = []
        for n, line in enumerate(reader, start=2):
            try:
                seasons = {int(s) for s in (line["seasons"] or "").split()}
                rows.append(
                    {
                        "school": line["school"].strip(),
                        "class": int(line["class"]),
                        "region": int(line["region"]),
                        "seasons": seasons,
                    }
                )
            except (TypeError, ValueError) as e:
                raise ValueError(f"{path.name} line {n}: {e}") from None
    return rows


def assignments_for_season(season: int, path: Path | None = None) -> dict[str, tuple[int, int]]:
    """Each school's (class, region) in *season*, from its cycle's file: the lines for every season of
    the cycle and the ones naming *season*. Raises ValueError for a school given two places."""
    out: dict[str, tuple[int, int]] = {}
    path = path or cycle_path(season)
    for row in read_cycle(path):
        if row["seasons"] and season not in row["seasons"]:
            continue
        if row["school"] in out:
            raise ValueError(f"{path.name}: {row['school']} is listed more than once for {season}")
        out[row["school"]] = (row["class"], row["region"])
    return out


def new_names(season: int) -> set[str]:
    """Schools that start in *season* under a name the site hasn't had: renames and successors."""
    return {new for _, new, first in [*SCHOOL_RENAMES, *SCHOOL_SUCCESSORS] if first == season}


def accounted_for(school: str, season: int, assigned: dict) -> bool:
    """True when last season's *school* is here in *season*: under its own or its new name, continued
    by another school, or closed after last season."""
    if school_name_for_season(school, season) in assigned:
        return True
    if any(old == school and first == season and new in assigned for old, new, first in SCHOOL_SUCCESSORS):
        return True
    return any(name == school and last == season - 1 for name, last, _ in SCHOOL_CLOSURES)


def problems(assigned: dict[str, tuple[int, int]], season: int, known: set[str], prior: set[str] | None) -> list[str]:
    """What's wrong with *season*'s assignments, as sentences ([] when nothing is). *known* is every
    school the site has (``schools``); *prior* the schools of the season before (None to skip that check)."""
    out = []
    allowed = known | new_names(season)
    for school in sorted(set(assigned) - allowed):
        out.append(
            f"{school} isn't a school the site knows. Fix the spelling to the site's name, or add it to "
            f"SCHOOL_RENAMES or SCHOOL_SUCCESSORS (or to schools, for a school that's new)."
        )
    by_class: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for clazz, region in assigned.values():
        by_class[clazz][region] += 1
    for clazz in range(1, 8):
        regions = by_class.get(clazz)
        if not regions:
            out.append(f"Class {clazz}A has no schools.")
            continue
        if sorted(regions) != list(range(1, len(regions) + 1)):
            out.append(f"Class {clazz}A's regions aren't numbered 1 to {len(regions)}: {sorted(regions)}.")
        for region, n in sorted(regions.items()):
            if n < MIN_REGION_TEAMS:
                out.append(f"Region {region}-{clazz}A has {n} {'school' if n == 1 else 'schools'}.")
    for clazz in sorted(set(by_class) - set(range(1, 8))):
        out.append(f"Class {clazz} isn't a class (1-7).")
    for school in sorted(prior or ()):
        if not accounted_for(school, season, assigned):
            out.append(
                f"{school} played in {season - 1} but isn't in {season}'s file. Add it, or record its "
                f"closure (SCHOOL_CLOSURES), rename (SCHOOL_RENAMES) or successor (SCHOOL_SUCCESSORS)."
            )
    return out
