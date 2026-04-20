"""Tests for bracket_helpers.survivors_from_games."""

from datetime import date

import pytest

from backend.helpers.bracket_helpers import survivors_from_games
from backend.helpers.data_classes import Game

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_DATE = date(2025, 11, 14)
_SEASON = 2025


def _game(school: str, result: str | None, round_name: str | None = "First Round") -> Game:
    """Build a minimal Game record with only the fields survivors_from_games cares about."""
    return Game(
        school=school,
        date=_DATE,
        season=_SEASON,
        location_id=None,
        points_for=None,
        points_against=None,
        round=round_name,
        kickoff_time=None,
        opponent=None,
        result=result,
        game_status=None,
        source=None,
    )


# School → (region, seed) lookup used across tests.
_LOOKUP: dict[str, tuple[int, int]] = {
    "Taylorsville": (8, 1),
    "West Lincoln": (7, 4),
    "South Delta": (6, 2),
    "Ethel": (5, 3),
    "Bogue Chitto": (7, 1),
    "Richton": (8, 4),
    "Leake County": (5, 2),
    "Shaw": (6, 3),
    "Nanih Waiya": (5, 1),
    "Lumberton": (8, 3),
    "Simmons": (6, 1),
    "Stringer": (8, 2),
}


# ---------------------------------------------------------------------------
# 1. Empty / no completed games
# ---------------------------------------------------------------------------


class TestNoGames:
    """survivors_from_games returns empty sets when no completed games are present."""

    def test_empty_list_returns_empty_sets(self):
        """An empty game list produces two empty survivor sets."""
        known, r1 = survivors_from_games([], _LOOKUP)
        assert known == set()
        assert r1 == set()

    def test_unplayed_games_ignored(self):
        """Games with result=None (not yet played) contribute nothing to either set."""
        games = [
            _game("Taylorsville", None),
            _game("West Lincoln", None),
        ]
        known, r1 = survivors_from_games(games, _LOOKUP)
        assert known == set()
        assert r1 == set()


# ---------------------------------------------------------------------------
# 2. After First Round only
# ---------------------------------------------------------------------------


class TestAfterR1:
    """Post-R1 state for the 1A South half (2025 actual results)."""

    # R1 winners: Taylorsville, South Delta, Bogue Chitto, Leake County,
    #             Nanih Waiya, Lumberton, Simmons, Stringer
    # R1 losers:  West Lincoln, Ethel, Richton, Shaw,
    #             (+ the other 4 from the North group — not in this lookup)

    @pytest.fixture
    def r1_games(self):
        """Eight W/L game records representing the actual 2025 1A south-half R1 results."""
        return [
            _game("Taylorsville", "W", "First Round"),
            _game("West Lincoln", "L", "First Round"),
            _game("South Delta", "W", "First Round"),
            _game("Ethel", "L", "First Round"),
            _game("Bogue Chitto", "W", "First Round"),
            _game("Richton", "L", "First Round"),
            _game("Leake County", "W", "First Round"),
            _game("Shaw", "L", "First Round"),
            _game("Nanih Waiya", "W", "First Round"),
            _game("Lumberton", "W", "First Round"),
            _game("Simmons", "W", "First Round"),
            _game("Stringer", "W", "First Round"),
        ]

    def test_known_survivors_are_r1_winners(self, r1_games):
        """known_survivors equals the set of all eight R1 winners."""
        known, _ = survivors_from_games(r1_games, _LOOKUP)
        assert known == {
            (8, 1),
            (6, 2),
            (7, 1),
            (5, 2),
            (5, 1),
            (8, 3),
            (6, 1),
            (8, 2),
        }

    def test_r1_survivors_match_known_after_r1(self, r1_games):
        """After only R1, r1_survivors and known_survivors are identical."""
        known, r1 = survivors_from_games(r1_games, _LOOKUP)
        assert r1 == known

    def test_losers_not_in_known_survivors(self, r1_games):
        """R1 losers (West Lincoln, Ethel, Richton, Shaw) must not appear in known_survivors."""
        known, _ = survivors_from_games(r1_games, _LOOKUP)
        for seed_pair in [(7, 4), (5, 3), (8, 4), (6, 3)]:
            assert seed_pair not in known


