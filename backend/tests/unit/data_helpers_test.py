"""Unit tests for backend.helpers.data_helpers.

Covers all public and private utility functions: name normalization, school
name mapping, float conversion, HTML stripping, text extraction, field
lookup, school name cleaning, pair normalization, and completed-game parsing.
"""

import pytest

from backend.helpers.data_classes import RawCompletedGame, School
from backend.helpers.data_helpers import (
    _color_to_hex,
    _colors_csv_to_hex,
    _get_field,
    _month_to_num,
    _norm,
    _normalize_color,
    _normalize_mascot,
    _normalize_ws,
    _pad,
    _parse_colors,
    _split_color_words,
    as_float_or_none,
    clean_school_name,
    get_completed_games,
    get_school_name_from_ahsfhs,
    normalize_nces_school_name,
    normalize_pair,
    parse_text_section,
    to_normal_case,
    to_plain_text,
    update_school_name_for_ahsfhs_search,
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
# normalize_nces_school_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nces_name,expected",
    [
        ("WEST JONES HIGH SCHOOL", "West Jones"),
        ("SOUTH PANOLA HIGH SCHOOL", "South Panola"),
        ("GREENWOOD HIGH SCHOOL", "Greenwood"),
        ("WEST BOLIVAR HIGH SCHOOL", "West Bolivar"),
        ("LEAKE COUNTY SCHOOL", "Leake County"),
        ("PRENTISS CHRISTIAN SCHOOL", "Prentiss Christian"),
        ("NORTHWEST RANKIN SENIOR HIGH SCHOOL", "Northwest Rankin"),
        ("J Z GEORGE HIGH SCHOOL", "J.Z. George"),
        ("M S PALMER HIGH SCHOOL", "M. S. Palmer"),
        ("H W BYERS HIGH SCHOOL", "H. W. Byers"),
        ("THOMAS E EDWARDS HIGH SCHOOL", "Thomas E. Edwards"),
        ("PEARL RIVER CENTRAL HIGH SCHOOL", "Pearl River Central"),
        # grade-range parentheticals
        ("BYHALIA HIGH SCHOOL (9-12)", "Byhalia"),
        ("POTTS CAMP HIGH SCHOOL (5-12)", "Potts Camp"),
        ("H W BYERS HIGH SCHOOL (5-12)", "H. W. Byers"),
        # standalone HIGH suffix (no SCHOOL)
        ("GRENADA HIGH", "Grenada"),
        # PUBLIC pre-modifier
        ("CANTON PUBLIC HIGH SCHOOL", "Canton"),
        # MEMORIAL pre-modifier
        ("PICAYUNE MEMORIAL HIGH SCHOOL", "Picayune"),
        # SECONDARY SCHOOL suffix
        ("WINONA SECONDARY SCHOOL", "Winona"),
        # MIDDLE-HIGH SCHOOL suffix
        ("ASHLAND MIDDLE-HIGH SCHOOL", "Ashland"),
        # ATTENDANCE CENTER suffix
        ("WESSON ATTENDANCE CENTER", "Wesson"),
        ("ETHEL ATTENDANCE CENTER", "Ethel"),
        ("MCLAURIN ATTENDANCE CENTER", "McLaurin"),
        # SENIOR HIGH SCH abbreviation + D'Iberville apostrophe
        ("DIBERVILLE SENIOR HIGH SCH", "D'Iberville"),
        # explicit remaps
        ("FRANKLIN HIGH SCHOOL", "Franklin County"),
        ("JDC HIGH SCHOOL", "Jefferson Davis County"),
        # Saint → St. conversion
        ("SAINT PATRICK HIGH SCHOOL", "St. Patrick"),
    ],
)
def test_normalize_nces_school_name(nces_name: str, expected: str) -> None:
    """normalize_nces_school_name strips suffix and title-cases correctly."""
    assert normalize_nces_school_name(nces_name) == expected


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


# ---------------------------------------------------------------------------
# _normalize_mascot
# ---------------------------------------------------------------------------


def test_normalize_mascot_empty_string() -> None:
    """Empty mascot returns empty string."""
    assert _normalize_mascot("") == ""


def test_normalize_mascot_basic_pluralizes() -> None:
    """A bare singular mascot is title-cased and pluralized."""
    assert _normalize_mascot("ram") == "Rams"


def test_normalize_mascot_already_plural() -> None:
    """A mascot already ending in 's' is not double-pluralized."""
    assert _normalize_mascot("Tigers") == "Tigers"


def test_normalize_mascot_slash_drops_lady_variant() -> None:
    """When both variants are separated by '/', the non-Lady form is kept."""
    assert _normalize_mascot("Rams/Lady Rams") == "Rams"


