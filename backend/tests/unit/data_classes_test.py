"""Unit tests for backend.helpers.data_classes.

Covers the DB-mapped dataclass serialization/deserialization methods
(as_db_tuple, from_db_tuple) for School, Game, Location, Bracket,
BracketTeam, and BracketGame, plus the equal_win_prob default function,
and the GameResult / MarginCondition scenario condition types.
"""

from datetime import date

import pytest

from backend.helpers.data_classes import (
    Bracket,
    BracketGame,
    BracketTeam,
    Game,
    GameResult,
    GameStatus,
    HelmetDesign,
    Location,
    MarginCondition,
    RemainingGame,
    School,
    equal_win_prob,
)

# ---------------------------------------------------------------------------
# equal_win_prob
# ---------------------------------------------------------------------------


def test_equal_win_prob_always_returns_half() -> None:
    """equal_win_prob returns 0.5 regardless of team names or date."""
    assert equal_win_prob("TeamA", "TeamB") == pytest.approx(0.5)
    assert equal_win_prob("TeamA", "TeamB", "2025-10-01") == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# School
# ---------------------------------------------------------------------------

_SCHOOL_FULL = School(
    school="Greenwood",
    season=2025,
    class_=5,
    region=3,
    city="Greenwood",
    zip="38930",
    latitude=33.5162,
    longitude=-90.1793,
    mascot="Bulldogs",
    primary_color="#003366",
    secondary_color="#FFFFFF",
)


def test_school_as_schools_tuple() -> None:
    """as_schools_tuple returns the correct 8-field tuple for the schools table."""
    t = _SCHOOL_FULL.as_schools_tuple()
    assert t == (
        "Greenwood",
        "Greenwood",
        "38930",
        33.5162,
        -90.1793,
        "Bulldogs",
        "#003366",
        "#FFFFFF",
    )


def test_school_as_school_seasons_tuple() -> None:
    """as_school_seasons_tuple returns (school, season, class_, region)."""
    assert _SCHOOL_FULL.as_school_seasons_tuple() == ("Greenwood", 2025, 5, 3)


def test_school_from_db_tuple_4col() -> None:
    """from_db_tuple with 4 columns populates identity fields; optional fields default."""
    s = School.from_db_tuple(("Greenwood", 2025, 5, 3))
    assert s.school == "Greenwood"
    assert s.season == 2025
    assert s.class_ == 5
    assert s.region == 3
    assert s.city == ""  # default


def test_school_from_db_tuple_11col() -> None:
    """from_db_tuple with 11 columns populates all fields including metadata."""
    row = (
        "Greenwood",
        2025,
        5,
        3,
        "Greenwood",
        "38930",
        33.5162,
        -90.1793,
        "Bulldogs",
        "#003366",
        "#FFFFFF",
    )
    s = School.from_db_tuple(row)
    assert s.school == "Greenwood"
    assert s.city == "Greenwood"
    assert s.mascot == "Bulldogs"
    assert s.primary_color == "#003366"


def test_school_from_db_tuple_11col_null_fields_become_defaults() -> None:
    """None values in optional columns fall back to empty string / 0.0 defaults."""
    row = ("Greenwood", 2025, 5, 3, None, None, None, None, None, None, None)
    s = School.from_db_tuple(row)
    assert s.city == ""
    assert s.latitude == pytest.approx(0.0)
    assert s.mascot == ""


def test_school_from_db_tuple_bad_length_raises() -> None:
    """from_db_tuple raises ValueError for unexpected row lengths."""
    with pytest.raises(ValueError):
        School.from_db_tuple(("Greenwood", 2025, 5))


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------

_GAME_DATE = date(2025, 10, 3)

_GAME_FULL = Game(
    school="Greenwood",
    date=_GAME_DATE,
    season=2025,
    location_id=42,
    points_for=28,
    points_against=14,
    round="Regular",
    kickoff_time="2025-10-03T19:00:00Z",
    opponent="Starkville",
    result="W",
    game_status=GameStatus.FINAL,
    source="maxpreps",
    location="home",
    region_game=True,
    final=True,
    overtime=0,
)


