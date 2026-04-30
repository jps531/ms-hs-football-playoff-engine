"""Helper functions for school name normalization, game result parsing, and pair normalization.

Used by both the Prefect pipeline and the pure-logic modules. Contains name
mapping constants, HTML-to-text utilities, ``get_completed_games()`` for
converting raw DB rows into CompletedGame instances, and school-identity
helpers for mascot normalisation and colour parsing / hex mapping.
"""

import re
import unicodedata
from collections.abc import Mapping

from bs4 import BeautifulSoup

from backend.helpers.data_classes import (
    CompletedGame,
    GameClock,
    GameStatus,
    RawCompletedGame,
)

# -------------------------
# Constants
# -------------------------

SPACE_RE = re.compile(r"\s+")
_NCES_GRADE_RANGE_RE = re.compile(r"\s*\(\d+-\d+\)\s*$")
_NCES_PREMOD_RE = re.compile(r"\s+(?:public|memorial)\b", re.IGNORECASE)
_NCES_SUFFIX_RE = re.compile(
    r"\s+(senior high school|senior high sch|secondary school|middle-high school|middle high school|attendance center|high school|senior high|school|hs|high)\s*$",
    re.IGNORECASE,
)
_NCES_NAME_REMAPS = {
    "Franklin": "Franklin County",
    "Jdc": "Jefferson Davis County",
}


# One source of truth: "official" -> "AHSFHS canonical"
OFFICIAL_TO_AHSFHS: dict[str, str] = {
    "D'Iberville": "DIberville",
    "St. Andrew’s": "Saint Andrews Episcopal",
    "O’Bannon": "OBannon",
    "St. Stanislaus": "Saint Stanislaus",
    "St. Patrick": "Saint Patrick",
    "St. Martin": "Saint Martin",
    "Thomas E. Edwards": "Thomas Edwards",
    "M. S. Palmer": "Palmer",
    "J Z George": "George",
    "H. W. Byers": "Byers",
    "Itawamba Agricultural": "Itawamba AHS",
    "Forrest County Agricultural": "Forrest County AHS",
    "Amanda Elzy": "Elzy",
    "Tupelo Christian": "Tupelo Christian Prep",
    "Jim Hill": "Hill",
    "French Camp": "French Camp Academy",
}

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


# --- REGIONS CLEANING CONFIG ---
CLEAN_PHRASES = [
    r"\bHigh School\b",
    r"\bHigh\b",
    r"\bSchool\b",
    r"\bPublic\b",
    r"\bMemorial\b",
    r"\bSecondary\b",
    r"\bHi Sch\b",
    r"\bSch\b",
    r"\bDist\b",
    r"\bMiddle\b",
    r"\bSenior\b",
    r"\bJr Sr\b",
    r"\bJr\s*[/\\-]?\s*Sr\b",
    r"\(5-12\)",
    r"\(9-12\)",
    r"\bAttendance Center\b",
    r"\bName\b",
    r"\bClass\b",
    r"\bRegion\b",
]

CLEAN_RE = re.compile("|".join(CLEAN_PHRASES), flags=re.IGNORECASE)

# ---------------------------------------------------------------------------
# School identity constants (colour parsing + mascot normalisation)
# ---------------------------------------------------------------------------

# Words that, when they appear at the END of a colour token, signal that the
# NEXT word begins a NEW colour rather than extending the current one.
# e.g. "Royal White" → ["Royal", "White"]; "Red White Blue" → three tokens.
_COLOR_BOUNDARY_WORDS = frozenset({
    "red", "blue", "green", "white", "black", "yellow", "orange",
    "purple", "brown", "gray", "grey", "maroon", "pink", "gold",
    "silver", "royal", "crimson", "scarlet", "teal", "tan",
})

