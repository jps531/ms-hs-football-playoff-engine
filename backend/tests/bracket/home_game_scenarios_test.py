"""Tests for home_game_scenarios.enumerate_home_game_scenarios and
the matching renderers in scenario_renderer.

Test strategy
-------------
All tests use the 2025 fixture data so results can be cross-checked against
known bracket outcomes:

* ``SLOTS_5A_7A_2025`` / ``SLOTS_1A_4A_2025`` — bracket slot structure.
* ``PLAYOFF_BRACKETS_2025`` — actual 2025 game results per round.
* ``REGION_RESULTS_2025`` — final seedings (used for team-name resolution).

Coverage areas
~~~~~~~~~~~~~~
1. **Dataclass integrity** — ``HomeGameCondition``, ``HomeGameScenario``,
   and ``RoundHomeScenarios`` have the expected fields and frozen behaviour.

2. **Round structure** — 5A–7A returns 3 rounds; 1A–4A returns 4 rounds.
   Round names are correct.

3. **First-round home detection** — the designated home team from each
   ``FormatSlot`` appears in ``will_host`` with an empty conditions tuple;
   the away team appears in ``will_not_host``.

4. **Second-round scenarios (1A–4A)** — adjacent-slot opponents are the
   only two candidates; actual 2025 R2 results agree with the ``will_host``
   grouping.

5. **Quarterfinal scenarios** — opponent pool size is correct (2 for 5A–7A,
   4 for 1A–4A); actual 2025 QF home teams appear in ``will_host``.

6. **Semifinal scenarios** — all teams from the opposing bracket half appear
   across ``will_host`` + ``will_not_host``; actual 2025 SF home teams
   appear in ``will_host``.

7. **Team-name resolution** — when ``team_lookup`` is supplied, resolved
   names appear in condition objects; without it, ``"Region X #Y Seed"``
   labels are used.

8. **Probability passthrough** — values in ``p_host_by_round`` are attached
   to the correct ``RoundHomeScenarios`` objects.

9. **Text renderer** — ``render_team_home_scenarios`` output contains the
   correct section headers and condition lines.

10. **Dict renderer** — ``team_home_scenarios_as_dict`` produces the
    expected keys and structure.

11. **Error handling** — ``ValueError`` is raised for unknown region/seed.
"""

import pytest

from backend.helpers.data_classes import (
    FormatSlot,
    HomeGameCondition,
    HomeGameScenario,
    RoundHomeScenarios,
)
from backend.helpers.home_game_scenarios import (
    _explain_r2,
    enumerate_home_game_scenarios,
    enumerate_team_matchups,
)
from backend.helpers.scenario_renderer import (
    render_team_home_scenarios,
    team_home_scenarios_as_dict,
)
from backend.tests.data.playoff_brackets_2025 import (
    PLAYOFF_BRACKETS_2025,
    SLOTS_1A_4A_2025,
    SLOTS_5A_7A_2025,
)
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025

SEASON = 2025


# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------


def _team_lookup_for_class(clazz: int) -> dict[tuple[int, int], str]:
    """Build a (region, seed) → school-name mapping for *clazz* from 2025 data."""
    num_regions = 4 if clazz >= 5 else 8
    lookup: dict[tuple[int, int], str] = {}
    for region in range(1, num_regions + 1):
        seeds = REGION_RESULTS_2025[(clazz, region)]["seeds"]
        for seed, school in seeds.items():
            lookup[(region, seed)] = school
    return lookup


def _slots(clazz: int) -> list[FormatSlot]:
    """Return the correct ``FormatSlot`` list for the given class."""
    return SLOTS_5A_7A_2025 if clazz >= 5 else SLOTS_1A_4A_2025


def _actual_home(
    clazz: int,
    round_key: str,
    region: int,
    seed: int,
) -> bool | None:
    """Return True/False if (region, seed) was the actual home team in the
    given round of the 2025 bracket, or None if data is absent."""
    games = PLAYOFF_BRACKETS_2025.get(clazz, {}).get(round_key, [])
    for hr, hs, ar, as_ in games:
        if hr == region and hs == seed:
            return True
        if ar == region and as_ == seed:
            return False
    return None


# ---------------------------------------------------------------------------
# 1. Dataclass integrity
# ---------------------------------------------------------------------------


class TestDataclasses:
    """Verify that the new home-game dataclasses are frozen and have the expected fields."""

    def test_home_game_condition_frozen(self):
        """HomeGameCondition must be immutable (frozen dataclass)."""
        cond = HomeGameCondition(
            kind="advances",
            round_name="Quarterfinals",
            region=1,
            seed=1,
            team_name="Oak Grove",
        )
        with pytest.raises((AttributeError, TypeError)):
            cond.seed = 2  # type: ignore[misc]

    def test_home_game_scenario_frozen(self):
        """HomeGameScenario must be immutable (frozen dataclass)."""
        sc = HomeGameScenario(conditions=(), explanation=None)
        with pytest.raises((AttributeError, TypeError)):
            sc.explanation = "changed"  # type: ignore[misc]

    def test_round_home_scenarios_frozen(self):
        """RoundHomeScenarios must be immutable (frozen dataclass)."""
        rnd = RoundHomeScenarios(
            round_name="First Round",
            will_host=(),
            will_not_host=(),
            p_reach=None,
            p_host_conditional=None,
            p_host_marginal=None,
            p_reach_weighted=None,
            p_host_conditional_weighted=None,
            p_host_marginal_weighted=None,
        )
        with pytest.raises((AttributeError, TypeError)):
            rnd.round_name = "Second Round"  # type: ignore[misc]

    def test_home_game_condition_fields(self):
        """HomeGameCondition exposes kind, round_name, region, seed, and team_name."""
        cond = HomeGameCondition(
            kind="seed_required", round_name=None, region=2, seed=3, team_name=None
        )
        assert cond.kind == "seed_required"
        assert cond.round_name is None
        assert cond.region == 2
        assert cond.seed == 3
        assert cond.team_name is None

    def test_home_game_scenario_conditions_are_tuple(self):
        """HomeGameScenario.conditions must be a tuple, not a list."""
        cond = HomeGameCondition(kind="advances", round_name="Quarterfinals",
                                 region=1, seed=1, team_name=None)
        sc = HomeGameScenario(conditions=(cond,), explanation="Higher seed (#1)")
        assert isinstance(sc.conditions, tuple)

    def test_round_home_scenarios_will_host_tuple(self):
        """RoundHomeScenarios.will_host and will_not_host must be tuples."""
        rnd = RoundHomeScenarios(
            round_name="Semifinals",
            will_host=(),
            will_not_host=(),
            p_reach=0.5,
            p_host_conditional=None,
            p_host_marginal=None,
            p_reach_weighted=None,
            p_host_conditional_weighted=None,
            p_host_marginal_weighted=None,
        )
        assert isinstance(rnd.will_host, tuple)
        assert isinstance(rnd.will_not_host, tuple)


# ---------------------------------------------------------------------------
# 2. Round structure
# ---------------------------------------------------------------------------


class TestRoundStructure:
    """Verify round count, round names, and error handling for unknown teams."""

    def test_5a_7a_returns_three_rounds(self):
        """5A–7A bracket returns exactly three rounds (First Round, QF, SF)."""
        result = enumerate_home_game_scenarios(1, 1, SLOTS_5A_7A_2025, SEASON)
        assert len(result) == 3

    def test_1a_4a_returns_four_rounds(self):
        """1A–4A bracket returns exactly four rounds (First Round, R2, QF, SF)."""
        result = enumerate_home_game_scenarios(1, 1, SLOTS_1A_4A_2025, SEASON)
        assert len(result) == 4

    def test_5a_7a_round_names(self):
        """5A–7A round names are First Round, Quarterfinals, Semifinals."""
        result = enumerate_home_game_scenarios(1, 1, SLOTS_5A_7A_2025, SEASON)
        names = [r.round_name for r in result]
        assert names == ["First Round", "Quarterfinals", "Semifinals"]

    def test_1a_4a_round_names(self):
        """1A–4A round names are First Round, Second Round, Quarterfinals, Semifinals."""
        result = enumerate_home_game_scenarios(1, 1, SLOTS_1A_4A_2025, SEASON)
        names = [r.round_name for r in result]
        assert names == ["First Round", "Second Round", "Quarterfinals", "Semifinals"]

    def test_invalid_region_raises(self):
        """ValueError is raised when the region is not found in slots."""
        with pytest.raises(ValueError, match="not found"):
            enumerate_home_game_scenarios(99, 1, SLOTS_5A_7A_2025, SEASON)

    def test_invalid_seed_raises(self):
        """ValueError is raised when the seed is not found in slots."""
        with pytest.raises(ValueError, match="not found"):
            enumerate_home_game_scenarios(1, 9, SLOTS_5A_7A_2025, SEASON)


