"""Tests for the pre-playoff (seed=None) path of enumerate_home_game_scenarios.

Uses Taylorsville (1A, Region 8, 2025) as the primary fixture.  With one
remaining week before the 2025-10-24 cutoff, Taylorsville can finish as seed 1
(p≈72.9%) or seed 2 (p≈27.1%).  Both Region 8 seeds 1 and 2 are the
designated home team in their first-round bracket slots, making R1 a clean
case: will_host has exactly 2 scenarios (one per seed path), will_not_host is
empty.

Coverage
--------
1. ValueError when seed=None but achievable_seeds is missing/empty.
2. Return value has the correct number of rounds (4 for 1A-4A).
3. Every scenario in every round starts with a seed_required condition.
4. seed_required conditions reference the correct seeds from achievable_seeds.
5. R1 home/away split is correct for Region 8 (both seeds 1 and 2 are home).
6. R2 scenarios exist for each possible R2 opponent (seed 2 path has split).
7. Renderer substitutes the team name for "Team" in seed_required conditions.
8. Aggregate odds pass through to the merged RoundHomeScenarios unchanged.
9. Post-playoff path (seed is not None) is unaffected — existing behaviour.
"""

import pytest

from backend.helpers.data_classes import RoundHomeScenarios
from backend.helpers.home_game_scenarios import enumerate_home_game_scenarios
from backend.helpers.scenario_renderer import render_team_home_scenarios
from backend.tests.data.playoff_brackets_2025 import SLOTS_1A_4A_2025, SLOTS_5A_7A_2025