# Two-word colour names that must NOT be split even when the first word is a
# boundary word (e.g. "Royal Blue" is one colour, not two).
_NO_SPLIT_PAIRS = frozenset({
    "royal blue", "navy blue", "kelly green", "forest green",
    "hunter green", "dark green", "midnight blue", "old gold",
    # "Green Bay Gold" — the city-name prefix must not split on "green"
    "green bay",
})

# Known MHSAA directory typos → canonical title-cased spelling.
_COLOR_TYPOS = {
    "whited": "White",
    "re":     "Red",
}

# Canonical hex values keyed by lower-cased colour name.
_COLOR_HEX_MAP: dict[str, str] = {
    # Blues
    "royal blue":      "#4169E1",
    "royal":           "#4169E1",
    "blue":            "#003DA5",
    "navy":            "#001F5B",
    "navy blue":       "#001F5B",
    "columbia blue":   "#9BDDFF",
    "carolina blue":   "#4B9CD3",
    "midnight blue":   "#191970",
    # Greens
    "green":           "#006400",
    "kelly green":     "#4CBB17",
    "forest green":    "#228B22",
    "emerald":         "#50C878",
    # Reds / Pinks
    "red":             "#CC0000",
    "scarlet":         "#FF2400",
    "cardinal":        "#C41E3A",
    "maroon":          "#800000",
    "crimson":         "#990000",
    # Yellows / Golds
    "gold":            "#FFD700",
    "athletic gold":   "#FFB81C",
    "bright gold":     "#FFC72C",
    "vegas gold":      "#C5A028",
    "green bay gold":  "#FFB612",
    "packer gold":     "#FFB612",
    "yellow":          "#FFD100",
    "cardinal yellow": "#FFD100",
    "old gold":        "#CFB53B",
    # Oranges
    "orange":          "#FF6600",
    # Purples
    "purple":          "#6B2D8B",
    "violet":          "#EE82EE",
    "lavender":        "#967BB6",
    # Neutrals
    "black":           "#000000",
    "white":           "#FFFFFF",
    "gray":            "#808080",
    "grey":            "#808080",
    "silver":          "#C0C0C0",
}

# Mascots that must NOT gain a trailing "s" during pluralisation.
_MASCOT_NO_PLURAL = frozenset({"maroon tide"})


# -------------------------
# Helpers
# -------------------------


def to_normal_case(s: str) -> str:
    """Convert a string to title case with special-case handling.

    Applies Python's str.title() then fixes common patterns: ``Mc``-prefixed
    surnames, possessive ``'s`` capitalization, ``D'Iber`` for D'Iberville,
    and bare ``St`` -> ``St.``.

    Args:
        s: Raw string to normalize.

    Returns:
        Title-cased string with the special-case corrections applied.
    """
    if not s:
        return s
    t = s.title()
    t = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), t)
    t = re.sub(r"(['’])S\b", r"\1s", t)
    t = re.sub(r"\bDiber", "D'Iber", t)
    t = re.sub(r"\bSt\b(?!\.)", "St.", t)
    return t


def _norm(s: str) -> str:
    """Normalize a string for fuzzy matching: strip, replace curly quotes, collapse whitespace, lowercase."""
    s = s.strip()
    s = s.replace("’", "'")
    s = SPACE_RE.sub(" ", s).strip()
    return s.lower()


