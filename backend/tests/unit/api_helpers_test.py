"""Unit tests for backend.helpers.api_helpers."""

from datetime import date

import pytest

from backend.helpers.api_helpers import (
    CLINCHED_THRESHOLD,
    DISPLAY_THRESHOLD,
    bracket_results_to_applied,
    build_bracket_entries,
    build_bracket_entries_from_odds_map,
    build_bracket_teams,
    build_hosting_entries,
    build_seeding_by_region,
    build_team_entries,
    clinched_school,
    compute_remaining_games,
    filter_remaining_after_simulation,
    num_rounds_for_class,
    parse_completed_games,
    records_from_completed,
    remaining_to_models,
    results_to_applied,
    scenarios_to_entries,
    standings_from_odds,
)
from backend.helpers.data_classes import BracketOdds, CompletedGame, RemainingGame, StandingsOdds
from backend.tests.data.playoff_brackets_2025 import SLOTS_1A_4A_2025, SLOTS_5A_7A_2025

# ---------------------------------------------------------------------------
# Shared test data helpers
# ---------------------------------------------------------------------------

_DATE = date(2025, 10, 3)


def _odds(
    school: str, p1=0.0, p2=0.0, p3=0.0, p4=0.0, p_playoffs=0.0, clinched=False, eliminated=False
) -> StandingsOdds:
    """Build a StandingsOdds for test use."""
    return StandingsOdds(
        school=school,
        p1=p1,
        p2=p2,
        p3=p3,
        p4=p4,
        p_playoffs=p_playoffs,
        final_playoffs=p_playoffs,
        clinched=clinched,
        eliminated=eliminated,
    )


def _completed(a: str, b: str, sa: int, sb: int) -> CompletedGame:
    """Build a CompletedGame (a < b alphabetically) from scores."""
    if sa > sb:
        res_a = 1
    elif sa < sb:
        res_a = -1
    else:
        res_a = 0
    return CompletedGame(a=a, b=b, res_a=res_a, pd_a=sa - sb, pa_a=sb, pa_b=sa)


# Minimal request stub so helpers don't need live Pydantic models
class _GameResult:
    """Minimal stub for GameResultRequest so helpers don't need live Pydantic models."""

    def __init__(self, winner, loser, winner_score=None, loser_score=None):
        """Initialise with winner/loser team names and optional scores."""
        self.winner = winner
        self.loser = loser
        self.winner_score = winner_score
        self.loser_score = loser_score


class _BracketResult:
    """Minimal stub for BracketGameResultRequest."""

    def __init__(self, home_region, home_seed, away_region, away_seed, home_wins):
        """Initialise with home/away slot coordinates and outcome."""
        self.home_region = home_region
        self.home_seed = home_seed
        self.away_region = away_region
        self.away_seed = away_seed
        self.home_wins = home_wins


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------


class TestConstants:
    """Sanity-check that plan-specified constant values haven't drifted."""

    def test_display_threshold(self):
        """DISPLAY_THRESHOLD should be 6."""
        assert DISPLAY_THRESHOLD == 6

    def test_clinched_threshold(self):
        """CLINCHED_THRESHOLD should be 0.999."""
        assert CLINCHED_THRESHOLD == pytest.approx(0.999)


# ---------------------------------------------------------------------------
# TestParseCompletedGames
# ---------------------------------------------------------------------------


class TestParseCompletedGames:
    """parse_completed_games deduplicates and normalises DB game rows."""

    def test_single_game_two_rows(self):
        """Two symmetric rows for the same game produce one CompletedGame."""
        rows = [
            ("Alpha", "Beta", 21, 14, _DATE),
            ("Beta", "Alpha", 14, 21, _DATE),
        ]
        result = parse_completed_games(rows)
        assert len(result) == 1

    def test_alphabetical_ordering(self):
        """a is always the lexicographically first team."""
        rows = [("Zebra", "Alpha", 28, 7, _DATE)]
        result = parse_completed_games(rows)
        assert result[0].a == "Alpha"
        assert result[0].b == "Zebra"

    def test_winner_via_res_a_a_wins(self):
        """res_a=1 when the lexicographically first team won."""
        rows = [("Alpha", "Beta", 21, 14, _DATE)]
        result = parse_completed_games(rows)
        assert result[0].res_a == 1

    def test_winner_via_res_a_b_wins(self):
        """res_a=-1 when the lexicographically second team won."""
        rows = [("Alpha", "Beta", 7, 28, _DATE)]
        result = parse_completed_games(rows)
        assert result[0].res_a == -1

    def test_tie(self):
        """res_a=0 for tied games."""
        rows = [("Alpha", "Beta", 14, 14, _DATE)]
        result = parse_completed_games(rows)
        assert result[0].res_a == 0

    def test_pd_a_from_a_perspective(self):
        """pd_a is sa - sb where sa/sb are scores from team a's perspective."""
        rows = [("Alpha", "Beta", 28, 7, _DATE)]  # Alpha wins by 21
        result = parse_completed_games(rows)
        assert result[0].pd_a == 21

    def test_pd_a_when_row_is_b_perspective(self):
        """pd_a is correct even when the winning row belongs to team b."""
        # Row is from Beta's perspective; Alpha still won
        rows = [("Beta", "Alpha", 7, 28, _DATE)]
        result = parse_completed_games(rows)
        assert result[0].a == "Alpha"
        assert result[0].pd_a == 21  # Alpha scored 28, Beta scored 7 → pd_a = 28-7

    def test_pa_fields(self):
        """pa_a = points scored by b; pa_b = points scored by a."""
        rows = [("Alpha", "Beta", 28, 7, _DATE)]
        result = parse_completed_games(rows)
        assert result[0].pa_a == 7  # points allowed by Alpha = Beta's score
        assert result[0].pa_b == 28  # points allowed by Beta = Alpha's score

    def test_none_scores_skipped(self):
        """Rows with None points_for or points_against are skipped."""
        rows = [
            ("Alpha", "Beta", None, None, _DATE),
            ("Alpha", "Beta", 21, None, _DATE),
        ]
        result = parse_completed_games(rows)
        assert result == []

    def test_deduplication_keeps_first(self):
        """Only the first occurrence of each pair is kept."""
        rows = [
            ("Alpha", "Beta", 21, 14, _DATE),
            ("Beta", "Alpha", 14, 21, _DATE),  # symmetric duplicate
        ]
        result = parse_completed_games(rows)
        assert len(result) == 1

    def test_multiple_games(self):
        """Multiple distinct games are all returned."""
        rows = [
            ("Alpha", "Beta", 21, 14, _DATE),
            ("Alpha", "Gamma", 7, 35, _DATE),
        ]
        result = parse_completed_games(rows)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# TestComputeRemainingGames