def test_game_as_db_tuple() -> None:
    """as_db_tuple returns the correct 16-field tuple for the games table."""
    t = _GAME_FULL.as_db_tuple()
    assert t == (
        "Greenwood",
        _GAME_DATE,
        2025,
        42,
        28,
        14,
        "Regular",
        "2025-10-03T19:00:00Z",
        "Starkville",
        "W",
        GameStatus.FINAL,
        "maxpreps",
        "home",
        True,
        True,
        0,
    )


def test_game_from_db_tuple_dict_path() -> None:
    """from_db_tuple with a dict row populates all fields correctly."""
    row = {
        "school": "Greenwood",
        "date": _GAME_DATE,
        "season": 2025,
        "location_id": 42,
        "points_for": 28,
        "points_against": 14,
        "round": "Regular",
        "kickoff_time": "2025-10-03T19:00:00Z",
        "opponent": "Starkville",
        "result": "W",
        "game_status": "Final",
        "source": "maxpreps",
        "location": "home",
        "region_game": True,
        "final": True,
        "overtime": 0,
    }
    g = Game.from_db_tuple(row)
    assert g.school == "Greenwood"
    assert g.date == _GAME_DATE
    assert g.result == "W"
    assert g.region_game is True


def test_game_from_db_tuple_dict_missing_date_raises() -> None:
    """from_db_tuple raises ValueError when the dict row is missing the required 'date' field."""
    row = {"school": "Greenwood"}  # missing 'date'
    with pytest.raises(ValueError):
        Game.from_db_tuple(row)


def test_game_from_db_tuple_dict_null_location_defaults_to_neutral() -> None:
    """None location in a dict row falls back to 'neutral'."""
    row = {"school": "Greenwood", "date": _GAME_DATE, "location": None}
    g = Game.from_db_tuple(row)
    assert g.location == "neutral"


def test_game_from_db_tuple_16col_tuple() -> None:
    """from_db_tuple with a 16-column positional tuple populates all fields correctly."""
    row = (
        "Greenwood",
        _GAME_DATE,
        2025,
        42,
        28,
        14,
        "Regular",
        "2025-10-03T19:00:00Z",
        "Starkville",
        "W",
        "Final",
        "maxpreps",
        "home",
        True,
        True,
        0,
    )
    g = Game.from_db_tuple(row)
    assert g.school == "Greenwood"
    assert g.points_for == 28
    assert g.final is True


def test_game_from_db_tuple_16col_null_location_defaults_to_neutral() -> None:
    """None location in a tuple row falls back to 'neutral'."""
    row = (
        "Greenwood",
        _GAME_DATE,
        2025,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        False,
        False,
        0,
    )
    g = Game.from_db_tuple(row)
    assert g.location == "neutral"


def test_game_from_db_tuple_bad_length_raises() -> None:
    """from_db_tuple raises ValueError for tuple rows with unexpected column counts."""
    with pytest.raises(ValueError):
        Game.from_db_tuple((1, 2, 3))


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

_LOCATION = Location(
    id=None,
    name="Williams-Nosef Stadium",
    city="Greenwood",
    home_team="Greenwood",
    latitude=33.5162,
    longitude=-90.1793,
)


def test_location_as_db_tuple() -> None:
    """as_db_tuple returns a 5-field tuple excluding the DB-assigned id."""
    t = _LOCATION.as_db_tuple()
    # id is excluded from the tuple (assigned by DB)
    assert t == ("Williams-Nosef Stadium", "Greenwood", "Greenwood", 33.5162, -90.1793)


def test_location_from_db_tuple_5col() -> None:
    """from_db_tuple with 5 columns populates all fields; id is set to None."""
    row = ("Williams-Nosef Stadium", "Greenwood", "Greenwood", 33.5162, -90.1793)
    loc = Location.from_db_tuple(row)
    assert loc.id is None
    assert loc.name == "Williams-Nosef Stadium"
    assert loc.home_team == "Greenwood"


