"""Unit tests for backend.helpers.api_helpers."""

from dataclasses import dataclass, field
from datetime import date

import pytest
from fastapi import HTTPException

from backend.api.models.requests import BracketGameResultRequest, ParticipantRef
from backend.api.models.responses import (
    BracketSlotHosting,
    RoundHostingOdds,
    TeamBracketEntry,
    TeamHostingEntry,
)
from backend.helpers.api_helpers import (
    CLINCHED_THRESHOLD,
    DISPLAY_THRESHOLD,
    PlayoffBracketState,
    _apply_round_ceilings,
    _collect_possible_opponents,
    _resolve_ref_to_school,
    _resolve_ref_to_slot_id,
    _slot_odds_for_region,
    build_bracket_entries,
    build_bracket_entries_from_odds_map,
    build_bracket_layout,
    build_enriched_bracket_layout,
    build_game_models,
    build_helmet_from_fields,
    build_helmet_from_row,
    build_hosting_entries,
    build_playoff_bracket_state,
    build_rank_entry,
    build_seeding_by_region,
    build_team_entries,
    clinched_school,
    compute_remaining_games,
    eliminated_team_hosting,
    filter_remaining_after_simulation,
    filter_scenarios_by_simulation,
    filter_to_team_or_404,
    has_displayable_scenarios,
    parse_completed_games,
    records_from_completed,
    remaining_to_models,
    resolve_hosting_scenario_inputs,
    results_to_applied,
    scenarios_to_entries,
    select_sentinel_region,
    standings_from_odds,
    standings_odds_from_row,
    today,
    within_display_threshold,
)
from backend.helpers.data_classes import (
    BracketOdds,
    CompletedGame,
    GameResult,
    MarginCondition,
    RemainingGame,
    StandingsOdds,
    StoredHostingOdds,
    equal_matchup_prob,
)
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


class TestToday:
    """today() is a thin, injectable seam over datetime.now().date()."""

    def test_returns_a_date_instance(self):
        """Return type is a plain date, not a datetime."""
        assert type(today()) is date

    def test_matches_current_date(self):
        """The returned date matches the real current date."""
        assert today() == date.today()


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
        """None winner_score/loser_score default to 12 and 0 (forfeit)."""
        body = [_GameResult("Alpha", "Beta")]
        result = results_to_applied(body)
        assert result[0].score_a == 12
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
# TestFilterScenariosBySimulation
# ---------------------------------------------------------------------------


class TestFilterScenariosBySimulation:
    """filter_scenarios_by_simulation prunes by (winner, loser) identity and, when scores are known, by margin bucket."""

    @staticmethod
    def _scenario(sub_label, conditions_atom):
        """Build a synthetic scenario dict with fixed game_winners/seeding for the given sub_label/conditions_atom."""
        return {
            "scenario_num": 2,
            "sub_label": sub_label,
            "game_winners": [("Lumberton", "Taylorsville"), ("Stringer", "Resurrection")],
            "conditions_atom": conditions_atom,
            "seeding": ("Taylorsville", "Stringer", "Lumberton", "Richton", "Resurrection"),
        }

    def _bucketed_scenarios(self):
        """Two mutually-exclusive margin buckets for the same (winner, loser) pairs."""
        bucket_a = [
            GameResult("Lumberton", "Taylorsville", min_margin=1, max_margin=12),
            GameResult("Stringer", "Resurrection", min_margin=1, max_margin=None),
        ]
        bucket_b = [
            GameResult("Lumberton", "Taylorsville", min_margin=12, max_margin=None),
            GameResult("Stringer", "Resurrection", min_margin=1, max_margin=None),
        ]
        return [self._scenario("a", bucket_a), self._scenario("b", bucket_b)]

    def test_margin_in_lower_bucket_keeps_only_that_branch(self):
        """A submitted margin of 5 (12-7) falls in the 1-11 bucket; the 12+ branch is dropped."""
        body = [_GameResult("Lumberton", "Taylorsville", winner_score=12, loser_score=7)]
        result = filter_scenarios_by_simulation(self._bucketed_scenarios(), body)
        assert [sc["sub_label"] for sc in result] == ["a"]

    def test_margin_in_upper_bucket_keeps_only_that_branch(self):
        """A submitted margin of 20 falls in the 12+ bucket; the 1-11 branch is dropped."""
        body = [_GameResult("Lumberton", "Taylorsville", winner_score=27, loser_score=7)]
        result = filter_scenarios_by_simulation(self._bucketed_scenarios(), body)
        assert [sc["sub_label"] for sc in result] == ["b"]

    def test_no_scores_keeps_both_buckets(self):
        """Without explicit scores, margin can't be validated, so both buckets survive (today's behavior)."""
        body = [_GameResult("Lumberton", "Taylorsville")]
        result = filter_scenarios_by_simulation(self._bucketed_scenarios(), body)
        assert {sc["sub_label"] for sc in result} == {"a", "b"}

    def test_scenario_without_conditions_atom_is_unaffected(self):
        """A scenario with conditions_atom=None is filtered purely on game_winners."""
        scenario = {
            "scenario_num": 1,
            "sub_label": "",
            "game_winners": [("Lumberton", "Taylorsville")],
            "conditions_atom": None,
            "seeding": ("Lumberton", "Taylorsville"),
        }
        body = [_GameResult("Lumberton", "Taylorsville", winner_score=12, loser_score=7)]
        result = filter_scenarios_by_simulation([scenario], body)
        assert result == [scenario]

    def test_empty_body_returns_all_scenarios(self):
        """Empty simulated_results leaves complete_scenarios unchanged."""
        scenarios = self._bucketed_scenarios()
        assert filter_scenarios_by_simulation(scenarios, []) == scenarios

    def test_non_game_result_atom_entries_are_skipped(self):
        """A conditions_atom mixing a MarginCondition with a GameResult still filters
        correctly — _margin_ok skips the non-GameResult entry instead of erroring."""
        margin_cond = MarginCondition(add=(("Stringer", "Resurrection"),), sub=(), op=">=", threshold=10)
        scenario = self._scenario(
            "a",
            [margin_cond, GameResult("Lumberton", "Taylorsville", min_margin=1, max_margin=12)],
        )
        body = [_GameResult("Lumberton", "Taylorsville", winner_score=12, loser_score=7)]
        result = filter_scenarios_by_simulation([scenario], body)
        assert result == [scenario]


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
# TestStandingsOddsFromRow
# ---------------------------------------------------------------------------


class TestStandingsOddsFromRow:
    """standings_odds_from_row builds a StandingsOdds from seeding-probability columns."""

    def test_fields_mapped(self):
        """school and p1-p4/p_playoffs columns map to the same-named fields."""
        result = standings_odds_from_row("Taylorsville", 0.1, 0.2, 0.3, 0.4, 0.9, False, False)
        assert result.school == "Taylorsville"
        assert (result.p1, result.p2, result.p3, result.p4) == (0.1, 0.2, 0.3, 0.4)
        assert result.p_playoffs == pytest.approx(0.9)

    def test_final_playoffs_mirrors_p_playoffs(self):
        """final_playoffs is always set equal to p_playoffs, not passed separately."""
        result = standings_odds_from_row("Taylorsville", 0.1, 0.2, 0.3, 0.4, 0.9, False, False)
        assert result.final_playoffs == result.p_playoffs

    def test_clinched_and_eliminated_coerced_to_bool(self):
        """Truthy/falsy DB values (e.g. 0/1 or None) are coerced to real bools."""
        result = standings_odds_from_row("Taylorsville", 0.1, 0.2, 0.3, 0.4, 0.9, 1, 0)
        assert result.clinched is True
        assert result.eliminated is False

    def test_none_clinched_eliminated_coerced_to_false(self):
        """None for clinched/eliminated (unset DB columns) coerces to False rather than raising."""
        result = standings_odds_from_row("Taylorsville", 0.1, 0.2, 0.3, 0.4, 0.9, None, None)
        assert result.clinched is False
        assert result.eliminated is False


# ---------------------------------------------------------------------------
# TestDisplayThresholdPredicates
# ---------------------------------------------------------------------------


class TestWithinDisplayThreshold:
    """within_display_threshold: len(remaining) <= DISPLAY_THRESHOLD, empty list counts as within."""

    def test_empty_list_is_within_threshold(self):
        """Zero remaining games is trivially within threshold."""
        assert within_display_threshold([]) is True

    def test_at_threshold_is_within(self):
        """Exactly DISPLAY_THRESHOLD games is within threshold."""
        assert within_display_threshold(list(range(DISPLAY_THRESHOLD))) is True

    def test_over_threshold_is_not_within(self):
        """More than DISPLAY_THRESHOLD games is not within threshold."""
        assert within_display_threshold(list(range(DISPLAY_THRESHOLD + 1))) is False


class TestHasDisplayableScenarios:
    """has_displayable_scenarios: non-empty AND len(remaining) <= DISPLAY_THRESHOLD."""

    def test_empty_list_has_no_displayable_scenarios(self):
        """Zero remaining games means nothing to display (unlike within_display_threshold)."""
        assert has_displayable_scenarios([]) is False

    def test_at_threshold_is_displayable(self):
        """A non-empty list at exactly DISPLAY_THRESHOLD is displayable."""
        assert has_displayable_scenarios(list(range(DISPLAY_THRESHOLD))) is True

    def test_over_threshold_is_not_displayable(self):
        """More than DISPLAY_THRESHOLD games is not displayable."""
        assert has_displayable_scenarios(list(range(DISPLAY_THRESHOLD + 1))) is False


# ---------------------------------------------------------------------------
# TestFilterToTeamOr404
# ---------------------------------------------------------------------------


@dataclass
class _FakeTeamEntry:
    """Minimal stand-in for a TeamStandingsEntry/TeamHostingEntry (only .school is used)."""

    school: str


@dataclass
class _FakeTeamsResponse:
    """Minimal stand-in for StandingsResponse/HostingResponse (only .teams is used)."""

    teams: list[_FakeTeamEntry] = field(default_factory=list)


class TestFilterToTeamOr404:
    """filter_to_team_or_404 narrows response.teams to one school or raises HTTP 404."""

    def test_matching_team_narrows_list(self):
        """teams is filtered down to only the entry matching the requested school."""
        response = _FakeTeamsResponse(teams=[_FakeTeamEntry("Alpha"), _FakeTeamEntry("Beta")])
        result = filter_to_team_or_404(response, "Alpha", clazz=5, region=2)
        assert [t.school for t in result.teams] == ["Alpha"]

    def test_returns_same_response_object(self):
        """The same response instance is returned (mutated in place), not a copy."""
        response = _FakeTeamsResponse(teams=[_FakeTeamEntry("Alpha")])
        result = filter_to_team_or_404(response, "Alpha", clazz=5, region=2)
        assert result is response

    def test_missing_team_raises_404(self):
        """A school not present in teams raises HTTP 404."""
        response = _FakeTeamsResponse(teams=[_FakeTeamEntry("Alpha")])
        with pytest.raises(HTTPException) as exc_info:
            filter_to_team_or_404(response, "Zeta", clazz=5, region=2)
        assert exc_info.value.status_code == 404
        assert "Zeta" in exc_info.value.detail

    def test_404_detail_includes_class_and_region(self):
        """The 404 detail message includes the class and region for context."""
        response = _FakeTeamsResponse(teams=[])
        with pytest.raises(HTTPException) as exc_info:
            filter_to_team_or_404(response, "Alpha", clazz=3, region=7)
        assert "3A Region 7" in exc_info.value.detail


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

    def test_conditions_field_populated_from_conditions_atom(self):
        """conditions_atom is serialized into the structured `conditions` field."""
        scenarios = [
            {
                "scenario_num": 1,
                "sub_label": "a",
                "game_winners": [("Lumberton", "Taylorsville")],
                "conditions_atom": [GameResult("Lumberton", "Taylorsville", min_margin=1, max_margin=12)],
                "seeding": ["Lumberton", "Taylorsville"],
            }
        ]
        result = scenarios_to_entries(scenarios)
        assert result is not None
        assert result[0].conditions == [
            {
                "type": "game_result",
                "winner": "Lumberton",
                "loser": "Taylorsville",
                "min_margin": 1,
                "max_margin": 12,
            }
        ]

    def test_conditions_field_none_when_no_conditions_atom(self):
        """conditions is None when the scenario dict has no conditions_atom."""
        scenarios = [{"scenario_num": 1, "sub_label": "1", "game_winners": [], "seeding": ["Alpha", "Beta"]}]
        result = scenarios_to_entries(scenarios)
        assert result is not None
        assert result[0].conditions is None


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
    "Alpha",
    5,
    2,
    0,
    3,
    1,
    0,  # 0-6
    0.6,
    0.3,
    0.1,
    0.0,
    1.0,  # 7-11 unweighted seeding
    False,
    False,
    False,  # 12-14 clinched/elim/coin
    _SNAP_DATE,  # 15 as_of_date
    0.65,
    0.28,
    0.07,
    0.0,
    1.0,  # 16-20 weighted seeding
    0.5,
    0.3,
    0.2,
    0.1,
    0.05,  # 21-25 bracket advancement
    0.45,
    0.25,
    0.15,
    0.08,
    0.04,  # 26-30 bracket weighted
    0.6,
    0.3,
    0.2,
    0.1,  # 31-34 home game
    0.55,
    0.28,
    0.18,
    0.09,  # 35-38 home game weighted
)
_ROW_BETA = (
    "Beta",
    4,
    3,
    0,
    1,
    3,
    0,  # 0-6
    0.1,
    0.2,
    0.4,
    0.3,
    1.0,  # 7-11 unweighted seeding
    False,
    False,
    True,  # 12-14 clinched/elim/coin
    _SNAP_DATE,  # 15 as_of_date
    0.08,
    0.18,
    0.42,
    0.32,
    1.0,  # 16-20 weighted seeding
    0.2,
    0.15,
    0.08,
    0.04,
    0.02,  # 21-25 bracket advancement
    0.18,
    0.12,
    0.06,
    0.03,
    0.01,  # 26-30 bracket weighted
    0.15,
    0.1,
    0.05,
    0.02,  # 31-34 home game
    0.12,
    0.09,
    0.04,
    0.02,  # 35-38 home game weighted
)