# ---------------------------------------------------------------------------


class TestComputeRemainingGames:
    """compute_remaining_games produces the correct set of unplayed pairs."""

    def test_no_games_played(self):
        """With no completed games all pairs are remaining."""
        teams = ["Alpha", "Beta", "Gamma"]
        result = compute_remaining_games(teams, [])
        pairs = {(r.a, r.b) for r in result}
        assert pairs == {("Alpha", "Beta"), ("Alpha", "Gamma"), ("Beta", "Gamma")}

    def test_all_games_played(self):
        """With all games completed, remaining is empty."""
        teams = ["Alpha", "Beta"]
        completed = [_completed("Alpha", "Beta", 21, 14)]
        result = compute_remaining_games(teams, completed)
        assert result == []

    def test_partial_completion(self):
        """Only unplayed games appear."""
        teams = ["Alpha", "Beta", "Gamma"]
        completed = [_completed("Alpha", "Beta", 21, 14)]
        result = compute_remaining_games(teams, completed)
        pairs = {(r.a, r.b) for r in result}
        assert pairs == {("Alpha", "Gamma"), ("Beta", "Gamma")}

    def test_pairs_alphabetically_ordered(self):
        """Each RemainingGame has a < b."""
        teams = ["Zebra", "Alpha", "Mango"]
        result = compute_remaining_games(teams, [])
        for r in result:
            assert r.a < r.b

    def test_result_is_sorted(self):
        """Returned list is deterministically sorted."""
        teams = ["Gamma", "Beta", "Alpha"]
        result = compute_remaining_games(teams, [])
        pairs = [(r.a, r.b) for r in result]
        assert pairs == sorted(pairs)


# ---------------------------------------------------------------------------
# TestResultsToApplied
# ---------------------------------------------------------------------------


class TestResultsToApplied:
    """results_to_applied converts GameResultRequest objects correctly."""

    def test_winner_and_loser_mapped(self):
        """team_a = winner, team_b = loser."""
        body = [_GameResult("Alpha", "Beta", winner_score=21, loser_score=14)]
        result = results_to_applied(body)
        assert result[0].team_a == "Alpha"
        assert result[0].team_b == "Beta"

    def test_scores_present(self):
        """Explicit scores are passed through."""
        body = [_GameResult("Alpha", "Beta", winner_score=35, loser_score=7)]
        result = results_to_applied(body)
        assert result[0].score_a == 35
        assert result[0].score_b == 7

    def test_none_scores_default(self):
        """None winner_score/loser_score default to 1 and 0."""
        body = [_GameResult("Alpha", "Beta")]
        result = results_to_applied(body)
        assert result[0].score_a == 1
        assert result[0].score_b == 0

    def test_multiple_results(self):
        """Multiple results are all converted."""
        body = [_GameResult("Alpha", "Beta"), _GameResult("Gamma", "Delta")]
        result = results_to_applied(body)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# TestFilterRemainingAfterSimulation
# ---------------------------------------------------------------------------


class TestFilterRemainingAfterSimulation:
    """filter_remaining_after_simulation removes applied pairs from remaining."""

    _REMAINING = [
        RemainingGame(a="Alpha", b="Beta"),
        RemainingGame(a="Alpha", b="Gamma"),
        RemainingGame(a="Beta", b="Gamma"),
    ]

    def test_applied_pair_removed(self):
        """A game whose pair was applied is removed from remaining."""
        body = [_GameResult("Alpha", "Beta")]
        result = filter_remaining_after_simulation(self._REMAINING, body)
        pairs = {(r.a, r.b) for r in result}
        assert ("Alpha", "Beta") not in pairs

    def test_other_games_kept(self):
        """Games not in body_results are not removed."""
        body = [_GameResult("Alpha", "Beta")]
        result = filter_remaining_after_simulation(self._REMAINING, body)
        pairs = {(r.a, r.b) for r in result}
        assert ("Alpha", "Gamma") in pairs
        assert ("Beta", "Gamma") in pairs

    def test_multiple_applied(self):
        """Multiple applied games are all removed."""
        body = [_GameResult("Alpha", "Beta"), _GameResult("Beta", "Gamma")]
        result = filter_remaining_after_simulation(self._REMAINING, body)
        pairs = {(r.a, r.b) for r in result}
        assert pairs == {("Alpha", "Gamma")}

    def test_empty_body(self):
        """Empty body_results leaves remaining unchanged."""
        result = filter_remaining_after_simulation(self._REMAINING, [])
        assert len(result) == len(self._REMAINING)


# ---------------------------------------------------------------------------
# TestBracketResultsToApplied
# ---------------------------------------------------------------------------


class TestBracketResultsToApplied:
    """bracket_results_to_applied uses R{region}S{seed} slot IDs."""

    def test_slot_ids_constructed(self):
        """team_a and team_b use R{region}S{seed} format."""
        body = [_BracketResult(1, 1, 2, 4, True)]
        result = bracket_results_to_applied(body)
        assert result[0].team_a == "R1S1"
        assert result[0].team_b == "R2S4"

    def test_home_wins_true(self):
        """home_wins=True → score_a=1, score_b=0."""
        body = [_BracketResult(1, 1, 2, 4, True)]
        result = bracket_results_to_applied(body)
        assert result[0].score_a == 1
        assert result[0].score_b == 0

    def test_home_wins_false(self):
        """home_wins=False → score_a=0, score_b=1."""
        body = [_BracketResult(1, 1, 2, 4, False)]
        result = bracket_results_to_applied(body)
        assert result[0].score_a == 0
        assert result[0].score_b == 1


# ---------------------------------------------------------------------------
# TestBuildBracketTeams
# ---------------------------------------------------------------------------


class TestBuildBracketTeams:
    """build_bracket_teams produces one BracketTeam per region/seed combination."""

    def test_count(self):
        """Two regions × 4 seeds = 8 teams."""
        by_region = {1: {}, 2: {}}
        result = build_bracket_teams(by_region, season=2025)
        assert len(result) == 8

    def test_slot_id_names(self):
        """School names follow the R{region}S{seed} format."""
        by_region = {1: {}}
        result = build_bracket_teams(by_region, season=2025)
        names = {t.school for t in result}
        assert names == {"R1S1", "R1S2", "R1S3", "R1S4"}

    def test_season_assigned(self):
        """Season is assigned to every team."""
        by_region = {3: {}}
        result = build_bracket_teams(by_region, season=2025)
        assert all(t.season == 2025 for t in result)