# ---------------------------------------------------------------------------
# 3. After Second Round
# ---------------------------------------------------------------------------


class TestAfterR2:
    """Post-R2 state: Lumberton lost R2 to Nanih Waiya, Stringer lost R2 to
    Simmons, Bogue Chitto lost R2 to Leake County, South Delta lost R2 to
    Taylorsville."""

    @pytest.fixture
    def r2_games(self):
        """R1 + R2 game records: all eight R1 winners, then four R2 W/L pairs."""
        return [
            # R1
            _game("Taylorsville", "W", "First Round"),
            _game("West Lincoln", "L", "First Round"),
            _game("South Delta", "W", "First Round"),
            _game("Ethel", "L", "First Round"),
            _game("Bogue Chitto", "W", "First Round"),
            _game("Richton", "L", "First Round"),
            _game("Leake County", "W", "First Round"),
            _game("Shaw", "L", "First Round"),
            _game("Nanih Waiya", "W", "First Round"),
            _game("Lumberton", "W", "First Round"),
            _game("Simmons", "W", "First Round"),
            _game("Stringer", "W", "First Round"),
            # R2
            _game("Taylorsville", "W", "Second Round"),
            _game("South Delta", "L", "Second Round"),
            _game("Leake County", "W", "Second Round"),
            _game("Bogue Chitto", "L", "Second Round"),
            _game("Nanih Waiya", "W", "Second Round"),
            _game("Lumberton", "L", "Second Round"),
            _game("Simmons", "W", "Second Round"),
            _game("Stringer", "L", "Second Round"),
        ]

    def test_known_survivors_are_r2_winners(self, r2_games):
        """known_survivors equals the four R2 winners (Taylorsville, Leake County, Nanih Waiya, Simmons)."""
        known, _ = survivors_from_games(r2_games, _LOOKUP)
        assert known == {(8, 1), (5, 2), (5, 1), (6, 1)}

    def test_r1_survivors_includes_r2_losers(self, r2_games):
        """r1_survivors must include teams that won R1 even if they lost R2."""
        _, r1 = survivors_from_games(r2_games, _LOOKUP)
        # Bogue Chitto and Lumberton won R1 but lost R2 — must be in r1_survivors.
        assert (7, 1) in r1  # Bogue Chitto
        assert (8, 3) in r1  # Lumberton

    def test_r1_survivors_excludes_r1_losers(self, r2_games):
        """Teams that lost in R1 must not appear in r1_survivors."""
        _, r1 = survivors_from_games(r2_games, _LOOKUP)
        assert (7, 4) not in r1  # West Lincoln lost R1
        assert (5, 3) not in r1  # Ethel lost R1

    def test_known_and_r1_differ_after_r2(self, r2_games):
        """After R2, known_survivors ⊂ r1_survivors (R2 losers stay in r1 but leave known)."""
        known, r1 = survivors_from_games(r2_games, _LOOKUP)
        assert known != r1
        assert known.issubset(r1)  # every current survivor also won R1


# ---------------------------------------------------------------------------
# 4. School not in lookup is skipped silently
# ---------------------------------------------------------------------------


class TestUnknownSchool:
    """Schools absent from school_to_seed are silently skipped without raising."""

    def test_unknown_winner_skipped(self):
        """A winning school not in the lookup does not appear in known_survivors."""
        games = [
            _game("Taylorsville", "W", "First Round"),
            _game("UnknownSchool", "W", "First Round"),
        ]
        known, r1 = survivors_from_games(games, _LOOKUP)
        assert (8, 1) in known
        # UnknownSchool has no entry — must not raise, must not appear
        for seed_pair in known:
            assert seed_pair in _LOOKUP.values()

    def test_unknown_loser_skipped(self):
        """A losing school not in the lookup does not affect known_survivors."""
        games = [
            _game("Taylorsville", "W", "First Round"),
            _game("UnknownSchool", "L", "First Round"),
        ]
        known, r1 = survivors_from_games(games, _LOOKUP)
        assert (8, 1) in known