# ---------------------------------------------------------------------------
# 3. First-round home detection — all R1 slots across both formats
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slot", SLOTS_5A_7A_2025)
class TestR1Detection5A7A:
    """Verify R1 home/away detection for every slot in the 5A–7A format."""

    def test_home_team_in_will_host(self, slot: FormatSlot):
        """Designated home team for each slot lands in will_host with no conditions."""
        result = enumerate_home_game_scenarios(
            slot.home_region, slot.home_seed, SLOTS_5A_7A_2025, SEASON
        )
        r1 = result[0]
        assert r1.round_name == "First Round"
        assert len(r1.will_host) == 1
        assert r1.will_host[0].conditions == ()

    def test_away_team_in_will_not_host(self, slot: FormatSlot):
        """Designated away team for each slot lands in will_not_host with no conditions."""
        result = enumerate_home_game_scenarios(
            slot.away_region, slot.away_seed, SLOTS_5A_7A_2025, SEASON
        )
        r1 = result[0]
        assert len(r1.will_not_host) == 1
        assert r1.will_not_host[0].conditions == ()

    def test_will_host_and_will_not_host_disjoint(self, slot: FormatSlot):
        """Exactly one of will_host / will_not_host is non-empty for each team."""
        for region, seed in (
            (slot.home_region, slot.home_seed),
            (slot.away_region, slot.away_seed),
        ):
            result = enumerate_home_game_scenarios(region, seed, SLOTS_5A_7A_2025, SEASON)
            r1 = result[0]
            total = len(r1.will_host) + len(r1.will_not_host)
            assert total == 1


@pytest.mark.parametrize("slot", SLOTS_1A_4A_2025)
class TestR1Detection1A4A:
    """Verify R1 home/away detection for every slot in the 1A–4A format."""

    def test_home_team_in_will_host(self, slot: FormatSlot):
        """Designated home team for each slot lands in will_host with no conditions."""
        result = enumerate_home_game_scenarios(
            slot.home_region, slot.home_seed, SLOTS_1A_4A_2025, SEASON
        )
        r1 = result[0]
        assert len(r1.will_host) == 1
        assert r1.will_host[0].conditions == ()

    def test_away_team_in_will_not_host(self, slot: FormatSlot):
        """Designated away team for each slot lands in will_not_host with no conditions."""
        result = enumerate_home_game_scenarios(
            slot.away_region, slot.away_seed, SLOTS_1A_4A_2025, SEASON
        )
        r1 = result[0]
        assert len(r1.will_not_host) == 1
        assert r1.will_not_host[0].conditions == ()


# ---------------------------------------------------------------------------
# 4. Second-round scenarios (1A-4A) — coverage and 2025 ground truth
# ---------------------------------------------------------------------------


class TestSecondRound1A4A:
    """Verify Second Round scenario coverage and 2025 ground-truth for 1A–4A."""

    def test_r2_exactly_two_opponent_paths_when_distinct(self):
        """Each R2 scenario references a distinct opponent from the adjacent slot."""
        result = enumerate_home_game_scenarios(1, 1, SLOTS_1A_4A_2025, SEASON)
        r2 = result[1]
        assert r2.round_name == "Second Round"
        all_scenarios = list(r2.will_host) + list(r2.will_not_host)
        # Either two separate scenarios (one per opponent) or one merged scenario
        assert 1 <= len(all_scenarios) <= 2

    def test_r2_conditions_reference_second_round(self):
        """Every condition in R2 scenarios refers to 'Second Round'."""
        result = enumerate_home_game_scenarios(1, 1, SLOTS_1A_4A_2025, SEASON)
        r2 = result[1]
        for sc in list(r2.will_host) + list(r2.will_not_host):
            for cond in sc.conditions:
                assert cond.round_name == "Second Round"

    @pytest.mark.parametrize("clazz", [1, 2, 3, 4])
    def test_r2_2025_ground_truth_home_team_in_will_host(self, clazz: int):
        """Every actual 2025 R2 home team appears in will_host for that round."""
        games = PLAYOFF_BRACKETS_2025.get(clazz, {}).get("second_round", [])
        if not games:
            pytest.skip("No 2025 R2 data for this class")
        slots = _slots(clazz)
        for hr, hs, _ar, _as in games:
            result = enumerate_home_game_scenarios(hr, hs, slots, SEASON)
            r2 = result[1]  # Second Round is index 1 for 1A-4A
            assert len(r2.will_host) >= 1, (
                f"Class {clazz}A Region {hr} #{hs}: expected will_host to be non-empty"
            )

    @pytest.mark.parametrize("clazz", [1, 2, 3, 4])
    def test_r2_2025_ground_truth_away_team_in_will_not_host(self, clazz: int):
        """Every actual 2025 R2 away team appears in will_not_host for that round."""
        games = PLAYOFF_BRACKETS_2025.get(clazz, {}).get("second_round", [])
        if not games:
            pytest.skip("No 2025 R2 data for this class")
        slots = _slots(clazz)
        for _hr, _hs, ar, as_ in games:
            result = enumerate_home_game_scenarios(ar, as_, slots, SEASON)
            r2 = result[1]
            assert len(r2.will_not_host) >= 1, (
                f"Class {clazz}A Region {ar} #{as_}: expected will_not_host to be non-empty"
            )


# ---------------------------------------------------------------------------
# 5. Quarterfinal scenarios — pool size and 2025 ground truth
# ---------------------------------------------------------------------------