# ---------------------------------------------------------------------------
# TestNumRoundsForClass
# ---------------------------------------------------------------------------


class TestNumRoundsForClass:
    """num_rounds_for_class returns 5 for 1A–4A, 4 for 5A–7A."""

    @pytest.mark.parametrize("clazz", [1, 2, 3, 4])
    def test_small_classes(self, clazz):
        """1A–4A use a 32-team, 5-round bracket."""
        assert num_rounds_for_class(clazz) == 5

    @pytest.mark.parametrize("clazz", [5, 6, 7])
    def test_large_classes(self, clazz):
        """5A–7A use a 16-team, 4-round bracket."""
        assert num_rounds_for_class(clazz) == 4


# ---------------------------------------------------------------------------
# TestRecordsFromCompleted
# ---------------------------------------------------------------------------


class TestRecordsFromCompleted:
    """records_from_completed tallies region W/L from CompletedGame objects."""

    def test_win_tallied(self):
        """Winning team gets a region win."""
        teams = ["Alpha", "Beta"]
        completed = [_completed("Alpha", "Beta", 21, 14)]  # Alpha wins
        result = records_from_completed(teams, completed)
        assert result["Alpha"][3] == 1  # region_wins
        assert result["Alpha"][4] == 0  # region_losses

    def test_loss_tallied(self):
        """Losing team gets a region loss."""
        teams = ["Alpha", "Beta"]
        completed = [_completed("Alpha", "Beta", 21, 14)]  # Beta loses
        result = records_from_completed(teams, completed)
        assert result["Beta"][3] == 0
        assert result["Beta"][4] == 1

    def test_team_with_no_games(self):
        """Team with no completed games defaults to all zeros."""
        teams = ["Alpha", "Beta", "Gamma"]
        completed = [_completed("Alpha", "Beta", 21, 14)]
        result = records_from_completed(teams, completed)
        assert result["Gamma"] == (0, 0, 0, 0, 0, 0)

    def test_overall_wlt_are_zero(self):
        """Overall W/L/T positions (0,1,2) are always 0 on the on-demand path."""
        teams = ["Alpha", "Beta"]
        completed = [_completed("Alpha", "Beta", 21, 14)]
        result = records_from_completed(teams, completed)
        assert result["Alpha"][0] == 0  # overall wins placeholder
        assert result["Alpha"][1] == 0  # overall losses placeholder
        assert result["Alpha"][2] == 0  # overall ties placeholder

    def test_multiple_games(self):
        """Multiple completed games accumulate correctly."""
        teams = ["Alpha", "Beta", "Gamma"]
        completed = [
            _completed("Alpha", "Beta", 21, 14),
            _completed("Alpha", "Gamma", 28, 7),
        ]
        result = records_from_completed(teams, completed)
        assert result["Alpha"][3] == 2  # won both
        assert result["Beta"][4] == 1
        assert result["Gamma"][4] == 1


# ---------------------------------------------------------------------------
# TestRemainingToModels
# ---------------------------------------------------------------------------


class TestRemainingToModels:
    """remaining_to_models converts RemainingGame dataclasses to response models."""

    def test_fields_mapped(self):
        """team_a, team_b, and location_a are mapped correctly."""
        remaining = [RemainingGame(a="Alpha", b="Beta", location_a="home")]
        result = remaining_to_models(remaining)
        assert result[0].team_a == "Alpha"
        assert result[0].team_b == "Beta"
        assert result[0].location_a == "home"

    def test_none_location(self):
        """location_a=None is preserved."""
        remaining = [RemainingGame(a="Alpha", b="Beta")]
        result = remaining_to_models(remaining)
        assert result[0].location_a is None

    def test_count(self):
        """One model per input game."""
        remaining = [RemainingGame(a="Alpha", b="Beta"), RemainingGame(a="Alpha", b="Gamma")]
        result = remaining_to_models(remaining)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# TestScenariosToEntries
# ---------------------------------------------------------------------------


class TestScenariosToEntries:
    """scenarios_to_entries converts scenario dicts to ScenarioEntry models."""

    def test_none_input(self):
        """None input returns None."""
        assert scenarios_to_entries(None) is None

    def test_empty_list(self):
        """Empty list returns None."""
        assert scenarios_to_entries([]) is None

    def test_seeding_to_labels(self):
        """Seeding list is converted to 1-indexed string labels."""
        scenarios = [
            {
                "scenario_num": 1,
                "sub_label": "1",
                "game_winners": [("Alpha", "Beta")],
                "tiebreaker_groups": None,
                "coinflip_groups": None,
                "seeding": ["Alpha", "Beta", "Gamma", "Delta"],
            }
        ]
        result = scenarios_to_entries(scenarios)
        assert result is not None
        assert result[0].outcomes == {"Alpha": "1", "Beta": "2", "Gamma": "3", "Delta": "4"}
        assert result[0].scenario_num == 1
        assert result[0].sub_label == "1"
        assert result[0].game_winners[0].winner == "Alpha"
        assert result[0].game_winners[0].loser == "Beta"

    def test_multiple_scenarios(self):
        """Multiple scenarios are all converted."""
        scenarios = [
            {"scenario_num": 1, "sub_label": "1", "game_winners": [], "seeding": ["Alpha", "Beta"]},
            {"scenario_num": 2, "sub_label": "2", "game_winners": [], "seeding": ["Beta", "Alpha"]},
        ]
        result = scenarios_to_entries(scenarios)
        assert result is not None
        assert len(result) == 2
        assert result[1].outcomes["Beta"] == "1"


# ---------------------------------------------------------------------------
# TestBuildTeamEntries
# ---------------------------------------------------------------------------

