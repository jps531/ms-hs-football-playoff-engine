"""Unit tests for backend.helpers.data_helpers.

Covers all public and private utility functions: name normalization, school
name mapping, float conversion, HTML stripping, text extraction, field
lookup, school name cleaning, pair normalization, and completed-game parsing.
"""

import pytest

from backend.helpers.data_classes import RawCompletedGame, School
from backend.helpers.data_helpers import (
    _get_field,
    _month_to_num,
    _norm,
    _normalize_ws,
    _pad,
    as_float_or_none,
    clean_school_name,
    get_completed_games,
    get_school_name_from_ahsfhs,
    normalize_pair,
    parse_text_section,
    to_normal_case,
    to_plain_text,
    update_school_name_for_ahsfhs_search,
    update_school_name_for_maxpreps_search,
)

# ---------------------------------------------------------------------------
# to_normal_case
# ---------------------------------------------------------------------------


def test_to_normal_case_empty_string() -> None:
    """to_normal_case returns an empty string unchanged."""
    assert to_normal_case("") == ""


def test_to_normal_case_basic_title_case() -> None:
    """to_normal_case title-cases a plain lowercase name."""
    assert to_normal_case("greenwood") == "Greenwood"


def test_to_normal_case_mc_prefix() -> None:
    """to_normal_case applies the Mc-prefix rule to capitalize the letter after Mc."""
    # Regex \bMc([a-z]) fires on the title-cased result → "Mcgregor" → "McGregor"
    assert to_normal_case("MCGREGOR") == "McGregor"
    assert to_normal_case("mcgregor field") == "McGregor Field"


def test_to_normal_case_mc_capitalized() -> None:
    """to_normal_case handles McGowan-style names via the Mc regex."""
    # title() → "Mcgowan", regex fires → "McGowan"
    assert to_normal_case("mcgowan") == "McGowan"


def test_to_normal_case_possessive_s_lowercase() -> None:
    """to_normal_case preserves the lowercase 's in possessives."""
    result = to_normal_case("st. andrew's school")
    # Possessive 's should stay lowercase, not become 'S
    assert "'s" in result


def test_to_normal_case_diberville() -> None:
    """to_normal_case handles the D'Iberville apostrophe-capitalization pattern."""
    result = to_normal_case("diberville")
    assert "D'Iber" in result


def test_to_normal_case_st_gets_dot() -> None:
    """to_normal_case adds a period after 'St' abbreviations."""
    result = to_normal_case("st martin")
    assert "St." in result


def test_to_normal_case_st_already_dotted_unchanged() -> None:
    """to_normal_case does not add a second period when 'St.' is already dotted."""
    result = to_normal_case("st. martin")
    # Should not become "St.." (double dot)
    assert "St.." not in result


# ---------------------------------------------------------------------------
# _norm
# ---------------------------------------------------------------------------


def test_norm_strips_and_lowercases() -> None:
    """_norm strips leading/trailing whitespace and lowercases the result."""
    assert _norm("  Hello World  ") == "hello world"


def test_norm_collapses_whitespace() -> None:
    """_norm collapses multiple internal spaces into a single space."""
    assert _norm("hello   world") == "hello world"


def test_norm_curly_quote_to_straight() -> None:
    """_norm converts Unicode right-single-quotation mark to a straight apostrophe."""
    assert _norm("D\u2019Iberville") == "d'iberville"


# ---------------------------------------------------------------------------
# update_school_name_for_maxpreps_search
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "input_name,expected",
    [
        ("Pearl River Central", "prc"),
        ("Cleveland Central", "cleveland"),
        ("Leake Central", "carthage"),
        ("Thomas E. Edwards", "ruleville"),
        ("J Z George", "j.z. george"),
        ("M. S. Palmer", "palmer"),
        ("H. W. Byers", "byers"),
        ("Leake County", "leake"),
        ("Enterprise Clarke", "enterprise bulldogs"),
        ("Enterprise Lincoln", "enterprise yellowjackets"),
        ("Greenwood", "greenwood"),  # no mapping → lowercased
    ],
)
def test_update_school_name_for_maxpreps_search(input_name: str, expected: str) -> None:
    """update_school_name_for_maxpreps_search returns the correct MaxPreps search key."""
    assert update_school_name_for_maxpreps_search(input_name) == expected


# ---------------------------------------------------------------------------
# update_school_name_for_ahsfhs_search
# ---------------------------------------------------------------------------


def test_ahsfhs_search_known_mapping() -> None:
    """update_school_name_for_ahsfhs_search returns the known AHSFHS-encoded name for mapped schools."""
    assert update_school_name_for_ahsfhs_search("D'Iberville") == "DIberville"