def test_location_from_db_tuple_bad_length_raises() -> None:
    """from_db_tuple raises ValueError for rows that don't have exactly 5 columns."""
    with pytest.raises(ValueError):
        Location.from_db_tuple(("Stadium",))


# ---------------------------------------------------------------------------
# Bracket
# ---------------------------------------------------------------------------

_BRACKET = Bracket(name="2025 5A Bracket", season=2025, class_=5, source="mhsaa")


def test_bracket_as_db_tuple() -> None:
    """as_db_tuple returns a 4-field tuple for the brackets table."""
    assert _BRACKET.as_db_tuple() == ("2025 5A Bracket", 2025, 5, "mhsaa")


def test_bracket_from_db_tuple_4col() -> None:
    """from_db_tuple with 4 columns populates all Bracket fields."""
    b = Bracket.from_db_tuple(("2025 5A Bracket", 2025, 5, "mhsaa"))
    assert b.name == "2025 5A Bracket"
    assert b.season == 2025
    assert b.class_ == 5
    assert b.source == "mhsaa"


def test_bracket_from_db_tuple_bad_length_raises() -> None:
    """from_db_tuple raises ValueError for rows that don't have exactly 4 columns."""
    with pytest.raises(ValueError):
        Bracket.from_db_tuple(("name", 2025))


# ---------------------------------------------------------------------------
# BracketTeam
# ---------------------------------------------------------------------------

_BRACKET_TEAM = BracketTeam(bracket_id=7, school="Greenwood", season=2025, seed=1, region=3)


def test_bracket_team_as_db_tuple() -> None:
    """as_db_tuple returns a 5-field tuple for the bracket_teams table."""
    assert _BRACKET_TEAM.as_db_tuple() == (7, "Greenwood", 2025, 1, 3)


def test_bracket_team_from_db_tuple_5col() -> None:
    """from_db_tuple with 5 columns populates all BracketTeam fields."""
    bt = BracketTeam.from_db_tuple((7, "Greenwood", 2025, 1, 3))
    assert bt.bracket_id == 7
    assert bt.school == "Greenwood"
    assert bt.seed == 1


def test_bracket_team_from_db_tuple_bad_length_raises() -> None:
    """from_db_tuple raises ValueError for rows that don't have exactly 5 columns."""
    with pytest.raises(ValueError):
        BracketTeam.from_db_tuple((7, "Greenwood", 2025))


# ---------------------------------------------------------------------------
# BracketGame
# ---------------------------------------------------------------------------

_BRACKET_GAME_FULL = BracketGame(
    bracket_id=7,
    round="quarterfinals",
    game_number=1,
    home="Greenwood",
    away="Starkville",
    home_region=3,
    home_seed=1,
    away_region=2,
    away_seed=2,
    next_game_id=99,
)


def test_bracket_game_as_db_tuple() -> None:
    """as_db_tuple returns a 10-field tuple for the bracket_games table."""
    t = _BRACKET_GAME_FULL.as_db_tuple()
    assert t == (7, "quarterfinals", 1, "Greenwood", "Starkville", 3, 1, 2, 2, 99)


def test_bracket_game_from_db_tuple_3col() -> None:
    """from_db_tuple with 3 columns sets matchup fields to None."""
    bg = BracketGame.from_db_tuple((7, "quarterfinals", 1))
    assert bg.bracket_id == 7
    assert bg.round == "quarterfinals"
    assert bg.game_number == 1
    assert bg.home is None
    assert bg.away is None
    assert bg.home_region is None
    assert bg.next_game_id is None


def test_bracket_game_from_db_tuple_10col() -> None:
    """from_db_tuple with 10 columns populates all BracketGame fields including matchup."""
    row = (7, "quarterfinals", 1, "Greenwood", "Starkville", 3, 1, 2, 2, 99)
    bg = BracketGame.from_db_tuple(row)
    assert bg.home == "Greenwood"
    assert bg.away == "Starkville"
    assert bg.home_seed == 1
    assert bg.next_game_id == 99


def test_bracket_game_from_db_tuple_bad_length_raises() -> None:
    """from_db_tuple raises ValueError for rows with neither 3 nor 10 columns."""
    with pytest.raises(ValueError):
        BracketGame.from_db_tuple((7, "quarterfinals", 1, "extra"))