class TestQuarterfinals:
    """Verify QF scenario pool sizes, condition labels, and 2025 ground-truth outcomes."""

    def test_5a_7a_qf_opponent_pool_size(self):
        """5A-7A QF: exactly 2 opponents in the adjacent slot."""
        result = enumerate_home_game_scenarios(1, 1, SLOTS_5A_7A_2025, SEASON)
        qf = result[1]  # QF is index 1 for 5A-7A
        assert qf.round_name == "Quarterfinals"
        total = len(qf.will_host) + len(qf.will_not_host)
        assert total == 2

    def test_1a_4a_qf_opponent_pool_size(self):
        """1A-4A QF: exactly 4 pool candidates; an opponent may appear in 2
        scenarios when its R2 home status determines the QF result differently."""
        result = enumerate_home_game_scenarios(1, 1, SLOTS_1A_4A_2025, SEASON)
        qf = result[2]  # QF is index 2 for 1A-4A
        assert qf.round_name == "Quarterfinals"
        # Unique QF opponent (region, seed) pairs must be drawn from the 4-team pool.
        unique_opps = {
            (c.region, c.seed)
            for sc in list(qf.will_host) + list(qf.will_not_host)
            for c in sc.conditions
            if c.region is not None and c.round_name == "Quarterfinals"
        }
        assert len(unique_opps) <= 4

    def test_5a_7a_qf_conditions_reference_quarterfinals(self):
        """QF conditions must name 'Quarterfinals' as the round."""
        result = enumerate_home_game_scenarios(1, 1, SLOTS_5A_7A_2025, SEASON)
        qf = result[1]
        for sc in list(qf.will_host) + list(qf.will_not_host):
            for cond in sc.conditions:
                assert cond.round_name == "Quarterfinals"

    @pytest.mark.parametrize("clazz", [5, 6, 7])
    def test_5a_7a_qf_2025_home_in_will_host(self, clazz: int):
        """Actual 2025 QF home team for each 5A-7A game is in will_host."""
        games = PLAYOFF_BRACKETS_2025.get(clazz, {}).get("quarterfinals", [])
        if not games:
            pytest.skip(f"No 2025 QF data for {clazz}A")
        slots = _slots(clazz)
        for hr, hs, _ar, _as in games:
            result = enumerate_home_game_scenarios(hr, hs, slots, SEASON)
            qf = result[1]
            assert len(qf.will_host) >= 1, (
                f"Class {clazz}A Region {hr} #{hs}: expected in will_host"
            )

    @pytest.mark.parametrize("clazz", [5, 6, 7])
    def test_5a_7a_qf_2025_away_in_will_not_host(self, clazz: int):
        """Actual 2025 QF away team for each 5A-7A game is in will_not_host."""
        games = PLAYOFF_BRACKETS_2025.get(clazz, {}).get("quarterfinals", [])
        if not games:
            pytest.skip(f"No 2025 QF data for {clazz}A")
        slots = _slots(clazz)
        for _hr, _hs, ar, as_ in games:
            result = enumerate_home_game_scenarios(ar, as_, slots, SEASON)
            qf = result[1]
            assert len(qf.will_not_host) >= 1, (
                f"Class {clazz}A Region {ar} #{as_}: expected in will_not_host"
            )

    @pytest.mark.parametrize("clazz", [1, 2, 3, 4])
    def test_1a_4a_qf_2025_home_in_will_host(self, clazz: int):
        """Actual 2025 QF home team for each 1A-4A game is in will_host."""
        games = PLAYOFF_BRACKETS_2025.get(clazz, {}).get("quarterfinals", [])
        if not games:
            pytest.skip(f"No 2025 QF data for {clazz}A")
        slots = _slots(clazz)
        for hr, hs, _ar, _as in games:
            result = enumerate_home_game_scenarios(hr, hs, slots, SEASON)
            qf = result[2]  # QF is index 2 for 1A-4A
            assert len(qf.will_host) >= 1, (
                f"Class {clazz}A Region {hr} #{hs}: expected in will_host"
            )

    @pytest.mark.parametrize("clazz", [1, 2, 3, 4])
    def test_1a_4a_qf_2025_away_in_will_not_host(self, clazz: int):
        """Actual 2025 QF away team for each 1A-4A game is in will_not_host."""
        games = PLAYOFF_BRACKETS_2025.get(clazz, {}).get("quarterfinals", [])
        if not games:
            pytest.skip(f"No 2025 QF data for {clazz}A")
        slots = _slots(clazz)
        for _hr, _hs, ar, as_ in games:
            result = enumerate_home_game_scenarios(ar, as_, slots, SEASON)
            qf = result[2]
            assert len(qf.will_not_host) >= 1, (
                f"Class {clazz}A Region {ar} #{as_}: expected in will_not_host"
            )


# ---------------------------------------------------------------------------
# 6. Semifinal scenarios — pool coverage and 2025 ground truth
# ---------------------------------------------------------------------------


class TestSemifinals:
    """Verify SF scenario pool coverage (intra-half) and 2025 ground-truth outcomes."""

    def test_5a_7a_sf_all_opposing_teams_covered(self):
        """SF must enumerate all 4 teams from the opposing bracket quarter.

        The SF is an intra-half game.  For 5A-7A (4 slots per half),
        round_offset=2 selects the 2 slots in the opposing quarter of the
        same half, yielding 4 unique candidates.
        """
        result = enumerate_home_game_scenarios(1, 1, SLOTS_5A_7A_2025, SEASON)
        sf = result[2]
        assert sf.round_name == "Semifinals"
        total = len(sf.will_host) + len(sf.will_not_host)
        assert total == 4

    def test_1a_4a_sf_all_opposing_teams_covered(self):
        """SF must enumerate all 8 teams from the opposing bracket quarter.

        For 1A-4A (8 slots per half), round_offset=3 selects the 4 slots in
        the opposing quarter of the same half, yielding 8 unique candidates.
        """
        result = enumerate_home_game_scenarios(1, 1, SLOTS_1A_4A_2025, SEASON)
        sf = result[3]
        assert sf.round_name == "Semifinals"
        total = len(sf.will_host) + len(sf.will_not_host)
        assert total == 8

    def test_sf_conditions_reference_semifinals(self):
        """All SF conditions must name 'Semifinals' as the round."""
        result = enumerate_home_game_scenarios(1, 1, SLOTS_5A_7A_2025, SEASON)
        sf = result[2]
        for sc in list(sf.will_host) + list(sf.will_not_host):
            for cond in sc.conditions:
                assert cond.round_name == "Semifinals"

    @pytest.mark.parametrize("clazz", [5, 6, 7])
    def test_5a_7a_sf_2025_home_in_will_host(self, clazz: int):
        """Actual 2025 SF home team is in will_host."""
        games = PLAYOFF_BRACKETS_2025.get(clazz, {}).get("semifinals", [])
        if not games:
            pytest.skip(f"No 2025 SF data for {clazz}A")
        slots = _slots(clazz)
        for hr, hs, _ar, _as in games:
            result = enumerate_home_game_scenarios(hr, hs, slots, SEASON)
            sf = result[2]
            assert len(sf.will_host) >= 1, (
                f"Class {clazz}A Region {hr} #{hs}: expected in will_host"
            )

    @pytest.mark.parametrize("clazz", [5, 6, 7])
    def test_5a_7a_sf_2025_away_in_will_not_host(self, clazz: int):
        """Actual 2025 SF away team is in will_not_host."""
        games = PLAYOFF_BRACKETS_2025.get(clazz, {}).get("semifinals", [])
        if not games:
            pytest.skip(f"No 2025 SF data for {clazz}A")
        slots = _slots(clazz)
        for _hr, _hs, ar, as_ in games:
            result = enumerate_home_game_scenarios(ar, as_, slots, SEASON)
            sf = result[2]
            assert len(sf.will_not_host) >= 1, (
                f"Class {clazz}A Region {ar} #{as_}: expected in will_not_host"
            )

    @pytest.mark.parametrize("clazz", [1, 2, 3, 4])
    def test_1a_4a_sf_2025_home_in_will_host(self, clazz: int):
        """Actual 2025 SF home team for each 1A–4A game is in will_host."""
        games = PLAYOFF_BRACKETS_2025.get(clazz, {}).get("semifinals", [])
        if not games:
            pytest.skip(f"No 2025 SF data for {clazz}A")
        slots = _slots(clazz)
        for hr, hs, _ar, _as in games:
            result = enumerate_home_game_scenarios(hr, hs, slots, SEASON)
            sf = result[3]
            assert len(sf.will_host) >= 1

    @pytest.mark.parametrize("clazz", [1, 2, 3, 4])
    def test_1a_4a_sf_2025_away_in_will_not_host(self, clazz: int):
        """Actual 2025 SF away team for each 1A–4A game is in will_not_host."""
        games = PLAYOFF_BRACKETS_2025.get(clazz, {}).get("semifinals", [])
        if not games:
            pytest.skip(f"No 2025 SF data for {clazz}A")
        slots = _slots(clazz)
        for _hr, _hs, ar, as_ in games:
            result = enumerate_home_game_scenarios(ar, as_, slots, SEASON)
            sf = result[3]
            assert len(sf.will_not_host) >= 1


# ---------------------------------------------------------------------------
# 7. Team-name resolution
# ---------------------------------------------------------------------------