def test_ahsfhs_search_unknown_encodes_spaces() -> None:
    """update_school_name_for_ahsfhs_search percent-encodes spaces in unmapped names."""
    assert update_school_name_for_ahsfhs_search("West Point") == "West%20Point"


def test_ahsfhs_search_no_spaces_unchanged() -> None:
    """update_school_name_for_ahsfhs_search leaves single-word unmapped names unchanged."""
    assert update_school_name_for_ahsfhs_search("Greenwood") == "Greenwood"


def test_ahsfhs_search_strips_leading_trailing_space() -> None:
    """update_school_name_for_ahsfhs_search strips surrounding whitespace before lookup."""
    # Strips leading/trailing whitespace before lookup
    result = update_school_name_for_ahsfhs_search("  D'Iberville  ")
    assert result == "DIberville"


# ---------------------------------------------------------------------------
# get_school_name_from_ahsfhs
# ---------------------------------------------------------------------------


def test_get_school_name_from_ahsfhs_known() -> None:
    """get_school_name_from_ahsfhs returns the canonical name for a known AHSFHS key."""
    assert get_school_name_from_ahsfhs("DIberville") == "D'Iberville"


def test_get_school_name_from_ahsfhs_unknown_passthrough() -> None:
    """get_school_name_from_ahsfhs passes through names with no reverse mapping."""
    assert get_school_name_from_ahsfhs("Greenwood") == "Greenwood"


def test_get_school_name_from_ahsfhs_strips_whitespace() -> None:
    """get_school_name_from_ahsfhs strips surrounding whitespace before reverse lookup."""
    assert get_school_name_from_ahsfhs("  DIberville  ") == "D'Iberville"


# ---------------------------------------------------------------------------
# as_float_or_none
# ---------------------------------------------------------------------------


def test_as_float_or_none_none_input() -> None:
    """as_float_or_none returns None for a None input."""
    assert as_float_or_none(None) is None


def test_as_float_or_none_empty_string() -> None:
    """as_float_or_none returns None for an empty string."""
    assert as_float_or_none("") is None


def test_as_float_or_none_blank_string() -> None:
    """as_float_or_none returns None for a whitespace-only string."""
    assert as_float_or_none("   ") is None


def test_as_float_or_none_valid_string() -> None:
    """as_float_or_none converts a numeric string to float."""
    assert as_float_or_none("3.14") == pytest.approx(3.14)


def test_as_float_or_none_valid_int() -> None:
    """as_float_or_none converts an integer to float."""
    assert as_float_or_none(42) == pytest.approx(42.0)


def test_as_float_or_none_invalid_string() -> None:
    """as_float_or_none returns None for a non-numeric string."""
    assert as_float_or_none("not_a_number") is None


# ---------------------------------------------------------------------------
# _pad
# ---------------------------------------------------------------------------


def test_pad_single_digit() -> None:
    """_pad zero-pads single-digit numbers to two characters."""
    assert _pad(3) == "03"


def test_pad_double_digit() -> None:
    """_pad leaves two-digit numbers unchanged."""
    assert _pad(11) == "11"


# ---------------------------------------------------------------------------
# _month_to_num
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "month_str,expected",
    [
        ("jan", 1),
        ("January", 1),
        ("feb", 2),
        ("september", 9),
        ("sept", 9),
        ("dec", 12),
        ("December", 12),
    ],
)
def test_month_to_num_valid(month_str: str, expected: int) -> None:
    """_month_to_num converts valid month abbreviations and full names to their integer number."""
    assert _month_to_num(month_str) == expected


def test_month_to_num_invalid_returns_none() -> None:
    """_month_to_num returns None for unrecognised month strings."""
    assert _month_to_num("notamonth") is None


# ---------------------------------------------------------------------------
# _normalize_ws
# ---------------------------------------------------------------------------


def test_normalize_ws_collapses_excessive_newlines() -> None:
    """_normalize_ws collapses 3+ consecutive newlines down to two."""
    result = _normalize_ws("a\n\n\n\nb")
    assert result == "a\n\nb"


def test_normalize_ws_nbsp_to_space() -> None:
    """_normalize_ws converts non-breaking spaces to regular spaces."""
    result = _normalize_ws("hello\u00a0world")
    assert result == "hello world"


def test_normalize_ws_crlf_to_lf() -> None:
    """_normalize_ws converts CRLF line endings to LF."""
    result = _normalize_ws("line1\r\nline2")
    assert result == "line1\nline2"


# ---------------------------------------------------------------------------
# to_plain_text
# ---------------------------------------------------------------------------


def test_to_plain_text_strips_tags() -> None:
    """to_plain_text removes all HTML tags from the input."""
    result = to_plain_text("<p>Hello <b>world</b></p>")
    assert "Hello" in result
    assert "world" in result
    assert "<" not in result