# DB standings row — positions mirror _load_standings_snapshot SELECT:
#   0-6:   school, w, l, t, rw, rl, rt
#   7-11:  p1, p2, p3, p4, p_playoffs (unweighted seeding)
#   12-14: clinched, elim, coin_flip
#   15:    as_of_date
#   16-20: p1_w, p2_w, p3_w, p4_w, p_playoffs_w (weighted seeding)
#   21-25: bracket: second_round, quarterfinals, semifinals, finals, champion
#   26-30: bracket weighted: same 5
#   31-34: home: first_round, second_round, quarterfinals, semifinals
#   35-38: home weighted: same 4
_SNAP_DATE = date(2025, 10, 1)
_ROW_ALPHA = (
    "Alpha", 5, 2, 0, 3, 1, 0,          # 0-6
    0.6, 0.3, 0.1, 0.0, 1.0,             # 7-11 unweighted seeding
    False, False, False,                  # 12-14 clinched/elim/coin
    _SNAP_DATE,                           # 15 as_of_date
    0.65, 0.28, 0.07, 0.0, 1.0,          # 16-20 weighted seeding
    0.5, 0.3, 0.2, 0.1, 0.05,            # 21-25 bracket advancement
    0.45, 0.25, 0.15, 0.08, 0.04,        # 26-30 bracket weighted
    0.6, 0.3, 0.2, 0.1,                  # 31-34 home game
    0.55, 0.28, 0.18, 0.09,              # 35-38 home game weighted
)
_ROW_BETA = (
    "Beta", 4, 3, 0, 1, 3, 0,            # 0-6
    0.1, 0.2, 0.4, 0.3, 1.0,             # 7-11 unweighted seeding
    False, False, True,                   # 12-14 clinched/elim/coin
    _SNAP_DATE,                           # 15 as_of_date
    0.08, 0.18, 0.42, 0.32, 1.0,         # 16-20 weighted seeding
    0.2, 0.15, 0.08, 0.04, 0.02,         # 21-25 bracket advancement
    0.18, 0.12, 0.06, 0.03, 0.01,        # 26-30 bracket weighted
    0.15, 0.1, 0.05, 0.02,               # 31-34 home game
    0.12, 0.09, 0.04, 0.02,              # 35-38 home game weighted
)


class TestBuildTeamEntries:
    """build_team_entries constructs TeamStandingsEntry from DB rows with optional overrides."""

    def test_no_override_uses_db_odds(self):
        """Without an override, p1–p4 and weighted odds come from the DB row."""
        result = build_team_entries([_ROW_ALPHA], None, None)
        assert result[0].odds.p1 == pytest.approx(0.6)
        assert result[0].odds.p2 == pytest.approx(0.3)
        assert result[0].odds.p1_weighted == pytest.approx(0.65)
        assert result[0].bracket_odds is not None
        assert result[0].bracket_odds.second_round == pytest.approx(0.5)
        assert result[0].bracket_odds.champion == pytest.approx(0.05)
        assert result[0].bracket_odds.champion_weighted == pytest.approx(0.04)
        assert result[0].home_game_odds is not None
        assert result[0].home_game_odds.first_round == pytest.approx(0.6)
        assert result[0].home_game_odds.semifinals_weighted == pytest.approx(0.09)

    def test_no_override_uses_db_coin_flip(self):
        """Without override, coin_flip_needed comes from the DB row."""
        result = build_team_entries([_ROW_BETA], None, None)
        assert result[0].coin_flip_needed is True

    def test_odds_override_replaces_db_odds(self):
        """When odds_override contains the school, DB odds are replaced; bracket_odds is None."""
        override = {"Alpha": _odds("Alpha", p1=0.9, p2=0.1, p_playoffs=1.0, clinched=True)}
        result = build_team_entries([_ROW_ALPHA], override, None)
        assert result[0].odds.p1 == pytest.approx(0.9)
        assert result[0].clinched is True
        assert result[0].bracket_odds is None
        assert result[0].home_game_odds is None

    def test_coinflip_override_replaces_db_field(self):
        """When coinflip_override is provided, it controls coin_flip_needed."""
        override = {"Alpha": _odds("Alpha", p1=0.6, p2=0.3, p3=0.1, p_playoffs=1.0)}
        result = build_team_entries([_ROW_ALPHA], override, {"Alpha"})
        assert result[0].coin_flip_needed is True

    def test_record_always_from_db_row(self):
        """Record fields always come from DB row positions."""
        result = build_team_entries([_ROW_ALPHA], None, None)
        assert result[0].record.wins == 5
        assert result[0].record.region_wins == 3


# ---------------------------------------------------------------------------
# TestStandingsFromOdds
# ---------------------------------------------------------------------------


class TestStandingsFromOdds:
    """standings_from_odds builds entries from on-demand computation results."""

    _ODDS = {
        "Beta": _odds("Beta", p1=0.2, p2=0.5, p3=0.3, p_playoffs=1.0),
        "Alpha": _odds("Alpha", p1=0.8, p_playoffs=0.8),
    }
    _RECORDS = {
        "Alpha": (0, 0, 0, 2, 1, 0),
        "Beta": (0, 0, 0, 1, 2, 0),
    }

    def test_sorted_alphabetically(self):
        """Teams are returned sorted alphabetically regardless of dict order."""
        result = standings_from_odds(self._ODDS, set(), self._RECORDS)
        assert result[0].school == "Alpha"
        assert result[1].school == "Beta"

    def test_odds_mapped(self):
        """Odds fields come from the StandingsOdds object."""
        result = standings_from_odds(self._ODDS, set(), self._RECORDS)
        alpha = next(e for e in result if e.school == "Alpha")
        assert alpha.odds.p1 == pytest.approx(0.8)

    def test_records_merged(self):
        """Region W/L from records dict are populated."""
        result = standings_from_odds(self._ODDS, set(), self._RECORDS)
        alpha = next(e for e in result if e.school == "Alpha")
        assert alpha.record.region_wins == 2

    def test_coinflip_applied(self):
        """coin_flip_needed is True only for teams in coinflip_teams."""
        result = standings_from_odds(self._ODDS, {"Beta"}, self._RECORDS)
        alpha = next(e for e in result if e.school == "Alpha")
        beta = next(e for e in result if e.school == "Beta")
        assert alpha.coin_flip_needed is False
        assert beta.coin_flip_needed is True

    def test_missing_record_defaults_to_zeros(self):
        """Teams absent from records default to all-zero record."""
        result = standings_from_odds(self._ODDS, set(), {})
        assert result[0].record.region_wins == 0


# ---------------------------------------------------------------------------
# TestClinched
# ---------------------------------------------------------------------------


class TestClinched:
    """clinched_school returns the team that has clinched a given seed."""

    def test_team_at_threshold_returned(self):
        """A team at exactly CLINCHED_THRESHOLD is considered clinched."""
        region_odds = {"Alpha": _odds("Alpha", p1=CLINCHED_THRESHOLD)}
        assert clinched_school(region_odds, 1) == "Alpha"

    def test_team_above_threshold_returned(self):
        """A team above CLINCHED_THRESHOLD is returned."""
        region_odds = {"Alpha": _odds("Alpha", p1=1.0)}
        assert clinched_school(region_odds, 1) == "Alpha"

    def test_team_below_threshold_returns_none(self):
        """No team meeting the threshold returns None."""
        region_odds = {"Alpha": _odds("Alpha", p1=0.998)}
        assert clinched_school(region_odds, 1) is None

    def test_correct_seed_attribute_checked(self):
        """Seed 2 checks p2, not p1."""
        region_odds = {"Alpha": _odds("Alpha", p1=0.0, p2=1.0)}
        assert clinched_school(region_odds, 1) is None
        assert clinched_school(region_odds, 2) == "Alpha"

    def test_empty_region_returns_none(self):
        """Empty region_odds returns None."""
        assert clinched_school({}, 1) is None