class TestTeamNameResolution:
    """Verify that team_lookup resolves names in conditions and falls back gracefully."""

    def test_names_substituted_when_lookup_provided(self):
        """Known names from REGION_RESULTS_2025 appear in condition team fields."""
        lookup = _team_lookup_for_class(7)
        result = enumerate_home_game_scenarios(1, 1, SLOTS_5A_7A_2025, SEASON, team_lookup=lookup)
        for rnd in result[1:]:  # skip R1 (no opponent conditions)
            for sc in list(rnd.will_host) + list(rnd.will_not_host):
                for cond in sc.conditions:
                    if cond.region is not None and cond.seed is not None:
                        # Opponent condition: team_name must be the resolved name
                        expected = lookup.get((cond.region, cond.seed))
                        if expected:
                            assert cond.team_name == expected, (
                                f"Expected {expected!r} for region={cond.region} "
                                f"seed={cond.seed}, got {cond.team_name!r}"
                            )

    def test_generic_label_without_lookup(self):
        """Without a lookup, opponent conditions use 'Region X #Y Seed' labels."""
        result = enumerate_home_game_scenarios(1, 1, SLOTS_5A_7A_2025, SEASON)
        for rnd in result[1:]:
            for sc in list(rnd.will_host) + list(rnd.will_not_host):
                for cond in sc.conditions:
                    if cond.region is not None and cond.team_name is not None:
                        assert cond.team_name == f"Region {cond.region} #{cond.seed} Seed"

    def test_target_team_condition_has_none_region(self):
        """The condition referring to the target team itself has region=None."""
        result = enumerate_home_game_scenarios(1, 1, SLOTS_5A_7A_2025, SEASON)
        for rnd in result[1:]:
            for sc in list(rnd.will_host) + list(rnd.will_not_host):
                if sc.conditions:
                    first = sc.conditions[0]
                    assert first.region is None, (
                        "First condition should refer to the target team (region=None)"
                    )


# ---------------------------------------------------------------------------
# 8. Probability passthrough
# ---------------------------------------------------------------------------


class TestProbabilityPassthrough:
    """Verify that probability-by-round dicts are attached to RoundHomeScenarios."""

    def test_p_host_marginal_attached_to_correct_round(self):
        """p_host_marginal values are attached to the matching RoundHomeScenarios."""
        p_by_round = {
            "First Round": 1.0,
            "Quarterfinals": 0.625,
            "Semifinals": 0.25,
        }
        result = enumerate_home_game_scenarios(
            1, 1, SLOTS_5A_7A_2025, SEASON, p_host_marginal_by_round=p_by_round
        )
        for rnd in result:
            assert rnd.p_host_marginal == p_by_round[rnd.round_name]

    def test_p_host_marginal_none_when_not_provided(self):
        """p_host_marginal is None on every round when no dict is passed."""
        result = enumerate_home_game_scenarios(1, 1, SLOTS_5A_7A_2025, SEASON)
        for rnd in result:
            assert rnd.p_host_marginal is None

    def test_p_host_marginal_weighted_attached(self):
        """p_host_marginal_weighted values are attached when the weighted dict is supplied."""
        pw_by_round = {"First Round": 1.0, "Quarterfinals": 0.70, "Semifinals": 0.30}
        result = enumerate_home_game_scenarios(
            1, 1, SLOTS_5A_7A_2025, SEASON, p_host_marginal_weighted_by_round=pw_by_round
        )
        for rnd in result:
            assert rnd.p_host_marginal_weighted == pw_by_round[rnd.round_name]

    def test_1a_4a_p_host_marginal_four_rounds(self):
        """p_host_marginal is attached to all four rounds for a 1A–4A team."""
        p_by_round = {
            "First Round": 1.0,
            "Second Round": 0.75,
            "Quarterfinals": 0.5,
            "Semifinals": 0.25,
        }
        result = enumerate_home_game_scenarios(
            1, 1, SLOTS_1A_4A_2025, SEASON, p_host_marginal_by_round=p_by_round
        )
        for rnd in result:
            assert rnd.p_host_marginal == p_by_round[rnd.round_name]


# ---------------------------------------------------------------------------
# 9. Text renderer
# ---------------------------------------------------------------------------


class TestRenderTeamHomeScenarios:
    """Verify the text output of render_team_home_scenarios."""

    def _scenarios_for(self, region: int, seed: int, slots, lookup=None):
        """Build scenarios for the given region/seed using 2025 fixtures."""
        return enumerate_home_game_scenarios(region, seed, slots, SEASON, team_lookup=lookup)

    def test_team_name_appears_as_first_line(self):
        """The school name is the first line of the rendered output."""
        lookup = _team_lookup_for_class(7)
        team = lookup[(1, 1)]
        scens = self._scenarios_for(1, 1, SLOTS_5A_7A_2025, lookup)
        text = render_team_home_scenarios(team, scens)
        assert text.startswith(team)

    def test_will_host_header_present(self):
        """Output contains a 'Will Host First Round' section header."""
        scens = self._scenarios_for(1, 1, SLOTS_5A_7A_2025)
        text = render_team_home_scenarios("TestTeam", scens)
        assert "Will Host First Round" in text

    def test_will_not_host_header_absent_for_unconditional_home(self):
        """When R1 is always home, 'Will Not Host First Round' must not appear."""
        scens = self._scenarios_for(1, 1, SLOTS_5A_7A_2025)
        # R1 slot 1: home=Region1#1 — this team always hosts
        text = render_team_home_scenarios("TestTeam", scens)
        assert "Will Not Host First Round" not in text

    def test_will_not_host_present_for_away_team(self):
        """Away team in R1 should have 'Will Not Host First Round' in output."""
        # Region 2 seed 4 is away in slot 1
        scens = self._scenarios_for(2, 4, SLOTS_5A_7A_2025)
        text = render_team_home_scenarios("TestTeam", scens)
        assert "Will Not Host First Round" in text
        assert "Will Host First Round" not in text

    def test_probability_suffix_in_header(self):
        """Percentage values from p_host_marginal_by_round appear in round section headers."""
        p_by_round = {"First Round": 1.0, "Quarterfinals": 0.625, "Semifinals": 0.25}
        scens = enumerate_home_game_scenarios(
            1, 1, SLOTS_5A_7A_2025, SEASON, p_host_marginal_by_round=p_by_round
        )
        text = render_team_home_scenarios("TestTeam", scens)
        assert "100.0%" in text
        assert "62.5%" in text

    def test_numbered_conditions_for_qf(self):
        """QF section should contain at least one '1.' bullet."""
        scens = self._scenarios_for(1, 1, SLOTS_5A_7A_2025)
        text = render_team_home_scenarios("TestTeam", scens)
        assert "1. TestTeam advances to Quarterfinals" in text

    def test_explanation_in_brackets(self):
        """Explanations are rendered in square brackets."""
        scens = self._scenarios_for(1, 1, SLOTS_5A_7A_2025)
        text = render_team_home_scenarios("TestTeam", scens)
        assert "[" in text and "]" in text

    def test_team_name_substituted_in_conditions(self):
        """The target team's name (not 'Team') appears in advance conditions."""
        scens = self._scenarios_for(1, 1, SLOTS_5A_7A_2025)
        text = render_team_home_scenarios("OakGrove", scens)
        assert "OakGrove advances to" in text
        assert "Team advances" not in text

    def test_7a_region1_seed1_2025_text_snapshot(self):
        """Smoke-test for 7A Region 1 #1 seed with resolved names."""
        lookup = _team_lookup_for_class(7)
        team = lookup[(1, 1)]
        scens = self._scenarios_for(1, 1, SLOTS_5A_7A_2025, lookup)
        text = render_team_home_scenarios(team, scens)
        # Should host First Round (unconditional)
        assert "Will Host First Round" in text
        # Should have QF and SF sections
        assert "Quarterfinals" in text
        assert "Semifinals" in text


# ---------------------------------------------------------------------------
# 10. Dict renderer
# ---------------------------------------------------------------------------