def test_to_plain_text_collapses_whitespace() -> None:
    """to_plain_text collapses multiple whitespace characters into a single space."""
    result = to_plain_text("<p>  too   many   spaces  </p>")
    assert "  " not in result


def test_to_plain_text_nbsp_removed() -> None:
    """to_plain_text removes non-breaking space entities from HTML."""
    result = to_plain_text("A&nbsp;B")
    assert "\u00a0" not in result


# ---------------------------------------------------------------------------
# parse_text_section
# ---------------------------------------------------------------------------


def test_parse_text_section_basic() -> None:
    """parse_text_section extracts trimmed text between start and end markers."""
    text = "Start: some content End"
    result = parse_text_section(text, "Start:", "End")
    assert result == "some content"


def test_parse_text_section_not_found_returns_empty() -> None:
    """parse_text_section returns an empty string when the markers are not found."""
    result = parse_text_section("no match here", "BEGIN", "END")
    assert result == ""


def test_parse_text_section_multiline() -> None:
    """parse_text_section captures multi-line content between markers."""
    text = "Header\nline 1\nline 2\nFooter"
    result = parse_text_section(text, "Header", "Footer")
    assert "line 1" in result
    assert "line 2" in result


def test_parse_text_section_non_greedy() -> None:
    """parse_text_section is non-greedy: stops at the first end marker."""
    text = "A content1 B content2 B"
    result = parse_text_section(text, "A", "B")
    assert "content1" in result
    assert "content2" not in result


# ---------------------------------------------------------------------------
# _get_field
# ---------------------------------------------------------------------------


def test_get_field_from_dataclass() -> None:
    """_get_field retrieves attribute values from dataclass instances by field name."""
    school = School(school="Greenwood", season=2025, class_=5, region=3)
    assert _get_field(school, "school") == "Greenwood"
    assert _get_field(school, "class_") == 5


def test_get_field_from_dict() -> None:
    """_get_field retrieves values from dict-like objects."""
    d = {"school": "Greenwood", "class": 5}
    assert _get_field(d, "school") == "Greenwood"


def test_get_field_alt_key_fallback() -> None:
    """_get_field falls back to alt_key when the primary key is absent."""
    d = {"class": 5}
    assert _get_field(d, "class_", alt_key="class") == 5


def test_get_field_missing_returns_none() -> None:
    """_get_field returns None when the key is absent and no alt_key matches."""
    d = {"school": "Greenwood"}
    assert _get_field(d, "nonexistent") is None


# ---------------------------------------------------------------------------
# clean_school_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("enterprise school", "Enterprise Lincoln"),
        ("Enterprise School", "Enterprise Lincoln"),  # case-insensitive
        ("enterprise high school", "Enterprise Clarke"),
        ("jefferson co high", "Jefferson County"),
        ("franklin high school", "Franklin County"),
        ("Greenwood High School", "Greenwood"),
        ("West Point High", "West Point"),
        ("Itawamba Agricultural High School", "Itawamba Agricultural"),
    ],
)
def test_clean_school_name(raw: str, expected: str) -> None:
    """clean_school_name normalizes raw school name strings to canonical MHSAA names."""
    assert clean_school_name(raw) == expected


# ---------------------------------------------------------------------------
# normalize_pair
# ---------------------------------------------------------------------------


def test_normalize_pair_already_sorted() -> None:
    """normalize_pair returns (a, b, +1) when a is already lexicographically first."""
    assert normalize_pair("Alpha", "Beta") == ("Alpha", "Beta", +1)


def test_normalize_pair_needs_swap() -> None:
    """normalize_pair swaps the pair and returns sign=-1 when b < a lexicographically."""
    assert normalize_pair("Beta", "Alpha") == ("Alpha", "Beta", -1)


def test_normalize_pair_equal() -> None:
    """normalize_pair returns sign=+1 when both team names are identical."""
    a, b, sign = normalize_pair("Same", "Same")
    assert a == "Same"
    assert b == "Same"
    assert sign == +1


# ---------------------------------------------------------------------------
# get_completed_games
# ---------------------------------------------------------------------------


def _raw(school, opponent, date, result, pf, pa) -> RawCompletedGame:
    """Build a RawCompletedGame dict for use in get_completed_games tests."""
    return {
        "school": school,
        "opponent": opponent,
        "date": date,
        "result": result,
        "points_for": pf,
        "points_against": pa,
    }


def test_get_completed_games_a_wins() -> None:
    """get_completed_games correctly builds a CompletedGame when team a wins."""
    raw = [_raw("Alpha", "Beta", "2025-10-01", "W", 21, 14)]
    games = get_completed_games(raw)
    assert len(games) == 1
    g = games[0]
    assert g.a == "Alpha"
    assert g.b == "Beta"
    assert g.res_a == 1
    assert g.pd_a == 7
    assert g.pa_a == 14
    assert g.pa_b == 21