def normalize_nces_school_name(s: str) -> str:
    """Strip boilerplate from an NCES school name for fuzzy matching.

    Handles: grade-range parentheticals like ``(9-12)``, pre-modifiers
    (PUBLIC, MEMORIAL), and suffixes including HIGH SCHOOL, SENIOR HIGH,
    ATTENDANCE CENTER, SECONDARY SCHOOL, MIDDLE-HIGH SCHOOL, and plain
    SCHOOL/HS.  The result is title-cased via ``to_normal_case`` (which
    handles D'Iberville, Mc-prefixes, possessives, St. abbreviations) and
    then checked against known name remaps (e.g. Franklin → Franklin County).

    Args:
        s: Raw NCES ``SCH_NAME`` value.

    Returns:
        Normalized title-case name ready for ``_norm()`` + ``_ratio()`` matching.
    """
    s = s.strip()
    s = _NCES_GRADE_RANGE_RE.sub("", s)
    s = _NCES_PREMOD_RE.sub("", s).strip()
    s = _NCES_SUFFIX_RE.sub("", s).strip()
    s = to_normal_case(s)
    s = re.sub(r"\bSaint\b", "St.", s)
    s = s.replace("J Z George", "J.Z. George")
    s = s.replace("M S Palmer", "M. S. Palmer")
    s = s.replace("H W Byers", "H. W. Byers")
    s = s.replace("Thomas E Edwards", "Thomas E. Edwards")
    return _NCES_NAME_REMAPS.get(s, s)


def update_school_name_for_ahsfhs_search(s: str) -> str:
    """Convert an official school name to the AHSFHS website search term.

    Looks up the name in ``OFFICIAL_TO_AHSFHS``; if found, returns the AHSFHS
    canonical name.  Otherwise URL-encodes spaces for use in a query string.

    Args:
        s: Official MHSAA school name.

    Returns:
        The AHSFHS search name or the original name with spaces replaced by
        ``%20``.
    """
    s = s.strip()

    if s in OFFICIAL_TO_AHSFHS:
        return OFFICIAL_TO_AHSFHS[s]

    return s.replace(" ", "%20")


def get_school_name_from_ahsfhs(s: str) -> str:
    """Convert an AHSFHS canonical school name to the official MHSAA name.

    Performs a reverse lookup in ``OFFICIAL_TO_AHSFHS``.  If the AHSFHS name
    is not found, the original string is returned unchanged.

    Args:
        s: School name as it appears on the AHSFHS website.

    Returns:
        The corresponding official MHSAA school name, or the original string
        if no mapping exists.
    """
    s = s.strip()

    for official_name, ahsfhs_name in OFFICIAL_TO_AHSFHS.items():
        if s == ahsfhs_name:
            return official_name

    return s


def as_float_or_none(x):
    """Convert a value to float, returning None for missing or invalid inputs.

    Args:
        x: Any value to attempt conversion.

    Returns:
        A float if conversion succeeds, or None if x is None, an empty string,
        or otherwise cannot be converted.
    """
    if x is None:
        return None
    if isinstance(x, str) and x.strip() == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _pad(n: int) -> str:
    """Zero-pad an integer to at least 2 digits."""
    return f"{n:02d}"


def _month_to_num(m: str) -> int | None:
    """Convert a month name or abbreviation to its 1-based integer number."""
    m = m.lower().rstrip(".")
    return _MONTHS.get(m)


def _normalize_ws(t: str) -> str:
    """Normalize unicode and whitespace in a raw HTML/text string."""
    # Unicode normalize and tame whitespace weirdness
    t = unicodedata.normalize("NFKC", t)
    t = t.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    # collapse 3+ newlines to 2 to avoid giant gaps
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t


def to_plain_text(html: str) -> str:
    """Convert an HTML string to normalized plain text.

    Strips all tags via BeautifulSoup, then collapses unicode whitespace
    (including non-breaking spaces) and runs of whitespace into single spaces.

    Args:
        html: Raw HTML string.

    Returns:
        Plain text with all tags removed and whitespace normalized.
    """
    # 1) parse HTML → text (inserts spaces between nodes)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ")

    # 2) normalize unicode, convert NBSP to space, collapse whitespace
    text = unicodedata.normalize("NFKC", text).replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_text_section(text: str, start_phrase: str, end_phrase: str) -> str:
    """Extract the text between two phrase boundaries.

    Uses a non-greedy regex so the shortest matching span is returned.
    Handles arbitrary whitespace and newlines gracefully.

    Args:
        text: The full text to search within.
        start_phrase: Literal string marking the beginning of the desired
            section (not included in the output).
        end_phrase: Literal string marking the end of the desired section
            (not included in the output).

    Returns:
        The extracted section text (stripped), or an empty string if the
        bounding phrases are not both found.
    """

    # Convert phrases into regex patterns that allow flexible whitespace
    pattern = rf"{start_phrase}(.*?){end_phrase}"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)

    if not match:
        return ""

    return match.group(1).strip()