SEASON = 2025
REGION = 8
# Taylorsville can finish as #1 or #2; Richton is always #4 (achievable from
# team's perspective, but not testable here), Resurrection is always out.
ACHIEVABLE_SEEDS = [1, 2]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scenarios(achievable_seeds=ACHIEVABLE_SEEDS, **kwargs) -> list[RoundHomeScenarios]:
    """Call enumerate_home_game_scenarios for Region 8, seed=None, with default achievable_seeds."""
    return enumerate_home_game_scenarios(
        region=REGION,
        seed=None,
        slots=SLOTS_1A_4A_2025,
        season=SEASON,
        achievable_seeds=achievable_seeds,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. Error handling
# ---------------------------------------------------------------------------


class TestPrePlayoffErrors:
    """seed=None requires a non-empty achievable_seeds list."""

    def test_raises_when_achievable_seeds_missing(self):
        """Omitting achievable_seeds raises ValueError mentioning 'achievable_seeds'."""
        with pytest.raises(ValueError, match="achievable_seeds"):
            enumerate_home_game_scenarios(region=REGION, seed=None, slots=SLOTS_1A_4A_2025, season=SEASON)

    def test_raises_when_achievable_seeds_empty(self):
        """Passing achievable_seeds=[] raises ValueError mentioning 'achievable_seeds'."""
        with pytest.raises(ValueError, match="achievable_seeds"):
            enumerate_home_game_scenarios(
                region=REGION,
                seed=None,
                slots=SLOTS_1A_4A_2025,
                season=SEASON,
                achievable_seeds=[],
            )


# ---------------------------------------------------------------------------
# 2. Round structure
# ---------------------------------------------------------------------------


class TestRoundStructure:
    """Return value has the correct round count and names for 1A–4A brackets."""

    def test_returns_four_rounds_for_1a_4a(self):
        """1A–4A bracket returns exactly four rounds."""
        rounds = _scenarios()
        assert len(rounds) == 4

    def test_round_names_are_correct(self):
        """Round names follow the canonical 1A–4A order."""
        rounds = _scenarios()
        assert [r.round_name for r in rounds] == ["First Round", "Second Round", "Quarterfinals", "Semifinals"]

    def test_single_seed_returns_same_count_as_post_playoff(self):
        """Pre-playoff with one seed should produce same scenario count as post-playoff."""
        pre = enumerate_home_game_scenarios(
            region=REGION,
            seed=None,
            slots=SLOTS_1A_4A_2025,
            season=SEASON,
            achievable_seeds=[1],
        )
        post = enumerate_home_game_scenarios(
            region=REGION,
            seed=1,
            slots=SLOTS_1A_4A_2025,
            season=SEASON,
        )
        for pre_round, post_round in zip(pre, post):
            assert len(pre_round.will_host) == len(post_round.will_host)
            assert len(pre_round.will_not_host) == len(post_round.will_not_host)


# ---------------------------------------------------------------------------
# 3 & 4. seed_required condition is always first, with correct seed values
# ---------------------------------------------------------------------------


class TestSeedRequiredCondition:
    """Every scenario in seed=None mode begins with a seed_required condition."""

    def test_every_scenario_starts_with_seed_required(self):
        """First condition of every scenario across all rounds has kind='seed_required'."""
        rounds = _scenarios()
        for rnd in rounds:
            for sc in rnd.will_host + rnd.will_not_host:
                assert len(sc.conditions) >= 1
                first = sc.conditions[0]
                assert first.kind == "seed_required"

    def test_seed_required_seeds_match_achievable_seeds(self):
        """seed_required conditions only reference seeds from achievable_seeds, and all are used."""
        rounds = _scenarios()
        used_seeds: set[int] = set()
        for rnd in rounds:
            for sc in rnd.will_host + rnd.will_not_host:
                cond = sc.conditions[0]
                assert cond.kind == "seed_required"
                assert cond.seed in ACHIEVABLE_SEEDS
                used_seeds.add(cond.seed)
        # Both achievable seeds must appear somewhere across all rounds
        assert used_seeds == set(ACHIEVABLE_SEEDS)

    def test_seed_required_region_and_team_name_are_none(self):
        """region=None / team_name=None triggers the target-team substitution path."""
        rounds = _scenarios()
        for rnd in rounds:
            for sc in rnd.will_host + rnd.will_not_host:
                first = sc.conditions[0]
                assert first.region is None
                assert first.team_name is None


# ---------------------------------------------------------------------------
# 5. First-round home/away split for Region 8
# ---------------------------------------------------------------------------


class TestFirstRound:
    """First-round home/away split for Region 8 (both seeds 1 and 2 are home)."""

    def test_both_seeds_are_home_in_r1(self):
        """Region 8 seeds 1 and 2 are both in home slots → all R1 scenarios are will_host."""
        r1 = _scenarios()[0]
        assert r1.round_name == "First Round"
        assert len(r1.will_host) == 2
        assert len(r1.will_not_host) == 0

    def test_r1_will_host_seeds_are_1_and_2(self):
        """The two will_host scenarios cover seed paths 1 and 2."""
        r1 = _scenarios()[0]
        seeds = {sc.conditions[0].seed for sc in r1.will_host}
        assert seeds == {1, 2}

    def test_r1_scenarios_have_only_seed_required_condition(self):
        """R1 is unconditional once the seed is known — only the seed_required prefix."""
        r1 = _scenarios()[0]
        for sc in r1.will_host:
            assert len(sc.conditions) == 1
            assert sc.conditions[0].kind == "seed_required"


# ---------------------------------------------------------------------------
# 6. Second-round scenarios for Region 8
# ---------------------------------------------------------------------------


class TestSecondRound:
    """Second-round scenarios: seed-1 always hosts; seed-2 path can split home/away."""

    def test_r2_has_scenarios_in_both_buckets(self):
        """Seed-1 path is always home in R2; seed-2 path may split."""
        r2 = _scenarios()[1]
        assert r2.round_name == "Second Round"
        # At minimum seed 1 contributes a will_host scenario
        assert len(r2.will_host) >= 1

    def test_r2_seed1_always_hosts(self):
        """Seed 1 is the best seed; always home in R2 regardless of opponent."""
        r2 = _scenarios()[1]
        seed1_host_scenarios = [sc for sc in r2.will_host if sc.conditions[0].seed == 1]
        assert len(seed1_host_scenarios) >= 1

    def test_r2_seed2_has_both_host_and_away_paths(self):
        """Seed 2 hosts if facing seed 4, is away if facing seed 1."""
        r2 = _scenarios()[1]
        seed2_host = [sc for sc in r2.will_host if sc.conditions[0].seed == 2]
        seed2_away = [sc for sc in r2.will_not_host if sc.conditions[0].seed == 2]
        assert len(seed2_host) >= 1
        assert len(seed2_away) >= 1

    def test_r2_conditions_include_advances_after_seed_required(self):
        """Beyond seed_required, each R2 scenario must include an 'advances' condition."""
        r2 = _scenarios()[1]
        for sc in r2.will_host + r2.will_not_host:
            kinds = [c.kind for c in sc.conditions]
            assert kinds[0] == "seed_required"
            assert "advances" in kinds[1:]


# ---------------------------------------------------------------------------
# 7. Renderer output
# ---------------------------------------------------------------------------


class TestRenderer:
    """render_team_home_scenarios output for the pre-playoff (seed=None) path."""

    def test_renderer_substitutes_team_name_for_seed_required(self):
        """'Team finishes as the #N seed' becomes 'Taylorsville finishes as the #N seed'."""
        rounds = _scenarios()
        rendered = render_team_home_scenarios("Taylorsville", rounds)
        assert "Taylorsville finishes as the #1 seed" in rendered
        assert "Taylorsville finishes as the #2 seed" in rendered

    def test_rendered_output_does_not_contain_raw_team_placeholder(self):
        """Raw 'Team finishes' placeholder is never present in rendered output."""
        rounds = _scenarios()
        rendered = render_team_home_scenarios("Taylorsville", rounds)
        assert "Team finishes" not in rendered

    def test_renderer_includes_all_four_round_headers(self):
        """All four round names appear as section headers in the rendered string."""
        rounds = _scenarios()
        rendered = render_team_home_scenarios("Taylorsville", rounds)
        for name in ("First Round", "Second Round", "Quarterfinals", "Semifinals"):
            assert name in rendered

    def test_renderer_with_team_lookup(self):
        """When team_lookup is provided, opponent names appear instead of generic labels."""
        lookup = {
            (7, 1): "South Pike",
            (7, 2): "Louin",
            (7, 3): "Stonewall",
            (7, 4): "Enterprise",
            (5, 3): "Lumberton",
            (5, 4): "Richton",
            (6, 1): "West Marion",
            (6, 2): "Prentiss",
        }
        rounds = enumerate_home_game_scenarios(
            region=REGION,
            seed=None,
            slots=SLOTS_1A_4A_2025,
            season=SEASON,
            achievable_seeds=ACHIEVABLE_SEEDS,
            team_lookup=lookup,
        )
        rendered = render_team_home_scenarios("Taylorsville", rounds)
        # At least one resolved name should appear in the conditions
        opponent_names = list(lookup.values())
        assert any(name in rendered for name in opponent_names)


# ---------------------------------------------------------------------------
# 8. Odds pass-through
# ---------------------------------------------------------------------------


class TestOddsPassthrough:
    """Caller-supplied odds dicts are forwarded unchanged to each RoundHomeScenarios."""

    def test_aggregate_odds_appear_on_merged_rounds(self):
        """p_reach and p_host_conditional supplied to enumerate_home_game_scenarios appear on each round."""
        p_reach = {"First Round": 1.0, "Second Round": 0.5, "Quarterfinals": 0.25, "Semifinals": 0.125}
        p_host_cond = {"First Round": 1.0, "Second Round": 0.6, "Quarterfinals": 0.5, "Semifinals": 0.4}
        rounds = _scenarios(
            p_reach_by_round=p_reach,
            p_host_conditional_by_round=p_host_cond,
        )
        for rnd in rounds:
            assert rnd.p_reach == p_reach[rnd.round_name]
            assert rnd.p_host_conditional == p_host_cond[rnd.round_name]

    def test_no_odds_means_none_fields(self):
        """Without odds dicts, p_reach / p_host_conditional / p_host_marginal are all None."""
        rounds = _scenarios()
        for rnd in rounds:
            assert rnd.p_reach is None
            assert rnd.p_host_conditional is None
            assert rnd.p_host_marginal is None


# ---------------------------------------------------------------------------
# 9. Post-playoff path is unaffected
# ---------------------------------------------------------------------------


class TestPostPlayoffUnchanged:
    """Passing an integer seed (post-playoff path) is unaffected by pre-playoff changes."""

    def test_post_playoff_still_works_with_seed_int(self):
        """Passing seed=1 (known) should still return valid scenarios."""
        rounds = enumerate_home_game_scenarios(
            region=REGION,
            seed=1,
            slots=SLOTS_1A_4A_2025,
            season=SEASON,
        )
        assert len(rounds) == 4
        r1 = rounds[0]
        # Seed 1 is home in slot 15
        assert len(r1.will_host) == 1
        assert len(r1.will_not_host) == 0
        # No seed_required condition in post-playoff mode
        for sc in r1.will_host:
            for cond in sc.conditions:
                assert cond.kind != "seed_required"

    def test_post_playoff_raises_for_invalid_seed(self):
        """seed=5 (out of range) raises ValueError in post-playoff mode."""
        with pytest.raises(ValueError):
            enumerate_home_game_scenarios(
                region=REGION,
                seed=5,
                slots=SLOTS_1A_4A_2025,
                season=SEASON,
            )


# ---------------------------------------------------------------------------
# 10. Combined renderer — Q1 snapshot / Q2 expansion / Q3 real odds
# ---------------------------------------------------------------------------
#
# Uses real 2025 Region 8-1A data: two remaining games at the 2025-10-24 cutoff
# (Taylorsville vs Lumberton and Stringer vs Resurrection), real seeding odds
# from PRE_FINAL_WEEK_EXPECTED, and real bracket hosting odds from the
# bracket_home_odds helpers.
#
# Atoms (from build_scenario_atoms):
#   Seed 1: "Taylorsville beats Lumberton"
#            "Stringer beats Resurrection AND Lumberton beats Taylorsville by 1–11"
#   Seed 2: "Lumberton beats Taylorsville by 12 or more"
#            "Resurrection beats Stringer AND Lumberton beats Taylorsville"


_CUTOFF_1_8 = "2025-10-24"

# Expected snapshot for "Will Host First Round" section (Q1).
_EXPECTED_R1_HOST = """\
Will Host First Round (100.0%):
1. Taylorsville beats Lumberton
   [Designated home team in bracket]
2. Stringer beats Resurrection AND Lumberton beats Taylorsville by 1\u201311
   [Designated home team in bracket]
3. Lumberton beats Taylorsville by 12 or more
   [Designated home team in bracket]
4. Resurrection beats Stringer AND Lumberton beats Taylorsville
   [Designated home team in bracket]"""

# Expected snapshot for "Will Host Second Round" section (Q1).
_EXPECTED_R2_HOST = """\
Will Host Second Round (43.2%):
1. Taylorsville beats Lumberton AND Taylorsville advances to Second Round
   [Higher seed (#1) hosts]
2. Stringer beats Resurrection AND Lumberton beats Taylorsville by 1\u201311 AND Taylorsville advances to Second Round
   [Higher seed (#1) hosts]
3. Lumberton beats Taylorsville by 12 or more AND Taylorsville advances to Second Round AND Region 5 #4 Seed advances to Second Round
   [Higher seed (#2) hosts]
4. Resurrection beats Stringer AND Lumberton beats Taylorsville AND Taylorsville advances to Second Round AND Region 5 #4 Seed advances to Second Round
   [Higher seed (#2) hosts]"""

# Expected snapshot for "Will Not Host Second Round" section (Q1).
_EXPECTED_R2_AWAY = """\
Will Not Host Second Round (56.8%):
1. Lumberton beats Taylorsville by 12 or more AND Taylorsville advances to Second Round AND Region 6 #1 Seed advances to Second Round
   [Higher seed (#1) hosts]
2. Resurrection beats Stringer AND Lumberton beats Taylorsville AND Taylorsville advances to Second Round AND Region 6 #1 Seed advances to Second Round
   [Higher seed (#1) hosts]"""


def _build_combined_render_fixtures():
    """Return (atoms, home_scenarios) for Taylorsville pre-final-week 2025."""
    from backend.helpers.bracket_home_odds import (
        compute_bracket_advancement_odds,
        compute_quarterfinal_home_odds,
        compute_second_round_home_odds,
        compute_semifinal_home_odds,
    )
    from backend.helpers.data_classes import RemainingGame
    from backend.helpers.data_helpers import get_completed_games
    from backend.helpers.scenario_viewer import build_scenario_atoms
    from backend.tests.data.pre_final_week_2025_expected import PRE_FINAL_WEEK_EXPECTED
    from backend.tests.data.results_2025_ground_truth import (
        REGION_RESULTS_2025,
        expand_results,
        teams_from_games,
    )

    fixture = REGION_RESULTS_2025[(1, 8)]
    all_games = fixture["games"]
    completed_compact = [g for g in all_games if g["date"] <= _CUTOFF_1_8]
    remaining_compact = [g for g in all_games if g["date"] > _CUTOFF_1_8]

    completed = get_completed_games(expand_results(completed_compact))
    remaining = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in remaining_compact]
    teams = teams_from_games(all_games)
    atoms = build_scenario_atoms(teams, completed, remaining)

    ODDS_8 = PRE_FINAL_WEEK_EXPECTED[(1, 8)]["odds"]
    tay = ODDS_8["Taylorsville"]
    ba = compute_bracket_advancement_odds(8, ODDS_8, SLOTS_1A_4A_2025)
    r2_host = compute_second_round_home_odds(8, ODDS_8, SLOTS_1A_4A_2025, SEASON)
    qf_host = compute_quarterfinal_home_odds(8, ODDS_8, SLOTS_1A_4A_2025, SEASON)
    sf_host = compute_semifinal_home_odds(8, ODDS_8, SLOTS_1A_4A_2025, SEASON)

    tay_ba = ba["Taylorsville"]
    p_reach = {
        "First Round": 1.0,
        "Second Round": tay_ba.second_round,
        "Quarterfinals": tay_ba.quarterfinals,
        "Semifinals": tay_ba.semifinals,
    }
    pm = {
        "First Round": tay.p1 + tay.p2,
        "Second Round": r2_host["Taylorsville"],
        "Quarterfinals": qf_host["Taylorsville"],
        "Semifinals": sf_host["Taylorsville"],
    }
    pc: dict[str, float] = {rn: pm[rn] / p_reach[rn] for rn in p_reach if p_reach[rn] > 0}

    home_scenarios = enumerate_home_game_scenarios(
        region=REGION,
        seed=None,
        slots=SLOTS_1A_4A_2025,
        season=SEASON,
        achievable_seeds=[1, 2],
        p_reach_by_round=p_reach,
        p_host_marginal_by_round=pm,
        p_host_conditional_by_round=pc,
    )
    return atoms, home_scenarios


