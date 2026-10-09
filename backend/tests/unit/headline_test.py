"""Tests for backend.helpers.headline.build_region_headline."""

from backend.api.models.responses import (
    KeyInsightConditionModel,
    KeyInsightModel,
    PathConditionModel,
    PathOutcomeModel,
    RecordModel,
    ScenarioPathModel,
    SeedingOddsModel,
    TeamStandingsEntry,
)
from backend.helpers.api_helpers import build_team_paths, current_standings_order
from backend.helpers.data_classes import RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.headline import build_region_headline
from backend.helpers.insights import extract_insights
from backend.helpers.scenario_viewer import build_scenario_atoms
from backend.helpers.scenarios import determine_odds, determine_scenarios
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025, expand_results, teams_from_games


def _entry(
    school: str,
    p: tuple[float, float, float, float] = (0, 0, 0, 0),
    *,
    record: tuple[int, int] = (0, 0),
    clinched: bool = False,
    eliminated: bool = False,
    paths: list[ScenarioPathModel] | None = None,
) -> TeamStandingsEntry:
    """A standings entry with the given seed odds; playoff odds are their sum."""
    return TeamStandingsEntry(
        school=school,
        record=RecordModel(wins=0, losses=0, ties=0, region_wins=record[0], region_losses=record[1], region_ties=0),
        odds=SeedingOddsModel(p1=p[0], p2=p[1], p3=p[2], p4=p[3], p_playoffs=sum(p)),
        clinched=clinched,
        eliminated=eliminated,
        coin_flip_needed=False,
        paths=paths,
    )


def _insight(kind: str, team: str, conds: list[tuple], seed: int | None = None) -> KeyInsightModel:
    """A key insight whose conditions are (winner, loser[, min_margin, max_margin]) tuples."""
    return KeyInsightModel(
        insight_type=kind,
        team=team,
        seed=seed,
        conditions=[
            KeyInsightConditionModel(winner=c[0], loser=c[1], **dict(zip(("min_margin", "max_margin"), c[2:])))
            for c in conds
        ],
        rendered="",
        r_computed=3,
    )


def _single_path(outcome: PathOutcomeModel, conds: list[tuple]) -> ScenarioPathModel:
    """A path with exactly one way through: all of *conds* (winner, loser) must happen."""
    group = [
        PathConditionModel(type="game_result", school=w, opponent=l, required_result="win", min_margin=1)
        for w, l in conds
    ]
    return ScenarioPathModel(outcome=outcome, p=0.5, conditions=[group], human_text="")


class TestSettledField:
    """Every playoff seed locked."""

    def _teams(self):
        """A region whose four playoff seeds are all locked."""
        return [
            _entry("A", (1, 0, 0, 0), clinched=True),
            _entry("B", (0, 1, 0, 0), clinched=True),
            _entry("C", (0, 0, 1, 0), clinched=True),
            _entry("D", (0, 0, 0, 1), clinched=True),
            _entry("E", eliminated=True),
        ]

    def test_region_complete_uses_past_tense(self):
        """With region play over, the champion "won" the region."""
        assert (
            build_region_headline(self._teams(), None, 0)
            == "A won the region, with B, C and D joining them in the playoffs."
        )

    def test_settled_with_games_left_uses_present_perfect(self):
        """Seeds locked with games still to play reads "has won"."""
        assert build_region_headline(self._teams(), None, 2).startswith("A has won the region")

    def test_float_noise_near_one_counts_as_locked(self):
        """Odds summed over outcomes can land a hair above 1.0; that's still locked."""
        teams = self._teams()
        teams[0].odds.p1 = 1.0000000000000027
        assert build_region_headline(teams, None, 0).startswith("A won the region")