def _get_field(r: object, attr: str, alt_key: str | None = None):
    """Fetch a named field from a dataclass instance or a Mapping.

    Tries ``getattr`` first (dataclass path), then key lookup on the Mapping.
    Falls back to ``alt_key`` to handle ``class`` / ``class_`` naming
    discrepancies between dict rows and the School dataclass.

    Args:
        r: A School dataclass instance or a dict-like Mapping.
        attr: Primary attribute/key name to fetch.
        alt_key: Fallback key name tried when ``attr`` is absent in a Mapping.

    Returns:
        The field value, or None if neither ``attr`` nor ``alt_key`` is found.
    """
    if hasattr(r, attr):
        return getattr(r, attr)
    if isinstance(r, Mapping):
        if attr in r:
            return r[attr]
        if alt_key and alt_key in r:
            return r[alt_key]
    return None


def clean_school_name(raw: str) -> str:
    """Clean a raw school name by removing boilerplate phrases and normalizing case.

    Handles several hard-coded special cases (Enterprise schools, Jefferson Co,
    Franklin) before stripping phrases defined in ``CLEAN_PHRASES`` and
    applying ``to_normal_case``.

    Args:
        raw: Raw school name string (e.g., from a scraped MHSAA page).

    Returns:
        A cleaned, title-cased school name string.
    """

    # Special cases: Differentiate Enterprises
    if raw.lower() == "enterprise school":
        return "Enterprise Lincoln"
    elif raw.lower() == "enterprise high school":
        return "Enterprise Clarke"
    elif raw.lower() == "jefferson co high":
        return "Jefferson County"
    elif raw.lower() == "franklin high school":
        return "Franklin County"
    else:
        tmp = CLEAN_RE.sub("", raw)
        tmp = SPACE_RE.sub(" ", tmp).strip(" ,.-\u2013\u2014\t\r\n")
        return to_normal_case(tmp)


def normalize_pair(x: str, y: str) -> tuple[str, str, int]:
    """Normalize a team pair into lexicographic order with a direction sign.

    Ensures all game lookups use a consistent canonical key regardless of which
    team was listed first in the source data.

    Args:
        x: First team name.
        y: Second team name.

    Returns:
        A 3-tuple ``(a, b, sign)`` where ``a <= b`` lexicographically and
        ``sign`` is ``+1`` if ``x == a`` (no swap) or ``-1`` if the teams
        were swapped.
    """
    return (x, y, +1) if x <= y else (y, x, -1)