_HELMET_EMPTY = (None,) * 15  # id=None means "no helmet designated"


def _game_row(
    school: str,
    opponent: str,
    game_date=_DATE,
    pf: int | None = 21,
    pa: int | None = 14,
    location: str | None = "home",
    region_game: bool = True,
    status: str = "final",
    season: int = 2025,
    venue_name: str | None = None,
    helmet_a=_HELMET_EMPTY,
    helmet_b=_HELMET_EMPTY,
    final: bool = True,
) -> tuple:
    """Build a raw /games join row tuple matching build_game_models' expected shape."""
    return (
        school, opponent, game_date, pf, pa, location, region_game, status, season,
        venue_name, None, None, None,
        *helmet_a, *helmet_b,
        None, None, None, final, None, None, None,
    )


class TestBuildHelmetFromFields:
    """build_helmet_from_fields maps flat helmet_designs columns to a HelmetDesignModel."""

    def test_none_id_returns_none(self):
        """A None id (no helmet designated) returns None rather than a model."""
        assert build_helmet_from_fields(*_HELMET_EMPTY) is None

    def test_fields_mapped_in_order(self):
        """Fields map positionally per HELMET_FIELD_COLS order."""
        fields = (7, "Taylorsville", 2020, None, None, None, None, None, "Red", None, None, None, None, [], "note")
        result = build_helmet_from_fields(*fields)
        assert result is not None
        assert (result.id, result.school, result.year_first_worn) == (7, "Taylorsville", 2020)
        assert result.color == "Red"
        assert result.notes == "note"

    def test_years_worn_coerced_from_dicts(self):
        """A years_worn field of raw {"start", "end"} dicts coerces into YearsWornRange models."""
        fields = (
            1, "Taylorsville", 2018, 2020, [{"start": 2018, "end": 2020}],
            None, None, None, None, None, None, None, None, [], None,
        )
        result = build_helmet_from_fields(*fields)
        assert result is not None
        assert result.years_worn is not None
        assert (result.years_worn[0].start, result.years_worn[0].end) == (2018, 2020)


class TestBuildHelmetFromRow:
    """build_helmet_from_row wraps build_helmet_from_fields, asserting a real (non-None-id) row."""

    def test_returns_model_for_real_row(self):
        """A row with a real id returns a HelmetDesignModel."""
        row = (3, "Taylorsville", 2021, None, None, None, None, None, None, None, None, None, None, [], None)
        result = build_helmet_from_row(row)
        assert result.id == 3
        assert result.school == "Taylorsville"

    def test_none_id_raises_assertion(self):
        """A row with id=None violates the 'known existing helmet' contract and raises."""
        with pytest.raises(AssertionError):
            build_helmet_from_row(_HELMET_EMPTY)


class TestBuildGameModels:
    """build_game_models dedupes symmetric pairs, canonicalises team order, and builds GameModel."""

    def test_single_row_maps_fields(self):
        """A single row (no dedup needed) maps straight through to GameModel fields."""
        row = _game_row("Alpha", "Beta", pf=21, pa=14, location="home")
        result = build_game_models([row], team_filter=None)
        assert len(result) == 1
        g = result[0]
        assert (g.team_a, g.team_b) == ("Alpha", "Beta")
        assert (g.score_a, g.score_b) == (21, 14)
        assert g.location_a == "home"

    def test_symmetric_pair_deduplicated(self):
        """Both perspectives of the same game collapse to a single GameModel."""
        rows = [
            _game_row("Alpha", "Beta", pf=21, pa=14, location="home"),
            _game_row("Beta", "Alpha", pf=14, pa=21, location="away"),
        ]
        result = build_game_models(rows, team_filter=None)
        assert len(result) == 1

    def test_canonical_order_swaps_when_school_after_opponent(self):
        """When the row's school sorts after its opponent, fields are swapped to canonical order."""
        row = _game_row("Zeta", "Alpha", pf=21, pa=14, location="home")
        result = build_game_models([row], team_filter=None)
        g = result[0]
        assert (g.team_a, g.team_b) == ("Alpha", "Zeta")
        assert (g.score_a, g.score_b) == (14, 21)
        assert g.location_a == "away"  # flipped from Zeta's home to Alpha's away

    def test_no_dedup_or_canonicalization_with_team_filter(self):
        """With a team_filter, every row is kept as-is (perspective of the filtered team)."""
        rows = [
            _game_row("Zeta", "Alpha", pf=21, pa=14, location="home"),
        ]
        result = build_game_models(rows, team_filter="Zeta")
        g = result[0]
        assert (g.team_a, g.team_b) == ("Zeta", "Alpha")
        assert g.location_a == "home"

    def test_venue_none_when_no_venue_name(self):
        """A row with no venue name produces venue=None."""
        row = _game_row("Alpha", "Beta", venue_name=None)
        result = build_game_models([row], team_filter=None)
        assert result[0].venue is None

    def test_venue_built_when_venue_name_present(self):
        """A row with a venue name produces a populated VenueModel."""
        row = _game_row("Alpha", "Beta", venue_name="Memorial Stadium")
        result = build_game_models([row], team_filter=None)
        assert result[0].venue is not None
        assert result[0].venue.name == "Memorial Stadium"

    def test_no_helmet_when_id_is_none(self):
        """Helmet fields with id=None produce helmet_a/helmet_b=None."""
        row = _game_row("Alpha", "Beta")
        result = build_game_models([row], team_filter=None)
        assert result[0].helmet_a is None
        assert result[0].helmet_b is None

    def test_helmet_built_when_id_present(self):
        """Helmet fields with a non-None id produce a populated HelmetDesignModel."""
        helmet_a = (7, "Alpha", 2020, None, None, None, None, None, "Red", None, None, None, None, [], None)
        row = _game_row("Alpha", "Beta", helmet_a=helmet_a)
        result = build_game_models([row], team_filter=None)
        assert result[0].helmet_a is not None
        assert result[0].helmet_a.id == 7
        assert result[0].helmet_a.color == "Red"

    def test_helmets_swapped_with_school_order(self):
        """When school/opponent are swapped for canonical order, helmets swap with them."""
        helmet_zeta = (1, "Zeta", 2019, None, None, None, None, None, "Blue", None, None, None, None, [], None)
        helmet_alpha = (2, "Alpha", 2018, None, None, None, None, None, "Green", None, None, None, None, [], None)
        row = _game_row("Zeta", "Alpha", helmet_a=helmet_zeta, helmet_b=helmet_alpha)
        result = build_game_models([row], team_filter=None)
        g = result[0]
        assert g.helmet_a is not None and g.helmet_b is not None
        # team_a is now Alpha, so helmet_a should be Alpha's helmet
        assert g.helmet_a.color == "Green"
        assert g.helmet_b.color == "Blue"


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

    def test_weighted_odds_map_populates_weighted_fields(self):
        """When odds_map_weighted is supplied, *_weighted fields are set on each entry."""
        from backend.helpers.data_classes import BracketOdds

        weighted_map = {
            "R1S1": BracketOdds(
                school="R1S1", second_round=0.9, quarterfinals=0.6, semifinals=0.3, finals=0.15, champion=0.08
            )
        }
        by_region = {1: {"Alpha": _odds("Alpha", p1=1.0, clinched=True)}}
        result = build_bracket_entries_from_odds_map(
            by_region,
            {"R1S1": _bracket_odds("R1S1")},
            odds_map_weighted=weighted_map,
        )
        assert result[0].second_round_weighted == pytest.approx(0.9)
        assert result[0].quarterfinals_weighted == pytest.approx(0.6)
        assert result[0].champion_weighted == pytest.approx(0.08)


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
            "Alpha": StandingsOdds(
                school="Alpha",
                p1=0.6,
                p2=0.3,
                p3=0.1,
                p4=0.0,
                p_playoffs=1.0,
                final_playoffs=1.0,
                clinched=False,
                eliminated=False,
            ),
            "Beta": StandingsOdds(
                school="Beta",
                p1=0.4,
                p2=0.7,
                p3=0.9,
                p4=1.0,
                p_playoffs=1.0,
                final_playoffs=1.0,
                clinched=False,
                eliminated=False,
            ),
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


def _hosting_entry(
    school: str = "Able",
    *,
    fr: RoundHostingOdds | None = None,
    sr: RoundHostingOdds | None = None,
    qf: RoundHostingOdds | None = None,
    sf: RoundHostingOdds | None = None,
) -> TeamHostingEntry:
    """Build a TeamHostingEntry with RoundHostingOdds fixtures (all-None round by default)."""
    empty = RoundHostingOdds(p_host_given_reach=None, p_host_overall=None)
    return TeamHostingEntry(
        school=school,
        first_round=fr or empty,
        second_round=sr or empty,
        quarterfinals=qf or empty,
        semifinals=sf or empty,
    )


class TestResolveHostingScenarioInputs:
    """resolve_hosting_scenario_inputs derives seed/achievable-seeds and per-round probability dicts."""

    def test_clinched_seed_returned_no_achievable_seeds(self):
        """A seed at/above CLINCHED_THRESHOLD is returned as `seed`; achievable_seeds is None."""
        odds = _odds("Able", p2=0.999, p_playoffs=1.0)
        seed, achievable, *_ = resolve_hosting_scenario_inputs(odds, _hosting_entry())
        assert seed == 2
        assert achievable is None

    def test_unclinched_returns_achievable_seeds(self):
        """Below the clinch threshold, every seed with nonzero probability is achievable."""
        odds = _odds("Able", p1=0.3, p2=0.5, p3=0.2, p4=0.0, p_playoffs=1.0)
        seed, achievable, *_ = resolve_hosting_scenario_inputs(odds, _hosting_entry())
        assert seed is None
        assert achievable == [1, 2, 3]

    def test_p_reach_derived_from_overall_over_given_reach(self):
        """p_reach[round] = p_host_overall / p_host_given_reach for that round."""
        odds = _odds("Able", p1=1.0, p_playoffs=1.0)
        entry = _hosting_entry(fr=RoundHostingOdds(p_host_given_reach=0.5, p_host_overall=0.25))
        _, _, p_reach, p_given_reach, p_overall, *_ = resolve_hosting_scenario_inputs(odds, entry)
        assert p_reach is not None and p_given_reach is not None and p_overall is not None
        assert p_reach["First Round"] == pytest.approx(0.5)
        assert p_given_reach["First Round"] == pytest.approx(0.5)
        assert p_overall["First Round"] == pytest.approx(0.25)

    def test_zero_given_reach_skips_p_reach_division(self):
        """A zero p_host_given_reach does not raise ZeroDivisionError; p_reach is simply omitted."""
        odds = _odds("Able", p1=1.0, p_playoffs=1.0)
        entry = _hosting_entry(fr=RoundHostingOdds(p_host_given_reach=0.0, p_host_overall=0.0))
        _, _, p_reach, *_ = resolve_hosting_scenario_inputs(odds, entry)
        assert p_reach is None

    def test_all_none_rounds_return_none_dicts(self):
        """When no round has any hosting odds set, every probability dict is None (not {})."""
        odds = _odds("Able", p1=1.0, p_playoffs=1.0)
        result = resolve_hosting_scenario_inputs(odds, _hosting_entry())
        _, _, p_reach, p_given_reach, p_overall, p_reach_w, p_given_reach_w, p_overall_w = result
        assert (p_reach, p_given_reach, p_overall) == (None, None, None)
        assert (p_reach_w, p_given_reach_w, p_overall_w) == (None, None, None)

    def test_weighted_dicts_derived_independently(self):
        """Weighted p_reach/p_host_given_reach/p_host_overall come from the *_weighted fields."""
        odds = _odds("Able", p1=1.0, p_playoffs=1.0)
        entry = _hosting_entry(
            fr=RoundHostingOdds(
                p_host_given_reach=None, p_host_overall=None,
                p_host_given_reach_weighted=0.4, p_host_overall_weighted=0.2,
            )
        )
        *_, p_reach_w, p_given_reach_w, p_overall_w = resolve_hosting_scenario_inputs(odds, entry)
        assert p_reach_w is not None and p_given_reach_w is not None and p_overall_w is not None
        assert p_reach_w["First Round"] == pytest.approx(0.5)
        assert p_given_reach_w["First Round"] == pytest.approx(0.4)
        assert p_overall_w["First Round"] == pytest.approx(0.2)