def test_normalize_mascot_slash_both_lady_uses_first() -> None:
    """When all slash parts start with 'Lady', the first part is used after stripping the prefix."""
    assert _normalize_mascot("Lady Rams/Lady Tigers") == "Rams"


def test_normalize_mascot_bare_lady_prefix_stripped() -> None:
    """A bare 'Lady ' prefix is stripped before title-casing."""
    assert _normalize_mascot("Lady Warriors") == "Warriors"


def test_normalize_mascot_maroon_tide_no_plural() -> None:
    """'Maroon Tide' is in the no-plural set and must not gain a trailing 's'."""
    assert _normalize_mascot("Maroon Tide") == "Maroon Tide"


def test_normalize_mascot_maroon_tide_lowercase_no_plural() -> None:
    """No-plural check is case-insensitive; lowercase input still yields 'Maroon Tide'."""
    assert _normalize_mascot("maroon tide") == "Maroon Tide"


def test_normalize_mascot_greenwave_pluralized() -> None:
    """'Greenwave' is not in the no-plural set and does not end in 's', so it gains one."""
    assert _normalize_mascot("Greenwave") == "Greenwaves"


def test_normalize_mascot_title_cases() -> None:
    """Mascot is title-cased even when the input is all-lowercase."""
    assert _normalize_mascot("eagles") == "Eagles"


def test_normalize_mascot_empty_after_lady_strip() -> None:
    """A slash entry whose non-lady part is empty returns '' rather than crashing."""
    # "/Lady" → parts=["", "Lady"], non_lady=[""], mascot="" → empty after strip → ""
    assert _normalize_mascot("/Lady") == ""


# ---------------------------------------------------------------------------
# _split_color_words
# ---------------------------------------------------------------------------


def test_split_color_words_single_word() -> None:
    """A single-word input is returned as a one-element list."""
    assert _split_color_words("Red") == ["Red"]


def test_split_color_words_empty_string() -> None:
    """An empty string returns an empty list."""
    assert _split_color_words("") == []


def test_split_color_words_boundary_splits() -> None:
    """'Royal White' splits at the boundary word 'Royal' because the pair is not protected."""
    assert _split_color_words("Royal White") == ["Royal", "White"]


def test_split_color_words_protected_pair_not_split() -> None:
    """'Royal Blue' is a protected pair and must not be split."""
    assert _split_color_words("Royal Blue") == ["Royal Blue"]


def test_split_color_words_compound_colors() -> None:
    """'Kelly Green Cardinal Yellow' splits into two two-word colour tokens."""
    assert _split_color_words("Kelly Green Cardinal Yellow") == ["Kelly Green", "Cardinal Yellow"]


def test_split_color_words_three_boundary_words() -> None:
    """'Red White Blue' splits into three single-word tokens."""
    assert _split_color_words("Red White Blue") == ["Red", "White", "Blue"]


def test_split_color_words_green_bay_not_split() -> None:
    """'Green Bay Gold' does not split at 'Green' because 'green bay' is a protected pair."""
    assert _split_color_words("Green Bay Gold") == ["Green Bay Gold"]


def test_split_color_words_navy_blue_protected() -> None:
    """'Navy Blue' is a protected pair and stays together."""
    assert _split_color_words("Navy Blue") == ["Navy Blue"]


# ---------------------------------------------------------------------------
# _normalize_color
# ---------------------------------------------------------------------------


def test_normalize_color_empty_string() -> None:
    """Empty string returns empty string."""
    assert _normalize_color("") == ""


def test_normalize_color_whitespace_only() -> None:
    """Whitespace-only string returns empty string."""
    assert _normalize_color("   ") == ""


def test_normalize_color_typo_whited() -> None:
    """'whited' (MHSAA directory typo) is corrected to 'White'."""
    assert _normalize_color("whited") == "White"


def test_normalize_color_typo_re() -> None:
    """'re' (truncated 'Red') is corrected to 'Red'."""
    assert _normalize_color("re") == "Red"


def test_normalize_color_title_cases() -> None:
    """A normal colour name is title-cased."""
    assert _normalize_color("royal blue") == "Royal Blue"


def test_normalize_color_strips_surrounding_whitespace() -> None:
    """Surrounding whitespace is stripped before title-casing."""
    assert _normalize_color("  gold  ") == "Gold"


# ---------------------------------------------------------------------------
# _color_to_hex
# ---------------------------------------------------------------------------


def test_color_to_hex_known_color() -> None:
    """A known colour name returns its hex value."""
    assert _color_to_hex("Red") == "#CC0000"


def test_color_to_hex_case_insensitive() -> None:
    """Lookup is case-insensitive."""
    assert _color_to_hex("GOLD") == "#FFD700"


def test_color_to_hex_compound_color() -> None:
    """A known two-word colour returns its hex value."""
    assert _color_to_hex("Royal Blue") == "#4169E1"