def get_completed_games(raw_results: list[RawCompletedGame]) -> list[CompletedGame]:
    """Convert raw game-result dicts into normalized CompletedGame instances.

    Deduplicates by canonical game key (a, b, date) where ``a < b``
    lexicographically.  When both the a-row and b-row are present for the same
    game, the a-row is preferred.  Aggregates multiple meetings between the
    same pair across dates, collapsing ``res_a`` to ``{-1, 0, +1}``.

    Args:
        raw_results: List of RawCompletedGame dicts as returned from a DB
            query (each row is from one team's perspective).

    Returns:
        A list of CompletedGame instances, one per unique (a, b) pair, with
        all fields expressed from the perspective of the lexicographically
        first team.
    """

    # Deduplicate by *game* key (a,b,date) where a<b (lexicographic).
    # Prefer the row where school==a (lex-first) if it exists; otherwise use the b-row inverted.
    by_game: dict[tuple[str, str, str], dict[str, int] | tuple[str, ...]] = {}

    for result in raw_results:
        a, b, _sign = normalize_pair(result["school"], result["opponent"])  # a<b
        gkey = (a, b, result["date"])

        # Compute contributions from the perspective of team 'a' (lex-first)
        if result["school"] == a:
            # from a's row directly
            if result["result"] == "W":
                res_a = 1
            elif result["result"] == "L":
                res_a = -1
            else:
                res_a = 0
            pd_a = (
                (result["points_for"] - result["points_against"])
                if (result["points_for"] is not None and result["points_against"] is not None)
                else 0
            )
            pa_a = result["points_against"] or 0
            pa_b = result["points_for"] or 0

            # Always prefer the a-row: overwrite any prior b-row for this (a,b,date)
            by_game[gkey] = {"res_a": res_a, "pd_a": pd_a, "pa_a": pa_a, "pa_b": pa_b, "has_a": 1}

        else:
            # row is from b's perspective; invert to 'a'
            if result["result"] == "W":
                res_a = -1
            elif result["result"] == "L":
                res_a = 1
            else:
                res_a = 0
            pd_a = (
                (-(result["points_for"] - result["points_against"]))
                if (result["points_for"] is not None and result["points_against"] is not None)
                else 0
            )
            pa_a = result["points_for"] or 0  # a allowed b's points_for
            pa_b = result["points_against"] or 0  # b allowed a's points_for

            prev = by_game.get(gkey)
            # Only store if we don't already have an a-row for this game
            if not prev or (isinstance(prev, dict) and not prev.get("has_a")):
                by_game[gkey] = {"res_a": res_a, "pd_a": pd_a, "pa_a": pa_a, "pa_b": pa_b, "has_a": 0}

    # Now aggregate per pair (a,b) across dates (in case there were multiple meetings)
    pair_totals: dict[tuple[str, str], dict[str, int]] = {}
    for (a, b, _date), vals in by_game.items():
        d = pair_totals.setdefault((a, b), {"res_a": 0, "pd_a": 0, "pa_a": 0, "pa_b": 0})
        d["res_a"] += vals["res_a"]  # type: ignore
        d["pd_a"] += vals["pd_a"]  # type: ignore
        d["pa_a"] += vals["pa_a"]  # type: ignore
        d["pa_b"] += vals["pa_b"]  # type: ignore

    out: list[CompletedGame] = []
    for (a, b), v in pair_totals.items():
        # Collapse res_a to {-1, 0, +1} for the season series (win/loss/split from 'a' pov)
        if v["res_a"] > 0:
            res_a_sign = 1
        elif v["res_a"] < 0:
            res_a_sign = -1
        else:
            res_a_sign = 0
        out.append(CompletedGame(a, b, res_a_sign, v["pd_a"], v["pa_a"], v["pa_b"]))

    return out


# ---------------------------------------------------------------------------
# Game status parsing
# ---------------------------------------------------------------------------

# Matches regulation clock strings like "8:00 1Q", "0:24 4Q", "11:47 2Q"
_REG_CLOCK_RE = re.compile(
    r"^(?P<mm>\d{1,2}):(?P<ss>\d{2})\s+(?P<q>[1-4])Q$", re.IGNORECASE
)
# Matches OT in-progress strings: "OT", "1OT", "2OT", "3OT", …
_OT_PROGRESS_RE = re.compile(r"^(?P<n>\d*)OT$", re.IGNORECASE)
# Matches OT-ended strings: "End OT", "End 1OT", "End 2OT", …
_OT_END_RE = re.compile(r"^End\s+(?P<n>\d*)OT$", re.IGNORECASE)