class TestSelectSentinelRegion:
    """select_sentinel_region picks a deterministic representative region for a class."""

    def test_picks_lowest_numbered_region(self):
        """The lowest region number is chosen regardless of dict insertion order."""
        regions = {3: ["Team A"], 1: ["Team B"], 2: ["Team C"]}
        assert select_sentinel_region(regions) == 1

    def test_single_region_class(self):
        """A class with only one region returns that region."""
        assert select_sentinel_region({4: ["Team A", "Team B"]}) == 4

    def test_deterministic_across_calls(self):
        """Repeated calls on the same input always agree."""
        regions = {5: [], 2: [], 8: []}
        assert select_sentinel_region(regions) == select_sentinel_region(regions) == 2


class TestBuildHostingEntries:
    """build_hosting_entries returns one TeamHostingEntry per team, with correct round structure."""

    def test_5a_7a_returns_entry_per_team(self):
        """One entry per team in region_odds."""
        result = build_hosting_entries(_REGION1_ODDS_5A, SLOTS_5A_7A_2025, region=1, season=2025, clazz=5)
        assert len(result) == 4

    def test_5a_7a_second_round_odds_none(self):
        """5A–7A second_round has p_host_given_reach=None, p_host_overall=None."""
        result = build_hosting_entries(_REGION1_ODDS_5A, SLOTS_5A_7A_2025, region=1, season=2025, clazz=5)
        for entry in result:
            assert entry.second_round.p_host_given_reach is None
            assert entry.second_round.p_host_overall is None

    def test_5a_7a_first_round_p_host_given_reach(self):
        """Seeds 1 and 2 host R1 (p_host_given_reach=1.0); seeds 3 and 4 play away (p_host_given_reach=0.0)."""
        result = build_hosting_entries(_REGION1_ODDS_5A, SLOTS_5A_7A_2025, region=1, season=2025, clazz=5)
        by_school = {e.school: e for e in result}
        assert by_school["Alpha"].first_round.p_host_given_reach == pytest.approx(1.0)  # seed 1 — home
        assert by_school["Beta"].first_round.p_host_given_reach == pytest.approx(1.0)  # seed 2 — home
        assert by_school["Gamma"].first_round.p_host_given_reach == pytest.approx(0.0)  # seed 3 — away
        assert by_school["Delta"].first_round.p_host_given_reach == pytest.approx(0.0)  # seed 4 — away

    def test_1a_4a_returns_entry_per_team(self):
        """One entry per team in region_odds for 1A–4A."""
        result = build_hosting_entries(_REGION1_ODDS_1A, SLOTS_1A_4A_2025, region=1, season=2025, clazz=1)
        assert len(result) == 4

    def test_1a_4a_second_round_odds_not_none(self):
        """1A–4A second_round has non-None p_host_overall when team can advance."""
        result = build_hosting_entries(_REGION1_ODDS_1A, SLOTS_1A_4A_2025, region=1, season=2025, clazz=1)
        # Seed-1 team (Able) has p_r1_adv > 0, so second_round.p_host_overall should be non-None.
        able = next(e for e in result if e.school == "Able")
        assert able.second_round.p_host_overall is not None

    def test_1a_4a_first_round_p_host_given_reach(self):
        """Seeds 1 and 2 host R1 (p_host_given_reach=1.0); seeds 3 and 4 play away (p_host_given_reach=0.0)."""
        result = build_hosting_entries(_REGION1_ODDS_1A, SLOTS_1A_4A_2025, region=1, season=2025, clazz=1)
        by_school = {e.school: e for e in result}
        assert by_school["Able"].first_round.p_host_given_reach == pytest.approx(1.0)  # seed 1 — home
        assert by_school["Baker"].first_round.p_host_given_reach == pytest.approx(1.0)  # seed 2 — home
        assert by_school["Camp"].first_round.p_host_given_reach == pytest.approx(0.0)  # seed 3 — away
        assert by_school["Dog"].first_round.p_host_given_reach == pytest.approx(0.0)  # seed 4 — away

    def test_zero_advancement_gives_none_p_host_given_reach(self):
        """When p_r1_adv == 0 (no seed probability), second_round p_host_given_reach is None."""
        # A team with all p values = 0 has zero second-round advancement probability.
        region_odds = {
            "Able": _odds("Able", p1=1.0, p_playoffs=1.0, clinched=True),
            "Baker": _odds("Baker", p2=1.0, p_playoffs=1.0, clinched=True),
            "Camp": _odds("Camp", p3=1.0, p_playoffs=1.0, clinched=True),
            "Zero": _odds("Zero", p_playoffs=0.0),  # no seeds → second_round = 0
        }
        result = build_hosting_entries(region_odds, SLOTS_1A_4A_2025, region=1, season=2025, clazz=1)
        zero = next(e for e in result if e.school == "Zero")
        assert zero.second_round.p_host_given_reach is None

    def test_eliminated_hosting_override_used_for_eliminated_team(self):
        """An eliminated team present in eliminated_hosting gets the deterministic
        override tuple (r1, r2, qf, sf) instead of computed probabilistic odds
        (lines 858-867, and _det_round_hosting via this path).
        """
        region_odds = dict(_REGION1_ODDS_1A)
        region_odds["Dog"] = _odds("Dog", p4=0.0, p_playoffs=0.0, eliminated=True)
        result = build_hosting_entries(
            region_odds, SLOTS_1A_4A_2025, region=1, season=2025, clazz=1,
            eliminated_hosting={"Dog": (1.0, 0.0, None, None)},
        )
        dog = next(e for e in result if e.school == "Dog")
        assert dog.first_round.p_host_given_reach == pytest.approx(1.0)
        assert dog.second_round.p_host_given_reach == pytest.approx(0.0)
        assert dog.quarterfinals.p_host_given_reach is None
        assert dog.quarterfinals.p_host_overall == pytest.approx(0.0)
        assert dog.semifinals.p_host_given_reach is None

    # ------------------------------------------------------------------
    # Stored-odds path (home_p_host_given_reach + stored_adv provided)
    # ------------------------------------------------------------------

    def test_stored_path_1a_4a_uses_stored_values(self):
        """When home_p_host_given_reach and stored_adv are supplied, p_host_overall = p_host_given_reach × advancement."""
        home_p_host_given_reach = {
            "Able": (1.0, 0.6, 0.3, 0.15),
            "Baker": (1.0, 0.5, 0.25, 0.1),
            "Camp": (0.0, 0.0, 0.0, 0.0),
            "Dog": (0.0, 0.0, 0.0, 0.0),
        }
        stored_adv = {
            "Able": (1.0, 0.5, 0.25, 0.125),
            "Baker": (1.0, 0.5, 0.25, 0.125),
            "Camp": (0.5, 0.25, 0.125, 0.0625),
            "Dog": (0.5, 0.25, 0.125, 0.0625),
        }
        result = build_hosting_entries(
            _REGION1_ODDS_1A,
            SLOTS_1A_4A_2025,
            region=1,
            season=2025,
            clazz=1,
            stored=StoredHostingOdds(
                given_reach=home_p_host_given_reach,
                given_reach_weighted={},
                advancement=stored_adv,
                advancement_weighted={},
            ),
        )
        by_school = {e.school: e for e in result}
        able = by_school["Able"]
        assert able.first_round.p_host_given_reach == pytest.approx(1.0)
        assert able.first_round.p_host_overall == pytest.approx(1.0 * 1.0)
        assert able.second_round.p_host_given_reach == pytest.approx(0.6)
        assert able.second_round.p_host_overall == pytest.approx(0.6 * 0.5)
        assert able.quarterfinals.p_host_given_reach == pytest.approx(0.3)
        assert able.quarterfinals.p_host_overall == pytest.approx(0.3 * 0.25)
        assert able.semifinals.p_host_given_reach == pytest.approx(0.15)
        assert able.semifinals.p_host_overall == pytest.approx(0.15 * 0.125)

    def test_stored_path_5a_7a_second_round_always_none(self):
        """5A–7A stored path: second_round p_host_given_reach and p_host_overall are always None."""
        home_p_host_given_reach = {s: (1.0, 0.0, 0.5, 0.25) for s in ("Alpha", "Beta", "Gamma", "Delta")}
        stored_adv = {s: (1.0, 0.0, 0.5, 0.25) for s in ("Alpha", "Beta", "Gamma", "Delta")}
        result = build_hosting_entries(
            _REGION1_ODDS_5A,
            SLOTS_5A_7A_2025,
            region=1,
            season=2025,
            clazz=5,
            stored=StoredHostingOdds(
                given_reach=home_p_host_given_reach,
                given_reach_weighted={},
                advancement=stored_adv,
                advancement_weighted={},
            ),
        )
        for entry in result:
            assert entry.second_round.p_host_given_reach is None
            assert entry.second_round.p_host_overall is None

    def test_stored_path_zero_advancement_gives_none_p_host_given_reach(self):
        """Stored path: p_host_given_reach is None when the advancement probability is zero."""
        home_p_host_given_reach = {"Able": (1.0, 0.5, 0.3, 0.15)}
        stored_adv = {"Able": (0.0, 0.0, 0.0, 0.0)}  # no advancement
        region_odds = {"Able": _odds("Able", p1=1.0, p_playoffs=1.0, clinched=True)}
        result = build_hosting_entries(
            region_odds,
            SLOTS_1A_4A_2025,
            region=1,
            season=2025,
            clazz=1,
            stored=StoredHostingOdds(
                given_reach=home_p_host_given_reach,
                given_reach_weighted={},
                advancement=stored_adv,
                advancement_weighted={},
            ),
        )
        able = result[0]
        assert able.second_round.p_host_given_reach is None
        assert able.quarterfinals.p_host_given_reach is None
        assert able.semifinals.p_host_given_reach is None

    # ------------------------------------------------------------------
    # Weighted fallback path (win_prob_fn_weighted provided)
    # ------------------------------------------------------------------

    def test_weighted_fallback_1a_4a_populates_weighted_fields(self):
        """Passing win_prob_fn_weighted produces non-None p_host_given_reach_weighted values."""

        def equal_w(hr: int, hs: int, ar: int, as_: int) -> float:
            """Return 0.5 for all matchups (equal probability)."""
            return 0.5

        result = build_hosting_entries(
            _REGION1_ODDS_1A,
            SLOTS_1A_4A_2025,
            region=1,
            season=2025,
            clazz=1,
            win_prob_fn_weighted=equal_w,
        )
        able = next(e for e in result if e.school == "Able")
        assert able.first_round.p_host_given_reach_weighted is not None
        assert able.second_round.p_host_overall_weighted is not None

    def test_weighted_fallback_matches_unweighted_for_equal_prob(self):
        """With 50/50 weighted fn, p_host_given_reach_weighted equals p_host_given_reach."""

        def equal_w(hr: int, hs: int, ar: int, as_: int) -> float:
            """Return 0.5 for all matchups (equal probability)."""
            return 0.5

        result = build_hosting_entries(
            _REGION1_ODDS_1A,
            SLOTS_1A_4A_2025,
            region=1,
            season=2025,
            clazz=1,
            win_prob_fn_weighted=equal_w,
        )
        for entry in result:
            assert entry.first_round.p_host_given_reach_weighted == pytest.approx(
                entry.first_round.p_host_given_reach or 0.0, abs=1e-9
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
            return StandingsOdds(
                school=school, **kwargs, p_playoffs=1.0, final_playoffs=1.0, clinched=True, eliminated=False
            )

        def _eliminated(school: str) -> StandingsOdds:
            """Return a fully eliminated StandingsOdds."""
            return StandingsOdds(
                school=school,
                p1=0.0,
                p2=0.0,
                p3=0.0,
                p4=0.0,
                p_playoffs=0.0,
                final_playoffs=0.0,
                clinched=True,
                eliminated=True,
            )

        return {
            1: {
                "Able": _alive("Able", 1),
                "Baker": _alive("Baker", 2),
                "Camp": _alive("Camp", 3),
                "Dog": _alive("Dog", 4),
            },
            2: {
                "R2T1": _alive("R2T1", 1),
                "R2T2": _alive("R2T2", 2),
                "R2T3": _alive("R2T3", 3),
                "R2T4": _alive("R2T4", 4),
            },
            3: {
                "R3T1": _eliminated("R3T1"),  # seed-1 eliminated
                "R3T2": _alive("R3T2", 2),
                "R3T3": _alive("R3T3", 3),
                "R3T4": _alive("R3T4", 4),
            },
            4: {
                "R4T1": _eliminated("R4T1"),  # seed-1 eliminated
                "R4T2": _alive("R4T2", 2),
                "R4T3": _alive("R4T3", 3),
                "R4T4": _alive("R4T4", 4),
            },
        }

    def test_sf_p_host_given_reach_1_when_all_opp_seed1s_eliminated(self):
        """When all opposing-quarter seed-1 teams are eliminated, SF p_host_given_reach = 1.0 for seed-1 team.

        Uses season=2024 (even year) so that equal-seed SF matchups are decided by higher
        region number hosting — meaning R1-1 would NOT host against R3-1 or R4-1 in a normal
        bracket.  Eliminating both R3-1 and R4-1 forces all SF opponents to be lower seeds,
        guaranteeing R1-1 hosts.
        """
        all_region_odds = self._1a_all_region_odds_eliminate_r3_r4_seed1()
        result = build_hosting_entries(
            _REGION1_ODDS_1A,
            SLOTS_1A_4A_2025,
            region=1,
            season=2024,
            clazz=1,
            all_region_odds=all_region_odds,
        )
        able = next(e for e in result if e.school == "Able")
        assert able.semifinals.p_host_given_reach == pytest.approx(1.0)

    def test_sf_p_host_given_reach_partial_elimination_between_0_and_1(self):
        """Eliminating only one opposing seed-1 puts SF p_host_given_reach strictly between baseline and 1.0."""
        all_region_odds = self._1a_all_region_odds_eliminate_r3_r4_seed1()
        # Restore R3-seed-1 as alive — only R4-seed-1 is eliminated.
        all_region_odds[3]["R3T1"] = StandingsOdds(
            school="R3T1",
            p1=1.0,
            p2=0.0,
            p3=0.0,
            p4=0.0,
            p_playoffs=1.0,
            final_playoffs=1.0,
            clinched=True,
            eliminated=False,
        )
        baseline = build_hosting_entries(
            _REGION1_ODDS_1A,
            SLOTS_1A_4A_2025,
            region=1,
            season=2024,
            clazz=1,
        )
        result = build_hosting_entries(
            _REGION1_ODDS_1A,
            SLOTS_1A_4A_2025,
            region=1,
            season=2024,
            clazz=1,
            all_region_odds=all_region_odds,
        )
        able = next(e for e in result if e.school == "Able")
        baseline_able = next(e for e in baseline if e.school == "Able")
        assert able.semifinals.p_host_given_reach is not None
        assert (baseline_able.semifinals.p_host_given_reach or 0.0) < able.semifinals.p_host_given_reach < 1.0

    def test_sf_p_host_given_reach_unchanged_with_no_elimination(self):
        """With all_region_odds but no eliminations, SF p_host_given_reach matches the baseline (no all_region_odds)."""
        all_region_odds = self._1a_all_region_odds_eliminate_r3_r4_seed1()
        # Restore both R3 and R4 seed-1 as alive.
        for reg in (3, 4):
            school = f"R{reg}T1"
            all_region_odds[reg][school] = StandingsOdds(
                school=school,
                p1=1.0,
                p2=0.0,
                p3=0.0,
                p4=0.0,
                p_playoffs=1.0,
                final_playoffs=1.0,
                clinched=True,
                eliminated=False,
            )
        baseline = build_hosting_entries(
            _REGION1_ODDS_1A,
            SLOTS_1A_4A_2025,
            region=1,
            season=2024,
            clazz=1,
        )
        with_odds = build_hosting_entries(
            _REGION1_ODDS_1A,
            SLOTS_1A_4A_2025,
            region=1,
            season=2024,
            clazz=1,
            all_region_odds=all_region_odds,
        )
        baseline_able = next(e for e in baseline if e.school == "Able")
        with_able = next(e for e in with_odds if e.school == "Able")
        assert with_able.semifinals.p_host_given_reach == pytest.approx(baseline_able.semifinals.p_host_given_reach or 0.0, abs=1e-6)

    # ------------------------------------------------------------------
    # QF p_host_given_reach — cross-region eliminations / confirmed wins
    # ------------------------------------------------------------------
    #
    # South-half 1A 2025 bracket (slots 9–16, 0-based indices 8–15):
    #   Q4 upper-south: slots  9 (R5-1 vs R6-4) + 10 (R7-2 vs R8-3)
    #   Q4 upper-north: slots 11 (R6-1 vs R5-4) + 12 (R8-2 vs R7-3)
    #   Q4 lower-north: slots 13 (R7-1 vs R8-4) + 14 (R5-2 vs R6-3)  ← QF opp source for R8-1
    #   Q4 lower-south: slots 15 (R8-1 vs R7-4) + 16 (R6-2 vs R5-3)  ← R8-1's sub-bracket
    #
    # Scenario: R7-1 eliminated (lost R1), R8-4 has 1 win (won R1, lost R2 to R5-2),
    # R6-3 eliminated (lost R1), R5-2 has 2 wins → guaranteed QF opponent of R8-1.
    # R8-1 (seed-1) always hosts R2; R5-2 (seed-2) hosted R2 vs R8-4 (seed-4).
    # Equal home games (2 each) → higher seed (R8-1 seed-1) hosts → p_host_given_reach = 1.0.

    def _region8_odds_1a(self) -> dict:
        """Region 8 seeding odds for QF p_host_given_reach tests."""
        return {
            "R8T1": _odds("R8T1", p1=1.0, p_playoffs=1.0),
            "R8T2": _odds("R8T2", p2=1.0, p_playoffs=1.0),
            "R8T3": _odds("R8T3", p3=1.0, p_playoffs=1.0),
            "R8T4": _odds("R8T4", p4=1.0, p_playoffs=1.0),
        }

    def _all_region_odds_qf_test(self) -> dict:
        """all_region_odds for QF p_host_given_reach tests: R7-1 and R6-3 eliminated (0 wins);
        R8-4 eliminated with 1 win (survived R1, lost R2 to R5-2); R5-2 alive.
        """

        def _alive(school: str, seed: int) -> StandingsOdds:
            """Return a clinched StandingsOdds with a single confirmed seed."""
            kwargs = {"p1": 0.0, "p2": 0.0, "p3": 0.0, "p4": 0.0}
            kwargs[f"p{seed}"] = 1.0
            return StandingsOdds(
                school=school, **kwargs, p_playoffs=1.0, final_playoffs=1.0, clinched=True, eliminated=False
            )

        def _eliminated(school: str) -> StandingsOdds:
            """Return a fully eliminated StandingsOdds."""
            return StandingsOdds(
                school=school,
                p1=0.0,
                p2=0.0,
                p3=0.0,
                p4=0.0,
                p_playoffs=0.0,
                final_playoffs=0.0,
                clinched=True,
                eliminated=True,
            )

        return {
            # North half — all alive (not involved in south-half QF computation)
            1: {
                "R1T1": _alive("R1T1", 1),
                "R1T2": _alive("R1T2", 2),
                "R1T3": _alive("R1T3", 3),
                "R1T4": _alive("R1T4", 4),
            },
            2: {
                "R2T1": _alive("R2T1", 1),
                "R2T2": _alive("R2T2", 2),
                "R2T3": _alive("R2T3", 3),
                "R2T4": _alive("R2T4", 4),
            },
            3: {
                "R3T1": _alive("R3T1", 1),
                "R3T2": _alive("R3T2", 2),
                "R3T3": _alive("R3T3", 3),
                "R3T4": _alive("R3T4", 4),
            },
            4: {
                "R4T1": _alive("R4T1", 1),
                "R4T2": _alive("R4T2", 2),
                "R4T3": _alive("R4T3", 3),
                "R4T4": _alive("R4T4", 4),
            },
            # South half — selective eliminations
            # Slot 14 (R5-2 home vs R6-3 away): R6-3 eliminated (lost R1), R5-2 alive
            5: {
                "R5T1": _alive("R5T1", 1),
                "R5T2": _alive("R5T2", 2),
                "R5T3": _alive("R5T3", 3),
                "R5T4": _alive("R5T4", 4),
            },
            6: {
                "R6T1": _alive("R6T1", 1),
                "R6T2": _alive("R6T2", 2),
                "R6T3": _eliminated("R6T3"),
                "R6T4": _alive("R6T4", 4),
            },
            # Slot 13 (R7-1 home vs R8-4 away): R7-1 eliminated (lost R1); R8-4 eliminated (won R1, lost R2)
            7: {
                "R7T1": _eliminated("R7T1"),
                "R7T2": _alive("R7T2", 2),
                "R7T3": _alive("R7T3", 3),
                "R7T4": _alive("R7T4", 4),
            },
            8: {
                "R8T1": _alive("R8T1", 1),
                "R8T2": _alive("R8T2", 2),
                "R8T3": _alive("R8T3", 3),
                "R8T4": _eliminated("R8T4"),
            },
        }

    def test_qf_p_host_given_reach_1_when_guaranteed_home_opponent(self):
        """QF p_host_given_reach = 1.0 when the only surviving QF opponent was home in R2.

        Scenario mirrors the Taylorsville bug: R8-1 seed-1 vs confirmed R5-2 (seed-2).
        Both teams had 2 home games entering QF, so R8-1 (higher seed) hosts → 1.0.
        """
        all_region_odds = self._all_region_odds_qf_test()
        # R5-2 has 2 confirmed wins; R8-4 has 1 (survived R1 → valid R2 opponent for R5-2).
        cross_region_wins: dict = {(5, 2): 2, (8, 4): 1}
        result = build_hosting_entries(
            self._region8_odds_1a(),
            SLOTS_1A_4A_2025,
            region=8,
            season=2025,
            clazz=1,
            all_region_odds=all_region_odds,
            cross_region_wins=cross_region_wins,
        )
        r8t1 = next(e for e in result if e.school == "R8T1")
        assert r8t1.quarterfinals.p_host_given_reach == pytest.approx(1.0)

    def test_qf_p_host_given_reach_between_0_and_1_with_partial_elimination(self):
        """Partial elimination leaves QF p_host_given_reach strictly between baseline and 1.0."""
        all_region_odds = self._all_region_odds_qf_test()
        # Restore R7-1 as alive — now R7-1 and R5-2 are both QF candidates.
        all_region_odds[7]["R7T1"] = StandingsOdds(
            school="R7T1",
            p1=1.0,
            p2=0.0,
            p3=0.0,
            p4=0.0,
            p_playoffs=1.0,
            final_playoffs=1.0,
            clinched=True,
            eliminated=False,
        )
        cross_region_wins: dict = {(5, 2): 2, (8, 4): 1}
        baseline = build_hosting_entries(
            self._region8_odds_1a(),
            SLOTS_1A_4A_2025,
            region=8,
            season=2025,
            clazz=1,
        )
        result = build_hosting_entries(
            self._region8_odds_1a(),
            SLOTS_1A_4A_2025,
            region=8,
            season=2025,
            clazz=1,
            all_region_odds=all_region_odds,
            cross_region_wins=cross_region_wins,
        )
        r8t1 = next(e for e in result if e.school == "R8T1")
        baseline_r8t1 = next(e for e in baseline if e.school == "R8T1")
        assert r8t1.quarterfinals.p_host_given_reach is not None
        assert (baseline_r8t1.quarterfinals.p_host_given_reach or 0.0) <= r8t1.quarterfinals.p_host_given_reach <= 1.0


# ---------------------------------------------------------------------------
# TestBuildPlayoffBracketState
# ---------------------------------------------------------------------------


def _game_result(winner: str, loser: str) -> BracketGameResultRequest:
    """Convenience constructor for BracketGameResultRequest with school-name refs."""
    return BracketGameResultRequest(winner=ParticipantRef(school=winner), loser=ParticipantRef(school=loser))


def _school_to_seed_4teams() -> dict[str, tuple[int, int]]:
    """Minimal 4-team bracket: one seed per region in two regions."""
    return {
        "AlphaS1": (1, 1),
        "AlphaS2": (1, 2),
        "BetaS1": (2, 1),
        "BetaS2": (2, 2),
    }


class TestBuildPlayoffBracketState:
    """build_playoff_bracket_state is a pure function — fully unit-testable."""

    def _base_state(self, submitted=None, db_wins=None, db_losers=None):
        """Return a PlayoffBracketState built from a fixed 4-team bracket for use in tests."""
        return build_playoff_bracket_state(
            school_to_seed=_school_to_seed_4teams(),
            db_wins=db_wins or {},
            db_losers=db_losers or set(),
            submitted_results=submitted or [],
            elo_ratings={},
            slots=SLOTS_5A_7A_2025,
            season=2025,
            clazz=5,
        )

    def test_returns_playoff_bracket_state(self):
        """Return type is PlayoffBracketState."""
        assert isinstance(self._base_state(), PlayoffBracketState)

    def test_all_alive_with_no_results(self):
        """Without any results all schools are alive (p_playoffs=1.0)."""
        state = self._base_state()
        for reg_odds in state.all_region_odds.values():
            for so in reg_odds.values():
                assert so.p_playoffs == pytest.approx(1.0)

    def test_submitted_winner_gets_win_credit(self):
        """Submitted winner's win count increments by 1."""
        state = self._base_state(submitted=[_game_result("AlphaS1", "BetaS1")])
        assert state.wins_by_team.get("AlphaS1", 0) == 1

    def test_submitted_loser_is_eliminated(self):
        """Submitted loser's slot has p_playoffs=0.0 in all_region_odds."""
        state = self._base_state(submitted=[_game_result("AlphaS1", "BetaS1")])
        loser_odds = state.all_region_odds[2]["BetaS1"]
        assert loser_odds.p_playoffs == pytest.approx(0.0)
        assert loser_odds.eliminated is True

    def test_db_loser_overridden_by_submitted_winner(self):
        """A school marked as DB loser but also submitted as winner stays alive."""
        state = self._base_state(
            db_losers={"AlphaS1"},
            submitted=[_game_result("AlphaS1", "BetaS1")],
        )
        alpha_odds = state.all_region_odds[1]["AlphaS1"]
        assert alpha_odds.p_playoffs == pytest.approx(1.0)
        assert alpha_odds.eliminated is False

    def test_cross_region_wins_populated(self):
        """cross_region_wins maps (region, seed) → confirmed wins."""
        state = self._base_state(submitted=[_game_result("AlphaS1", "BetaS1")])
        assert state.cross_region_wins.get((1, 1), 0) == 1

    def test_eliminated_hosting_map_contains_losers(self):
        """eliminated_hosting_map is keyed by losers' school names."""
        state = self._base_state(submitted=[_game_result("AlphaS1", "BetaS1")])
        assert "BetaS1" in state.eliminated_hosting_map

    def test_no_elo_ratings_matchup_fn_is_none(self):
        """matchup_fn is None when elo_ratings is empty."""
        state = self._base_state()
        assert state.matchup_fn is None

    def test_with_elo_ratings_matchup_fn_is_not_none(self):
        """matchup_fn is set when elo_ratings are provided."""
        state = build_playoff_bracket_state(
            school_to_seed=_school_to_seed_4teams(),
            db_wins={},
            db_losers=set(),
            submitted_results=[],
            elo_ratings={"AlphaS1": 1500.0, "AlphaS2": 1400.0, "BetaS1": 1480.0, "BetaS2": 1420.0},
            slots=SLOTS_5A_7A_2025,
            season=2025,
            clazz=5,
        )
        assert state.matchup_fn is not None

    def test_unresolvable_winner_name_gets_no_win_credit(self):
        """A winner ref naming a school not in school_to_seed resolves via
        _resolve_ref_to_school but is skipped (lines 1339->1337, 1349->1351) —
        no win credit and no submitted_winners membership.
        """
        state = self._base_state(submitted=[_game_result("NotClinchedYet", "AlphaS1")])
        assert state.wins_by_team.get("NotClinchedYet", 0) == 0
        # AlphaS1 was the named loser here but the "winner" side is unresolvable,
        # so AlphaS1 still gets marked eliminated via the loser branch.
        assert state.all_region_odds[1]["AlphaS1"].eliminated is True

    def test_unresolvable_loser_name_is_not_marked_eliminated(self):
        """A loser ref naming a school not in school_to_seed is skipped
        (line 1353->1347) — no seed gets added to losers_known for it."""
        state = self._base_state(submitted=[_game_result("AlphaS1", "NotClinchedYet")])
        # The only real seed here is the winner (AlphaS1), which is not eliminated;
        # no exception is raised trying to mark the unresolvable loser's seed.
        assert state.all_region_odds[1]["AlphaS1"].eliminated is False

    def test_unresolvable_loserless_winner_sets_no_ceiling(self):
        """A loser-less result whose winner ref is unresolvable does not reach
        _collect_possible_opponents (line 1355->1347) — round_ceiling stays empty.
        """
        layout = build_bracket_layout(SLOTS_5A_7A_2025)
        state = build_playoff_bracket_state(
            school_to_seed=_school_to_seed_4teams(),
            db_wins={},
            db_losers=set(),
            submitted_results=[BracketGameResultRequest(winner=ParticipantRef(school="NotClinchedYet"), round="quarterfinals")],
            elo_ratings={},
            slots=SLOTS_5A_7A_2025,
            season=2025,
            clazz=5,
            layout=layout,
        )
        assert state.round_ceiling == {}


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

    def test_weighted_fields_none_without_prob_fn(self):
        """*_weighted fields are None when win_prob_fn_weighted is not supplied."""
        result = build_bracket_entries(self._by_region(), SLOTS_5A_7A_2025)
        for entry in result:
            assert entry.second_round_weighted is None
            assert entry.quarterfinals_weighted is None
            assert entry.semifinals_weighted is None
            assert entry.finals_weighted is None
            assert entry.champion_weighted is None

    def test_hosting_none_without_season_clazz(self):
        """hosting is None when season/clazz are not passed."""
        result = build_bracket_entries(self._by_region(), SLOTS_5A_7A_2025)
        assert all(e.hosting is None for e in result)

    def test_5a_7a_hosting_second_round_is_null(self):
        """5A–7A has no second round: hosting.second_round p_host_given_reach/p_host_overall are None."""
        result = build_bracket_entries(self._by_region(), SLOTS_5A_7A_2025, season=2025, clazz=5)
        for entry in result:
            assert entry.hosting is not None
            assert entry.hosting.second_round.p_host_given_reach is None
            assert entry.hosting.second_round.p_host_overall is None

    def test_1a_4a_hosting_second_round_is_populated(self):
        """1A–4A has a second round: hosting.second_round p_host_overall is not None."""
        result = build_bracket_entries(self._by_region(), SLOTS_1A_4A_2025, season=2025, clazz=1)
        for entry in result:
            assert entry.hosting is not None
            assert entry.hosting.second_round.p_host_overall is not None

    def test_seed1_hosting_first_round_p_host_given_reach_is_one(self):
        """Every seed-1 slot is the home team in round 1: p_host_given_reach == 1.0."""
        result = build_bracket_entries(self._by_region(), SLOTS_5A_7A_2025, season=2025, clazz=5)
        seed1_entries = [e for e in result if e.seed == 1]
        assert seed1_entries, "expected at least one seed-1 entry"
        for entry in seed1_entries:
            assert entry.hosting is not None
            assert entry.hosting.first_round.p_host_given_reach == pytest.approx(1.0)

    def test_r1_p_host_overall_equals_p_host_given_reach_when_all_clinched(self):
        """When all teams are clinched (p_playoffs=1.0), R1 p_host_overall == p_host_given_reach."""
        result = build_bracket_entries(self._by_region(), SLOTS_5A_7A_2025, season=2025, clazz=5)
        for entry in result:
            h = entry.hosting
            assert h is not None
            cond = h.first_round.p_host_given_reach
            marg = h.first_round.p_host_overall
            if cond is not None and marg is not None:
                assert marg == pytest.approx(cond, abs=1e-9)

    def test_wins_by_slot_param_applied(self):
        """Direct wins_by_slot param boosts advancement odds for the named slot.

        For 5A-7A there is no second round, so a confirmed first-round win shows
        up as quarterfinals=1.0 (the team is confirmed into the second game).
        """
        by_region = self._by_region()
        baseline = build_bracket_entries(by_region, SLOTS_5A_7A_2025)
        result = build_bracket_entries(by_region, SLOTS_5A_7A_2025, wins_by_slot={"R1S1": 1})
        r1s1_base = next(e for e in baseline if e.region == 1 and e.seed == 1)
        r1s1 = next(e for e in result if e.region == 1 and e.seed == 1)
        assert r1s1.quarterfinals > r1s1_base.quarterfinals

    def test_slot_odds_for_region_skips_school_with_no_seed_above_half(self):
        """A school with no p{s} > 0.5 (undecided seed) is skipped rather than
        assigned to a slot (line 2001->1999 false branch), while other schools
        in the same region with a clinched seed are still included.
        """
        source = {
            "Undecided": _odds("Undecided", p1=0.4, p2=0.3, p3=0.3, p_playoffs=1.0),
            "Clinched": _odds("Clinched", p1=1.0, p_playoffs=1.0, clinched=True),
        }
        slot_odds = _slot_odds_for_region(1, source)
        assert "R1S1" in slot_odds
        assert len(slot_odds) == 1  # only the clinched school got a slot

    def test_win_prob_fn_weighted_populates_weighted_hosting_fields(self):
        """win_prob_fn_weighted turns on the entire weighted-hosting computation path
        in build_bracket_entries (line 2266) and _p_host_odds_from_overall's have_w
        branches (lines 2051, 2053) — otherwise every *_weighted hosting field is None.
        """
        by_region = self._by_region()
        result = build_bracket_entries(
            by_region, SLOTS_5A_7A_2025, season=2025, clazz=5,
            win_prob_fn_weighted=equal_matchup_prob,
        )
        seed1 = next(e for e in result if e.region == 1 and e.seed == 1)
        assert seed1.hosting.quarterfinals.p_host_overall_weighted is not None
        assert seed1.hosting.semifinals.p_host_overall_weighted is not None
        assert seed1.quarterfinals_weighted is not None

    def test_win_prob_fn_weighted_zero_advancement_gives_zero_overall_weighted(self):
        """An eliminated team still holding its seed slot has zero advancement in
        both the unweighted and weighted odds, hitting the have_w-but-not-adv_w_pos
        branch (line 2053): p_host_overall_weighted=0.0 rather than a positive value.
        Requires all_region_odds so the school-based (not synthetic) slot path is used.
        """
        by_region = self._by_region()
        by_region[1]["T1S4"] = _odds("T1S4", p4=1.0, p_playoffs=0.0, eliminated=True)
        result = build_bracket_entries(
            by_region, SLOTS_5A_7A_2025, season=2025, clazz=5,
            all_region_odds=by_region, win_prob_fn_weighted=equal_matchup_prob,
        )
        seed4 = next(e for e in result if e.region == 1 and e.seed == 4)
        assert seed4.hosting.quarterfinals.p_host_overall_weighted == pytest.approx(0.0)

    def test_wins_by_team_with_all_region_odds_boosts_slot(self):
        """wins_by_team (school-keyed) combined with all_region_odds resolves the
        school->slot mapping internally (lines 2239-2245) and feeds the confirmed
        win into advancement odds the same way wins_by_slot does directly.
        """
        by_region = self._by_region()
        baseline = build_bracket_entries(by_region, SLOTS_5A_7A_2025)
        result = build_bracket_entries(
            by_region, SLOTS_5A_7A_2025,
            wins_by_team={"T1S1": 1}, all_region_odds=by_region,
        )
        r1s1_base = next(e for e in baseline if e.region == 1 and e.seed == 1)
        r1s1 = next(e for e in result if e.region == 1 and e.seed == 1)
        assert r1s1.quarterfinals > r1s1_base.quarterfinals

    def test_eliminated_hosting_maps_to_slot_via_school_to_slot(self):
        """eliminated_hosting (school-keyed) is mapped to a slot-ID key via the
        school_to_slot dict, which is only populated when wins_by_team and
        all_region_odds are both supplied (lines 2253-2258). The resulting
        eliminated_by_slot entry drives _hosting_for_slot's deterministic
        override (lines 2084-2085) instead of computed hosting odds.
        """
        by_region = self._by_region()
        result = build_bracket_entries(
            by_region, SLOTS_5A_7A_2025, season=2025, clazz=5,
            wins_by_team={"T1S1": 1}, all_region_odds=by_region,
            eliminated_hosting={"T1S1": (0.0, None, 0.0, 0.0)},
        )
        r1s1 = next(e for e in result if e.region == 1 and e.seed == 1)
        assert r1s1.hosting.first_round.p_host_given_reach == pytest.approx(0.0)
        assert r1s1.hosting.quarterfinals.p_host_given_reach == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# TestEliminatedTeamHosting
# ---------------------------------------------------------------------------


class TestEliminatedTeamHosting:
    """eliminated_team_hosting produces a deterministic (r1, r2, qf, sf) tuple for
    a team eliminated in round rounds_played, resolving each round's opponent via
    _find_bracket_survivor as rounds_played increases.
    """

    def test_resolves_qf_opponent_5a7a(self):
        """5A-7A: a team eliminated after 2 rounds (rounds_played=2) resolves its QF
        opponent via _find_bracket_survivor (lines 1165-1204's QF branch), producing
        a non-None qf value while sf stays None (round not yet played).
        """
        result = eliminated_team_hosting(
            region=1, seed=1, rounds_played=2, slots=SLOTS_5A_7A_2025,
            seed_to_school={(2, 2): "Opp"}, wins_by_team={"Opp": 1},
            season=2025, clazz=5,
        )
        r1, r2, qf, sf = result
        assert r1 == pytest.approx(1.0)  # R1s1 hosts R1
        assert r2 is None  # 5A-7A has no second round
        assert qf is not None
        assert sf is None  # rounds_played=2 < rounds_for_sf=3

    def test_resolves_r2_and_sf_1a4a(self):
        """1A-4A: a team eliminated after 4 rounds resolves R2 (line 1165-1173) and
        SF (near line 1199-1204) opponents via _find_bracket_survivor.
        """
        # North half slot layout (indices 0-7): [0] (1,1)v(2,4) [1] (3,2)v(4,3)
        # [2] (2,1)v(1,4) [3] (4,2)v(3,3) [4] (3,1)v(4,4) [5] (1,2)v(2,3)
        # [6] (4,1)v(3,4) [7] (2,2)v(1,3). R1s1 (idx 0): R2 opp in [1], QF opp in
        # [2,3], SF opp in [4-7].
        result = eliminated_team_hosting(
            region=1, seed=1, rounds_played=4, slots=SLOTS_1A_4A_2025,
            seed_to_school={(3, 2): "R2Opp", (2, 1): "QFOpp", (4, 1): "SFOpp"},
            wins_by_team={"R2Opp": 1, "QFOpp": 2, "SFOpp": 3},
            season=2025, clazz=1,
        )
        r1, r2, qf, sf = result
        assert r1 == pytest.approx(1.0)
        assert r2 is not None
        assert qf is not None
        assert sf is not None

    def test_returns_partial_when_survivor_not_found(self):
        """When no confirmed-win candidate exists in the QF opponent slots,
        _find_bracket_survivor returns None and the tuple stops at qf=None."""
        result = eliminated_team_hosting(
            region=1, seed=1, rounds_played=2, slots=SLOTS_5A_7A_2025,
            seed_to_school={}, wins_by_team={},
            season=2025, clazz=5,
        )
        assert result == (1.0, None, None, None)


# ---------------------------------------------------------------------------
# TestResolveParticipantRef
# ---------------------------------------------------------------------------


class TestResolveParticipantRef:
    """_resolve_ref_to_school and _resolve_ref_to_slot_id resolution helpers."""

    _SEED_TO_SCHOOL: dict[tuple[int, int], str] = {
        (1, 1): "AlphaS1",
        (1, 2): "AlphaS2",
        (2, 1): "BetaS1",
    }

    def test_school_ref_returns_name_directly(self):
        """A school-name ref returns the name without consulting seed_to_school."""
        ref = ParticipantRef(school="AlphaS1")
        assert _resolve_ref_to_school(ref, self._SEED_TO_SCHOOL) == "AlphaS1"

    def test_slot_ref_resolved_when_clinched(self):
        """A slot ref resolves to the school that clinched that seed."""
        ref = ParticipantRef(region=1, seed=1)
        assert _resolve_ref_to_school(ref, self._SEED_TO_SCHOOL) == "AlphaS1"

    def test_slot_ref_returns_none_when_not_clinched(self):
        """A slot ref for an unclinched (unknown) slot returns None."""
        ref = ParticipantRef(region=3, seed=1)
        assert _resolve_ref_to_school(ref, self._SEED_TO_SCHOOL) is None

    def test_resolve_slot_id_correct_format(self):
        """_resolve_ref_to_slot_id returns 'R{region}S{seed}' for slot refs."""
        ref = ParticipantRef(region=2, seed=3)
        assert _resolve_ref_to_slot_id(ref) == "R2S3"

    def test_resolve_slot_id_returns_none_for_school_ref(self):
        """_resolve_ref_to_slot_id returns None for school-name refs."""
        ref = ParticipantRef(school="AlphaS1")
        assert _resolve_ref_to_slot_id(ref) is None


# ---------------------------------------------------------------------------
# TestParticipantRefValidation
# ---------------------------------------------------------------------------


class TestParticipantRefValidation:
    """ParticipantRef validates and coerces its inputs."""

    def test_plain_string_coerces_to_school(self):
        """A plain string is coerced to a school-name ref."""
        ref = ParticipantRef.model_validate("School Name")
        assert ref.school == "School Name"
        assert ref.region is None
        assert ref.seed is None

    def test_school_dict_form(self):
        """Explicit school field works."""
        ref = ParticipantRef(school="Alpha")
        assert ref.school == "Alpha"

    def test_slot_dict_form(self):
        """(region, seed) slot form works."""
        ref = ParticipantRef(region=1, seed=2)
        assert ref.region == 1
        assert ref.seed == 2
        assert ref.school is None

    def test_both_school_and_slot_raises(self):
        """Providing school + region + seed raises ValueError."""
        with pytest.raises(ValueError, match="not both"):
            ParticipantRef(school="Alpha", region=1, seed=2)

    def test_region_without_seed_raises(self):
        """Providing region without seed raises ValueError."""
        with pytest.raises(ValueError, match="together"):
            ParticipantRef(region=1)

    def test_seed_without_region_raises(self):
        """Providing seed without region raises ValueError."""
        with pytest.raises(ValueError, match="together"):
            ParticipantRef(seed=2)

    def test_neither_school_nor_slot_raises(self):
        """Providing neither school nor slot raises ValueError."""
        with pytest.raises(ValueError, match="Provide either"):
            ParticipantRef()

    def test_bracket_game_result_accepts_string_winner(self):
        """BracketGameResultRequest coerces string winner/loser to ParticipantRef."""
        r = BracketGameResultRequest(winner="Team A", loser="Team B")  # type: ignore[arg-type]
        assert r.winner.school == "Team A"
        assert r.loser is not None
        assert r.loser.school == "Team B"

    def test_bracket_game_result_accepts_slot_ref(self):
        """BracketGameResultRequest accepts slot-ref dicts."""
        r = BracketGameResultRequest(
            winner={"region": 1, "seed": 1},  # type: ignore[arg-type]
            loser={"region": 2, "seed": 4},  # type: ignore[arg-type]
        )
        assert r.winner.region == 1
        assert r.winner.seed == 1
        assert r.loser is not None
        assert r.loser.region == 2


# ---------------------------------------------------------------------------
# TestBuildBracketLayout
# ---------------------------------------------------------------------------


class TestBuildBracketLayout:
    """build_bracket_layout produces the correct tree structure for both bracket formats."""

    def test_1a_4a_produces_n_and_s_halves(self):
        """1A-4A format produces exactly the N and S halves."""
        layout = build_bracket_layout(SLOTS_1A_4A_2025)
        assert set(layout.halves.keys()) == {"N", "S"}

    def test_1a_4a_north_has_four_rounds(self):
        """1A-4A north half has 4 rounds with 8/4/2/1 games."""
        layout = build_bracket_layout(SLOTS_1A_4A_2025)
        rounds = layout.halves["N"]
        assert len(rounds) == 4
        assert [len(r) for r in rounds] == [8, 4, 2, 1]

    def test_1a_4a_south_has_four_rounds(self):
        """1A-4A south half has 4 rounds with 8/4/2/1 games."""
        layout = build_bracket_layout(SLOTS_1A_4A_2025)
        rounds = layout.halves["S"]
        assert len(rounds) == 4
        assert [len(r) for r in rounds] == [8, 4, 2, 1]

    def test_5a_7a_north_has_three_rounds(self):
        """5A-7A north half has 3 rounds with 4/2/1 games."""
        layout = build_bracket_layout(SLOTS_5A_7A_2025)
        rounds = layout.halves["N"]
        assert len(rounds) == 3
        assert [len(r) for r in rounds] == [4, 2, 1]

    def test_r1_games_have_slot_and_participants_not_feeds_from(self):
        """Round-1 games carry a slot and both participants, and no feeds_from."""
        layout = build_bracket_layout(SLOTS_1A_4A_2025)
        for game in layout.halves["N"][0]:
            assert game.slot is not None
            assert game.participant_a is not None
            assert game.participant_b is not None
            assert game.feeds_from is None

    def test_later_round_games_have_feeds_from_not_slot(self):
        """Rounds after round 1 carry feeds_from and have no slot."""
        layout = build_bracket_layout(SLOTS_1A_4A_2025)
        for round_ in layout.halves["N"][1:]:
            for game in round_:
                assert game.feeds_from is not None
                assert game.slot is None

    def test_r2_first_game_feeds_from_r1_0_and_1(self):
        """First round-2 game feeds from round-1 games 0 and 1."""
        layout = build_bracket_layout(SLOTS_1A_4A_2025)
        assert layout.halves["N"][1][0].feeds_from == [0, 1]

    def test_r2_second_game_feeds_from_r1_2_and_3(self):
        """Second round-2 game feeds from round-1 games 2 and 3."""
        layout = build_bracket_layout(SLOTS_1A_4A_2025)
        assert layout.halves["N"][1][1].feeds_from == [2, 3]

    def test_sf_is_single_game_feeding_from_two_qf_games(self):
        """The semifinal round is a single game fed by both quarterfinal games."""
        layout = build_bracket_layout(SLOTS_1A_4A_2025)
        sf_round = layout.halves["N"][-1]
        assert len(sf_round) == 1
        assert sf_round[0].feeds_from == [0, 1]

    def test_championship_feeds_from_halves(self):
        """The championship game feeds from the N and S halves."""
        layout = build_bracket_layout(SLOTS_1A_4A_2025)
        assert layout.championship.feeds_from_halves == ["N", "S"]

    def test_r1_slot_numbers_match_format_input(self):
        """Round-1 slot numbers match the slots given in the input format."""
        layout = build_bracket_layout(SLOTS_1A_4A_2025)
        north_r1_slots = [g.slot for g in layout.halves["N"][0]]
        expected = sorted(s.slot for s in SLOTS_1A_4A_2025 if s.north_south == "N")
        assert north_r1_slots == expected


# ---------------------------------------------------------------------------
# TestEliminatedTeamsInBracket
# ---------------------------------------------------------------------------


class TestEliminatedTeamsInBracket:
    """After playoff R1, eliminated teams appear with school name and zero advancement odds."""

    # school names are "R{region}S{seed}" for easy assertion
    _S2S: dict[str, tuple[int, int]] = {f"R{r}S{s}": (r, s) for r in (1, 2, 3, 4) for s in (1, 2, 3, 4)}

    def _by_region_post_r1(self) -> dict:
        """by_region after R1: seeds 1+2 survived; seeds 3+4 eliminated (all-zero odds)."""
        result: dict = {}
        for r in (1, 2, 3, 4):
            result[r] = {
                f"R{r}S1": _odds(f"R{r}S1", p1=1.0, p_playoffs=1.0, clinched=True),
                f"R{r}S2": _odds(f"R{r}S2", p2=1.0, p_playoffs=1.0, clinched=True),
                # Pipeline zeros all odds for losers
                f"R{r}S3": _odds(f"R{r}S3", clinched=True, eliminated=True),
                f"R{r}S4": _odds(f"R{r}S4", clinched=True, eliminated=True),
            }
        return result

    def _state_post_r1(self):
        """PlayoffBracketState with seeds 3+4 eliminated in all regions."""
        db_losers = {f"R{r}S{s}" for r in (1, 2, 3, 4) for s in (3, 4)}
        return build_playoff_bracket_state(self._S2S, {}, db_losers, [], {}, SLOTS_5A_7A_2025, 2025, 5)

    def _entries(self, state):
        """Build bracket entries for ``state`` using the post-R1 by-region odds fixture."""
        return build_bracket_entries(
            self._by_region_post_r1(),
            SLOTS_5A_7A_2025,
            all_region_odds=state.all_region_odds,
            wins_by_team=state.wins_by_team,
            cross_region_wins=state.cross_region_wins,
            eliminated_hosting=state.eliminated_hosting_map,
            school_to_seed=state.school_to_seed,
        )

    def test_all_16_entries_returned_post_r1(self):
        """All 16 slots are returned (not just 8 survivors)."""
        state = self._state_post_r1()
        assert len(self._entries(state)) == 16

    def test_eliminated_teams_have_school_populated(self):
        """Eliminated teams show a school name, not null."""
        state = self._state_post_r1()
        eliminated = [e for e in self._entries(state) if e.seed in (3, 4)]
        assert len(eliminated) == 8
        assert all(e.school is not None for e in eliminated)

    def test_eliminated_teams_school_name_matches_seed_assignment(self):
        """School name for an eliminated slot matches the expected team identifier."""
        state = self._state_post_r1()
        entries = self._entries(state)
        r1s3 = next(e for e in entries if e.region == 1 and e.seed == 3)
        assert r1s3.school == "R1S3"
        r2s4 = next(e for e in entries if e.region == 2 and e.seed == 4)
        assert r2s4.school == "R2S4"

    def test_eliminated_teams_have_zero_advancement_odds(self):
        """R1 losers have 0.0 for all remaining rounds."""
        state = self._state_post_r1()
        eliminated = [e for e in self._entries(state) if e.seed in (3, 4)]
        for e in eliminated:
            assert e.second_round == pytest.approx(0.0)
            assert e.quarterfinals == pytest.approx(0.0)
            assert e.semifinals == pytest.approx(0.0)
            assert e.finals == pytest.approx(0.0)
            assert e.champion == pytest.approx(0.0)

    def test_survivors_have_nonzero_quarterfinal_odds(self):
        """R1 winners have nonzero QF odds (5A-7A QF is the first cross-region round)."""
        state = self._state_post_r1()
        survivors = [e for e in self._entries(state) if e.seed in (1, 2)]
        assert len(survivors) == 8
        assert all(e.quarterfinals > 0 for e in survivors)

    def test_entries_still_sorted_by_region_then_seed(self):
        """All 16 entries are still ordered by (region, seed)."""
        state = self._state_post_r1()
        keys = [(e.region, e.seed) for e in self._entries(state)]
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# TestBuildEnrichedBracketLayout
# ---------------------------------------------------------------------------


class TestBuildEnrichedBracketLayout:
    """build_enriched_bracket_layout populates participants and results on each BracketGame node."""

    # Slot 1 in SLOTS_5A_7A_2025: R1S1 (home) vs R2S4 (away), North half
    _S2S: dict[tuple[int, int], str] = {(r, s): f"R{r}S{s}" for r in (1, 2, 3, 4) for s in (1, 2, 3, 4)}

    def _layout(self):
        """Base (unenriched) bracket layout for the 5A-7A format used by these tests."""
        return build_bracket_layout(SLOTS_5A_7A_2025)

    def test_r1_participants_populated_when_seed_to_school_provided(self):
        """R1 game nodes have participant_a and participant_b with school names."""
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, [], [])
        game = layout.halves["N"][0][0]  # slot 1: R1S1 vs R2S4
        assert game.participant_a is not None
        assert game.participant_b is not None
        assert game.participant_a.school == "R1S1"
        assert game.participant_b.school == "R2S4"

    def test_r1_participants_have_correct_region_and_seed(self):
        """Participant region and seed match the format slot."""
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, [], [])
        game = layout.halves["N"][0][0]  # R1S1 (home) vs R2S4 (away)
        assert game.participant_a is not None and game.participant_b is not None
        assert game.participant_a.region == 1
        assert game.participant_a.seed == 1
        assert game.participant_b.region == 2
        assert game.participant_b.seed == 4

    def test_r1_school_null_when_no_seed_to_school(self):
        """School is None for all participants when seed_to_school is not provided."""
        layout = build_enriched_bracket_layout(self._layout(), None, [], [])
        for game in layout.halves["N"][0]:
            assert game.participant_a is not None and game.participant_b is not None
            assert game.participant_a.school is None
            assert game.participant_b.school is None

    def test_r1_result_populated_from_confirmed(self):
        """A confirmed result for a matching pair appears on the R1 game node."""
        confirmed = [("R1S1", "R2S4", 28, 14)]
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, confirmed, [])
        game = layout.halves["N"][0][0]  # R1S1 vs R2S4
        assert game.result is not None
        assert game.result.loser is not None
        assert game.result.winner.school == "R1S1"
        assert game.result.loser.school == "R2S4"
        assert game.result.winner_score == 28
        assert game.result.loser_score == 14

    def test_r1_result_simulated_false_for_confirmed(self):
        """Confirmed results have simulated=False."""
        confirmed = [("R1S1", "R2S4", 28, 14)]
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, confirmed, [])
        game = layout.halves["N"][0][0]
        assert game.result is not None
        assert game.result.simulated is False

    def test_no_result_when_game_not_yet_played(self):
        """Game nodes with no matching result have result=None."""
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, [], [])
        assert layout.halves["N"][0][0].result is None

    def test_simulated_result_marked_simulated_true(self):
        """Results from the simulated list have simulated=True."""
        simulated = [("R1S1", "R2S4", None, None, None)]
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, [], simulated)
        assert layout.halves["N"][0][0].result is not None
        assert layout.halves["N"][0][0].result.simulated is True

    def test_real_result_not_overridden_by_simulated(self):
        """Confirmed DB result is not replaced by a simulated result for the same pair."""
        confirmed = [("R1S1", "R2S4", 28, 14)]
        simulated = [("R2S4", "R1S1", 21, 7, None)]  # reversed — simulated says opposite winner
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, confirmed, simulated)
        result = layout.halves["N"][0][0].result
        assert result is not None
        assert result.winner.school == "R1S1"  # DB result preserved
        assert result.simulated is False

    def test_qf_participants_populated_from_r1_winners(self):
        """QF game participants are the winners of the feeding R1 games."""
        # In 5A-7A North, R1 has 4 games; QF (round index 1) has 2 games.
        # Slots N[0][0] (R1S1 vs R2S4) and N[0][1] (R2S2 vs R1S3) feed into N[1][0].
        confirmed = [
            ("R1S1", "R2S4", 28, 14),  # N[0][0] winner: R1S1
            ("R2S2", "R1S3", 21, 7),  # N[0][1] winner: R2S2
        ]
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, confirmed, [])
        qf_game = layout.halves["N"][1][0]
        assert qf_game.participant_a is not None
        assert qf_game.participant_b is not None
        schools = {qf_game.participant_a.school, qf_game.participant_b.school}
        assert schools == {"R1S1", "R2S2"}

    def test_championship_participants_from_sf_winners(self):
        """Championship participants are the Semifinal winners of each half."""
        # Supply results for all rounds in the North half to propagate a winner.
        # North slots (from SLOTS_5A_7A_2025):
        #   R1: (R1S1 vs R2S4), (R2S2 vs R1S3), (R2S1 vs R1S4), (R1S2 vs R2S3)
        #   QF: R1S1 vs R2S2; R2S1 vs R1S2
        #   SF: R1S1 vs R2S1
        confirmed = [
            ("R1S1", "R2S4", 28, 14),
            ("R2S2", "R1S3", 21, 7),
            ("R2S1", "R1S4", 35, 0),
            ("R1S2", "R2S3", 14, 10),
            ("R1S1", "R2S2", 20, 17),  # QF
            ("R2S1", "R1S2", 30, 14),  # QF
            ("R1S1", "R2S1", 24, 21),  # SF — N half winner
            # South half — make R3S1 the SF winner
            ("R3S1", "R4S4", 28, 0),
            ("R4S2", "R3S3", 21, 7),
            ("R4S1", "R3S4", 35, 0),
            ("R3S2", "R4S3", 14, 10),
            ("R3S1", "R4S2", 20, 17),
            ("R4S1", "R3S2", 30, 14),
            ("R3S1", "R4S1", 24, 21),  # SF — S half winner
        ]
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, confirmed, [])
        champ = layout.championship
        assert champ.north_participant is not None
        assert champ.south_participant is not None
        assert champ.north_participant.school == "R1S1"
        assert champ.south_participant.school == "R3S1"

    def test_championship_result_populated(self):
        """Championship result is set when both SF winners have played each other."""
        confirmed = [
            ("R1S1", "R2S4", 28, 14),
            ("R2S2", "R1S3", 21, 7),
            ("R2S1", "R1S4", 35, 0),
            ("R1S2", "R2S3", 14, 10),
            ("R1S1", "R2S2", 20, 17),
            ("R2S1", "R1S2", 30, 14),
            ("R1S1", "R2S1", 24, 21),
            ("R3S1", "R4S4", 28, 0),
            ("R4S2", "R3S3", 21, 7),
            ("R4S1", "R3S4", 35, 0),
            ("R3S2", "R4S3", 14, 10),
            ("R3S1", "R4S2", 20, 17),
            ("R4S1", "R3S2", 30, 14),
            ("R3S1", "R4S1", 24, 21),
            ("R1S1", "R3S1", 31, 28),  # championship
        ]
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, confirmed, [])
        assert layout.championship.result is not None
        assert layout.championship.result.winner.school == "R1S1"

    def test_round_field_set_on_all_games(self):
        """Every game node has round set; R1=first_round, last round=semifinals."""
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, [], [])
        # 5A-7A has 3 rounds per half: first_round, quarterfinals, semifinals
        for half in ("N", "S"):
            rounds = layout.halves[half]
            assert rounds[0][0].round == "first_round"
            assert rounds[1][0].round == "quarterfinals"
            assert rounds[2][0].round == "semifinals"

    def test_home_team_set_on_r1_nodes_without_hosting_lookup(self):
        """R1 nodes always have home_team set (= participant_a) even with no p_host_given_reach_by_team."""
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, [], [])
        for game in layout.halves["N"][0]:
            assert game.home_team is not None
            assert game.participant_a is not None
            assert game.home_team.region == game.participant_a.region
            assert game.home_team.seed == game.participant_a.seed

    def test_home_team_set_when_hosting_deterministic(self):
        """home_team is a BracketParticipant with the hosting school when p_host_given_reach = 1.0."""
        hosting = {
            "R1S1": {"first_round": 1.0, "quarterfinals": 1.0, "semifinals": None, "second_round": None},
            "R2S4": {"first_round": 0.0, "quarterfinals": None, "semifinals": None, "second_round": None},
        }
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, [], [], p_host_given_reach_by_team=hosting)
        game = layout.halves["N"][0][0]  # R1S1 vs R2S4 — R1, so home_team = participant_a always
        assert game.home_team is not None
        assert game.home_team.school == "R1S1"

    def test_home_team_set_when_only_one_participant_known(self):
        """home_team is set when participant_a hosts deterministically even with no opponent."""
        hosting = {
            "R1S1": {"first_round": 1.0, "quarterfinals": 1.0, "semifinals": None, "second_round": None},
        }
        confirmed = [("R1S1", "R2S4", 28, 14)]  # only N[0][0] resolved → N[1][0].participant_b = None
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, confirmed, [], p_host_given_reach_by_team=hosting)
        qf_game = layout.halves["N"][1][0]
        assert qf_game.participant_b is None
        assert qf_game.home_team is not None
        assert qf_game.home_team.school == "R1S1"

    def test_home_team_falls_back_to_participant_b_hosting(self):
        """When participant_a's given_reach doesn't clear the 0.99 threshold (or is
        absent) but participant_b's does, home_team falls through to participant_b
        (lines 1812->1814 false arm, then 1815-1817).

        N[1][0] (quarterfinals) feeds from N[0][0] (R1S1 vs R2S4) and N[0][1]
        (R2S2 vs R1S3). Confirming both R1 games resolves both QF participants;
        the hosting dict only marks R2S2 (participant_b) as a deterministic host.
        """
        hosting = {"R2S2": {"first_round": 1.0, "quarterfinals": 1.0, "semifinals": None, "second_round": None}}
        confirmed = [("R1S1", "R2S4", 28, 14), ("R2S2", "R1S3", 21, 10)]
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, confirmed, [], p_host_given_reach_by_team=hosting)
        qf_game = layout.halves["N"][1][0]
        assert qf_game.participant_a is not None and qf_game.participant_a.school == "R1S1"
        assert qf_game.participant_b is not None and qf_game.participant_b.school == "R2S2"
        assert qf_game.home_team is not None
        assert qf_game.home_team.school == "R2S2"

    def test_home_team_null_on_r2_without_hosting_lookup(self):
        """R2+ nodes have home_team=None when no p_host_given_reach_by_team is provided."""
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, [], [])
        for round_games in layout.halves["N"][1:]:  # skip R1
            for game in round_games:
                assert game.home_team is None

    # ------------------------------------------------------------------
    # Winner-only (loser-less) simulated results
    # ------------------------------------------------------------------

    def test_winner_only_result_propagates_to_next_round(self):
        """A simulated result with None loser advances the winner to the next round."""
        simulated = [("R1S1", None, 12, 0, "first_round")]
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, [], simulated)
        qf_game = layout.halves["N"][1][0]
        winner_schools = {p.school for p in (qf_game.participant_a, qf_game.participant_b) if p}
        assert "R1S1" in winner_schools

    def test_winner_only_result_has_null_loser_on_game_node(self):
        """A winner-only game node has result.loser = None."""
        simulated = [("R1S1", None, 12, 0, "first_round")]
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, [], simulated)
        r1_game = layout.halves["N"][0][0]  # R1S1 vs R2S4
        assert r1_game.result is not None
        assert r1_game.result.winner.school == "R1S1"
        assert r1_game.result.loser is None

    def test_winner_only_result_marked_simulated(self):
        """Winner-only game results have simulated=True."""
        simulated = [("R1S1", None, 12, 0, "first_round")]
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, [], simulated)
        game = layout.halves["N"][0][0]
        assert game.result is not None
        assert game.result.simulated is True

    def test_confirmed_result_takes_priority_over_winner_only(self):
        """A confirmed DB result is not replaced by a winner-only simulated entry."""
        confirmed = [("R2S4", "R1S1", 21, 14)]  # upset — R2S4 wins
        simulated = [("R1S1", None, 12, 0, "first_round")]
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, confirmed, simulated)
        r1_game = layout.halves["N"][0][0]
        assert r1_game.result is not None
        assert r1_game.result.winner.school == "R2S4"
        assert r1_game.result.simulated is False

    def test_winner_only_result_does_not_bleed_to_later_rounds(self):
        """A winner-only R1 result does not show as QF/SF winner — only applies to first_round."""
        simulated = [("R1S1", None, 12, 0, "first_round")]
        layout = build_enriched_bracket_layout(self._layout(), self._S2S, [], simulated)
        # QF game should have R1S1 as a participant but no result (opponent unknown)
        qf_game = layout.halves["N"][1][0]
        assert qf_game.result is None