class TestTitleOpen:
    """Nobody has locked the #1 seed."""

    def _teams(self, a_paths=None):
        """A three-team region with an open title; *a_paths* become the leader's paths."""
        return [
            _entry("Taylorsville", (0.75, 0.25, 0, 0), record=(4, 0), clinched=True, paths=a_paths),
            _entry("Mize", (0.25, 0.5, 0.25, 0), record=(3, 1)),
            _entry("Stringer", (0, 0.25, 0.5, 0.25), record=(2, 2)),
        ]

    def test_self_contained_clinch_needs_no_help(self):
        """A clinch depending only on the team's own win is tagged "no help needed"."""
        insights = [_insight("clinch_seed", "Taylorsville", [("Taylorsville", "Mize")], seed=1)]
        assert build_region_headline(self._teams(), insights, 3) == (
            "Taylorsville clinches the region with a win over Mize — no help needed."
        )

    def test_clinch_with_outside_help_says_also(self):
        """Outside results the clinch also needs are named with "also"."""
        insights = [_insight("clinch_seed", "Mize", [("Mize", "Taylorsville"), ("Stringer", "Bay")], seed=1)]
        assert build_region_headline(self._teams(), insights, 3) == (
            "Mize clinches the region with a win over Taylorsville if Stringer also beats Bay."
        )

    def test_clinch_needing_only_others(self):
        """A clinch that depends only on other games reads "if X beats Y"."""
        insights = [_insight("clinch_seed", "Mize", [("Stringer", "Taylorsville")], seed=1)]
        assert (
            build_region_headline(self._teams(), insights, 3)
            == "Mize clinches the region if Stringer beats Taylorsville."
        )

    def test_margin_conditions_are_stated(self):
        """A required winning margin is part of the sentence, never dropped."""
        insights = [_insight("clinch_seed", "Mize", [("Mize", "Taylorsville", 8, None)], seed=1)]
        assert build_region_headline(self._teams(), insights, 3) == (
            "Mize clinches the region with a win over Taylorsville by 8 or more — no help needed."
        )

    def test_fewest_conditions_wins_then_likeliest_team(self):
        """The simplest clinch leads; ties go to the team likelier to win the title."""
        insights = [
            _insight("clinch_seed", "Mize", [("Mize", "Taylorsville"), ("Stringer", "Bay")], seed=1),
            _insight("clinch_seed", "Mize", [("Mize", "Taylorsville")], seed=1),
            _insight("clinch_seed", "Taylorsville", [("Taylorsville", "Mize")], seed=1),
        ]
        assert build_region_headline(self._teams(), insights, 3).startswith("Taylorsville clinches the region")

    def test_ignores_insights_for_other_seeds(self):
        """Only #1-seed clinches count while the title is open."""
        insights = [_insight("clinch_seed", "Mize", [("Mize", "Stringer")], seed=2)]
        assert build_region_headline(self._teams(), insights, 3) == (
            "Two teams can still win the region, and Taylorsville leads at 4–0."
        )

    def test_single_way_path_covers_teams_insights_skip(self):
        """Key insights skip teams already in the playoffs; their exact path still counts."""
        path = _single_path(PathOutcomeModel(type="seed", value=1), [("Taylorsville", "Mize")])
        assert build_region_headline(self._teams(a_paths=[path]), [], 3) == (
            "Taylorsville clinches the region with a win over Mize — no help needed."
        )

    def test_paths_ignored_when_not_margin_accurate(self):
        """At six games left paths are win/loss-only, so they can't be stated as guarantees."""
        path = _single_path(PathOutcomeModel(type="seed", value=1), [("Taylorsville", "Mize")])
        assert build_region_headline(self._teams(a_paths=[path]), [], 6).startswith("Two teams can still win")

    def test_paths_with_alternatives_are_not_a_single_clinch(self):
        group = [PathConditionModel(type="game_result", school="Taylorsville", opponent="Mize", required_result="win")]
        path = ScenarioPathModel(
            outcome=PathOutcomeModel(type="seed", value=1), p=0.75, conditions=[group, group], human_text=""
        )
        assert build_region_headline(self._teams(a_paths=[path]), [], 3).startswith("Two teams can still win")

    def test_lone_contender_without_lock(self):
        """One team alive for the title but not locked: name the leader and record."""
        teams = [_entry("A", (0.9, 0.1, 0, 0), record=(3, 0)), _entry("B", (0, 0.9, 0.1, 0), record=(2, 1))]
        assert build_region_headline(teams, None, 12) == "A leads the region at 3–0."