def test_color_to_hex_unknown_returns_empty() -> None:
    """An unmapped colour returns an empty string."""
    assert _color_to_hex("Chartreuse") == ""


def test_color_to_hex_empty_string_returns_empty() -> None:
    """Empty string returns empty string."""
    assert _color_to_hex("") == ""


# ---------------------------------------------------------------------------
# _colors_csv_to_hex
# ---------------------------------------------------------------------------


def test_colors_csv_to_hex_empty_string() -> None:
    """Empty input returns empty string."""
    assert _colors_csv_to_hex("") == ""


def test_colors_csv_to_hex_single_known() -> None:
    """A single known colour returns its hex value."""
    assert _colors_csv_to_hex("Navy") == "#001F5B"


def test_colors_csv_to_hex_multiple_known() -> None:
    """Multiple known colours are returned as comma-separated hex values."""
    assert _colors_csv_to_hex("Red, White") == "#CC0000, #FFFFFF"


def test_colors_csv_to_hex_unknown_omitted() -> None:
    """Unknown colours are omitted rather than represented as empty slots."""
    assert _colors_csv_to_hex("Red, Chartreuse, White") == "#CC0000, #FFFFFF"


def test_colors_csv_to_hex_all_unknown_returns_empty() -> None:
    """If all colours are unknown the result is an empty string."""
    assert _colors_csv_to_hex("Chartreuse, Mauve") == ""


# ---------------------------------------------------------------------------
# _parse_colors
# ---------------------------------------------------------------------------


def test_parse_colors_empty_string() -> None:
    """Empty input returns ('', '')."""
    assert _parse_colors("") == ("", "")


def test_parse_colors_single_color() -> None:
    """A single colour returns (primary, '') with no secondary."""
    assert _parse_colors("Red") == ("Red", "")


def test_parse_colors_and_separator() -> None:
    """'Red and White' splits on 'and' into primary and secondary."""
    assert _parse_colors("Red and White") == ("Red", "White")


def test_parse_colors_ampersand_separator() -> None:
    """'Red & White' splits on '&'."""
    assert _parse_colors("Red & White") == ("Red", "White")


def test_parse_colors_slash_separator() -> None:
    """'Red/White' splits on '/'."""
    assert _parse_colors("Red/White") == ("Red", "White")


def test_parse_colors_comma_separator() -> None:
    """'Red, White' splits on ','."""
    assert _parse_colors("Red, White") == ("Red", "White")


def test_parse_colors_hyphen_separator() -> None:
    """'Red-Navy' splits on '-' (real MHSAA data pattern)."""
    primary, secondary = _parse_colors("Red-Navy")
    assert primary == "Red"
    assert secondary == "Navy"


def test_parse_colors_strips_parenthetical() -> None:
    """Parenthetical annotations like '(Sundown)' are stripped before splitting."""
    assert _parse_colors("Bright Gold (Sundown)") == ("Bright Gold", "")


def test_parse_colors_comma_after_parenthetical_not_doubled() -> None:
    """'Bright Gold, (Sundown)' → parenthetical stripped, no spurious empty token."""
    primary, secondary = _parse_colors("Bright Gold, (Sundown)")
    assert primary == "Bright Gold"
    assert secondary == ""


def test_parse_colors_implicit_boundary_split() -> None:
    """'Royal White' splits on the implicit word boundary into two colours."""
    assert _parse_colors("Royal White") == ("Royal", "White")


def test_parse_colors_compound_implicit_split() -> None:
    """'Kelly Green Cardinal Yellow' splits into two two-word compound colours."""
    assert _parse_colors("Kelly Green Cardinal Yellow") == ("Kelly Green", "Cardinal Yellow")


def test_parse_colors_three_colors_red_white_blue() -> None:
    """'Red White Blue' splits into three single-word colours."""
    primary, secondary = _parse_colors("Red White Blue")
    assert primary == "Red"
    assert secondary == "White, Blue"


def test_parse_colors_green_bay_gold_not_split() -> None:
    """'Green Bay Gold' stays as a single primary colour (protected pair)."""
    assert _parse_colors("Green Bay Gold") == ("Green Bay Gold", "")


def test_parse_colors_typo_corrected() -> None:
    """Typos in colour names are corrected during normalization."""
    primary, _ = _parse_colors("Whited")
    assert primary == "White"


def test_parse_colors_title_cases_output() -> None:
    """Output colours are always title-cased."""
    primary, secondary = _parse_colors("red and white")
    assert primary == "Red"
    assert secondary == "White"


def test_parse_colors_only_parenthetical_returns_empty() -> None:
    """Input that is entirely a parenthetical annotation yields ('', '')."""
    assert _parse_colors("(Sundown)") == ("", "")