class TestTeamHomeScenariosAsDict:
    """Verify the dict structure produced by team_home_scenarios_as_dict."""

    def _scenarios_for(self, region, seed, slots, lookup=None):
        """Build scenarios for the given region/seed using 2025 fixtures."""
        return enumerate_home_game_scenarios(region, seed, slots, SEASON, team_lookup=lookup)

    def test_5a_7a_keys(self):
        """5A–7A dict has keys for first_round, quarterfinals, and semifinals."""
        scens = self._scenarios_for(1, 1, SLOTS_5A_7A_2025)
        d = team_home_scenarios_as_dict("TestTeam", scens)
        assert set(d.keys()) == {"first_round", "quarterfinals", "semifinals"}

    def test_1a_4a_keys(self):
        """1A–4A dict additionally has a second_round key."""
        scens = self._scenarios_for(1, 1, SLOTS_1A_4A_2025)
        d = team_home_scenarios_as_dict("TestTeam", scens)
        assert set(d.keys()) == {"first_round", "second_round", "quarterfinals", "semifinals"}

    def test_round_entry_structure(self):
        """Each round entry contains all six odds fields plus will_host/will_not_host."""
        scens = self._scenarios_for(1, 1, SLOTS_5A_7A_2025)
        d = team_home_scenarios_as_dict("TestTeam", scens)
        for rnd_dict in d.values():
            assert "p_reach" in rnd_dict
            assert "p_host_conditional" in rnd_dict
            assert "p_host_marginal" in rnd_dict
            assert "p_reach_weighted" in rnd_dict
            assert "p_host_conditional_weighted" in rnd_dict
            assert "p_host_marginal_weighted" in rnd_dict
            assert "will_host" in rnd_dict
            assert "will_not_host" in rnd_dict
            assert isinstance(rnd_dict["will_host"], list)
            assert isinstance(rnd_dict["will_not_host"], list)

    def test_scenario_entry_structure(self):
        """Each scenario entry contains conditions and explanation keys."""
        scens = self._scenarios_for(1, 1, SLOTS_5A_7A_2025)
        d = team_home_scenarios_as_dict("TestTeam", scens)
        qf = d["quarterfinals"]
        all_scenarios = qf["will_host"] + qf["will_not_host"]
        assert len(all_scenarios) > 0
        for sc in all_scenarios:
            assert "conditions" in sc
            assert "explanation" in sc
            assert isinstance(sc["conditions"], list)

    def test_condition_entry_structure(self):
        """Each condition entry contains kind, round, region, seed, and team keys."""
        scens = self._scenarios_for(1, 1, SLOTS_5A_7A_2025)
        d = team_home_scenarios_as_dict("TestTeam", scens)
        qf = d["quarterfinals"]
        all_scenarios = qf["will_host"] + qf["will_not_host"]
        for sc in all_scenarios:
            for cond in sc["conditions"]:
                assert "kind" in cond
                assert "round" in cond
                assert "region" in cond
                assert "seed" in cond
                assert "team" in cond

    def test_target_team_name_in_first_condition(self):
        """The first condition in each QF/SF scenario must name the target team."""
        scens = self._scenarios_for(1, 1, SLOTS_5A_7A_2025)
        d = team_home_scenarios_as_dict("OakGrove", scens)
        qf = d["quarterfinals"]
        for sc in qf["will_host"] + qf["will_not_host"]:
            if sc["conditions"]:
                assert sc["conditions"][0]["team"] == "OakGrove"

    def test_p_host_marginal_propagated_to_dict(self):
        """p_host_marginal values from RoundHomeScenarios are surfaced in the dict."""
        p_by_round = {"First Round": 1.0, "Quarterfinals": 0.5, "Semifinals": 0.25}
        scens = enumerate_home_game_scenarios(
            1, 1, SLOTS_5A_7A_2025, SEASON, p_host_marginal_by_round=p_by_round
        )
        d = team_home_scenarios_as_dict("TestTeam", scens)
        assert d["first_round"]["p_host_marginal"] == pytest.approx(1.0)
        assert d["quarterfinals"]["p_host_marginal"] == pytest.approx(0.5)
        assert d["semifinals"]["p_host_marginal"] == pytest.approx(0.25)

    def test_resolved_names_in_dict_conditions(self):
        """Resolved team names from lookup appear in dict condition 'team' fields."""
        lookup = _team_lookup_for_class(7)
        scens = self._scenarios_for(1, 1, SLOTS_5A_7A_2025, lookup)
        d = team_home_scenarios_as_dict(lookup[(1, 1)], scens)
        qf = d["quarterfinals"]
        opponent_names = {
            cond["team"]
            for sc in qf["will_host"] + qf["will_not_host"]
            for cond in sc["conditions"]
            if cond["region"] is not None
        }
        # All opponent names should be real school names (not "Region X #Y Seed")
        for name in opponent_names:
            assert "Region" not in name or "Seed" not in name or name in lookup.values(), (
                f"Expected resolved name but got: {name!r}"
            )


# ---------------------------------------------------------------------------
# 11. Specific 2025 scenario spot-checks
# ---------------------------------------------------------------------------


class TestSpotChecks2025:
    """Targeted checks for specific known 2025 outcomes."""

    def test_7a_r1_region1_seed1_always_hosts(self):
        """7A Region 1 #1 seed is always home in R1 (slot 1 home team)."""
        result = enumerate_home_game_scenarios(1, 1, SLOTS_5A_7A_2025, SEASON)
        r1 = result[0]
        assert len(r1.will_host) == 1
        assert len(r1.will_not_host) == 0

    def test_7a_r1_region2_seed4_never_hosts(self):
        """7A Region 2 #4 seed is always away in R1 (slot 1 away team)."""
        result = enumerate_home_game_scenarios(2, 4, SLOTS_5A_7A_2025, SEASON)
        r1 = result[0]
        assert len(r1.will_host) == 0
        assert len(r1.will_not_host) == 1

    def test_7a_qf_2025_region1_seed1_hosted(self):
        """7A 2025 QF: Region 1 #1 hosted (1,1,2,2) — must be in will_host."""
        # Slot 1: home=R1#1, away=R2#4. Adjacent slot 2: home=R2#2, away=R1#3.
        # So QF opponent of R1#1 is either R2#2 or R1#3.
        # Actual QF: (1,1,2,2) → R1#1 hosted → opponent was R2#2.
        result = enumerate_home_game_scenarios(1, 1, SLOTS_5A_7A_2025, SEASON)
        qf = result[1]
        # R1#1 should host against R2#2 (higher seed)
        host_opponents = {
            (cond.region, cond.seed)
            for sc in qf.will_host
            for cond in sc.conditions
            if cond.region is not None
        }
        assert (2, 2) in host_opponents, (
            f"Expected (2,2) in will_host opponents, got {host_opponents}"
        )

    def test_7a_sf_2025_region1_seed1_hosted(self):
        """7A 2025 SF: Region 1 #1 hosted (1,1,2,1) — must be in will_host."""
        # SF: R1#1 vs R2#1. Odd year 2025 → lower region# hosts if seeds equal.
        # Both are #1 seeds, Region 1 < Region 2 → Region 1 hosts. Correct.
        result = enumerate_home_game_scenarios(1, 1, SLOTS_5A_7A_2025, SEASON)
        sf = result[2]
        host_opponents = {
            (cond.region, cond.seed)
            for sc in sf.will_host
            for cond in sc.conditions
            if cond.region is not None
        }
        assert (2, 1) in host_opponents, (
            f"Expected (2,1) in will_host opponents, got {host_opponents}"
        )

    def test_4a_qf_2025_region4_seed2_hosted_over_region1_seed1(self):
        """4A 2025 QF: (4,2,1,1) — Region 4 #2 hosted over Region 1 #1.

        This is the 'fewer home games' rule: Region 1 #1 was home in both R1
        and R2 (2 home games); Region 4 #2 was home in R2 only (1 home game).
        """
        result = enumerate_home_game_scenarios(4, 2, SLOTS_1A_4A_2025, SEASON)
        qf = result[2]  # QF is index 2 for 1A-4A
        assert len(qf.will_host) >= 1, "Region 4 #2 should have a will_host scenario"

    def test_4a_qf_2025_region1_seed1_was_away(self):
        """4A 2025 QF: Region 1 #1 was away against Region 4 #2 — must be in will_not_host."""
        result = enumerate_home_game_scenarios(1, 1, SLOTS_1A_4A_2025, SEASON)
        qf = result[2]
        assert len(qf.will_not_host) >= 1, "Region 1 #1 should have a will_not_host scenario"

    def test_explanations_are_strings(self):
        """All scenarios must have a non-empty string explanation."""
        for clazz in (7, 4):
            slots = _slots(clazz)
            for region in range(1, 5 if clazz >= 5 else 9):
                for seed in range(1, 5):
                    result = enumerate_home_game_scenarios(region, seed, slots, SEASON)
                    for rnd in result:
                        for sc in list(rnd.will_host) + list(rnd.will_not_host):
                            assert sc.explanation is not None, (
                                f"Class {clazz}A R{region}#{seed} "
                                f"round={rnd.round_name}: explanation is None"
                            )
                            assert isinstance(sc.explanation, str)
                            assert len(sc.explanation) > 0