# ---------------------------------------------------------------------------
# Shared fixtures for GameResult / MarginCondition tests
# ---------------------------------------------------------------------------

_REMAINING = [
    RemainingGame("Brandon", "Meridian"),  # bit 0: Brandon wins if bit set
    RemainingGame("Oak Grove", "Pearl"),  # bit 1
    RemainingGame("Northwest Rankin", "Petal"),  # bit 2
]

# outcome_mask=0b101 → Brandon wins (bit 0), Pearl wins (bit 1=0), NWR wins (bit 2)
_MASK_BRN_NWR = 0b101
_MARGINS_BRN_NWR = {
    ("Brandon", "Meridian"): 7,
    ("Oak Grove", "Pearl"): 3,  # Pearl wins by 3
    ("Northwest Rankin", "Petal"): 5,
}


# ---------------------------------------------------------------------------
# GameResult
# ---------------------------------------------------------------------------


def test_game_result_winner_no_margin_constraint() -> None:
    """satisfied_by returns True when the winner won, with no margin constraint."""
    gr = GameResult("Brandon", "Meridian")
    assert gr.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


def test_game_result_loser_returns_false() -> None:
    """satisfied_by returns False when the named winner actually lost."""
    gr = GameResult("Meridian", "Brandon")
    assert not gr.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


def test_game_result_pearl_wins_loser_perspective() -> None:
    """satisfied_by returns True when the game pair is stored in reversed (b, a) order."""
    # Pearl won (Oak Grove lost) — bit 1 is 0
    gr = GameResult("Pearl", "Oak Grove")
    assert gr.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


def test_game_result_min_margin_satisfied() -> None:
    """satisfied_by returns True when the actual margin equals the minimum required."""
    gr = GameResult("Brandon", "Meridian", min_margin=7)
    assert gr.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


def test_game_result_min_margin_not_met() -> None:
    """satisfied_by returns False when the actual margin falls short of min_margin."""
    gr = GameResult("Brandon", "Meridian", min_margin=8)
    assert not gr.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


def test_game_result_max_margin_satisfied() -> None:
    """satisfied_by returns True when the actual margin is within the exclusive upper bound."""
    # Brandon wins by 7; max_margin=8 means ≤7 passes (exclusive upper)
    gr = GameResult("Brandon", "Meridian", min_margin=1, max_margin=8)
    assert gr.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


def test_game_result_max_margin_exceeded() -> None:
    """satisfied_by returns False when the actual margin equals the exclusive upper bound."""
    # Brandon wins by 7; max_margin=7 means must be ≤6 — fails
    gr = GameResult("Brandon", "Meridian", min_margin=1, max_margin=7)
    assert not gr.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


def test_game_result_str_no_margin() -> None:
    """__str__ without a margin constraint produces 'winner>loser'."""
    assert str(GameResult("Brandon", "Meridian")) == "Brandon>Meridian"


def test_game_result_str_min_only() -> None:
    """__str__ with only min_margin produces 'by N+' notation."""
    assert str(GameResult("Brandon", "Meridian", min_margin=4)) == "Brandon>Meridian by 4+"


def test_game_result_str_range() -> None:
    """__str__ with both min and max_margin produces an inclusive range 'by N–M'."""
    assert str(GameResult("Brandon", "Meridian", min_margin=4, max_margin=9)) == "Brandon>Meridian by 4–8"


# ---------------------------------------------------------------------------
# MarginCondition
# ---------------------------------------------------------------------------


def test_margin_condition_single_game_ge() -> None:
    """satisfied_by returns True for a single-game >= condition that is met exactly."""
    # NWR wins by 5 >= 5 → True
    mc = MarginCondition(
        add=(("Northwest Rankin", "Petal"),),
        sub=(),
        op=">=",
        threshold=5,
    )
    assert mc.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