class TestTitleDecided:
    """#1 is locked but the rest of the field isn't."""

    def _teams(self):
        """2-7A's shape: three teams in, two chasing the last spot, one out."""
        return [
            _entry("Oxford", (1, 0, 0, 0), clinched=True),
            _entry("Germantown", (0, 1, 0, 0), clinched=True),
            _entry("Starkville", (0, 0, 0.5, 0.5), clinched=True),
            _entry("Madison Central", (0, 0, 0.5, 0.15)),
            _entry("Clinton", (0, 0, 0, 0.35)),
            _entry("Murrah", eliminated=True),
        ]

    def test_last_spot_clinch(self):
        """With one spot open, a clinch reads as clinching "the last playoff spot"."""
        insights = [_insight("clinch_playoffs", "Madison Central", [("Madison Central", "Clinton")])]
        assert build_region_headline(self._teams(), insights, 3) == (
            "Oxford has the region won, and Madison Central clinches the last playoff spot "
            "with a win over Clinton — no help needed."
        )

    def test_names_the_chasers_without_a_clean_clinch(self):
        """No proven clinch: name the teams still chasing the open spot."""
        assert build_region_headline(self._teams(), [], 3) == (
            "Oxford has the region won, and Madison Central and Clinton are playing for the last playoff spot."
        )

    def test_insights_for_clinched_or_eliminated_teams_ignored(self):
        """Only teams still chasing a spot can headline the playoff race."""
        insights = [_insight("clinch_playoffs", "Murrah", [("Murrah", "Oxford")])]
        assert "Murrah" not in build_region_headline(self._teams(), insights, 3)

    def test_counts_many_chasers(self):
        """More than three chasers are counted rather than listed."""
        teams = [_entry("A", (1, 0, 0, 0), clinched=True)] + [_entry(n, (0, 0.3, 0.3, 0.3)) for n in "BCDE"]
        assert (
            build_region_headline(teams, [], 8)
            == "A has the region won, and four teams are chasing the last three playoff spots."
        )

    def test_field_set_seeding_open(self):
        """All four spots clinched but seeds unsettled."""
        teams = [
            _entry("A", (1, 0, 0, 0), clinched=True),
            _entry("B", (0, 0.5, 0.5, 0), clinched=True),
            _entry("C", (0, 0.5, 0.5, 0), clinched=True),
            _entry("D", (0, 0, 0, 1), clinched=True),
        ]
        assert build_region_headline(teams, [], 1) == (
            "A has the region won, and the playoff field is set with seeding still to decide."
        )


def test_no_teams_returns_none():
    """An empty region has no headline."""
    assert build_region_headline([], None, 0) is None


# ---------------------------------------------------------------------------
# Real 2025 regions, pre-final-week, through the actual engine
# ---------------------------------------------------------------------------


def _engine_headline(clazz: int, region: int, cutoff: str = "2025-10-31") -> str | None:
    """Run the scenario engine on a 2025 fixture region and build its headline."""
    games = REGION_RESULTS_2025[(clazz, region)]["games"]
    teams = teams_from_games(games)
    completed = get_completed_games(expand_results([g for g in games if g["date"] <= cutoff]))
    remaining = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in games if g["date"] > cutoff]
    sr = determine_scenarios(teams, completed, remaining)
    odds = determine_odds(teams, sr.first_counts, sr.second_counts, sr.third_counts, sr.fourth_counts, sr.denom)
    atoms = build_scenario_atoms(teams, completed, remaining)
    insights = [
        KeyInsightModel(
            insight_type=i.insight_type,
            team=i.team,
            seed=i.seed,
            conditions=[
                KeyInsightConditionModel(
                    winner=c.winner, loser=c.loser, min_margin=c.min_margin, max_margin=c.max_margin
                )
                for c in i.conditions
            ],
            rendered=i.rendered,
            r_computed=i.r_computed,
        )
        for i in extract_insights(atoms, teams, completed, remaining, odds, r_computed=len(remaining))
    ]
    entries = {
        t: TeamStandingsEntry(
            school=t,
            record=RecordModel(wins=0, losses=0, ties=0, region_wins=0, region_losses=0, region_ties=0),
            odds=SeedingOddsModel(
                p1=odds[t].p1, p2=odds[t].p2, p3=odds[t].p3, p4=odds[t].p4, p_playoffs=odds[t].p_playoffs
            ),
            clinched=odds[t].clinched,
            eliminated=odds[t].eliminated,
            coin_flip_needed=False,
            paths=build_team_paths(t, atoms.get(t, {}), {}, odds[t]),
        )
        for t in teams
    }
    ordered = [entries[t] for t in current_standings_order(teams, completed, odds)]
    return build_region_headline(ordered, insights, len(remaining))


def test_engine_region_2_7a_last_spot():
    """2-7A: Oxford locked at #1; a Madison Central win over Clinton settles the last spot outright."""
    assert _engine_headline(7, 2) == (
        "Oxford has the region won, and Madison Central clinches the last playoff spot "
        "with a win over Clinton — no help needed."
    )


def test_engine_region_1_7a_title_from_exact_path():
    """1-7A: the title clinch comes from an exact path, since the contender is already in the playoffs."""
    assert _engine_headline(7, 1) == "DeSoto Central clinches the region with a win over Tupelo — no help needed."


def test_engine_region_3_7a_outside_help():
    """3-7A: a clinch that also depends on other games names them."""
    assert _engine_headline(7, 3) == (
        "Northwest Rankin clinches the region with a win over Petal if Pearl also beats Oak Grove and Meridian beats Brandon."
    )