# ---------------------------------------------------------------------------
# TestCollectPossibleOpponents
# ---------------------------------------------------------------------------


class TestCollectPossibleOpponents:
    """_collect_possible_opponents returns R1 seeds on the opponent's bracket branch."""

    def _layout(self):
        """Base bracket layout for the 5A-7A format used by these tests."""
        return build_bracket_layout(SLOTS_5A_7A_2025)

    def test_qf_opponents_of_r1s1(self):
        """QF opponent branch for R1S1 (slot 1, N half) is R1 game at index 1."""
        # SLOTS_5A_7A_2025 North: game0=(R1S1 vs R2S4), game1=(R2S2 vs R1S3)
        # QF game0 feeds_from=[0, 1] — R1S1 comes from game0, opponent branch is game1
        opponents = _collect_possible_opponents(self._layout(), 1, 1, "quarterfinals")
        assert opponents == {(2, 2), (1, 3)}

    def test_sf_opponents_of_r1s1(self):
        """SF opponent branch for R1S1 covers all 4 seeds from the other QF sub-tree."""
        # North SF: QF0 winner vs QF1 winner; QF0 feeds game0+game1, QF1 feeds game2+game3
        opponents = _collect_possible_opponents(self._layout(), 1, 1, "semifinals")
        assert opponents == {(2, 1), (1, 4), (1, 2), (2, 3)}

    def test_unknown_winner_returns_empty(self):
        """Returns empty set when (region, seed) not found in any R1 slot."""
        opponents = _collect_possible_opponents(self._layout(), 9, 9, "quarterfinals")
        assert opponents == set()

    def test_invalid_round_returns_empty(self):
        """Returns empty set for an unrecognized round name."""
        opponents = _collect_possible_opponents(self._layout(), 1, 1, "championship")
        assert opponents == set()

    def test_first_round_returns_empty(self):
        """Returns empty set for first_round (not a valid loser-less round)."""
        opponents = _collect_possible_opponents(self._layout(), 1, 1, "first_round")
        assert opponents == set()