def test_margin_condition_single_game_ge_fails() -> None:
    """satisfied_by returns False when the single-game margin falls short of the threshold."""
    # NWR wins by 5 >= 6 → False
    mc = MarginCondition(
        add=(("Northwest Rankin", "Petal"),),
        sub=(),
        op=">=",
        threshold=6,
    )
    assert not mc.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


def test_margin_condition_sum_two_games() -> None:
    """satisfied_by returns True when the sum of two game margins meets the threshold."""
    # NWR(5) + Pearl(3) = 8 >= 8 → True
    mc = MarginCondition(
        add=(("Northwest Rankin", "Petal"), ("Oak Grove", "Pearl")),
        sub=(),
        op=">=",
        threshold=8,
    )
    assert mc.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


def test_margin_condition_sum_two_games_fails() -> None:
    """satisfied_by returns False when the sum of two game margins falls short of the threshold."""
    # NWR(5) + Pearl(3) = 8 >= 9 → False
    mc = MarginCondition(
        add=(("Northwest Rankin", "Petal"), ("Oak Grove", "Pearl")),
        sub=(),
        op=">=",
        threshold=9,
    )
    assert not mc.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


def test_margin_condition_difference() -> None:
    """satisfied_by returns True for a difference condition (add minus sub > threshold)."""
    # NWR(5) - Pearl(3) = 2 > 1 → True
    mc = MarginCondition(
        add=(("Northwest Rankin", "Petal"),),
        sub=(("Oak Grove", "Pearl"),),
        op=">",
        threshold=1,
    )
    assert mc.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


def test_margin_condition_lt() -> None:
    """satisfied_by returns True for a strict less-than condition."""
    # NWR(5) < 6 → True
    mc = MarginCondition(
        add=(("Northwest Rankin", "Petal"),),
        sub=(),
        op="<",
        threshold=6,
    )
    assert mc.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


def test_margin_condition_le_boundary() -> None:
    """satisfied_by returns True when the margin exactly equals the <= threshold."""
    # NWR(5) <= 5 → True
    mc = MarginCondition(
        add=(("Northwest Rankin", "Petal"),),
        sub=(),
        op="<=",
        threshold=5,
    )
    assert mc.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


def test_margin_condition_eq_boundary() -> None:
    """satisfied_by returns True when margin exactly equals the == threshold."""
    # NWR(5) == 5 → True; NWR(5) == 6 → False
    mc_true = MarginCondition(
        add=(("Northwest Rankin", "Petal"),),
        sub=(),
        op="==",
        threshold=5,
    )
    mc_false = MarginCondition(
        add=(("Northwest Rankin", "Petal"),),
        sub=(),
        op="==",
        threshold=6,
    )
    assert mc_true.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)
    assert not mc_false.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


def test_margin_condition_str() -> None:
    """__str__ renders add-only conditions as a sum expression."""
    mc = MarginCondition(
        add=(("Northwest Rankin", "Petal"), ("Oak Grove", "Pearl")),
        sub=(),
        op=">=",
        threshold=10,
    )
    assert str(mc) == "Northwest RankinvPetal_margin + Oak GrovevPearl_margin >= 10"


def test_margin_condition_str_with_sub() -> None:
    """__str__ renders add-minus-sub conditions with a subtraction term."""
    mc = MarginCondition(
        add=(("Northwest Rankin", "Petal"),),
        sub=(("Oak Grove", "Pearl"),),
        op=">",
        threshold=0,
    )
    assert str(mc) == "Northwest RankinvPetal_margin - Oak GrovevPearl_margin > 0"


def test_game_result_satisfied_by_pair_not_in_remaining() -> None:
    """Returns False when neither (winner, loser) nor (loser, winner) is in remaining."""
    gr = GameResult("Petal", "Oak Grove")  # this game is not in _REMAINING
    assert gr.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING) is False


def test_margin_condition_satisfied_by_reversed_pair() -> None:
    """_margin() fallback: pair passed in reversed order is still resolved correctly."""
    # ("Pearl", "Oak Grove") is reversed relative to the RemainingGame("Oak Grove", "Pearl") key
    mc = MarginCondition(add=(("Pearl", "Oak Grove"),), sub=(), op=">=", threshold=1)
    assert mc.satisfied_by(0, _MARGINS_BRN_NWR, _REMAINING) is True  # Pearl's margin = 3 >= 1