# ---------------------------------------------------------------------------
# TestBuildBracketEntriesFromOddsMap
# ---------------------------------------------------------------------------


def _bracket_odds(
    school: str, second_round=0.5, quarterfinals=0.25, semifinals=0.125, finals=0.0625, champion=0.03125
) -> BracketOdds:
    """Build a BracketOdds for test use."""
    return BracketOdds(
        school=school,
        second_round=second_round,
        quarterfinals=quarterfinals,
        semifinals=semifinals,
        finals=finals,
        champion=champion,
    )


class TestBuildBracketEntriesFromOddsMap:
    """build_bracket_entries_from_odds_map builds TeamBracketEntry list from odds_map."""

    _BY_REGION = {
        1: {"Alpha": _odds("Alpha", p1=1.0, clinched=True), "Beta": _odds("Beta", p2=1.0)},
        2: {"Gamma": _odds("Gamma", p1=1.0, clinched=True)},
    }
    _ODDS_MAP = {
        "R1S1": _bracket_odds("R1S1"),
        "R1S2": _bracket_odds("R1S2"),
        "R2S1": _bracket_odds("R2S1"),
    }

    def test_entry_count_matches_odds_map(self):
        """One entry per slot present in odds_map."""
        result = build_bracket_entries_from_odds_map(self._BY_REGION, self._ODDS_MAP)
        assert len(result) == 3

    def test_missing_slot_skipped(self):
        """Slots absent from odds_map produce no entry."""
        result = build_bracket_entries_from_odds_map(self._BY_REGION, self._ODDS_MAP)
        slot_ids = {(e.region, e.seed) for e in result}
        assert (2, 2) not in slot_ids  # R2S2 not in odds_map

    def test_entries_sorted_by_region_then_seed(self):
        """Entries are ordered region ascending, seed ascending within each region."""
        result = build_bracket_entries_from_odds_map(self._BY_REGION, self._ODDS_MAP)
        keys = [(e.region, e.seed) for e in result]
        assert keys == sorted(keys)

    def test_clinched_school_populated(self):
        """school is set when a team has clinched the seed position."""
        result = build_bracket_entries_from_odds_map(self._BY_REGION, self._ODDS_MAP)
        r1s1 = next(e for e in result if e.region == 1 and e.seed == 1)
        assert r1s1.school == "Alpha"

    def test_unclinched_school_is_none(self):
        """school is None when no team has clinched the seed."""
        by_region = {1: {"Alpha": _odds("Alpha", p1=0.6, p2=0.4)}}
        odds_map = {"R1S1": _bracket_odds("R1S1")}
        result = build_bracket_entries_from_odds_map(by_region, odds_map)
        assert result[0].school is None

    def test_bracket_odds_fields_mapped(self):
        """second_round, quarterfinals, semifinals, finals, champion come from BracketOdds."""
        by_region = {1: {"Alpha": _odds("Alpha", p1=1.0, clinched=True)}}
        odds_map = {
            "R1S1": _bracket_odds(
                "R1S1", second_round=0.8, quarterfinals=0.4, semifinals=0.2, finals=0.1, champion=0.05
            )
        }
        result = build_bracket_entries_from_odds_map(by_region, odds_map)
        assert result[0].second_round == pytest.approx(0.8)
        assert result[0].quarterfinals == pytest.approx(0.4)
        assert result[0].semifinals == pytest.approx(0.2)
        assert result[0].finals == pytest.approx(0.1)
        assert result[0].champion == pytest.approx(0.05)

    def test_empty_odds_map_returns_empty(self):
        """Empty odds_map produces an empty entry list."""
        result = build_bracket_entries_from_odds_map(self._BY_REGION, {})
        assert result == []

    def test_region_and_seed_fields_set(self):
        """region and seed are set correctly on each entry."""
        result = build_bracket_entries_from_odds_map(self._BY_REGION, self._ODDS_MAP)
        r1s2 = next(e for e in result if e.region == 1 and e.seed == 2)
        assert r1s2.region == 1
        assert r1s2.seed == 2


# ---------------------------------------------------------------------------
# TestRecordsFromCompleted — res_a == -1 branch
# ---------------------------------------------------------------------------
# The existing class covers the res_a==1 (team-a wins) path.  This standalone
# function exercises the res_a==-1 (team-b wins) branch on lines 171-173.


def test_records_from_completed_b_wins():
    """When res_a == -1, team b gets the win and team a gets the loss."""
    teams = ["Alpha", "Beta"]
    # sa=7 < sb=21 → res_a = -1 → Beta wins
    completed = [_completed("Alpha", "Beta", 7, 21)]
    result = records_from_completed(teams, completed)
    assert result["Beta"][3] == 1  # region_wins
    assert result["Beta"][4] == 0  # region_losses
    assert result["Alpha"][3] == 0
    assert result["Alpha"][4] == 1


def test_records_from_completed_tie():
    """When res_a == 0 (tie), neither team receives a win or loss credit."""
    teams = ["Alpha", "Beta"]
    completed = [_completed("Alpha", "Beta", 14, 14)]  # tied → res_a=0
    result = records_from_completed(teams, completed)
    assert result["Alpha"][3] == 0
    assert result["Alpha"][4] == 0
    assert result["Beta"][3] == 0
    assert result["Beta"][4] == 0


# ---------------------------------------------------------------------------
# TestBuildSeedingByRegion
# ---------------------------------------------------------------------------