# ---------------------------------------------------------------------------
# 12. Taylorsville 2025 ground truth (1A Region 8 #1 seed)
# ---------------------------------------------------------------------------


class TestTaylorsville2025:
    """Exact expected home-game scenarios for Taylorsville, 1A Region 8 #1 seed, 2025.

    Ground truth comes from the 2025 1A playoff bracket.  The Semifinals game
    was ``(6, 1, 8, 1)`` — Simmons (Region 6 #1) hosted Taylorsville — so
    Simmons must appear in ``will_not_host`` for the Semifinals round.
    """

    @staticmethod
    def _result() -> list[RoundHomeScenarios]:
        """Run enumeration with the full 1A-2025 team-name lookup."""
        lookup = _team_lookup_for_class(1)
        return enumerate_home_game_scenarios(8, 1, SLOTS_1A_4A_2025, SEASON, team_lookup=lookup)

    # --- R1 ---

    def test_r1_unconditional_will_host(self):
        """Taylorsville is the designated home team in R1 — no conditions needed."""
        r1 = self._result()[0]
        assert r1.round_name == "First Round"
        assert len(r1.will_host) == 1
        assert len(r1.will_host[0].conditions) == 0
        assert r1.will_host[0].explanation == "Designated home team in bracket"

    def test_r1_empty_will_not_host(self):
        """Taylorsville has no will-not-host scenarios in R1."""
        r1 = self._result()[0]
        assert len(r1.will_not_host) == 0

    # --- R2 ---

    def test_r2_single_merged_will_host(self):
        """Both R2 opponents yield the same home outcome, so they merge into one scenario."""
        r2 = self._result()[1]
        assert r2.round_name == "Second Round"
        assert len(r2.will_host) == 1

    def test_r2_will_host_advances_condition(self):
        """R2 will_host has a single 'Taylorsville advances' condition (region/seed=None)."""
        r2 = self._result()[1]
        sc = r2.will_host[0]
        assert len(sc.conditions) == 1
        cond = sc.conditions[0]
        assert cond.kind == "advances"
        assert cond.region is None
        assert cond.seed is None
        assert cond.round_name == "Second Round"

    def test_r2_will_host_explanation(self):
        """R2 will_host explanation is the higher-seed hosting rule."""
        r2 = self._result()[1]
        assert r2.will_host[0].explanation == "Higher seed (#1) hosts"

    def test_r2_empty_will_not_host(self):
        """Taylorsville has no will-not-host scenarios in R2 (always hosts as #1 seed)."""
        r2 = self._result()[1]
        assert len(r2.will_not_host) == 0

    # --- QF ---

    def test_qf_two_will_host_scenarios(self):
        """QF has exactly two will-host paths (Richton and Leake County)."""
        qf = self._result()[2]
        assert qf.round_name == "Quarterfinals"
        assert len(qf.will_host) == 2

    def test_qf_three_will_not_host_scenarios(self):
        """QF has exactly three will-not-host paths.

        Bogue Chitto and Shaw are single scenarios; Leake County gains a second
        scenario (via the Bogue Chitto R2 path) because that sub-case produces
        a different QF hosting outcome than the Richton R2 path.
        """
        qf = self._result()[2]
        assert len(qf.will_not_host) == 3

    def test_qf_will_host_richton(self):
        """Taylorsville hosts if Richton (Region 8 #4) advances — same-region rule."""
        qf = self._result()[2]
        opponent_pairs = {
            (c.region, c.seed)
            for sc in qf.will_host
            for c in sc.conditions
            if c.region is not None
        }
        assert (8, 4) in opponent_pairs

    def test_qf_will_host_richton_explanation(self):
        """Same-region game — higher seed (#1) hosts."""
        qf = self._result()[2]
        sc = next(
            sc for sc in qf.will_host
            if any(c.region == 8 and c.seed == 4 for c in sc.conditions)
        )
        assert sc.explanation == "Same-region game — higher seed (#1) hosts"

    def test_qf_will_host_leake_county(self):
        """Taylorsville hosts if Leake County advances via the Richton (R8#4) R2 path.

        When Richton (R8#4) wins R1 and Leake County beats them in R2, Leake
        County has 2 home games entering the QF (R1 home + R2 home).  Equal
        home-game counts send the tiebreak to seed: Taylorsville (#1) hosts.
        The will_host scenario for Leake County must include a condition that
        Richton advances to the Second Round.
        """
        qf = self._result()[2]
        leake_host_sc = next(
            sc for sc in qf.will_host
            if any(c.region == 5 and c.seed == 2 for c in sc.conditions)
        )
        # The scenario must include both the R1-winner (Richton) and Leake County.
        r2_cond_names = {c.team_name for c in leake_host_sc.conditions if c.round_name == "Second Round"}
        assert "Richton" in r2_cond_names

    def test_qf_will_host_leake_county_explanation(self):
        """Cross-region, #1 vs #2, equal home-game counts — higher seed (#1) hosts."""
        qf = self._result()[2]
        sc = next(
            sc for sc in qf.will_host
            if any(c.region == 5 and c.seed == 2 for c in sc.conditions)
        )
        assert sc.explanation == "Higher seed (#1) hosts"

    def test_qf_will_not_host_leake_county_via_bogue_chitto(self):
        """Leake County also appears in will_not_host when Bogue Chitto wins R1.

        When Bogue Chitto (R7#1) wins R1 and Leake County beats them in R2,
        Leake County is the away team in R2 (1 home game entering QF).  That
        gives Leake County fewer home games than Taylorsville (1 vs 2), so
        Leake County hosts — Taylorsville is away.  This path must include a
        condition that Bogue Chitto advances to the Second Round.
        """
        qf = self._result()[2]
        leake_away_sc = next(
            sc for sc in qf.will_not_host
            if any(c.region == 5 and c.seed == 2 for c in sc.conditions)
        )
        r2_cond_names = {c.team_name for c in leake_away_sc.conditions if c.round_name == "Second Round"}
        assert "Bogue Chitto" in r2_cond_names

    def test_qf_will_not_host_leake_county_via_bogue_chitto_explanation(self):
        """Leake County had 1 home game (Bogue Chitto path) vs Taylorsville's 2 — LC hosts."""
        qf = self._result()[2]
        sc = next(
            sc for sc in qf.will_not_host
            if any(c.region == 5 and c.seed == 2 for c in sc.conditions)
        )
        assert sc.explanation == "Fewer home games played (1 vs 2) — opponent hosts"

    def test_qf_will_not_host_bogue_chitto(self):
        """Taylorsville is away if Bogue Chitto (Region 7 #1) advances — region tiebreak."""
        qf = self._result()[2]
        opponent_pairs = {
            (c.region, c.seed)
            for sc in qf.will_not_host
            for c in sc.conditions
            if c.region is not None
        }
        assert (7, 1) in opponent_pairs

    def test_qf_will_not_host_bogue_chitto_explanation(self):
        """Equal #1 seeds — odd year region tiebreak: lower region# (Region 7) hosts."""
        qf = self._result()[2]
        sc = next(
            sc for sc in qf.will_not_host
            if any(c.region == 7 and c.seed == 1 for c in sc.conditions)
        )
        assert sc.explanation == (
            "Equal seed (#1) — region tiebreak: odd year, lower region# hosts (Region 7)"
        )

    def test_qf_will_not_host_shaw(self):
        """Taylorsville is away if Shaw (Region 6 #3) advances — fewer home games rule."""
        qf = self._result()[2]
        opponent_pairs = {
            (c.region, c.seed)
            for sc in qf.will_not_host
            for c in sc.conditions
            if c.region is not None
        }
        assert (6, 3) in opponent_pairs

    def test_qf_will_not_host_shaw_explanation(self):
        """Shaw has fewer home games than Taylorsville regardless of Shaw's R2 path.

        Shaw (R6#3) is the away team in R1.  In R2 Shaw faces the winner of
        (R7#1 vs R8#4).  Both sub-cases produce the same QF outcome (Shaw
        hosts), so the scenarios are collapsed.  The algorithm uses the first
        R2 option (R7#1 wins R1 → Shaw is away in R2 → 0 home games entering QF).
        """
        qf = self._result()[2]
        sc = next(
            sc for sc in qf.will_not_host
            if any(c.region == 6 and c.seed == 3 for c in sc.conditions)
        )
        assert sc.explanation == "Fewer home games played (0 vs 2) — opponent hosts"

    def test_qf_will_host_team_names_resolved(self):
        """Team names in QF conditions should be resolved from team_lookup."""
        qf = self._result()[2]
        all_names = {
            c.team_name
            for sc in list(qf.will_host) + list(qf.will_not_host)
            for c in sc.conditions
            if c.team_name is not None
        }
        assert "Richton" in all_names
        assert "Leake County" in all_names
        assert "Bogue Chitto" in all_names
        assert "Shaw" in all_names

    # --- SF ---

    def test_sf_six_will_host_scenarios(self):
        """SF has exactly 6 will-host paths."""
        sf = self._result()[3]
        assert sf.round_name == "Semifinals"
        assert len(sf.will_host) == 6

    def test_sf_two_will_not_host_scenarios(self):
        """SF has exactly 2 will-not-host paths (equal #1 seeds in lower regions)."""
        sf = self._result()[3]
        assert len(sf.will_not_host) == 2

    def test_sf_will_host_opponents(self):
        """The 6 will-host SF opponents are West Bolivar, Salem, Lumberton, Noxapater, Stringer, Mount Olive."""
        sf = self._result()[3]
        host_opponents = {
            (c.region, c.seed)
            for sc in sf.will_host
            for c in sc.conditions
            if c.region is not None
        }
        expected = {(6, 4), (7, 2), (8, 3), (5, 4), (8, 2), (7, 3)}
        assert host_opponents == expected

    def test_sf_will_host_team_names(self):
        """Will-host SF opponents appear with their resolved school names."""
        sf = self._result()[3]
        host_names = {
            c.team_name
            for sc in sf.will_host
            for c in sc.conditions
            if c.team_name is not None
        }
        assert host_names == {
            "West Bolivar",
            "Salem",
            "Lumberton",
            "Noxapater",
            "Stringer",
            "Mount Olive",
        }

    def test_sf_will_not_host_nanih_waiya(self):
        """Nanih Waiya (Region 5 #1) is in will_not_host — equal seed, Region 5 < Region 8."""
        sf = self._result()[3]
        opponent_pairs = {
            (c.region, c.seed)
            for sc in sf.will_not_host
            for c in sc.conditions
            if c.region is not None
        }
        assert (5, 1) in opponent_pairs

    def test_sf_will_not_host_nanih_waiya_explanation(self):
        """Odd year, lower region# (Region 5) hosts over Region 8."""
        sf = self._result()[3]
        sc = next(
            sc for sc in sf.will_not_host
            if any(c.region == 5 and c.seed == 1 for c in sc.conditions)
        )
        assert sc.explanation == (
            "Equal seed (#1) — region tiebreak: odd year, lower region# hosts (Region 5)"
        )

    def test_sf_will_not_host_simmons(self):
        """Simmons (Region 6 #1) is in will_not_host — matches actual 2025 result."""
        sf = self._result()[3]
        opponent_pairs = {
            (c.region, c.seed)
            for sc in sf.will_not_host
            for c in sc.conditions
            if c.region is not None
        }
        assert (6, 1) in opponent_pairs

    def test_sf_will_not_host_simmons_explanation(self):
        """Odd year, lower region# (Region 6) hosts over Region 8."""
        sf = self._result()[3]
        sc = next(
            sc for sc in sf.will_not_host
            if any(c.region == 6 and c.seed == 1 for c in sc.conditions)
        )
        assert sc.explanation == (
            "Equal seed (#1) — region tiebreak: odd year, lower region# hosts (Region 6)"
        )

    def test_sf_ground_truth_simmons_hosted_2025(self):
        """2025 bracket: game (6,1,8,1) — Simmons hosted Taylorsville in the SF.

        Simmons is Region 6 #1.  Taylorsville is Region 8 #1.  Simmons appears
        in ``will_not_host`` as expected; ``_actual_home`` returns False for
        Taylorsville, confirming the bracket data agrees.
        """
        assert _actual_home(1, "semifinals", 8, 1) is False, (
            "2025 bracket: Taylorsville (R8#1) was away in the SF — Simmons hosted"
        )
        sf = self._result()[3]
        not_host_opponents = {
            (c.region, c.seed)
            for sc in sf.will_not_host
            for c in sc.conditions
            if c.region is not None
        }
        assert (6, 1) in not_host_opponents, "Simmons (R6#1) must be in SF will_not_host"