# ---------------------------------------------------------------------------
# TestBuildPlayoffBracketStateLoserless
# ---------------------------------------------------------------------------


class TestBuildPlayoffBracketStateLoserless:
    """build_playoff_bracket_state handles loser-less results via round-based elimination."""

    def _school_to_seed(self):
        """8-team school_to_seed fixture matching the North half of SLOTS_5A_7A_2025."""
        # 8 teams (2 regions × 4 seeds) matching North half of SLOTS_5A_7A_2025
        return {
            "R1S1": (1, 1),
            "R1S2": (1, 2),
            "R1S3": (1, 3),
            "R1S4": (1, 4),
            "R2S1": (2, 1),
            "R2S2": (2, 2),
            "R2S3": (2, 3),
            "R2S4": (2, 4),
        }

    def _loserless_result(self, winner: str, round_: str) -> BracketGameResultRequest:
        """Build a submitted result naming only the winner and target round, no loser."""
        return BracketGameResultRequest(winner=ParticipantRef(school=winner), round=round_)

    def _state(self, submitted):
        """Build playoff bracket state from ``submitted`` results over the 5A-7A layout."""
        layout = build_bracket_layout(SLOTS_5A_7A_2025)
        return build_playoff_bracket_state(
            school_to_seed=self._school_to_seed(),
            db_wins={},
            db_losers=set(),
            submitted_results=submitted,
            elo_ratings={},
            slots=SLOTS_5A_7A_2025,
            season=2025,
            clazz=5,
            layout=layout,
        )

    def test_winner_gets_win_credit(self):
        """Winner's win count increments even without a named loser."""
        state = self._state([self._loserless_result("R1S1", "quarterfinals")])
        assert state.wins_by_team.get("R1S1", 0) == 1

    def test_possible_opponents_marked_ceiling(self):
        """All seeds on the opponent QF branch are tracked in round_ceiling (not eliminated)."""
        state = self._state([self._loserless_result("R1S1", "quarterfinals")])
        # QF opponents of R1S1: R2S2 and R1S3 (game1 in North R1)
        assert state.round_ceiling.get((2, 2)) == "quarterfinals"
        assert state.round_ceiling.get((1, 3)) == "quarterfinals"
        # They are NOT in losers_known — still have playoff odds
        assert state.all_region_odds[2]["R2S2"].eliminated is False
        assert state.all_region_odds[1]["R1S3"].eliminated is False

    def test_winner_not_eliminated(self):
        """The winner itself is not marked eliminated."""
        state = self._state([self._loserless_result("R1S1", "quarterfinals")])
        assert state.all_region_odds[1]["R1S1"].eliminated is False

    def test_non_opponent_seeds_not_eliminated(self):
        """Seeds outside the opponent branch are unaffected."""
        state = self._state([self._loserless_result("R1S1", "quarterfinals")])
        # R2S1 and R1S4 are in a different QF sub-tree — they should still be alive
        assert state.all_region_odds[2]["R2S1"].eliminated is False
        assert state.all_region_odds[1]["R1S4"].eliminated is False

    def test_second_loserless_result_keeps_more_restrictive_ceiling(self):
        """A second loser-less result whose opponent pool overlaps with the first's
        does not overwrite an already-more-restrictive (earlier-round) ceiling
        (lines 1358-1371's "keep existing" branch).

        North half slots: [0] R1S1/R2S4  [1] R2S2/R1S3  [2] R2S1/R1S4  [3] R1S2/R2S3.
        R1S1's semifinals opponent pool is the *other* quarter: {R2S1, R1S4, R1S2,
        R2S3} (slots 2-3). R2S1's quarterfinals opponent pool (adjacent slot 3) is
        {R1S2, R2S3} — a subset of R1S1's semifinals pool. Submitting R2S1's
        quarterfinals result first sets R1S2/R2S3 to "quarterfinals"; R1S1's
        semifinals result (proposing the later round "semifinals") must not
        overwrite them.
        """
        state = self._state([
            self._loserless_result("R2S1", "quarterfinals"),
            self._loserless_result("R1S1", "semifinals"),
        ])
        assert state.round_ceiling.get((1, 2)) == "quarterfinals"
        assert state.round_ceiling.get((2, 3)) == "quarterfinals"

    def test_second_loserless_result_upgrades_less_restrictive_ceiling(self):
        """Submitting the wider (R1S1 semifinals) result first, then the narrower
        (R2S1 quarterfinals) one, upgrades the overlapping seeds' ceiling to the
        more restrictive round (the "new_idx < existing_idx" True arm of lines
        1360-1371). See test above for the opponent-pool layout.
        """
        state = self._state([
            self._loserless_result("R1S1", "semifinals"),
            self._loserless_result("R2S1", "quarterfinals"),
        ])
        assert state.round_ceiling.get((1, 2)) == "quarterfinals"
        assert state.round_ceiling.get((2, 3)) == "quarterfinals"