class TestBuildSeedingByRegion:
    """build_seeding_by_region combines simulated-region odds with stored other-region rows."""

    def _simulated_odds(self) -> dict[str, StandingsOdds]:
        """Return two-team fractional seeding odds for region 1."""
        return {
            "Alpha": StandingsOdds(school="Alpha", p1=0.6, p2=0.3, p3=0.1, p4=0.0, p_playoffs=1.0, final_playoffs=1.0, clinched=False, eliminated=False),
            "Beta":  StandingsOdds(school="Beta",  p1=0.4, p2=0.7, p3=0.9, p4=1.0, p_playoffs=1.0, final_playoffs=1.0, clinched=False, eliminated=False),
        }

    def test_simulated_region_present(self):
        """Simulated region appears in the result with correct odds."""
        result = build_seeding_by_region(1, self._simulated_odds(), [])
        assert 1 in result
        assert result[1]["Alpha"].p1 == pytest.approx(0.6)

    def test_simulated_odds_passed_through_unchanged(self):
        """The simulated_odds dict is stored as-is (same object reference)."""
        odds = self._simulated_odds()
        result = build_seeding_by_region(1, odds, [])
        assert result[1] is odds

    def test_empty_other_rows_gives_only_simulated_region(self):
        """No other-region rows → only the simulated region key is present."""
        result = build_seeding_by_region(3, self._simulated_odds(), [])
        assert set(result.keys()) == {3}

    def test_other_region_rows_added(self):
        """Other-region rows appear under the correct region key with correct seed odds."""
        other_rows = [
            ("TeamX", 2, 1.0, 0.0, 0.0, 0.0),
            ("TeamY", 2, 0.0, 1.0, 0.0, 0.0),
        ]
        result = build_seeding_by_region(1, self._simulated_odds(), other_rows)
        assert 2 in result
        assert "TeamX" in result[2]
        assert result[2]["TeamX"].p1 == pytest.approx(1.0)
        assert result[2]["TeamY"].p2 == pytest.approx(1.0)

    def test_multiple_other_regions(self):
        """Teams from different regions each land in their own dict entry."""
        other_rows = [
            ("TeamA", 2, 1.0, 0.0, 0.0, 0.0),
            ("TeamB", 3, 0.0, 0.0, 1.0, 0.0),
            ("TeamC", 4, 0.0, 0.0, 0.0, 1.0),
        ]
        result = build_seeding_by_region(1, self._simulated_odds(), other_rows)
        assert set(result.keys()) == {1, 2, 3, 4}

    def test_p_playoffs_computed_from_seeds(self):
        """p_playoffs for other-region teams equals sum of p1+p2+p3+p4."""
        other_rows = [("TeamX", 2, 0.3, 0.4, 0.2, 0.1)]
        result = build_seeding_by_region(1, self._simulated_odds(), other_rows)
        assert result[2]["TeamX"].p_playoffs == pytest.approx(1.0)

    def test_partial_p_playoffs(self):
        """Fractional seeding odds produce fractional p_playoffs."""
        other_rows = [("TeamX", 2, 0.3, 0.2, 0.0, 0.0)]
        result = build_seeding_by_region(1, self._simulated_odds(), other_rows)
        assert result[2]["TeamX"].p_playoffs == pytest.approx(0.5)

    def test_multiple_teams_same_other_region(self):
        """All four teams from a single other region are grouped under that region key."""
        other_rows = [
            ("Reg2S1", 2, 1.0, 0.0, 0.0, 0.0),
            ("Reg2S2", 2, 0.0, 1.0, 0.0, 0.0),
            ("Reg2S3", 2, 0.0, 0.0, 1.0, 0.0),
            ("Reg2S4", 2, 0.0, 0.0, 0.0, 1.0),
        ]
        result = build_seeding_by_region(1, self._simulated_odds(), other_rows)
        assert len(result[2]) == 4


# ---------------------------------------------------------------------------
# TestBuildHostingEntries
# ---------------------------------------------------------------------------

# Four teams seeded equally across region 1 for a 5A-7A bracket.
_REGION1_ODDS_5A = {
    "Alpha": _odds("Alpha", p1=1.0, p_playoffs=1.0),
    "Beta": _odds("Beta", p2=1.0, p_playoffs=1.0),
    "Gamma": _odds("Gamma", p3=1.0, p_playoffs=1.0),
    "Delta": _odds("Delta", p4=1.0, p_playoffs=1.0),
}

# Four teams seeded equally across region 1 for a 1A-4A bracket.
_REGION1_ODDS_1A = {
    "Able": _odds("Able", p1=1.0, p_playoffs=1.0),
    "Baker": _odds("Baker", p2=1.0, p_playoffs=1.0),
    "Camp": _odds("Camp", p3=1.0, p_playoffs=1.0),
    "Dog": _odds("Dog", p4=1.0, p_playoffs=1.0),
}