# ---------------------------------------------------------------------------
# 5. Partial lookup (one bracket half only)
# ---------------------------------------------------------------------------


class TestPartialLookup:
    """Passing only one bracket half's schools is a valid use case."""

    def test_other_half_schools_silently_excluded(self):
        """Schools from the other bracket half (not in lookup) are silently dropped."""
        partial_lookup = {"Taylorsville": (8, 1), "Leake County": (5, 2)}
        games = [
            _game("Taylorsville", "W", "First Round"),
            _game("Nanih Waiya", "W", "First Round"),  # not in partial_lookup
        ]
        known, r1 = survivors_from_games(games, partial_lookup)
        assert known == {(8, 1)}
        assert r1 == {(8, 1)}


# ---------------------------------------------------------------------------
# 6. result=None rows are ignored
# ---------------------------------------------------------------------------


class TestNoneResult:
    """Games with result=None (not yet played) are ignored by survivors_from_games."""

    def test_none_result_not_counted(self):
        """A None-result game is not counted as a loss, so the opponent stays eligible."""
        games = [
            _game("Taylorsville", "W", "First Round"),
            _game("West Lincoln", None, "First Round"),  # not yet played
        ]
        known, r1 = survivors_from_games(games, _LOOKUP)
        # West Lincoln has no result — should NOT appear as loser, so Taylorsville
        # is alive and West Lincoln is neither in nor excluded from survivors.
        assert (8, 1) in known  # Taylorsville won
        assert (7, 4) not in known  # West Lincoln has no W


# ---------------------------------------------------------------------------
# 7. Integration: use output directly in enumerate_team_matchups
# ---------------------------------------------------------------------------


class TestRoundTripWithEnumerateMatchups:
    """Verify survivors_from_games output feeds enumerate_team_matchups correctly."""

    def test_post_r1_feeds_enumerate_matchups(self):
        """known_survivors + r1_survivors from games produce correct QF pool."""
        from backend.helpers.home_game_scenarios import enumerate_team_matchups
        from backend.tests.data.playoff_brackets_2025 import SLOTS_1A_4A_2025

        r1_games = [
            _game("Taylorsville", "W", "First Round"),
            _game("West Lincoln", "L", "First Round"),
            _game("South Delta", "W", "First Round"),
            _game("Ethel", "L", "First Round"),
            _game("Bogue Chitto", "W", "First Round"),
            _game("Richton", "L", "First Round"),
            _game("Leake County", "W", "First Round"),
            _game("Shaw", "L", "First Round"),
            _game("Nanih Waiya", "W", "First Round"),
            _game("Lumberton", "W", "First Round"),
            _game("Simmons", "W", "First Round"),
            _game("Stringer", "W", "First Round"),
        ]
        known, r1 = survivors_from_games(r1_games, _LOOKUP)

        rounds = enumerate_team_matchups(
            region=8,
            seed=1,
            slots=SLOTS_1A_4A_2025,
            season=2025,
            known_survivors=known,
            r1_survivors=r1,
            completed_rounds={"First Round"},
        )
        round_names = [r.round_name for r in rounds]
        assert "First Round" not in round_names
        assert "Second Round" in round_names

        # QF must show only alive QF opponents (Richton/Shaw eliminated)
        qf = next(r for r in rounds if r.round_name == "Quarterfinals")
        qf_opponents = {e.opponent_region * 10 + e.opponent_seed for e in qf.entries}
        # Richton (8,4) and Shaw (6,3) must not appear
        assert (8 * 10 + 4) not in qf_opponents
        assert (6 * 10 + 3) not in qf_opponents


