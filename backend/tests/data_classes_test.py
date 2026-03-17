"""Unit tests for backend.helpers.data_classes.

Covers the DB-mapped dataclass serialization/deserialization methods
(as_db_tuple, from_db_tuple) for School, Game, Location, Bracket,
BracketTeam, and BracketGame, plus the equal_win_prob default function.
"""

from datetime import date

import pytest

from backend.helpers.data_classes import (
    Bracket,
    BracketGame,
    BracketTeam,
    Game,
    Location,
    School,
    equal_win_prob,
)

# ---------------------------------------------------------------------------
# equal_win_prob
# ---------------------------------------------------------------------------


def test_equal_win_prob_always_returns_half() -> None:
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
    maxpreps_id="abc123",
    maxpreps_url="https://maxpreps.com/greenwood",
    maxpreps_logo="https://maxpreps.com/logo.png",
    primary_color="#003366",
    secondary_color="#FFFFFF",
)


def test_school_as_schools_tuple() -> None:
    t = _SCHOOL_FULL.as_schools_tuple()
    assert t == (
        "Greenwood",
        "Greenwood",
        "38930",
        33.5162,
        -90.1793,
        "Bulldogs",
        "abc123",
        "https://maxpreps.com/greenwood",
        "https://maxpreps.com/logo.png",
        "#003366",
        "#FFFFFF",
    )


def test_school_as_school_seasons_tuple() -> None:
    assert _SCHOOL_FULL.as_school_seasons_tuple() == ("Greenwood", 2025, 5, 3)


def test_school_from_db_tuple_4col() -> None:
    s = School.from_db_tuple(("Greenwood", 2025, 5, 3))
    assert s.school == "Greenwood"
    assert s.season == 2025
    assert s.class_ == 5
    assert s.region == 3
    assert s.city == ""  # default


def test_school_from_db_tuple_14col() -> None:
    row = (
        "Greenwood", 2025, 5, 3,
        "Greenwood", "38930", 33.5162, -90.1793,
        "Bulldogs", "abc123", "https://maxpreps.com/greenwood",
        "https://maxpreps.com/logo.png", "#003366", "#FFFFFF",
    )
    s = School.from_db_tuple(row)
    assert s.school == "Greenwood"
    assert s.city == "Greenwood"
    assert s.mascot == "Bulldogs"
    assert s.primary_color == "#003366"


def test_school_from_db_tuple_14col_null_fields_become_defaults() -> None:
    row = ("Greenwood", 2025, 5, 3, None, None, None, None, None, None, None, None, None, None)
    s = School.from_db_tuple(row)
    assert s.city == ""
    assert s.latitude == pytest.approx(0.0)
    assert s.mascot == ""


def test_school_from_db_tuple_bad_length_raises() -> None:
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
    game_status="Final",
    source="maxpreps",
    location="home",
    region_game=True,
    final=True,
    overtime=0,
)


def test_game_as_db_tuple() -> None:
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
        "Final",
        "maxpreps",
        "home",
        True,
        True,
        0,
    )


def test_game_from_db_tuple_dict_path() -> None:
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
    row = {"school": "Greenwood"}  # missing 'date'
    with pytest.raises(ValueError):
        Game.from_db_tuple(row)


def test_game_from_db_tuple_dict_null_location_defaults_to_neutral() -> None:
    row = {"school": "Greenwood", "date": _GAME_DATE, "location": None}
    g = Game.from_db_tuple(row)
    assert g.location == "neutral"


def test_game_from_db_tuple_16col_tuple() -> None:
    row = (
        "Greenwood", _GAME_DATE, 2025, 42, 28, 14,
        "Regular", "2025-10-03T19:00:00Z", "Starkville", "W",
        "Final", "maxpreps", "home", True, True, 0,
    )
    g = Game.from_db_tuple(row)
    assert g.school == "Greenwood"
    assert g.points_for == 28
    assert g.final is True


def test_game_from_db_tuple_16col_null_location_defaults_to_neutral() -> None:
    row = (
        "Greenwood", _GAME_DATE, 2025, None, None, None,
        None, None, None, None, None, None, None, False, False, 0,
    )
    g = Game.from_db_tuple(row)
    assert g.location == "neutral"


def test_game_from_db_tuple_bad_length_raises() -> None:
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
    t = _LOCATION.as_db_tuple()
    # id is excluded from the tuple (assigned by DB)
    assert t == ("Williams-Nosef Stadium", "Greenwood", "Greenwood", 33.5162, -90.1793)


def test_location_from_db_tuple_5col() -> None:
    row = ("Williams-Nosef Stadium", "Greenwood", "Greenwood", 33.5162, -90.1793)
    loc = Location.from_db_tuple(row)
    assert loc.id is None
    assert loc.name == "Williams-Nosef Stadium"
    assert loc.home_team == "Greenwood"


def test_location_from_db_tuple_bad_length_raises() -> None:
    with pytest.raises(ValueError):
        Location.from_db_tuple(("Stadium",))


# ---------------------------------------------------------------------------
# Bracket
# ---------------------------------------------------------------------------

_BRACKET = Bracket(name="2025 5A Bracket", season=2025, class_=5, source="mhsaa")


def test_bracket_as_db_tuple() -> None:
    assert _BRACKET.as_db_tuple() == ("2025 5A Bracket", 2025, 5, "mhsaa")


def test_bracket_from_db_tuple_4col() -> None:
    b = Bracket.from_db_tuple(("2025 5A Bracket", 2025, 5, "mhsaa"))
    assert b.name == "2025 5A Bracket"
    assert b.season == 2025
    assert b.class_ == 5
    assert b.source == "mhsaa"


def test_bracket_from_db_tuple_bad_length_raises() -> None:
    with pytest.raises(ValueError):
        Bracket.from_db_tuple(("name", 2025))


# ---------------------------------------------------------------------------
# BracketTeam
# ---------------------------------------------------------------------------

_BRACKET_TEAM = BracketTeam(bracket_id=7, school="Greenwood", season=2025, seed=1, region=3)


def test_bracket_team_as_db_tuple() -> None:
    assert _BRACKET_TEAM.as_db_tuple() == (7, "Greenwood", 2025, 1, 3)


def test_bracket_team_from_db_tuple_5col() -> None:
    bt = BracketTeam.from_db_tuple((7, "Greenwood", 2025, 1, 3))
    assert bt.bracket_id == 7
    assert bt.school == "Greenwood"
    assert bt.seed == 1


def test_bracket_team_from_db_tuple_bad_length_raises() -> None:
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
    t = _BRACKET_GAME_FULL.as_db_tuple()
    assert t == (7, "quarterfinals", 1, "Greenwood", "Starkville", 3, 1, 2, 2, 99)


def test_bracket_game_from_db_tuple_3col() -> None:
    bg = BracketGame.from_db_tuple((7, "quarterfinals", 1))
    assert bg.bracket_id == 7
    assert bg.round == "quarterfinals"
    assert bg.game_number == 1
    assert bg.home is None
    assert bg.away is None
    assert bg.home_region is None
    assert bg.next_game_id is None


def test_bracket_game_from_db_tuple_10col() -> None:
    row = (7, "quarterfinals", 1, "Greenwood", "Starkville", 3, 1, 2, 2, 99)
    bg = BracketGame.from_db_tuple(row)
    assert bg.home == "Greenwood"
    assert bg.away == "Starkville"
    assert bg.home_seed == 1
    assert bg.next_game_id == 99


def test_bracket_game_from_db_tuple_bad_length_raises() -> None:
    with pytest.raises(ValueError):
        BracketGame.from_db_tuple((7, "quarterfinals", 1, "extra"))