class TestCombinedPrePlayoffRenderer:
    """Q1/Q2/Q3: snapshot test, atom expansion, and real odds for Taylorsville."""

    @pytest.fixture(scope="class")
    def fixtures(self):
        """Build (atoms, home_scenarios) once for the whole class."""
        return _build_combined_render_fixtures()

    @pytest.fixture(scope="class")
    def rendered(self, fixtures):
        """Render the combined pre-playoff output for Taylorsville once for the whole class."""
        from backend.helpers.scenario_renderer import render_pre_playoff_team_home_scenarios

        atoms, home_scenarios = fixtures
        return render_pre_playoff_team_home_scenarios("Taylorsville", home_scenarios, atoms)

    # Q2: combined renderer expands seed_required to game conditions

    def test_seed_required_not_in_combined_output(self, rendered):
        """Combined render never shows raw 'finishes as the #N seed' text."""
        assert "finishes as the #" not in rendered

    def test_r1_game_conditions_present(self, rendered):
        """R1 output shows actual game conditions, not seed placeholders."""
        assert "Taylorsville beats Lumberton" in rendered
        assert "Lumberton beats Taylorsville by 12 or more" in rendered
        assert "Resurrection beats Stringer AND Lumberton beats Taylorsville" in rendered

    def test_r1_has_four_scenarios(self, rendered):
        """R1 will_host has exactly 4 expanded scenarios (2 atoms × 2 seeds)."""
        r1_section = rendered.split("Will Host Second Round")[0]
        numbered = [ln for ln in r1_section.splitlines() if ln.startswith(("1.", "2.", "3.", "4.", "5."))]
        assert len(numbered) == 4

    def test_r2_conditions_are_expanded(self, rendered):
        """R2 scenarios show game conditions followed by playoff advance conditions."""
        assert "Taylorsville beats Lumberton AND Taylorsville advances to Second Round" in rendered

    # Q3: real odds appear in round headers

    def test_r1_shows_100_percent(self, rendered):
        """First Round header shows 100.0% (both achievable seeds are home)."""
        assert "Will Host First Round (100.0%)" in rendered

    def test_r2_host_shows_real_odds(self, rendered):
        """Second Round host header shows 43.2% (computed from real seeding odds)."""
        assert "Will Host Second Round (43.2%)" in rendered

    def test_r2_away_shows_real_odds(self, rendered):
        """Second Round away header shows 56.8% (complement of 43.2%)."""
        assert "Will Not Host Second Round (56.8%)" in rendered

    def test_qf_odds_present(self, rendered):
        """Quarterfinal headers include non-trivial hosting odds."""
        assert "Will Host Quarterfinals (9.8%)" in rendered
        assert "Will Not Host Quarterfinals (90.2%)" in rendered

    def test_sf_odds_present(self, rendered):
        """Semifinal headers include non-trivial hosting odds."""
        assert "Will Host Semifinals (8.5%)" in rendered
        assert "Will Not Host Semifinals (91.5%)" in rendered

    # Q1: snapshot tests for R1 and R2 sections

    def test_snapshot_r1_host(self, rendered):
        """Exact snapshot of Will Host First Round section."""
        assert _EXPECTED_R1_HOST in rendered

    def test_snapshot_r2_host(self, rendered):
        """Exact snapshot of Will Host Second Round section."""
        assert _EXPECTED_R2_HOST in rendered

    def test_snapshot_r2_away(self, rendered):
        """Exact snapshot of Will Not Host Second Round section."""
        assert _EXPECTED_R2_AWAY in rendered

    # team_lookup substitution in combined renderer

    def test_team_lookup_replaces_generic_seed_label(self):
        """Clinched opponent names substitute 'Region X #Y Seed' in expanded conditions."""
        from backend.helpers.scenario_renderer import render_pre_playoff_team_home_scenarios

        lookup = {(5, 4): "Newton County"}
        atoms, _ = _build_combined_render_fixtures()
        # Re-enumerate with the lookup so the name is baked into conditions.
        home_scenarios_with_lookup = enumerate_home_game_scenarios(
            region=REGION,
            seed=None,
            slots=SLOTS_1A_4A_2025,
            season=SEASON,
            achievable_seeds=ACHIEVABLE_SEEDS,
            team_lookup=lookup,
        )
        rendered = render_pre_playoff_team_home_scenarios("Taylorsville", home_scenarios_with_lookup, atoms)
        assert "Region 5 #4 Newton County advances to Second Round" in rendered
        assert "Region 5 #4 Seed advances to Second Round" not in rendered

    def test_team_lookup_only_replaces_named_seeds(self):
        """Seeds absent from team_lookup keep the 'Region X #Y Seed' fallback label."""
        from backend.helpers.scenario_renderer import render_pre_playoff_team_home_scenarios

        lookup = {(5, 4): "Newton County"}  # only (5,4) is named
        atoms, _ = _build_combined_render_fixtures()
        home_scenarios_with_lookup = enumerate_home_game_scenarios(
            region=REGION,
            seed=None,
            slots=SLOTS_1A_4A_2025,
            season=SEASON,
            achievable_seeds=ACHIEVABLE_SEEDS,
            team_lookup=lookup,
        )
        rendered = render_pre_playoff_team_home_scenarios("Taylorsville", home_scenarios_with_lookup, atoms)
        # (6,1) was not in the lookup — generic label must still appear somewhere
        assert "Region 6 #1 Seed advances to" in rendered