# ---------------------------------------------------------------------------
# TestApplyRoundCeilings
# ---------------------------------------------------------------------------


class TestApplyRoundCeilings:
    """_apply_round_ceilings zeros advancement/hosting odds beyond each team's ceiling."""

    def _entry(
        self,
        region: int,
        seed: int,
        *,
        sr: float = 0.8,
        qf: float = 0.6,
        sf: float = 0.4,
        fn: float = 0.2,
        ch: float = 0.1,
    ) -> TeamBracketEntry:
        """Build a TeamBracketEntry with the given odds and a fixed hosting-odds fixture."""
        hosting = BracketSlotHosting(
            first_round=RoundHostingOdds(p_host_given_reach=1.0, p_host_overall=0.9),
            second_round=RoundHostingOdds(p_host_given_reach=0.7, p_host_overall=0.5),
            quarterfinals=RoundHostingOdds(p_host_given_reach=0.5, p_host_overall=0.3),
            semifinals=RoundHostingOdds(p_host_given_reach=0.3, p_host_overall=0.2),
        )
        return TeamBracketEntry(
            region=region,
            seed=seed,
            school=f"R{region}S{seed}",
            second_round=sr,
            quarterfinals=qf,
            semifinals=sf,
            finals=fn,
            champion=ch,
            second_round_weighted=sr,
            quarterfinals_weighted=qf,
            semifinals_weighted=sf,
            finals_weighted=fn,
            champion_weighted=ch,
            hosting=hosting,
        )

    def test_no_ceiling_entries_pass_through_unchanged(self):
        """Entries not in round_ceiling are returned unmodified."""
        entry = self._entry(1, 1)
        result = _apply_round_ceilings([entry], {})
        assert result[0] is entry

    def test_empty_ceiling_dict_returns_same_list(self):
        """Empty ceiling dict returns the same list object."""
        entries = [self._entry(1, 1)]
        result = _apply_round_ceilings(entries, {})
        assert result is entries

    def test_second_round_ceiling_zeros_qf_and_beyond(self):
        """second_round ceiling: QF, SF, finals, champion set to 0."""
        entry = self._entry(1, 2)
        result = _apply_round_ceilings([entry], {(1, 2): "second_round"})
        out = result[0]
        assert out.second_round == pytest.approx(0.8)  # preserved
        assert out.quarterfinals == 0.0
        assert out.semifinals == 0.0
        assert out.finals == 0.0
        assert out.champion == 0.0

    def test_quarterfinals_ceiling_zeros_sf_and_beyond(self):
        """quarterfinals ceiling: SF, finals, champion set to 0; second_round and QF preserved."""
        entry = self._entry(2, 3)
        result = _apply_round_ceilings([entry], {(2, 3): "quarterfinals"})
        out = result[0]
        assert out.second_round == pytest.approx(0.8)
        assert out.quarterfinals == pytest.approx(0.6)
        assert out.semifinals == 0.0
        assert out.finals == 0.0
        assert out.champion == 0.0

    def test_weighted_fields_also_zeroed(self):
        """Weighted advancement fields are zeroed alongside unweighted ones."""
        entry = self._entry(1, 3)
        result = _apply_round_ceilings([entry], {(1, 3): "second_round"})
        out = result[0]
        assert out.quarterfinals_weighted == 0.0
        assert out.semifinals_weighted == 0.0
        assert out.finals_weighted == 0.0
        assert out.champion_weighted == 0.0

    def test_hosting_zeroed_beyond_ceiling(self):
        """Hosting odds for rounds after the ceiling are set to p_host_given_reach=None, p_host_overall=0."""
        entry = self._entry(1, 4)
        result = _apply_round_ceilings([entry], {(1, 4): "second_round"})
        out = result[0]
        assert out.hosting is not None
        assert out.hosting.second_round.p_host_given_reach == pytest.approx(0.7)  # preserved
        assert out.hosting.quarterfinals.p_host_given_reach is None
        assert out.hosting.quarterfinals.p_host_overall == 0.0
        assert out.hosting.semifinals.p_host_given_reach is None
        assert out.hosting.semifinals.p_host_overall == 0.0

    def test_hosting_at_ceiling_round_preserved(self):
        """Hosting odds for the ceiling round itself are not zeroed."""
        entry = self._entry(2, 1)
        result = _apply_round_ceilings([entry], {(2, 1): "quarterfinals"})
        out = result[0]
        assert out.hosting is not None
        assert out.hosting.quarterfinals.p_host_given_reach == pytest.approx(0.5)
        assert out.hosting.semifinals.p_host_given_reach is None
        assert out.hosting.semifinals.p_host_overall == 0.0

    def test_semifinals_ceiling_leaves_hosting_untouched(self):
        """semifinals ceiling has no rounds after it in _HOSTING_ROUNDS_AFTER
        (empty list), so the hosting-update block is skipped entirely (line
        1908->1926) — hosting odds are unchanged even though finals/champion
        advancement is zeroed.
        """
        entry = self._entry(1, 1)
        result = _apply_round_ceilings([entry], {(1, 1): "semifinals"})
        out = result[0]
        assert out.finals == 0.0
        assert out.champion == 0.0
        assert out.hosting is not None
        assert out.hosting.semifinals.p_host_given_reach == pytest.approx(0.3)
        assert out.hosting.quarterfinals.p_host_given_reach == pytest.approx(0.5)

    def test_entry_without_ceiling_unmodified_alongside_ceilinged(self):
        """Entries without a ceiling are untouched when mixed with ceilinged entries."""
        e1 = self._entry(1, 1)
        e2 = self._entry(1, 2)
        result = _apply_round_ceilings([e1, e2], {(1, 2): "quarterfinals"})
        assert result[0] is e1
        assert result[1].semifinals == 0.0