class TestBuildHostingEntries:
    """build_hosting_entries returns one TeamHostingEntry per team, with correct round structure."""

    def test_5a_7a_returns_entry_per_team(self):
        """One entry per team in region_odds."""
        result = build_hosting_entries(_REGION1_ODDS_5A, SLOTS_5A_7A_2025, region=1, season=2025, clazz=5)
        assert len(result) == 4

    def test_5a_7a_second_round_odds_none(self):
        """5A–7A second_round has conditional=None, marginal=None."""
        result = build_hosting_entries(_REGION1_ODDS_5A, SLOTS_5A_7A_2025, region=1, season=2025, clazz=5)
        for entry in result:
            assert entry.second_round.conditional is None
            assert entry.second_round.marginal is None

    def test_5a_7a_first_round_conditional(self):
        """Seeds 1 and 2 host R1 (conditional=1.0); seeds 3 and 4 play away (conditional=0.0)."""
        result = build_hosting_entries(_REGION1_ODDS_5A, SLOTS_5A_7A_2025, region=1, season=2025, clazz=5)
        by_school = {e.school: e for e in result}
        assert by_school["Alpha"].first_round.conditional == pytest.approx(1.0)  # seed 1 — home
        assert by_school["Beta"].first_round.conditional == pytest.approx(1.0)   # seed 2 — home
        assert by_school["Gamma"].first_round.conditional == pytest.approx(0.0)  # seed 3 — away
        assert by_school["Delta"].first_round.conditional == pytest.approx(0.0)  # seed 4 — away

    def test_1a_4a_returns_entry_per_team(self):
        """One entry per team in region_odds for 1A–4A."""
        result = build_hosting_entries(_REGION1_ODDS_1A, SLOTS_1A_4A_2025, region=1, season=2025, clazz=1)
        assert len(result) == 4

    def test_1a_4a_second_round_odds_not_none(self):
        """1A–4A second_round has non-None marginal when team can advance."""
        result = build_hosting_entries(_REGION1_ODDS_1A, SLOTS_1A_4A_2025, region=1, season=2025, clazz=1)
        # Seed-1 team (Able) has p_r1_adv > 0, so second_round.marginal should be non-None.
        able = next(e for e in result if e.school == "Able")
        assert able.second_round.marginal is not None

    def test_1a_4a_first_round_conditional(self):
        """Seeds 1 and 2 host R1 (conditional=1.0); seeds 3 and 4 play away (conditional=0.0)."""
        result = build_hosting_entries(_REGION1_ODDS_1A, SLOTS_1A_4A_2025, region=1, season=2025, clazz=1)
        by_school = {e.school: e for e in result}
        assert by_school["Able"].first_round.conditional == pytest.approx(1.0)   # seed 1 — home
        assert by_school["Baker"].first_round.conditional == pytest.approx(1.0)  # seed 2 — home
        assert by_school["Camp"].first_round.conditional == pytest.approx(0.0)   # seed 3 — away
        assert by_school["Dog"].first_round.conditional == pytest.approx(0.0)    # seed 4 — away

    def test_zero_advancement_gives_none_conditional(self):
        """When p_r1_adv == 0 (no seed probability), second_round conditional is None."""
        # A team with all p values = 0 has zero second-round advancement probability.
        region_odds = {
            "Able": _odds("Able", p1=1.0, p_playoffs=1.0, clinched=True),
            "Baker": _odds("Baker", p2=1.0, p_playoffs=1.0, clinched=True),
            "Camp": _odds("Camp", p3=1.0, p_playoffs=1.0, clinched=True),
            "Zero": _odds("Zero", p_playoffs=0.0),  # no seeds → second_round = 0
        }
        result = build_hosting_entries(region_odds, SLOTS_1A_4A_2025, region=1, season=2025, clazz=1)
        zero = next(e for e in result if e.school == "Zero")
        assert zero.second_round.conditional is None

    # ------------------------------------------------------------------
    # Stored-odds path (home_cond + stored_adv provided)
    # ------------------------------------------------------------------

    def test_stored_path_1a_4a_uses_stored_values(self):
        """When home_cond and stored_adv are supplied, marginal = conditional × advancement."""
        home_cond = {
            "Able":  (1.0, 0.6, 0.3, 0.15),
            "Baker": (1.0, 0.5, 0.25, 0.1),
            "Camp":  (0.0, 0.0, 0.0, 0.0),
            "Dog":   (0.0, 0.0, 0.0, 0.0),
        }
        stored_adv = {
            "Able":  (1.0, 0.5, 0.25, 0.125),
            "Baker": (1.0, 0.5, 0.25, 0.125),
            "Camp":  (0.5, 0.25, 0.125, 0.0625),
            "Dog":   (0.5, 0.25, 0.125, 0.0625),
        }
        result = build_hosting_entries(
            _REGION1_ODDS_1A, SLOTS_1A_4A_2025, region=1, season=2025, clazz=1,
            home_cond=home_cond, stored_adv=stored_adv,
        )
        by_school = {e.school: e for e in result}
        able = by_school["Able"]
        assert able.first_round.conditional == pytest.approx(1.0)
        assert able.first_round.marginal == pytest.approx(1.0 * 1.0)
        assert able.second_round.conditional == pytest.approx(0.6)
        assert able.second_round.marginal == pytest.approx(0.6 * 0.5)
        assert able.quarterfinals.conditional == pytest.approx(0.3)
        assert able.quarterfinals.marginal == pytest.approx(0.3 * 0.25)
        assert able.semifinals.conditional == pytest.approx(0.15)
        assert able.semifinals.marginal == pytest.approx(0.15 * 0.125)

    def test_stored_path_5a_7a_second_round_always_none(self):
        """5A–7A stored path: second_round conditional and marginal are always None."""
        home_cond = {s: (1.0, 0.0, 0.5, 0.25) for s in ("Alpha", "Beta", "Gamma", "Delta")}
        stored_adv = {s: (1.0, 0.0, 0.5, 0.25) for s in ("Alpha", "Beta", "Gamma", "Delta")}
        result = build_hosting_entries(
            _REGION1_ODDS_5A, SLOTS_5A_7A_2025, region=1, season=2025, clazz=5,
            home_cond=home_cond, stored_adv=stored_adv,
        )
        for entry in result:
            assert entry.second_round.conditional is None
            assert entry.second_round.marginal is None

    def test_stored_path_zero_advancement_gives_none_conditional(self):
        """Stored path: conditional is None when the advancement probability is zero."""
        home_cond = {"Able": (1.0, 0.5, 0.3, 0.15)}
        stored_adv = {"Able": (0.0, 0.0, 0.0, 0.0)}  # no advancement
        region_odds = {"Able": _odds("Able", p1=1.0, p_playoffs=1.0, clinched=True)}
        result = build_hosting_entries(
            region_odds, SLOTS_1A_4A_2025, region=1, season=2025, clazz=1,
            home_cond=home_cond, stored_adv=stored_adv,
        )
        able = result[0]
        assert able.second_round.conditional is None
        assert able.quarterfinals.conditional is None
        assert able.semifinals.conditional is None

    # ------------------------------------------------------------------
    # Weighted fallback path (win_prob_fn_weighted provided)
    # ------------------------------------------------------------------

    def test_weighted_fallback_1a_4a_populates_weighted_fields(self):
        """Passing win_prob_fn_weighted produces non-None conditional_weighted values."""
        def equal_w(hr: int, hs: int, ar: int, as_: int) -> float:
            """Return 0.5 for all matchups (equal probability)."""
            return 0.5

        result = build_hosting_entries(
            _REGION1_ODDS_1A, SLOTS_1A_4A_2025, region=1, season=2025, clazz=1,
            win_prob_fn_weighted=equal_w,
        )
        able = next(e for e in result if e.school == "Able")
        assert able.first_round.conditional_weighted is not None
        assert able.second_round.marginal_weighted is not None

    def test_weighted_fallback_matches_unweighted_for_equal_prob(self):
        """With 50/50 weighted fn, conditional_weighted equals conditional."""
        def equal_w(hr: int, hs: int, ar: int, as_: int) -> float:
            """Return 0.5 for all matchups (equal probability)."""
            return 0.5

        result = build_hosting_entries(
            _REGION1_ODDS_1A, SLOTS_1A_4A_2025, region=1, season=2025, clazz=1,
            win_prob_fn_weighted=equal_w,
        )
        for entry in result:
            assert entry.first_round.conditional_weighted == pytest.approx(
                entry.first_round.conditional or 0.0, abs=1e-9
            )

    # ------------------------------------------------------------------
    # Cross-region elimination via all_region_odds / cross_region_wins
    # ------------------------------------------------------------------

    def _1a_all_region_odds_eliminate_r3_r4_seed1(self) -> dict:
        """Build all_region_odds where R3/R4 seed-1 teams are eliminated.

        R1 and R2 are unchanged (seed-1 alive).  R3 and R4 seed-1 are zeroed
        so that Able (R1-seed-1) is the only remaining seed-1 in the north half.
        """
        def _alive(school: str, seed: int) -> StandingsOdds:
            """Return a clinched StandingsOdds with a single confirmed seed."""
            kwargs = {"p1": 0.0, "p2": 0.0, "p3": 0.0, "p4": 0.0}
            kwargs[f"p{seed}"] = 1.0
            return StandingsOdds(school=school, **kwargs, p_playoffs=1.0, final_playoffs=1.0, clinched=True, eliminated=False)

        def _eliminated(school: str) -> StandingsOdds:
            """Return a fully eliminated StandingsOdds."""
            return StandingsOdds(school=school, p1=0.0, p2=0.0, p3=0.0, p4=0.0, p_playoffs=0.0, final_playoffs=0.0, clinched=True, eliminated=True)

        return {
            1: {
                "Able":  _alive("Able",  1),
                "Baker": _alive("Baker", 2),
                "Camp":  _alive("Camp",  3),
                "Dog":   _alive("Dog",   4),
            },
            2: {
                "R2T1": _alive("R2T1", 1),
                "R2T2": _alive("R2T2", 2),
                "R2T3": _alive("R2T3", 3),
                "R2T4": _alive("R2T4", 4),
            },
            3: {
                "R3T1": _eliminated("R3T1"),   # seed-1 eliminated
                "R3T2": _alive("R3T2", 2),
                "R3T3": _alive("R3T3", 3),
                "R3T4": _alive("R3T4", 4),
            },
            4: {
                "R4T1": _eliminated("R4T1"),   # seed-1 eliminated
                "R4T2": _alive("R4T2", 2),
                "R4T3": _alive("R4T3", 3),
                "R4T4": _alive("R4T4", 4),
            },
        }

    def test_sf_conditional_1_when_all_opp_seed1s_eliminated(self):
        """When all opposing-quarter seed-1 teams are eliminated, SF conditional = 1.0 for seed-1 team.

        Uses season=2024 (even year) so that equal-seed SF matchups are decided by higher
        region number hosting — meaning R1-1 would NOT host against R3-1 or R4-1 in a normal
        bracket.  Eliminating both R3-1 and R4-1 forces all SF opponents to be lower seeds,
        guaranteeing R1-1 hosts.
        """
        all_region_odds = self._1a_all_region_odds_eliminate_r3_r4_seed1()
        result = build_hosting_entries(
            _REGION1_ODDS_1A, SLOTS_1A_4A_2025, region=1, season=2024, clazz=1,
            all_region_odds=all_region_odds,
        )
        able = next(e for e in result if e.school == "Able")
        assert able.semifinals.conditional == pytest.approx(1.0)

    def test_sf_conditional_partial_elimination_between_0_and_1(self):
        """Eliminating only one opposing seed-1 puts SF conditional strictly between baseline and 1.0."""
        all_region_odds = self._1a_all_region_odds_eliminate_r3_r4_seed1()
        # Restore R3-seed-1 as alive — only R4-seed-1 is eliminated.
        all_region_odds[3]["R3T1"] = StandingsOdds(
            school="R3T1", p1=1.0, p2=0.0, p3=0.0, p4=0.0,
            p_playoffs=1.0, final_playoffs=1.0, clinched=True, eliminated=False,
        )
        baseline = build_hosting_entries(
            _REGION1_ODDS_1A, SLOTS_1A_4A_2025, region=1, season=2024, clazz=1,
        )
        result = build_hosting_entries(
            _REGION1_ODDS_1A, SLOTS_1A_4A_2025, region=1, season=2024, clazz=1,
            all_region_odds=all_region_odds,
        )
        able = next(e for e in result if e.school == "Able")
        baseline_able = next(e for e in baseline if e.school == "Able")
        assert able.semifinals.conditional is not None
        assert (baseline_able.semifinals.conditional or 0.0) < able.semifinals.conditional < 1.0

    def test_sf_conditional_unchanged_with_no_elimination(self):
        """With all_region_odds but no eliminations, SF conditional matches the baseline (no all_region_odds)."""
        all_region_odds = self._1a_all_region_odds_eliminate_r3_r4_seed1()
        # Restore both R3 and R4 seed-1 as alive.
        for reg in (3, 4):
            school = f"R{reg}T1"
            all_region_odds[reg][school] = StandingsOdds(
                school=school, p1=1.0, p2=0.0, p3=0.0, p4=0.0,
                p_playoffs=1.0, final_playoffs=1.0, clinched=True, eliminated=False,
            )
        baseline = build_hosting_entries(
            _REGION1_ODDS_1A, SLOTS_1A_4A_2025, region=1, season=2024, clazz=1,
        )
        with_odds = build_hosting_entries(
            _REGION1_ODDS_1A, SLOTS_1A_4A_2025, region=1, season=2024, clazz=1,
            all_region_odds=all_region_odds,
        )
        baseline_able = next(e for e in baseline if e.school == "Able")
        with_able = next(e for e in with_odds if e.school == "Able")
        assert with_able.semifinals.conditional == pytest.approx(
            baseline_able.semifinals.conditional or 0.0, abs=1e-6
        )