# ---------------------------------------------------------------------------
# 11. 5A–7A pre-playoff path (is_1a_4a=False, branch 793→799)
# ---------------------------------------------------------------------------


class TestFiveSevenAPrePlayoff:
    """Exercises the seed=None path for a 5A–7A bracket (no Second Round)."""

    def test_returns_three_rounds_for_5a_7a(self):
        """5A–7A bracket has three rounds (no Second Round)."""
        rounds = enumerate_home_game_scenarios(
            region=1,
            seed=None,
            slots=SLOTS_5A_7A_2025,
            season=SEASON,
            achievable_seeds=[1, 2],
        )
        assert len(rounds) == 3
        assert [r.round_name for r in rounds] == ["First Round", "Quarterfinals", "Semifinals"]

    def test_no_second_round_in_5a_7a(self):
        """'Second Round' does not appear in the round names for a 5A–7A bracket."""
        rounds = enumerate_home_game_scenarios(
            region=1,
            seed=None,
            slots=SLOTS_5A_7A_2025,
            season=SEASON,
            achievable_seeds=[1, 2],
        )
        assert "Second Round" not in [r.round_name for r in rounds]

    def test_every_scenario_starts_with_seed_required_5a_7a(self):
        """seed_required is the first condition in every scenario for 5A–7A brackets."""
        rounds = enumerate_home_game_scenarios(
            region=1,
            seed=None,
            slots=SLOTS_5A_7A_2025,
            season=SEASON,
            achievable_seeds=[1, 2],
        )
        for rnd in rounds:
            for sc in rnd.will_host + rnd.will_not_host:
                assert sc.conditions[0].kind == "seed_required"


# ---------------------------------------------------------------------------
# 12. Unrecognised seed in achievable_seeds is silently skipped (line 783)
# ---------------------------------------------------------------------------


class TestUnknownSeedSkipped:
    """Seed values not present in the bracket half-slots are ignored via `continue`."""

    def test_unknown_seed_does_not_crash(self):
        """A seed not present in the bracket slots (99) is silently skipped without raising."""
        rounds = enumerate_home_game_scenarios(
            region=1,
            seed=None,
            slots=SLOTS_5A_7A_2025,
            season=SEASON,
            achievable_seeds=[1, 99],
        )
        assert len(rounds) == 3

    def test_unknown_seed_produces_no_scenarios(self):
        """No scenario has a seed_required condition referencing the unknown seed value."""
        rounds = enumerate_home_game_scenarios(
            region=1,
            seed=None,
            slots=SLOTS_5A_7A_2025,
            season=SEASON,
            achievable_seeds=[1, 99],
        )
        for rnd in rounds:
            for sc in rnd.will_host + rnd.will_not_host:
                assert sc.conditions[0].seed != 99
