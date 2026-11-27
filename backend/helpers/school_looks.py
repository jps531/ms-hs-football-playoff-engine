"""A school's past looks (mascot and colors by season), from the checked-in file
``backend/data/school_looks.csv``, one look a line::

    school,first_season,last_season,mascot,primary_color,secondary_color,primary_color_hex,secondary_color_hex,approximate,note
    Shaw,,2019,Hawks,Green,Gold,#00843D,#FFC72C,yes,The Shaw Hawks through 2019; ...

``school`` is the site's name for the school (its current name: a renamed school's past looks are under
the name it has now). ``first_season`` blank is as far back as known, ``last_season`` blank still in
use (a school's look now belongs in ``schools``, so a line here mostly has a last season).
``approximate`` (yes/no) marks hex colors that are standard shades for the named colors, not the
school's own. A season no line covers has the school's look now.

``read_looks`` reads the file; ``problems`` checks it before anything is loaded (``school_looks_pipeline``).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

LOOKS_PATH = Path(__file__).resolve().parents[1] / "data" / "school_looks.csv"
FIELDS = [
    "school",
    "first_season",
    "last_season",
    "mascot",
    "primary_color",
    "secondary_color",
    "primary_color_hex",
    "secondary_color_hex",
    "approximate",
    "note",
]
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _season(text: str | None) -> int | None:
    """A blank cell's None, or the season."""
    text = (text or "").strip()
    return int(text) if text else None


def read_looks(path: Path = LOOKS_PATH) -> list[dict]:
    """The file's looks, each {school, first_season, last_season, mascot, primary_color, secondary_color,
    primary_color_hex, secondary_color_hex, approximate, note}: seasons None where blank, text None where
    blank, approximate a bool. Raises ValueError for a wrong header or a line that doesn't read."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != FIELDS:
            raise ValueError(f"{path.name}: the header must be {','.join(FIELDS)}")
        looks = []
        for n, line in enumerate(reader, start=2):
            try:
                approximate = (line["approximate"] or "").strip().lower()
                if approximate not in ("yes", "no", ""):
                    raise ValueError(f"approximate is {approximate!r}, not yes or no")
                looks.append(
                    {
                        "school": line["school"].strip(),
                        "first_season": _season(line["first_season"]),
                        "last_season": _season(line["last_season"]),
                        **{k: (line[k] or "").strip() or None for k in FIELDS[3:8]},
                        "approximate": approximate == "yes",
                        "note": (line["note"] or "").strip() or None,
                    }
                )
            except (TypeError, ValueError) as e:
                raise ValueError(f"{path.name} line {n}: {e}") from None
    return looks


def problems(looks: list[dict], known: set[str]) -> list[str]:
    """What's wrong with the looks, as sentences ([] when nothing is): a school the site doesn't know, a
    span that ends before it starts, a hex color that isn't #RRGGBB, or two looks of a school whose
    seasons overlap. *known* is every school the site has (``schools``)."""
    out = []
    for look in looks:
        name = look["school"]
        if name not in known:
            out.append(f"{name} isn't a school the site knows: use its name on the site (its name now).")
        first, last = look["first_season"], look["last_season"]
        if first is not None and last is not None and first > last:
            out.append(f"{name}'s look from {first} ends in {last}, before it starts.")
        for key in ("primary_color_hex", "secondary_color_hex"):  # (secondary: one or more, comma-joined)
            value = look[key]
            if value is not None and not all(HEX.match(h.strip()) for h in value.split(",")):
                out.append(f"{name}'s {key} is {value!r}, not a color like #00843D.")
    by_school: dict[str, list[dict]] = {}
    for look in looks:
        by_school.setdefault(look["school"], []).append(look)
    for name, mine in sorted(by_school.items()):
        spans = sorted(
            (
                (-(10**6) if lk["first_season"] is None else lk["first_season"]),
                (10**6 if lk["last_season"] is None else lk["last_season"]),
            )
            for lk in mine
        )
        for (_, end), (start, _) in zip(spans, spans[1:], strict=False):
            if start <= end:
                out.append(f"{name} has two looks whose seasons overlap.")
    return out


def look_for(looks: list[dict], school: str, season: int) -> dict | None:
    """*school*'s look in *season* from *looks*, or None (its look now)."""
    return next(
        (
            lk
            for lk in looks
            if lk["school"] == school
            and (lk["first_season"] is None or lk["first_season"] <= season)
            and (lk["last_season"] is None or season <= lk["last_season"])
        ),
        None,
    )