_TERMINAL_STATUS_MAP: dict[str, GameStatus] = {
    "final": GameStatus.FINAL,
    "final - forfeit": GameStatus.FINAL_FORFEIT,
    "end 1q": GameStatus.END_1Q,
    "halftime": GameStatus.HALFTIME,
    "end 3q": GameStatus.END_3Q,
    "end 4q": GameStatus.END_4Q,
    "postponed": GameStatus.POSTPONED,
    "canceled": GameStatus.CANCELED,
    "cancelled": GameStatus.CANCELED,
    "suspended": GameStatus.SUSPENDED,
}


def normalize_game_status(raw: str | None) -> GameStatus:
    """Map a raw scraper status string to a canonical ``GameStatus`` value."""
    if not raw:
        return GameStatus.NOT_STARTED
    norm = raw.strip()
    lower = norm.lower()
    if lower in _TERMINAL_STATUS_MAP:
        return _TERMINAL_STATUS_MAP[lower]
    if _OT_END_RE.match(norm):
        return GameStatus.END_OT
    if _OT_PROGRESS_RE.match(norm):
        return GameStatus.IN_PROGRESS
    if _REG_CLOCK_RE.match(norm):
        return GameStatus.IN_PROGRESS
    return GameStatus.NOT_STARTED


def parse_game_clock(raw: str | None) -> GameClock:
    """Parse a raw status string into a structured ``GameClock``.

    Regulation in-progress (``"8:00 1Q"``): ``quarter`` 1–4, ``clock`` ``"MM:SS"``.
    OT in-progress (``"OT"``/``"2OT"``): ``quarter = 4 + ot_number`` (so OT1→5), ``clock = None``.
    OT ended (``"End 1OT"``): ``status = END_OT``, same quarter encoding, ``clock = None``.
    Terminal/break states: ``quarter = None``, ``clock = None``.
    """
    norm = (raw or "").strip()

    reg_m = _REG_CLOCK_RE.match(norm)
    if reg_m:
        mm = int(reg_m.group("mm"))
        ss = int(reg_m.group("ss"))
        return GameClock(
            status=GameStatus.IN_PROGRESS,
            quarter=int(reg_m.group("q")),
            clock=f"{mm}:{ss:02d}",
        )

    ot_m = _OT_PROGRESS_RE.match(norm)
    if ot_m:
        ot_n = int(ot_m.group("n") or "1")
        return GameClock(status=GameStatus.IN_PROGRESS, quarter=4 + ot_n, clock=None)

    ot_end_m = _OT_END_RE.match(norm)
    if ot_end_m:
        ot_n = int(ot_end_m.group("n") or "1")
        return GameClock(status=GameStatus.END_OT, quarter=4 + ot_n, clock=None)

    return GameClock(status=normalize_game_status(raw), quarter=None, clock=None)


def game_seconds_remaining(quarter: int, clock: str) -> int:
    """Return total regulation seconds remaining given the current quarter and clock.

    ``clock`` must be ``"MM:SS"`` format.  Returns ``0`` for ``quarter > 4``
    (OT is untimed — callers should use the OT win probability model instead).

    Each quarter is 12 minutes (720 seconds); total regulation is 2 880 seconds.
    """
    if quarter > 4:
        return 0
    mm, ss = clock.split(":")
    remaining_this_q = int(mm) * 60 + int(ss)
    full_qs_after = max(0, 4 - quarter) * 720
    return remaining_this_q + full_qs_after


# ---------------------------------------------------------------------------
# School identity helpers (colour parsing + mascot normalisation)
# ---------------------------------------------------------------------------