# ---------------------------------------------------------------------------
# TestBuildBracketEntries
# ---------------------------------------------------------------------------


class TestBuildBracketEntries:
    """build_bracket_entries produces entries for each (region, seed) slot."""

    def _by_region(self) -> dict:
        """Return a by_region dict with one clinched team per seed for all 4 regions."""
        return {
            r: {
                f"T{r}S1": _odds(f"T{r}S1", p1=1.0, p_playoffs=1.0, clinched=True),
                f"T{r}S2": _odds(f"T{r}S2", p2=1.0, p_playoffs=1.0, clinched=True),
                f"T{r}S3": _odds(f"T{r}S3", p3=1.0, p_playoffs=1.0, clinched=True),
                f"T{r}S4": _odds(f"T{r}S4", p4=1.0, p_playoffs=1.0, clinched=True),
            }
            for r in (1, 2, 3, 4)
        }

    def test_5a_7a_entry_count(self):
        """4 regions × 4 seeds = 16 entries for a 5A–7A class."""
        result = build_bracket_entries(self._by_region(), SLOTS_5A_7A_2025)
        assert len(result) == 16

    def test_entries_sorted_region_then_seed(self):
        """Entries are ordered by region ascending, then seed ascending."""
        result = build_bracket_entries(self._by_region(), SLOTS_5A_7A_2025)
        keys = [(e.region, e.seed) for e in result]
        assert keys == sorted(keys)

    def test_advancement_odds_are_floats(self):
        """All advancement probability fields are numeric (not None)."""
        result = build_bracket_entries(self._by_region(), SLOTS_5A_7A_2025)
        for entry in result:
            assert isinstance(entry.second_round, float)
            assert isinstance(entry.semifinals, float)
            assert isinstance(entry.champion, float)