def test_margin_condition_satisfied_by_missing_pair_raises() -> None:
    """KeyError raised when the pair is absent from remaining games entirely."""
    mc = MarginCondition(add=(("Petal", "Oak Grove"),), sub=(), op=">=", threshold=1)
    with pytest.raises(KeyError):
        mc.satisfied_by(0, _MARGINS_BRN_NWR, _REMAINING)


def test_margin_condition_satisfied_by_unknown_op_raises() -> None:
    """ValueError raised for an unrecognised operator."""
    mc = MarginCondition(add=(("Brandon", "Meridian"),), sub=(), op="!=", threshold=0)
    with pytest.raises(ValueError, match="Unknown operator"):
        mc.satisfied_by(_MASK_BRN_NWR, _MARGINS_BRN_NWR, _REMAINING)


# ---------------------------------------------------------------------------
# CoinFlipResult
# ---------------------------------------------------------------------------


def test_coin_flip_result_satisfied_by_always_true() -> None:
    """CoinFlipResult.satisfied_by always returns True regardless of arguments."""
    from backend.helpers.data_classes import CoinFlipResult

    cfr = CoinFlipResult(winner="Alpha", loser="Beta")
    assert cfr.satisfied_by(0, {}, []) is True
    assert cfr.satisfied_by(0xFF, {"x": 1}, _REMAINING) is True


def test_coin_flip_result_str() -> None:
    """CoinFlipResult.__str__ returns the expected human-readable phrase."""
    from backend.helpers.data_classes import CoinFlipResult

    cfr = CoinFlipResult(winner="Alpha", loser="Beta")
    assert str(cfr) == "Alpha wins coin flip vs Beta"


# ---------------------------------------------------------------------------
# PDRankCondition
# ---------------------------------------------------------------------------


def test_pd_rank_condition_satisfied_by_always_true() -> None:
    """PDRankCondition.satisfied_by always returns True regardless of arguments."""
    from backend.helpers.data_classes import PDRankCondition

    cond = PDRankCondition(team="Alpha", rank=1, group=("Alpha", "Beta", "Gamma"))
    assert cond.satisfied_by(0, {}, []) is True
    assert cond.satisfied_by(0xFF, {"x": 1}, _REMAINING) is True


def test_pd_rank_condition_str_ordinals() -> None:
    """PDRankCondition.__str__ formats rank 1-4 with correct ordinal suffixes."""
    from backend.helpers.data_classes import PDRankCondition

    group = ("Alpha", "Beta")
    assert str(PDRankCondition("Alpha", 1, group)) == "Alpha finishes 1st in point differential"
    assert str(PDRankCondition("Beta", 2, group)) == "Beta finishes 2nd in point differential"
    assert str(PDRankCondition("Alpha", 3, group)) == "Alpha finishes 3rd in point differential"
    assert str(PDRankCondition("Beta", 4, group)) == "Beta finishes 4th in point differential"


def test_pd_rank_condition_str_fifth_or_higher() -> None:
    """PDRankCondition.__str__ falls back to 'Nth' for rank > 4."""
    from backend.helpers.data_classes import PDRankCondition

    cond = PDRankCondition(team="Alpha", rank=5, group=("Alpha", "Beta"))
    assert str(cond) == "Alpha finishes 5th in point differential"


# ---------------------------------------------------------------------------
# HelmetDesign
# ---------------------------------------------------------------------------

_HELMET_FULL = HelmetDesign(
    id=42,
    school="Greenwood",
    year_first_worn=2001,
    year_last_worn=2018,
    years_worn=[{"start": 2001, "end": 2005}, {"start": 2007, "end": 2007}, {"start": 2009, "end": 2018}],
    image_left="https://example.com/helmet_left.png",
    image_right="https://example.com/helmet_right.png",
    photo="https://example.com/helmet_photo.jpg",
    color="matte black",
    finish="matte",
    facemask_color="white",
    logo="outlined script G",
    stripe="single center stripe",
    tags=["throwback", "special edition"],
    notes="Worn only for rivalry games in odd years.",
)