# ---------------------------------------------------------------------------
# 12. Even-year tiebreak (lines 198-199, 231-232 in home_game_scenarios.py;
#     lines 570, 608 in bracket_home_odds.py)
# ---------------------------------------------------------------------------
#
# The equal-seed cross-region QF/SF tiebreak uses odd/even year:
#   odd year  → lower region# hosts
#   even year → higher region# hosts (the uncovered branch)
#
# 5A-7A SF case: R1s2 (slot 4) can face R2s2 in the SF — seeds equal, cross-region.
#   Odd year (2025): Region 1 hosts.  Even year (2024): Region 2 hosts.
#
# 1A-4A QF case: R3s2 (slot 2) can face R4s2 in the QF — seeds equal, cross-region.
#   Odd year (2025): Region 3 hosts.  Even year (2024): Region 4 hosts.

EVEN_SEASON = 2024


class TestEvenYearTiebreak:
    """Cover even-year QF/SF explanation paths in home_game_scenarios and bracket_home_odds."""

    def test_sf_even_year_explanation_present_5a7a(self):
        """R1s2 SF: even year produces an 'even year' explanation in will_not_host."""
        result = enumerate_home_game_scenarios(1, 2, SLOTS_5A_7A_2025, EVEN_SEASON)
        sf = result[2]  # First Round (0), QF (1), SF (2)
        even_year_explanations = [
            sc.explanation
            for sc in sf.will_not_host
            if sc.explanation and "even year" in sc.explanation
        ]
        assert len(even_year_explanations) >= 1, (
            "Expected at least one SF will_not_host scenario with an 'even year' explanation"
        )

    def test_sf_even_year_names_higher_region_as_host_5a7a(self):
        """Even-year SF explanation says Region 2 (higher region#) hosts vs R1s2."""
        result = enumerate_home_game_scenarios(1, 2, SLOTS_5A_7A_2025, EVEN_SEASON)
        sf = result[2]
        even_year_explanations = [
            sc.explanation
            for sc in sf.will_not_host
            if sc.explanation and "even year" in sc.explanation
        ]
        assert any("Region 2" in exp for exp in even_year_explanations), (
            f"Expected explanation to name Region 2 as host; got: {even_year_explanations}"
        )

    def test_sf_odd_year_no_even_year_explanation_5a7a(self):
        """With odd-year season (2025), no SF explanation should mention 'even year'."""
        result = enumerate_home_game_scenarios(1, 2, SLOTS_5A_7A_2025, SEASON)
        sf = result[2]
        even_year_explanations = [
            sc.explanation
            for sc in list(sf.will_host) + list(sf.will_not_host)
            if sc.explanation and "even year" in sc.explanation
        ]
        assert even_year_explanations == [], (
            f"Unexpected even-year explanation with odd season: {even_year_explanations}"
        )

    def test_qf_even_year_explanation_present_1a4a(self):
        """R3s2 QF: even year produces an 'even year' explanation in will_not_host."""
        # R3s2 is in slot 2 (1A-4A North); QF opponents include R4s2 (equal seed, cross-region).
        result = enumerate_home_game_scenarios(3, 2, SLOTS_1A_4A_2025, EVEN_SEASON)
        qf = result[2]  # First Round (0), R2 (1), QF (2), SF (3)
        even_year_explanations = [
            sc.explanation
            for sc in qf.will_not_host
            if sc.explanation and "even year" in sc.explanation
        ]
        assert len(even_year_explanations) >= 1, (
            "Expected at least one QF will_not_host scenario with an 'even year' explanation"
        )

    def test_qf_even_year_names_higher_region_as_host_1a4a(self):
        """Even-year QF explanation says Region 4 (higher region#) hosts vs R3s2."""
        result = enumerate_home_game_scenarios(3, 2, SLOTS_1A_4A_2025, EVEN_SEASON)
        qf = result[2]
        even_year_explanations = [
            sc.explanation
            for sc in qf.will_not_host
            if sc.explanation and "even year" in sc.explanation
        ]
        assert any("Region 4" in exp for exp in even_year_explanations), (
            f"Expected explanation to name Region 4 as host; got: {even_year_explanations}"
        )

    def test_qf_odd_year_no_even_year_explanation_1a4a(self):
        """With odd-year season (2025), no QF explanation should mention 'even year'."""
        result = enumerate_home_game_scenarios(3, 2, SLOTS_1A_4A_2025, SEASON)
        qf = result[2]
        even_year_explanations = [
            sc.explanation
            for sc in list(qf.will_host) + list(qf.will_not_host)
            if sc.explanation and "even year" in sc.explanation
        ]
        assert even_year_explanations == [], (
            f"Unexpected even-year explanation with odd season: {even_year_explanations}"
        )