def _normalize_mascot(mascot: str) -> str:
    """Normalise a mascot string scraped from the MHSAA directory.

    Steps applied in order:

    1. Drop the "Lady" variant when schools list both nicknames separated by
       ``/`` (e.g. ``"Rams/Lady Rams"`` → ``"Rams"``).
    2. Strip a bare ``"Lady "`` prefix (``"Lady Rams"`` → ``"Rams"``).
    3. Title-case.
    4. Pluralise: append ``"s"`` unless the mascot already ends in ``"s"``
       or its lower-cased form is listed in ``_MASCOT_NO_PLURAL``
       (e.g. ``"Maroon Tide"`` stays unchanged).
    """
    if not mascot:
        return ""

    if "/" in mascot:
        parts = [p.strip() for p in mascot.split("/")]
        non_lady = [p for p in parts if not p.lower().startswith("lady")]
        mascot = non_lady[0] if non_lady else parts[0]

    mascot = re.sub(r"^lady\s+", "", mascot.strip(), flags=re.IGNORECASE).strip()
    if not mascot:
        return ""

    mascot = mascot.title()

    if mascot.lower() not in _MASCOT_NO_PLURAL and not mascot.endswith("s"):
        mascot += "s"

    return mascot


def _split_color_words(text: str) -> list[str]:
    """Split a colour segment into individual tokens on implicit word boundaries.

    A split is inserted before word *i* when word *i-1* is in
    ``_COLOR_BOUNDARY_WORDS`` and the bigram ``words[i-1] words[i]`` is not a
    known compound colour in ``_NO_SPLIT_PAIRS``.

    Examples::

        "Royal White"                  → ["Royal", "White"]
        "Kelly Green Cardinal Yellow"  → ["Kelly Green", "Cardinal Yellow"]
        "Red White Blue"               → ["Red", "White", "Blue"]
    """
    words = text.split()
    if len(words) <= 1:
        return [text.strip()] if text.strip() else []
    tokens: list[str] = []
    start = 0
    for i in range(1, len(words)):
        prev = words[i - 1].lower()
        if prev in _COLOR_BOUNDARY_WORDS:
            pair = f"{prev} {words[i].lower()}"
            if pair not in _NO_SPLIT_PAIRS:
                tokens.append(" ".join(words[start:i]))
                start = i
    tokens.append(" ".join(words[start:]))
    return tokens


def _normalize_color(color: str) -> str:
    """Title-case a colour name and apply known directory typo corrections."""
    stripped = color.strip()
    if not stripped:
        return ""
    lower = stripped.lower()
    if lower in _COLOR_TYPOS:
        return _COLOR_TYPOS[lower]
    return stripped.title()


def _color_to_hex(color: str) -> str:
    """Return the hex value for a single normalised colour name, or '' if unmapped."""
    return _COLOR_HEX_MAP.get(color.strip().lower(), "")


def _colors_csv_to_hex(colors_csv: str) -> str:
    """Convert a comma-separated colour list to a comma-separated hex list.

    Unknown colours are omitted rather than represented as empty slots.
    """
    if not colors_csv:
        return ""
    hexes = [_color_to_hex(c) for c in re.split(r",\s*", colors_csv) if c.strip()]
    return ", ".join(h for h in hexes if h)


def _parse_colors(raw: str) -> tuple[str, str]:
    """Parse a raw MHSAA colours string into ``(primary_color, secondary_color)``.

    Handles all observed separators (``and``, ``&``, ``/``, ``,``, ``@``, ``-``)
    and implicit space-separated colour names.  Parenthetical annotations
    (e.g. ``"Bright Gold (Sundown)"``) are stripped before splitting.
    Returns the first colour as the primary; remaining colours are title-cased
    and joined as a comma-separated secondary string.
    """
    if not raw:
        return "", ""

    raw = re.sub(r"\s*\([^)]*\)", "", raw).strip()
    parts = re.split(r"\s*(?:and|[&/,@\-])\s*", raw.strip(), flags=re.IGNORECASE)

    colors: list[str] = []
    for part in parts:
        part = re.sub(r"\s+", " ", part).strip()
        if part:
            colors.extend(_split_color_words(part))

    colors = [_normalize_color(c) for c in colors if c]

    if not colors:
        return "", ""

    primary = colors[0]
    secondary = ", ".join(colors[1:]) if len(colors) > 1 else ""
    return primary, secondary
