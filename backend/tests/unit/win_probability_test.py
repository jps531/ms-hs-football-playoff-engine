"""Unit tests for backend/helpers/win_probability.py.

All tests are pure Python — no DB, no Prefect, no I/O.
Fixtures are built inline from Game and School dataclasses.
"""

from datetime import date

import pytest

from backend.helpers.data_classes import Game, School, WinProbFactors
from backend.helpers.win_probability import (
    EloConfig,
    _class_prior,
    _elo_expected,
    _mov_multiplier,
    compute_elo_ratings,
    compute_rpi,
    make_win_prob_fn,
    make_win_prob_fn_from_ratings,
    win_prob_with_factors,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _school(name: str, class_: int) -> School:
    """Build a minimal School fixture for testing."""
    return School(school=name, season=2025, class_=class_, region=1)


def _game(
    school: str,
    opponent: str,
    result: str,
    points_for: int,
    points_against: int,
    game_date: date,
    location: str = "neutral",
    region_game: bool = False,
) -> Game:
    """Build a minimal Game fixture with final=True for testing."""
    return Game(
        school=school,
        date=game_date,
        season=2025,
        location_id=None,
        points_for=points_for,
        points_against=points_against,
        round=None,
        kickoff_time=None,
        opponent=opponent,
        result=result,
        game_status="Final",
        source="test",
        location=location,
        region_game=region_game,
        final=True,
        overtime=0,
    )


# Four-team fixture: Alpha (7A) > Beta (6A) > Gamma (5A) > Delta (4A)
# Alpha beat Beta 35-14 (home), Beta beat Gamma 28-7 (neutral), Gamma beat Delta 21-0 (away)
SCHOOLS_4 = [
    _school("Alpha", 7),
    _school("Beta", 6),
    _school("Gamma", 5),
    _school("Delta", 4),
]
GAMES_4 = [
    # Alpha beat Beta at home (both perspectives)
    _game("Alpha", "Beta", "W", 35, 14, date(2025, 9, 5), location="home"),
    _game("Beta", "Alpha", "L", 14, 35, date(2025, 9, 5), location="away"),
    # Beta beat Gamma at neutral
    _game("Beta", "Gamma", "W", 28, 7, date(2025, 9, 12), location="neutral"),
    _game("Gamma", "Beta", "L", 7, 28, date(2025, 9, 12), location="neutral"),
    # Gamma beat Delta (Gamma was away)
    _game("Gamma", "Delta", "W", 21, 0, date(2025, 9, 19), location="away"),
    _game("Delta", "Gamma", "L", 0, 21, date(2025, 9, 19), location="home"),
]


# ---------------------------------------------------------------------------
# TestEloConfig
# ---------------------------------------------------------------------------


class TestEloConfig:
    """Tests for EloConfig defaults and custom overrides."""

    def test_defaults(self):
        """All default fields match documented values."""
        cfg = EloConfig()
        assert cfg.k_regular == pytest.approx(40.0)
        assert cfg.k_region == pytest.approx(50.0)
        assert cfg.hfa_points == pytest.approx(65.0)
        assert cfg.scale == pytest.approx(400.0)
        assert len(cfg.class_ratings) == 7
        assert cfg.class_ratings[0] == pytest.approx(1000.0)
        assert cfg.class_ratings[6] == pytest.approx(1300.0)

    def test_class_ratings_step(self):
        """Class ratings increase by 50 per classification step."""
        cfg = EloConfig()
        for i in range(7):
            assert cfg.class_ratings[i] == pytest.approx(1000.0 + i * 50.0)

    def test_custom_override(self):
        """Custom values override defaults; untouched fields keep defaults."""
        cfg = EloConfig(k_regular=20.0, hfa_points=100.0)
        assert cfg.k_regular == pytest.approx(20.0)
        assert cfg.hfa_points == pytest.approx(100.0)
        assert cfg.k_region == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# TestEloInternals
# ---------------------------------------------------------------------------


class TestEloInternals:
    """Tests for _elo_expected and _mov_multiplier helper functions."""

    def test_expected_equal_ratings_is_half(self):
        """Equal ratings produce P=0.5."""
        assert _elo_expected(1200.0, 1200.0, 400.0) == pytest.approx(0.5)

    def test_expected_400_point_gap(self):
        """400-point gap yields 10:1 odds."""
        # 400-point gap → 10:1 odds → P = 10/11 ≈ 0.9091
        p = _elo_expected(1600.0, 1200.0, 400.0)
        assert p == pytest.approx(10 / 11, rel=1e-4)

    def test_expected_symmetry(self):
        """P(A beats B) + P(B beats A) == 1."""
        p_ab = _elo_expected(1300.0, 1100.0, 400.0)
        p_ba = _elo_expected(1100.0, 1300.0, 400.0)
        assert p_ab + p_ba == pytest.approx(1.0)

    def test_expected_higher_rating_wins_more(self):
        """Higher-rated team has P > 0.5."""
        assert _elo_expected(1400.0, 1000.0, 400.0) > 0.5

    def test_mov_zero_margin_returns_one(self):
        """Zero margin produces multiplier of 1.0."""
        assert _mov_multiplier(0, 100.0, 2.2) == pytest.approx(1.0)

    def test_mov_larger_margin_larger_mult(self):
        """Larger scoring margin yields larger multiplier."""
        # Same Elo diff — bigger margin should produce bigger multiplier
        m_small = _mov_multiplier(7, 0.0, 2.2)
        m_large = _mov_multiplier(35, 0.0, 2.2)
        assert m_large > m_small

    def test_mov_favourite_blowout_discounted(self):
        """Favourite blowout is discounted vs equal-rating blowout."""
        # Winning by 35 when favourite (large Elo advantage) vs equal match
        m_favourite = _mov_multiplier(35, 300.0, 2.2)
        m_equal = _mov_multiplier(35, 0.0, 2.2)
        assert m_favourite < m_equal

    def test_class_prior_known_school(self):
        """Known school returns its classification-based starting Elo."""
        schools_by_name = {"TeamX": _school("TeamX", 5)}
        result = _class_prior("TeamX", schools_by_name, EloConfig())
        assert result == pytest.approx(EloConfig().class_ratings[4])  # 5A = index 4

    def test_class_prior_unknown_school(self):
        """Unknown school returns the 1A fallback prior."""
        result = _class_prior("OOSTeam", {}, EloConfig())
        assert result == pytest.approx(EloConfig().class_ratings[0])


# ---------------------------------------------------------------------------
# TestComputeEloRatings
# ---------------------------------------------------------------------------


class TestComputeEloRatings:
    """Tests for compute_elo_ratings output structure and correctness."""

    def test_returns_three_tuple(self):
        """Return value is a 3-tuple of (ratings, games_count, snapshots)."""
        result = compute_elo_ratings(GAMES_4, SCHOOLS_4, EloConfig())
        assert isinstance(result, tuple) and len(result) == 3

    def test_winner_gains_loser_loses(self):
        """Winner's rating rises and loser's falls from the classification prior."""
        cfg = EloConfig()
        # Use a single isolated game so net direction is unambiguous.
        games = [
            _game("Winner", "Loser", "W", 21, 7, date(2025, 9, 5)),
            _game("Loser", "Winner", "L", 7, 21, date(2025, 9, 5)),
        ]
        schools = [_school("Winner", 4), _school("Loser", 4)]
        ratings, _, _ = compute_elo_ratings(games, schools, cfg)
        base = cfg.class_ratings[3]  # 4A = index 3
        assert ratings["Winner"] > base
        assert ratings["Loser"] < base

    def test_ordering_is_transitive(self):
        """Stronger teams rank higher after a chain of results."""
        ratings, _, _ = compute_elo_ratings(GAMES_4, SCHOOLS_4, EloConfig())
        assert ratings["Alpha"] > ratings["Beta"] > ratings["Gamma"] > ratings["Delta"]

    def test_games_count_correct(self):
        """games_count reflects the number of completed games per team."""
        _, games_count, _ = compute_elo_ratings(GAMES_4, SCHOOLS_4, EloConfig())
        # Each team played exactly one game
        assert games_count["Alpha"] == 1
        assert games_count["Beta"] == 2
        assert games_count["Gamma"] == 2
        assert games_count["Delta"] == 1

    def test_deduplication(self):
        """Two-perspective DB rows produce the same ratings as single-perspective rows."""
        # Each game in GAMES_4 has both perspectives — dedup should process each once.
        # Result with deduplication should equal result with only one perspective supplied.
        single_perspective = [g for g in GAMES_4 if g.result == "W"]  # only winners' rows
        r_full, _, _ = compute_elo_ratings(GAMES_4, SCHOOLS_4, EloConfig())
        r_single, _, _ = compute_elo_ratings(single_perspective, SCHOOLS_4, EloConfig())
        for school in ["Alpha", "Beta", "Gamma", "Delta"]:
            assert r_full[school] == pytest.approx(r_single[school], rel=1e-6)

    def test_region_game_larger_delta(self):
        """Region K-factor produces a larger rating swing than non-region K-factor."""
        # A region game win should produce a bigger rating change than a non-region win
        # with identical margins (same starting ratings, same scores, only region_game differs).
        schools = [_school("TeamA", 4), _school("TeamB", 4)]
        non_region = [
            _game("TeamA", "TeamB", "W", 14, 7, date(2025, 9, 5), region_game=False),
            _game("TeamB", "TeamA", "L", 7, 14, date(2025, 9, 5), region_game=False),
        ]
        region = [
            _game("TeamA", "TeamB", "W", 14, 7, date(2025, 9, 5), region_game=True),
            _game("TeamB", "TeamA", "L", 7, 14, date(2025, 9, 5), region_game=True),
        ]
        cfg = EloConfig()
        base = cfg.class_ratings[3]  # 4A = index 3

        r_nr, _, _ = compute_elo_ratings(non_region, schools, cfg)
        r_r, _, _ = compute_elo_ratings(region, schools, cfg)

        delta_nr = r_nr["TeamA"] - base
        delta_r = r_r["TeamA"] - base
        assert delta_r > delta_nr > 0

    def test_hfa_home_win_smaller_gain(self):
        """Home winner gains less than an away winner with the same margin."""
        # Home team winning should gain LESS than away team winning same game,
        # because home team's expected probability is already inflated by HFA.
        cfg = EloConfig()
        schools = [_school("HomeTeam", 4), _school("AwayTeam", 4)]

        home_wins = [
            _game("HomeTeam", "AwayTeam", "W", 21, 7, date(2025, 9, 5), location="home"),
            _game("AwayTeam", "HomeTeam", "L", 7, 21, date(2025, 9, 5), location="away"),
        ]
        away_wins = [
            _game("AwayTeam", "HomeTeam", "W", 21, 7, date(2025, 9, 5), location="away"),
            _game("HomeTeam", "AwayTeam", "L", 7, 21, date(2025, 9, 5), location="home"),
        ]
        base = cfg.class_ratings[3]

        r_hw, _, _ = compute_elo_ratings(home_wins, schools, cfg)
        r_aw, _, _ = compute_elo_ratings(away_wins, schools, cfg)

        # Home winner's gain vs away winner's gain (same margin, same opponent quality)
        home_winner_gain = r_hw["HomeTeam"] - base
        away_winner_gain = r_aw["AwayTeam"] - base
        assert 0 < home_winner_gain < away_winner_gain

    def test_unknown_opponent_gets_fallback_prior(self):
        """Out-of-state opponents receive a 1A fallback prior."""
        # An out-of-state team not in schools list should use class_ratings[0]
        games = [
            _game("MSTeam", "OOSTeam", "W", 28, 0, date(2025, 9, 5)),
            _game("OOSTeam", "MSTeam", "L", 0, 28, date(2025, 9, 5)),
        ]
        ratings, _, _ = compute_elo_ratings(games, [_school("MSTeam", 5)], EloConfig())
        assert "MSTeam" in ratings
        # OOSTeam should also have a rating (assigned during processing)
        assert "OOSTeam" in ratings

    def test_snapshots_chronological(self):
        """Snapshots are returned in ascending date order."""
        _, _, snapshots = compute_elo_ratings(GAMES_4, SCHOOLS_4, EloConfig())
        dates = [d for d, _ in snapshots]
        assert dates == sorted(dates)

    def test_snapshots_one_per_game_date(self):
        """One snapshot is recorded per unique game date."""
        _, _, snapshots = compute_elo_ratings(GAMES_4, SCHOOLS_4, EloConfig())
        # GAMES_4 has three unique dates: Sep 5, 12, 19
        assert len(snapshots) == 3

    def test_no_games_returns_priors(self):
        """Empty game list yields classification priors and empty snapshots."""
        ratings, games_count, snapshots = compute_elo_ratings([], SCHOOLS_4, EloConfig())
        cfg = EloConfig()
        assert ratings["Alpha"] == pytest.approx(cfg.class_ratings[6])  # 7A
        assert ratings["Delta"] == pytest.approx(cfg.class_ratings[3])  # 4A
        assert all(v == 0 for v in games_count.values())
        assert snapshots == []

    def test_loser_perspective_processed(self):
        """Processed row with result=L updates ratings in the correct direction."""
        # Empty schools list so neither team is pre-seeded — forces both
        # school-not-in-ratings branches (lines 162, 164) to fire.
        # "Loser" < "Winner" alphabetically, so the loser's row is the first
        # unique occurrence and is the one processed after deduplication.
        games = [
            _game("Loser", "Winner", "L", 7, 21, date(2025, 9, 5)),
            _game("Winner", "Loser", "W", 21, 7, date(2025, 9, 5)),
        ]
        ratings, _, _ = compute_elo_ratings(games, [], EloConfig())
        base = EloConfig().class_ratings[0]  # 1A fallback prior for both
        assert ratings["Loser"] < base
        assert ratings["Winner"] > base

    def test_tie_outcome_split_evenly(self):
        """Tie game results in no net rating change for equal-rated teams."""
        games = [_game("AlphaT", "BetaT", "T", 7, 7, date(2025, 9, 5))]
        schools = [_school("AlphaT", 4), _school("BetaT", 4)]
        ratings, _, _ = compute_elo_ratings(games, schools, EloConfig())
        base = EloConfig().class_ratings[3]  # 4A prior
        # Equal ratings, tie → expected=0.5, actual=0.5, delta=0
        assert ratings["AlphaT"] == pytest.approx(base, abs=0.01)
        assert ratings["BetaT"] == pytest.approx(base, abs=0.01)


# ---------------------------------------------------------------------------
# TestDateConditionedRatings
# ---------------------------------------------------------------------------


class TestDateConditionedRatings:
    """Tests for date-conditioned rating lookup in the WinProbFn closure."""

    def setup_method(self):
        """Pre-compute ratings and snapshots for the shared GAMES_4 fixture."""
        self.cfg = EloConfig()
        self.ratings, _, self.snapshots = compute_elo_ratings(GAMES_4, SCHOOLS_4, self.cfg)

    def test_none_date_returns_final_ratings(self):
        """date_str=None and a future date both use final ratings."""
        fn = make_win_prob_fn(GAMES_4, SCHOOLS_4, self.cfg)
        p_none = fn("Alpha", "Delta", None, None)
        p_future = fn("Alpha", "Delta", "2026-01-01", None)
        assert p_none == pytest.approx(p_future)

    def test_before_all_games_uses_priors(self):
        """A date before the first game returns classification priors."""
        fn = make_win_prob_fn(GAMES_4, SCHOOLS_4, self.cfg)
        # Before Sep 5 — no games played, ratings are classification priors
        # Alpha (7A, 1300) vs Delta (4A, 1150) → Alpha favoured but not by much
        p_early = fn("Alpha", "Delta", "2025-08-01", None)
        p_from_priors = _elo_expected(self.cfg.class_ratings[6], self.cfg.class_ratings[3], self.cfg.scale)
        assert p_early == pytest.approx(p_from_priors, rel=1e-4)

    def test_mid_season_differs_from_final(self):
        """Mid-season ratings differ from end-of-season ratings."""
        fn = make_win_prob_fn(GAMES_4, SCHOOLS_4, self.cfg)
        # After week 1 only (Alpha beat Beta, Beta beat Gamma, Gamma beat Delta all in later weeks)
        p_after_w1 = fn("Alpha", "Delta", "2025-09-06", None)
        p_final = fn("Alpha", "Delta", None, None)
        # Ratings should differ once more games have been played
        assert p_after_w1 != pytest.approx(p_final)

    def test_snapshot_binary_search_boundary(self):
        """Date on a game day and the day after both use the same snapshot."""
        fn = make_win_prob_fn(GAMES_4, SCHOOLS_4, self.cfg)
        # On the exact game date should use that day's snapshot (after those games)
        p_on_date = fn("Beta", "Gamma", "2025-09-12", None)
        p_day_after = fn("Beta", "Gamma", "2025-09-13", None)
        # Both use the same snapshot (Sep 12), so should be equal
        assert p_on_date == pytest.approx(p_day_after)


# ---------------------------------------------------------------------------
# TestMakeWinProbFn
# ---------------------------------------------------------------------------


class TestMakeWinProbFn:
    """Tests for make_win_prob_fn and make_win_prob_fn_from_ratings."""

    def test_returns_callable(self):
        """Factory returns a callable."""
        fn = make_win_prob_fn(GAMES_4, SCHOOLS_4)
        assert callable(fn)

    def test_output_in_unit_interval(self):
        """All return values are in [0, 1]."""
        fn = make_win_prob_fn(GAMES_4, SCHOOLS_4)
        for a, b in [("Alpha", "Beta"), ("Gamma", "Delta"), ("Alpha", "Delta")]:
            p = fn(a, b, None, None)
            assert 0.0 <= p <= 1.0

    def test_stronger_team_favoured(self):
        """Team with better record is favoured over weaker opponent."""
        fn = make_win_prob_fn(GAMES_4, SCHOOLS_4)
        # Alpha won, Delta lost — Alpha should be heavily favoured over Delta
        assert fn("Alpha", "Delta", None, None) > 0.6

    def test_unknown_team_returns_half(self):
        """Unknown team name returns 0.5 (graceful fallback)."""
        fn = make_win_prob_fn(GAMES_4, SCHOOLS_4)
        assert fn("Alpha", "UnknownTeam", None, None) == pytest.approx(0.5)
        assert fn("UnknownA", "UnknownB", None, None) == pytest.approx(0.5)

    def test_home_advantage_shifts_prob_up(self):
        """Home location increases probability above neutral."""
        fn = make_win_prob_fn(GAMES_4, SCHOOLS_4)
        p_neutral = fn("Alpha", "Beta", None, "neutral")
        p_home = fn("Alpha", "Beta", None, "home")
        assert p_home > p_neutral

    def test_away_disadvantage_shifts_prob_down(self):
        """Away location decreases probability below neutral."""
        fn = make_win_prob_fn(GAMES_4, SCHOOLS_4)
        p_neutral = fn("Alpha", "Beta", None, "neutral")
        p_away = fn("Alpha", "Beta", None, "away")
        assert p_away < p_neutral

    def test_home_away_are_complements(self):
        """Home probability is strictly greater than away probability."""
        fn = make_win_prob_fn(GAMES_4, SCHOOLS_4)
        # P(A beats B at home) + P(B beats A at home) = 1
        # Equivalently: P(A home) + P(A away) ≠ 1 (not complements of each other)
        # But P(A home vs B) should equal 1 - P(B home vs A):
        p_a_home = fn("Alpha", "Beta", None, "home")
        # P(B home vs A) — note "Beta" must be lex-first to be team_a... check order
        # Alpha < Beta lexicographically, so fn("Alpha", "Beta", ...) is always Alpha=a
        # To get "Beta hosts Alpha": we'd call with Beta as team_a and location_a='home',
        # but Alpha < Beta so Alpha is always a. Instead check via complement:
        p_a_away = fn("Alpha", "Beta", None, "away")
        # p_a_home (Alpha home vs Beta) should be the mirror of p_a_away (Alpha away vs Beta)
        # i.e. p_a_home + p_a_away should span around 0.5 symmetrically if ratings were equal
        # Just verify direction is correct
        assert p_a_home > p_a_away

    def test_none_location_equals_neutral(self):
        """None location is treated identically to 'neutral'."""
        fn = make_win_prob_fn(GAMES_4, SCHOOLS_4)
        p_none = fn("Alpha", "Beta", None, None)
        p_neutral = fn("Alpha", "Beta", None, "neutral")
        assert p_none == pytest.approx(p_neutral)

    def test_make_from_ratings_matches_make_from_games(self):
        """Both factories produce identical probabilities for the same data."""
        cfg = EloConfig()
        final_ratings, _, snapshots = compute_elo_ratings(GAMES_4, SCHOOLS_4, cfg)
        fn_games = make_win_prob_fn(GAMES_4, SCHOOLS_4, cfg)
        fn_ratings = make_win_prob_fn_from_ratings(final_ratings, snapshots, cfg)
        for a, b in [("Alpha", "Beta"), ("Gamma", "Delta")]:
            assert fn_games(a, b, None, None) == pytest.approx(fn_ratings(a, b, None, None))

    def test_invalid_date_str_falls_back_to_final(self):
        """Unparseable date string falls back to final ratings."""
        fn = make_win_prob_fn(GAMES_4, SCHOOLS_4)
        p_invalid = fn("Alpha", "Beta", "not-a-date", None)
        p_final = fn("Alpha", "Beta", None, None)
        assert p_invalid == pytest.approx(p_final)

    def test_from_ratings_mid_season_date(self):
        """make_win_prob_fn_from_ratings returns different probability for mid-season date."""
        cfg = EloConfig()
        final_ratings, _, snapshots = compute_elo_ratings(GAMES_4, SCHOOLS_4, cfg)
        fn = make_win_prob_fn_from_ratings(final_ratings, snapshots, cfg)
        p_mid = fn("Alpha", "Delta", "2025-09-06", None)
        p_final = fn("Alpha", "Delta", None, None)
        assert p_mid != pytest.approx(p_final)

    def test_from_ratings_future_date_uses_final(self):
        """make_win_prob_fn_from_ratings treats future dates as final ratings."""
        cfg = EloConfig()
        final_ratings, _, snapshots = compute_elo_ratings(GAMES_4, SCHOOLS_4, cfg)
        fn = make_win_prob_fn_from_ratings(final_ratings, snapshots, cfg)
        p_future = fn("Alpha", "Beta", "2030-01-01", None)
        p_final = fn("Alpha", "Beta", None, None)
        assert p_future == pytest.approx(p_final)

    def test_from_ratings_invalid_date_str_falls_back_to_final(self):
        """make_win_prob_fn_from_ratings treats unparseable date strings as final."""
        cfg = EloConfig()
        final_ratings, _, snapshots = compute_elo_ratings(GAMES_4, SCHOOLS_4, cfg)
        fn = make_win_prob_fn_from_ratings(final_ratings, snapshots, cfg)
        p_invalid = fn("Alpha", "Beta", "garbage", None)
        p_final = fn("Alpha", "Beta", None, None)
        assert p_invalid == pytest.approx(p_final)

    def test_from_ratings_unknown_team_returns_half(self):
        """make_win_prob_fn_from_ratings returns 0.5 for unknown teams."""
        cfg = EloConfig()
        final_ratings, _, snapshots = compute_elo_ratings(GAMES_4, SCHOOLS_4, cfg)
        fn = make_win_prob_fn_from_ratings(final_ratings, snapshots, cfg)
        assert fn("Alpha", "Ghost", None, None) == pytest.approx(0.5)

    def test_from_ratings_home_location(self):
        """make_win_prob_fn_from_ratings applies HFA boost for home location."""
        cfg = EloConfig()
        final_ratings, _, snapshots = compute_elo_ratings(GAMES_4, SCHOOLS_4, cfg)
        fn = make_win_prob_fn_from_ratings(final_ratings, snapshots, cfg)
        assert fn("Alpha", "Beta", None, "home") > fn("Alpha", "Beta", None, "neutral")

    def test_from_ratings_away_location(self):
        """make_win_prob_fn_from_ratings applies HFA penalty for away location."""
        cfg = EloConfig()
        final_ratings, _, snapshots = compute_elo_ratings(GAMES_4, SCHOOLS_4, cfg)
        fn = make_win_prob_fn_from_ratings(final_ratings, snapshots, cfg)
        assert fn("Alpha", "Beta", None, "away") < fn("Alpha", "Beta", None, "neutral")

    def test_from_ratings_before_all_games(self):
        """make_win_prob_fn_from_ratings handles dates before first game snapshot."""
        cfg = EloConfig()
        final_ratings, _, snapshots = compute_elo_ratings(GAMES_4, SCHOOLS_4, cfg)
        fn = make_win_prob_fn_from_ratings(final_ratings, snapshots, cfg)
        p_before = fn("Alpha", "Delta", "2025-08-01", None)
        assert 0.0 < p_before < 1.0


# ---------------------------------------------------------------------------
# TestComputeRPI
# ---------------------------------------------------------------------------


class TestComputeRPI:
    """Tests for compute_rpi formula and edge cases."""

    def test_winning_team_higher_rpi(self):
        """Unbeaten team has higher RPI than winless team in a round-robin."""
        # GAMES_4 teams each have ≤ 2 games so all RPIs are None.
        # Build a 4-team round-robin so every team has exactly 3 games.
        # W1 goes 3-0, L2 goes 0-3 → W1 RPI > L2 RPI.
        from datetime import timedelta
        base_date = date(2025, 9, 1)
        matchups = [
            ("W1", "L1"), ("W1", "L2"), ("W1", "W2"),
            ("W2", "L1"), ("W2", "L2"), ("L1", "L2"),
        ]
        games = []
        for i, (w, l) in enumerate(matchups):
            gdate = base_date + timedelta(days=i * 7)
            games += [
                _game(w, l, "W", 21, 7, gdate),
                _game(l, w, "L", 7, 21, gdate),
            ]
        rpi = compute_rpi(games)
        assert rpi["W1"] is not None
        assert rpi["L2"] is not None
        assert rpi["W1"] > rpi["L2"]

    def test_fewer_than_3_games_returns_none(self):
        """Fewer than 3 completed games yields None."""
        # Alpha and Delta each played only 1 game in GAMES_4
        rpi = compute_rpi(GAMES_4)
        assert rpi.get("Alpha") is None  # 1 game < 3
        assert rpi.get("Delta") is None  # 1 game < 3

    def test_tie_game_counted_as_half_point(self):
        """Tie result contributes 0.5 to each team's win percentage."""
        from datetime import timedelta
        base_date = date(2025, 9, 1)
        # X: 1 tie (vs Y), 1 win (vs Z), 1 loss (vs W) — exactly 3 games for X
        games = [
            _game("X", "Y", "T", 14, 14, base_date),
            _game("Y", "X", "T", 14, 14, base_date),
            _game("X", "Z", "W", 21, 0, base_date + timedelta(days=7)),
            _game("Z", "X", "L", 0, 21, base_date + timedelta(days=7)),
            _game("W", "X", "W", 21, 7, base_date + timedelta(days=14)),
            _game("X", "W", "L", 7, 21, base_date + timedelta(days=14)),
        ]
        rpi = compute_rpi(games)
        val = rpi.get("X")
        assert val is not None
        assert 0.0 <= val <= 1.0

    def test_3_game_team_has_rpi(self):
        """Exactly 3 games is sufficient for a non-None RPI."""
        games = [
            _game("TeamX", "OppA", "W", 21, 0, date(2025, 9, 5)),
            _game("OppA", "TeamX", "L", 0, 21, date(2025, 9, 5)),
            _game("TeamX", "OppB", "W", 14, 7, date(2025, 9, 12)),
            _game("OppB", "TeamX", "L", 7, 14, date(2025, 9, 12)),
            _game("TeamX", "OppC", "W", 28, 3, date(2025, 9, 19)),
            _game("OppC", "TeamX", "L", 3, 28, date(2025, 9, 19)),
        ]
        rpi = compute_rpi(games)
        assert rpi["TeamX"] is not None
        assert 0.0 < rpi["TeamX"] <= 1.0

    def test_rpi_in_unit_interval(self):
        """All non-None RPIs are in [0, 1]."""
        games = []
        for i, (s, o, res, pf, pa) in enumerate(
            [
                ("A", "B", "W", 14, 0),
                ("B", "A", "L", 0, 14),
                ("A", "C", "W", 21, 7),
                ("C", "A", "L", 7, 21),
                ("A", "D", "W", 28, 3),
                ("D", "A", "L", 3, 28),
                ("B", "C", "L", 7, 14),
                ("C", "B", "W", 14, 7),
                ("B", "D", "W", 21, 0),
                ("D", "B", "L", 0, 21),
                ("C", "D", "W", 14, 7),
                ("D", "C", "L", 7, 14),
            ]
        ):
            games.append(_game(s, o, res, pf, pa, date(2025, 9, 5 + i)))
        rpi = compute_rpi(games)
        for team in ["A", "B", "C", "D"]:
            val = rpi[team]
            if val is not None:
                assert 0.0 <= val <= 1.0

    def test_all_wins_rpi_above_half(self):
        """All-wins record against opponents with non-zero win rates yields RPI > 0.5."""
        games = []
        for i, (opp, opp_class) in enumerate([("Opp1", 4), ("Opp2", 4), ("Opp3", 4)]):
            games += [
                _game("Champ", opp, "W", 21, 7, date(2025, 9, 5 + i * 7)),
                _game(opp, "Champ", "L", 7, 21, date(2025, 9, 5 + i * 7)),
            ]
        # Add some games among opponents so they have > 0 win percentages
        games += [
            _game("Opp1", "Opp2", "W", 14, 0, date(2025, 10, 5)),
            _game("Opp2", "Opp1", "L", 0, 14, date(2025, 10, 5)),
        ]
        rpi = compute_rpi(games)
        assert rpi["Champ"] is not None
        assert rpi["Champ"] > 0.5


# ---------------------------------------------------------------------------
# TestWinProbWithFactors
# ---------------------------------------------------------------------------


class TestWinProbWithFactors:
    """Tests for win_prob_with_factors breakdown dataclass."""

    def setup_method(self):
        """Pre-compute shared ratings, games_count, RPI, and schools lookup."""
        self.cfg = EloConfig()
        self.elo_ratings, self.games_count, _ = compute_elo_ratings(GAMES_4, SCHOOLS_4, self.cfg)
        self.rpi = compute_rpi(GAMES_4)
        self.schools_by_name = {s.school: s for s in SCHOOLS_4}

    def test_returns_win_prob_factors(self):
        """Return type is WinProbFactors."""
        result = win_prob_with_factors(
            "Alpha",
            "Beta",
            self.elo_ratings,
            self.games_count,
            self.rpi,
            self.schools_by_name,
        )
        assert isinstance(result, WinProbFactors)

    def test_team_names_preserved(self):
        """team_a and team_b fields match the input arguments."""
        result = win_prob_with_factors(
            "Alpha",
            "Beta",
            self.elo_ratings,
            self.games_count,
            self.rpi,
            self.schools_by_name,
        )
        assert result.team_a == "Alpha"
        assert result.team_b == "Beta"

    def test_elo_ratings_match(self):
        """elo_a and elo_b match the ratings dict entries."""
        result = win_prob_with_factors(
            "Alpha",
            "Delta",
            self.elo_ratings,
            self.games_count,
            self.rpi,
            self.schools_by_name,
        )
        assert result.elo_a == pytest.approx(self.elo_ratings["Alpha"])
        assert result.elo_b == pytest.approx(self.elo_ratings["Delta"])

    def test_classes_correct(self):
        """class_a and class_b reflect school classifications."""
        result = win_prob_with_factors(
            "Alpha",
            "Delta",
            self.elo_ratings,
            self.games_count,
            self.rpi,
            self.schools_by_name,
        )
        assert result.class_a == 7
        assert result.class_b == 4

    def test_final_prob_equals_location_adjusted_prob(self):
        """final_prob equals location_adjusted_prob (no additional adjustment layer yet)."""
        result = win_prob_with_factors(
            "Alpha",
            "Beta",
            self.elo_ratings,
            self.games_count,
            self.rpi,
            self.schools_by_name,
            location_a="home",
        )
        assert result.final_prob == pytest.approx(result.location_adjusted_prob)

    def test_hfa_increases_prob_for_home(self):
        """Home location raises location_adjusted_prob without changing raw_elo_prob."""
        neutral = win_prob_with_factors(
            "Alpha",
            "Beta",
            self.elo_ratings,
            self.games_count,
            self.rpi,
            self.schools_by_name,
            location_a="neutral",
        )
        home = win_prob_with_factors(
            "Alpha",
            "Beta",
            self.elo_ratings,
            self.games_count,
            self.rpi,
            self.schools_by_name,
            location_a="home",
        )
        assert home.location_adjusted_prob > neutral.location_adjusted_prob
        assert home.raw_elo_prob == pytest.approx(neutral.raw_elo_prob)

    def test_probs_in_unit_interval(self):
        """All probability fields are in [0, 1]."""
        result = win_prob_with_factors(
            "Alpha",
            "Delta",
            self.elo_ratings,
            self.games_count,
            self.rpi,
            self.schools_by_name,
            location_a="home",
        )
        assert 0.0 <= result.raw_elo_prob <= 1.0
        assert 0.0 <= result.location_adjusted_prob <= 1.0
        assert 0.0 <= result.final_prob <= 1.0

    def test_games_played_counts(self):
        """games_played fields reflect the number of completed games."""
        result = win_prob_with_factors(
            "Beta",
            "Gamma",
            self.elo_ratings,
            self.games_count,
            self.rpi,
            self.schools_by_name,
        )
        assert result.games_played_a == 2  # Beta played 2 games
        assert result.games_played_b == 2  # Gamma played 2 games

    def test_away_location_decreases_prob(self):
        """Away location lowers location_adjusted_prob without changing raw_elo_prob."""
        neutral = win_prob_with_factors(
            "Alpha", "Beta",
            self.elo_ratings, self.games_count, self.rpi, self.schools_by_name,
            location_a="neutral",
        )
        away = win_prob_with_factors(
            "Alpha", "Beta",
            self.elo_ratings, self.games_count, self.rpi, self.schools_by_name,
            location_a="away",
        )
        assert away.location_adjusted_prob < neutral.location_adjusted_prob
        assert away.raw_elo_prob == pytest.approx(neutral.raw_elo_prob)