# ---------------------------------------------------------------------------
# 12. _explain_r2 — same-region and equal-seed branches (lines 143–144, 149–150)
# ---------------------------------------------------------------------------


class TestExplainR2:
    """Direct unit tests for the private _explain_r2 helper.

    The standard different-region / different-seed branch (lines 145–147) is
    already exercised via 1A-4A second-round tests.  This class targets the
    two remaining branches:
      - same-region R2 game (lines 143–144)
      - cross-region equal-seed tiebreak (lines 149–150)
    """

    def test_same_region_higher_seed_hosts(self):
        """Same-region R2: the lower seed# (better seed) hosts — lines 143–144."""
        result = _explain_r2(team_region=1, team_seed=2, opp_region=1, opp_seed=3, season=SEASON)
        assert result == "Same-region game — higher seed (#2) hosts"

    def test_same_region_team_is_lower_seed(self):
        """Same-region R2: explanation correct when team is the worse seed — lines 143–144."""
        result = _explain_r2(team_region=2, team_seed=4, opp_region=2, opp_seed=1, season=SEASON)
        assert result == "Same-region game — higher seed (#1) hosts"

    def test_equal_seed_cross_region_odd_year_lower_region_hosts(self):
        """Cross-region equal-seed, odd year: lower region# hosts — lines 149–150."""
        result = _explain_r2(team_region=2, team_seed=2, opp_region=3, opp_seed=2, season=2025)
        assert result == "Equal seed (#2) — region tiebreak: odd year, lower region# hosts (Region 2)"

    def test_equal_seed_cross_region_even_year_higher_region_hosts(self):
        """Cross-region equal-seed, even year: higher region# hosts — lines 149–150."""
        result = _explain_r2(team_region=2, team_seed=2, opp_region=3, opp_seed=2, season=2024)
        assert result == "Equal seed (#2) — region tiebreak: even year, higher region# hosts (Region 3)"

    def test_equal_seed_cross_region_names_correct_odd_host(self):
        """Odd year: host region is min(team_region, opp_region)."""
        result = _explain_r2(team_region=5, team_seed=3, opp_region=1, opp_seed=3, season=2025)
        assert result == "Equal seed (#3) — region tiebreak: odd year, lower region# hosts (Region 1)"

    def test_different_region_different_seed_unchanged(self):
        """Sanity-check: the covered branch still returns the expected string."""
        result = _explain_r2(team_region=1, team_seed=1, opp_region=2, opp_seed=3, season=SEASON)
        assert result == "Higher seed (#1) hosts"


# ---------------------------------------------------------------------------
# 13. SF dedup `continue` guards (lines 643, 920)
# ---------------------------------------------------------------------------

# Synthetic 4-slot bracket half where one (region, seed) pair appears in two
# different SF opponent slots.  Slot indices 0-3:
#   idx 0 — R1s1 vs R2s4   (slot 1)
#   idx 1 — R1s1 vs R1s3   (slot 2)  ← R1s1 appears again → dedup fires
#   idx 2 — R2s1 vs R1s4   (slot 3)
#   idx 3 — R1s2 vs R2s3   (slot 4)  ← target team
#
# For R1s2 (idx 3), sf_round_offset = log2(4) = 2, so
# opponent_slot_indices(3, 2) covers indices [0, 1].
# Both slots 0 and 1 list R1s1 as a team → `seen` fires on the second encounter.
_SF_DEDUP_SLOTS = [
    FormatSlot(slot=1, home_region=1, home_seed=1, away_region=2, away_seed=4, north_south="N"),
    FormatSlot(slot=2, home_region=1, home_seed=1, away_region=1, away_seed=3, north_south="N"),
    FormatSlot(slot=3, home_region=2, home_seed=1, away_region=1, away_seed=4, north_south="N"),
    FormatSlot(slot=4, home_region=1, home_seed=2, away_region=2, away_seed=3, north_south="N"),
]


class TestSFDedupGuard:
    """Tests that exercise the `seen` duplicate-opponent guard in the SF builders.

    With _SF_DEDUP_SLOTS, R1s2's SF opponent pool is slots 0 and 1 (indices 0
    and 1).  Both slots contain R1s1, so the second encounter triggers the
    `continue` at line 643 (_enumerate_sf) and line 920 (_matchup_raw_sf).
    The resulting scenario list must have exactly 3 unique opponents (R1s1,
    R2s4, R1s3) rather than 4.
    """

    def test_enumerate_sf_dedup_fires_correct_opponent_count(self):
        """enumerate_home_game_scenarios: R1s2 has 3 unique SF opponents, not 4 (line 643)."""
        result = enumerate_home_game_scenarios(1, 2, _SF_DEDUP_SLOTS, SEASON)
        sf = result[-1]  # last round = Semifinals
        assert sf.round_name == "Semifinals"
        total_scenarios = len(sf.will_host) + len(sf.will_not_host)
        assert total_scenarios == 3, (
            f"Expected 3 unique SF opponents after dedup; got {total_scenarios}"
        )

    def test_enumerate_sf_dedup_r1s1_appears_once(self):
        """After dedup, R1s1 appears exactly once in the SF scenario list (line 643)."""
        result = enumerate_home_game_scenarios(1, 2, _SF_DEDUP_SLOTS, SEASON)
        sf = result[-1]
        all_scenarios = list(sf.will_host) + list(sf.will_not_host)
        # Each scenario has conditions (team_cond, opp_cond); opp_cond carries region/seed
        r1s1_count = sum(
            1 for sc in all_scenarios
            for cond in sc.conditions
            if cond.region == 1 and cond.seed == 1
        )
        assert r1s1_count == 1, f"R1s1 should appear exactly once; found {r1s1_count}"

    def test_matchup_raw_sf_dedup_fires_correct_opponent_count(self):
        """enumerate_team_matchups: R1s2 has 3 unique SF matchup entries, not 4 (line 920)."""
        result = enumerate_team_matchups(1, 2, _SF_DEDUP_SLOTS, SEASON)
        sf = result[-1]  # last round = Semifinals
        assert sf.round_name == "Semifinals"
        assert len(sf.entries) == 3, (
            f"Expected 3 unique SF matchup entries after dedup; got {len(sf.entries)}"
        )

    def test_matchup_raw_sf_dedup_r1s1_appears_once(self):
        """After dedup, R1s1 appears exactly once in enumerate_team_matchups SF results (line 920)."""
        result = enumerate_team_matchups(1, 2, _SF_DEDUP_SLOTS, SEASON)
        sf = result[-1]
        r1s1_count = sum(
            1 for m in sf.entries
            if m.opponent_region == 1 and m.opponent_seed == 1
        )
        assert r1s1_count == 1, f"R1s1 should appear exactly once; found {r1s1_count}"