# ---------------------------------------------------------------------------
# TestBuildRankEntry
# ---------------------------------------------------------------------------


def _rankings_row() -> tuple:
    """Build a 38-column region_standings row matching rankings.py's _SELECT column order."""
    return (
        "Taylorsville",  # 0 school
        5,  # 1 class
        2,  # 2 region
        8, 2, 0, 4, 1, 0,  # 3-8 wins, losses, ties, region_wins, region_losses, region_ties
        _DATE,  # 9 as_of_date
        0.9, 0.05, 0.03, 0.02, 1.0,  # 10-14 odds_1st-odds_playoffs
        0.85, 0.08, 0.04, 0.03, 0.99,  # 15-19 weighted
        0.7, 0.5, 0.3, 0.1, 0.05,  # 20-24 second_round-champion
        0.65, 0.45, 0.25, 0.09, 0.04,  # 25-29 weighted
        0.6, 0.4, 0.2, 0.1,  # 30-33 home odds
        0.55, 0.35, 0.15, 0.08,  # 34-37 weighted home odds
    )


class TestBuildRankEntry:
    """build_rank_entry maps a region_standings row into a TeamRankEntry."""

    def test_identity_and_record_fields(self):
        """school/class_/region/as_of_date and the record block map to the correct columns."""
        entry = build_rank_entry(_rankings_row(), "odds_1st")
        assert (entry.school, entry.class_, entry.region) == ("Taylorsville", 5, 2)
        assert entry.as_of_date == _DATE
        assert (entry.record.wins, entry.record.losses) == (8, 2)
        assert (entry.record.region_wins, entry.record.region_losses) == (4, 1)

    def test_seeding_odds_mapped(self):
        """seeding_odds pulls from the unweighted and weighted odds_1st-odds_playoffs columns."""
        entry = build_rank_entry(_rankings_row(), "odds_1st")
        assert entry.seeding_odds.p1 == pytest.approx(0.9)
        assert entry.seeding_odds.p1_weighted == pytest.approx(0.85)
        assert entry.seeding_odds.p_playoffs == pytest.approx(1.0)

    def test_bracket_and_home_odds_mapped(self):
        """bracket and home blocks pull from their respective column ranges."""
        entry = build_rank_entry(_rankings_row(), "odds_1st")
        assert entry.bracket.second_round == pytest.approx(0.7)
        assert entry.bracket.champion_weighted == pytest.approx(0.04)
        assert entry.home.first_round == pytest.approx(0.6)
        assert entry.home.semifinals_weighted == pytest.approx(0.08)

    def test_sort_value_uses_requested_column(self):
        """sort_value is pulled from whichever column name is passed as sort_col."""
        row = _rankings_row()
        assert build_rank_entry(row, "odds_1st").sort_value == pytest.approx(0.9)
        assert build_rank_entry(row, "odds_champion").sort_value == pytest.approx(0.05)
        assert build_rank_entry(row, "odds_semifinals_home_weighted").sort_value == pytest.approx(0.08)