def test_get_completed_games_a_loses() -> None:
    """get_completed_games sets res_a=-1 and correct pd_a when team a loses."""
    raw = [_raw("Alpha", "Beta", "2025-10-01", "L", 7, 21)]
    games = get_completed_games(raw)
    g = games[0]
    assert g.res_a == -1
    assert g.pd_a == -14


def test_get_completed_games_b_perspective_inverted() -> None:
    """Row from b's perspective is inverted to a's perspective."""
    raw = [_raw("Beta", "Alpha", "2025-10-01", "L", 14, 21)]
    # Beta is lex-after Alpha, so this is a b-row. Beta loses → Alpha wins → res_a=+1
    games = get_completed_games(raw)
    g = games[0]
    assert g.a == "Alpha"
    assert g.b == "Beta"
    assert g.res_a == 1


def test_get_completed_games_a_row_preferred_over_b_row() -> None:
    """When both a and b rows exist for the same game, the a-row wins."""
    a_row = _raw("Alpha", "Beta", "2025-10-01", "W", 21, 14)
    b_row = _raw("Beta", "Alpha", "2025-10-01", "W", 14, 21)  # Beta "wins" — contradicts a-row
    games = get_completed_games([b_row, a_row])  # b-row first, then a-row
    g = games[0]
    assert g.res_a == 1  # a-row (Alpha wins) should be used, not b-row


def test_get_completed_games_null_points_treated_as_zero() -> None:
    """None points_for/points_against fall back to 0 without error."""
    raw = [_raw("Alpha", "Beta", "2025-10-01", "W", None, None)]
    games = get_completed_games(raw)
    g = games[0]
    assert g.res_a == 1
    assert g.pd_a == 0
    assert g.pa_a == 0
    assert g.pa_b == 0


def test_get_completed_games_null_points_b_perspective() -> None:
    """None points in b-row also fall back to 0."""
    raw = [_raw("Beta", "Alpha", "2025-10-01", "L", None, None)]
    games = get_completed_games(raw)
    g = games[0]
    assert g.pd_a == 0
    assert g.pa_a == 0
    assert g.pa_b == 0


def test_get_completed_games_deduplicates_same_game() -> None:
    """Duplicate rows for the same (a, b, date) result in one CompletedGame."""
    row = _raw("Alpha", "Beta", "2025-10-01", "W", 21, 14)
    games = get_completed_games([row, row])
    assert len(games) == 1


def test_get_completed_games_aggregates_multiple_meetings() -> None:
    """Multiple games between the same pair are aggregated into one CompletedGame."""
    raw = [
        _raw("Alpha", "Beta", "2025-10-01", "W", 28, 14),
        _raw("Alpha", "Beta", "2025-10-08", "L", 7, 21),
    ]
    games = get_completed_games(raw)
    assert len(games) == 1
    g = games[0]
    # res_a: +1 + (-1) = 0 → sign = 0 (split)
    assert g.res_a == 0
    assert g.pd_a == 0


def test_get_completed_games_tie_result() -> None:
    """get_completed_games sets res_a=0 and pd_a=0 for tied games."""
    raw = [_raw("Alpha", "Beta", "2025-10-01", "T", 14, 14)]
    games = get_completed_games(raw)
    g = games[0]
    assert g.res_a == 0
    assert g.pd_a == 0


def test_get_completed_games_b_row_tie_result() -> None:
    """Tie result from b-row perspective (covers line 419: res_a = 0 in b-row branch)."""
    # Beta is lex-after Alpha, so this is a b-row. Tie → res_a = 0.
    raw = [_raw("Beta", "Alpha", "2025-10-01", "T", 14, 14)]
    games = get_completed_games(raw)
    g = games[0]
    assert g.a == "Alpha"
    assert g.res_a == 0


def test_get_completed_games_b_row_does_not_overwrite_a_row() -> None:
    """A b-row arriving after an a-row for the same game is silently discarded."""
    a_row = _raw("Alpha", "Beta", "2025-10-01", "W", 28, 7)
    b_row = _raw("Beta", "Alpha", "2025-10-01", "W", 7, 28)  # b's "W" contradicts a-row
    games = get_completed_games([a_row, b_row])
    g = games[0]
    assert g.res_a == 1  # a-row result preserved; b-row discarded


def test_get_field_non_mapping_non_dataclass_returns_none() -> None:
    """_get_field returns None when r is neither a dataclass nor a Mapping."""
    assert _get_field(42, "anything") is None