# ---------------------------------------------------------------------------
# 8. Real 2025 game data — 1A south half (Taylorsville bracket)
# ---------------------------------------------------------------------------


class TestWith2025ActualGames:
    """Verify survivors_from_games against real 2025 1A playoff results.

    Scope: the 1A south-half bracket (the 12 schools Taylorsville encountered
    or could have encountered through the semifinals).  Games for all other
    schools are silently ignored because they are absent from the lookup.
    """

    from backend.tests.data.playoff_games_2025 import PLAYOFF_GAMES_2025 as _ALL_GAMES

    _LOOKUP: dict[str, tuple[int, int]] = {
        "Taylorsville": (8, 1),
        "West Lincoln": (7, 4),
        "South Delta": (6, 2),
        "Ethel": (5, 3),
        "Bogue Chitto": (7, 1),
        "Richton": (8, 4),
        "Leake County": (5, 2),
        "Shaw": (6, 3),
        "Nanih Waiya": (5, 1),
        "Lumberton": (8, 3),
        "Simmons": (6, 1),
        "Stringer": (8, 2),
    }

    def _games_through(self, *round_names: str) -> list:
        """Filter PLAYOFF_GAMES_2025 to only the given round names."""
        return [g for g in self._ALL_GAMES if g.round in round_names]

    def test_after_r1_known_equals_r1_survivors(self):
        """After R1, all eight south-half winners are alive and r1_survivors == known_survivors."""
        games = self._games_through("First Round")
        known, r1 = survivors_from_games(games, self._LOOKUP)
        assert known == {(8, 1), (6, 2), (7, 1), (5, 2), (5, 1), (8, 3), (6, 1), (8, 2)}
        assert known == r1

    def test_after_r2_known_survivors(self):
        """After R2, only the four R2 winners (Taylorsville, Leake County, Nanih Waiya, Simmons) are alive."""
        games = self._games_through("First Round", "Second Round")
        known, _ = survivors_from_games(games, self._LOOKUP)
        assert known == {(8, 1), (5, 2), (5, 1), (6, 1)}

    def test_after_r2_r1_survivors_includes_r2_losers(self):
        """r1_survivors includes Bogue Chitto and Lumberton even though both lost in R2."""
        games = self._games_through("First Round", "Second Round")
        _, r1 = survivors_from_games(games, self._LOOKUP)
        # Bogue Chitto (7,1) and Lumberton (8,3) won R1 but lost R2
        assert (7, 1) in r1
        assert (8, 3) in r1
        # R1 losers still excluded
        assert (7, 4) not in r1  # West Lincoln
        assert (5, 3) not in r1  # Ethel

    def test_after_qf_known_survivors(self):
        """After QF, only Taylorsville and Simmons remain alive (both won their QF)."""
        games = self._games_through("First Round", "Second Round", "Quarterfinals")
        known, _ = survivors_from_games(games, self._LOOKUP)
        assert known == {(8, 1), (6, 1)}

    def test_after_sf_taylorsville_eliminated(self):
        """After SF, only Simmons remains — Simmons beat Taylorsville in the actual 2025 semifinal."""
        games = self._games_through("First Round", "Second Round", "Quarterfinals", "Semifinals")
        known, _ = survivors_from_games(games, self._LOOKUP)
        assert (8, 1) not in known  # Taylorsville lost
        assert (6, 1) in known  # Simmons won
        assert known == {(6, 1)}

    def test_r1_survivors_unchanged_after_later_rounds(self):
        """r1_survivors computed from R1-only equals r1_survivors computed from all rounds."""
        r1_games = self._games_through("First Round")
        _, r1_after_r1 = survivors_from_games(r1_games, self._LOOKUP)

        all_games = self._games_through("First Round", "Second Round", "Quarterfinals", "Semifinals")
        _, r1_full = survivors_from_games(all_games, self._LOOKUP)

        assert r1_after_r1 == r1_full