_HELMET_MINIMAL = HelmetDesign(school="Greenwood", year_first_worn=2023)


def test_helmet_design_as_db_tuple_full() -> None:
    """as_db_tuple returns a 14-element tuple (no id) in column order."""
    t = _HELMET_FULL.as_db_tuple()
    assert len(t) == 14
    assert t == (
        "Greenwood",
        2001,
        2018,
        [{"start": 2001, "end": 2005}, {"start": 2007, "end": 2007}, {"start": 2009, "end": 2018}],
        "https://example.com/helmet_left.png",
        "https://example.com/helmet_right.png",
        "https://example.com/helmet_photo.jpg",
        "matte black",
        "matte",
        "white",
        "outlined script G",
        "single center stripe",
        ["throwback", "special edition"],
        "Worn only for rivalry games in odd years.",
    )


def test_helmet_design_as_db_tuple_minimal() -> None:
    """as_db_tuple with only required fields has 14 elements; all optional slots are None."""
    t = _HELMET_MINIMAL.as_db_tuple()
    assert len(t) == 14
    assert t[0] == "Greenwood"
    assert t[1] == 2023
    assert all(v is None for v in t[2:])  # all optional fields are None


def test_helmet_design_from_db_tuple_tuple_path() -> None:
    """from_db_tuple with a 15-element tuple populates all fields correctly."""
    row = (
        42,
        "Greenwood",
        2001,
        2018,
        [{"start": 2001, "end": 2005}],
        "https://example.com/left.png",
        "https://example.com/right.png",
        "https://example.com/photo.jpg",
        "matte black",
        "matte",
        "white",
        "outlined script G",
        "single center stripe",
        ["throwback"],
        "Rivalry only.",
    )
    h = HelmetDesign.from_db_tuple(row)
    assert h.id == 42
    assert h.school == "Greenwood"
    assert h.year_first_worn == 2001
    assert h.year_last_worn == 2018
    assert h.years_worn == [{"start": 2001, "end": 2005}]
    assert h.color == "matte black"
    assert h.finish == "matte"
    assert h.tags == ["throwback"]
    assert h.notes == "Rivalry only."


def test_helmet_design_from_db_tuple_dict_path() -> None:
    """from_db_tuple with a dict row (psycopg RealDictRow style) populates all fields."""
    row = {
        "id": 7,
        "school": "Starkville",
        "year_first_worn": 2015,
        "year_last_worn": None,
        "years_worn": [{"start": 2015, "end": 2018}, {"start": 2020, "end": 2020}],
        "image_left": None,
        "image_right": None,
        "photo": "https://example.com/p.jpg",
        "color": "gold",
        "finish": "gloss",
        "facemask_color": "black",
        "logo": "block S",
        "stripe": None,
        "tags": ["current"],
        "notes": None,
    }
    h = HelmetDesign.from_db_tuple(row)
    assert h.id == 7
    assert h.school == "Starkville"
    assert h.year_first_worn == 2015
    assert h.year_last_worn is None
    assert h.years_worn == [{"start": 2015, "end": 2018}, {"start": 2020, "end": 2020}]
    assert h.color == "gold"
    assert h.tags == ["current"]


def test_helmet_design_from_db_tuple_null_fields() -> None:
    """None values in optional columns become None; tags=None becomes []."""
    row = (1, "Greenwood", 2010, None, None, None, None, None, None, None, None, None, None, None, None)
    h = HelmetDesign.from_db_tuple(row)
    assert h.id == 1
    assert h.school == "Greenwood"
    assert h.year_first_worn == 2010
    assert h.year_last_worn is None
    assert h.color is None
    assert h.tags == []


def test_helmet_design_from_db_tuple_bad_length() -> None:
    """from_db_tuple raises ValueError when given the wrong number of columns."""
    with pytest.raises(ValueError, match="Expected 15 columns"):
        HelmetDesign.from_db_tuple((1, "Greenwood", 2010))
