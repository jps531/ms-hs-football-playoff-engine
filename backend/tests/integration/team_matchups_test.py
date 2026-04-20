"""Tests for enumerate_team_matchups and the matchup renderers.

Test strategy
-------------
Uses the same 2025 fixture data as home_game_scenarios_test.py.

Coverage areas
~~~~~~~~~~~~~~
1. **Dataclass integrity** — ``MatchupEntry`` and ``RoundMatchups`` are frozen.

2. **Round structure** — 5A-7A returns 3 rounds; 1A-4A returns 4 rounds.
   Round names are correct.

3. **Per-round entry counts** — correct pool sizes:
   * R1:  1 entry (one deterministic opponent).
   * R2:  2 entries (two possible R1 survivors from adjacent slot).
   * QF:  4 entries for 5A-7A; up to 8 for 1A-4A.
   * SF:  4 entries for 5A-7A; up to 8 for 1A-4A.

4. **p_conditional sums to 1.0** in every round under equal win probability.

5. **R1 correctness** — the single R1 entry has the right opponent and
   home/away status, verified against the 2025 ``FormatSlot`` data.

6. **R2 correctness** — both R2 candidate opponents appear in entries;
   actual 2025 R2 home teams appear in home=True entries.

7. **QF/SF actual-game validation** — for teams that played QF/SF in 2025,
   the actual opponent appears with the correct home status.

8. **Odds passthrough** — round-level and per-matchup odds land on the right
   objects.

9. **Weighted placeholder** — passing ``p_conditional_weighted_by_matchup``
   populates ``p_conditional_weighted``; omitting it leaves it as ``None``.

10. **Dict renderer** — ``team_matchups_as_dict`` has the expected keys.

11. **Text renderer** — ``render_team_matchups`` output contains expected
    opponent labels and percentage suffixes.

12. **Error handling** — ``ValueError`` for unknown region/seed.
"""

import pytest

from backend.helpers.data_classes import FormatSlot, MatchupEntry, PlayoffState, RoundMatchups
from backend.helpers.home_game_scenarios import enumerate_team_matchups
from backend.helpers.scenario_renderer import render_team_matchups, team_matchups_as_dict
from backend.tests.data.playoff_brackets_2025 import (
    PLAYOFF_BRACKETS_2025,
    SLOTS_1A_4A_2025,
    SLOTS_5A_7A_2025,
)
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025

SEASON = 2025


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slots(clazz: int) -> list[FormatSlot]:
    """Return the correct ``FormatSlot`` list for the given class."""
    return SLOTS_5A_7A_2025 if clazz >= 5 else SLOTS_1A_4A_2025


def _team_lookup(clazz: int) -> dict[tuple[int, int], str]:
    """Build a ``(region, seed)`` → school-name mapping for *clazz* from 2025 data."""
    num_regions = 4 if clazz >= 5 else 8
    lookup: dict[tuple[int, int], str] = {}
    for region in range(1, num_regions + 1):
        seeds = REGION_RESULTS_2025[(clazz, region)]["seeds"]
        for seed, school in seeds.items():
            lookup[(region, seed)] = school
    return lookup


def _matchups(clazz: int, region: int, seed: int, **kwargs) -> list[RoundMatchups]:
    """Call ``enumerate_team_matchups`` with the correct slots and season for *clazz*."""
    return enumerate_team_matchups(
        region=region,
        seed=seed,
        slots=_slots(clazz),
        season=SEASON,
        **kwargs,
    )


def _actual_opponent(clazz: int, round_key: str, region: int, seed: int):
    """Return (opp_region, opp_seed, home) from the 2025 bracket, or None."""
    for hr, hs, ar, as_ in PLAYOFF_BRACKETS_2025.get(clazz, {}).get(round_key, []):
        if hr == region and hs == seed:
            return ar, as_, True
        if ar == region and as_ == seed:
            return hr, hs, False
    return None


# ---------------------------------------------------------------------------
# 1. Dataclass integrity
# ---------------------------------------------------------------------------


class TestDataclasses:
    """Verify that MatchupEntry and RoundMatchups are frozen and well-formed."""

    def test_matchup_entry_frozen(self):
        """MatchupEntry must be immutable (frozen dataclass)."""
        entry = MatchupEntry(
            opponent="West Jones",
            opponent_region=7,
            opponent_seed=4,
            home=True,
            p_conditional=1.0,
            p_conditional_weighted=None,
            p_marginal=None,
            p_marginal_weighted=None,
            explanation="Designated home team in bracket",
        )
        with pytest.raises((AttributeError, TypeError)):
            entry.home = False  # type: ignore[misc]

    def test_round_matchups_frozen(self):
        """RoundMatchups must be immutable (frozen dataclass)."""
        rnd = RoundMatchups(
            round_name="First Round",
            p_reach=None,
            p_host_conditional=None,
            p_host_marginal=None,
            p_reach_weighted=None,
            p_host_conditional_weighted=None,
            p_host_marginal_weighted=None,
            entries=(),
        )
        with pytest.raises((AttributeError, TypeError)):
            rnd.round_name = "Quarterfinals"  # type: ignore[misc]

    def test_entries_is_tuple(self):
        """RoundMatchups.entries must be a tuple of MatchupEntry objects."""
        rounds = _matchups(7, region=1, seed=1)
        for rnd in rounds:
            assert isinstance(rnd.entries, tuple)
            for entry in rnd.entries:
                assert isinstance(entry, MatchupEntry)


# ---------------------------------------------------------------------------
# 2. Round structure
# ---------------------------------------------------------------------------


class TestRoundStructure:
    """Verify round counts and names for both bracket formats."""

    def test_5a_7a_returns_3_rounds(self):
        """5A-7A must return exactly 3 rounds."""
        rounds = _matchups(7, region=1, seed=1)
        assert len(rounds) == 3

    def test_1a_4a_returns_4_rounds(self):
        """1A-4A must return exactly 4 rounds."""
        rounds = _matchups(2, region=8, seed=1)
        assert len(rounds) == 4

    def test_5a_7a_round_names(self):
        """5A-7A round names must be First Round, Quarterfinals, Semifinals."""
        rounds = _matchups(7, region=1, seed=1)
        assert [r.round_name for r in rounds] == ["First Round", "Quarterfinals", "Semifinals"]

    def test_1a_4a_round_names(self):
        """1A-4A round names must be First Round, Second Round, Quarterfinals, Semifinals."""
        rounds = _matchups(2, region=8, seed=1)
        assert [r.round_name for r in rounds] == [
            "First Round", "Second Round", "Quarterfinals", "Semifinals"
        ]


# ---------------------------------------------------------------------------
# 3. Per-round entry counts
# ---------------------------------------------------------------------------


class TestEntryCounts:
    """Verify the number of matchup entries per round matches the bracket pool size."""

    def test_r1_exactly_one_entry(self):
        """R1 is deterministic — exactly one possible opponent."""
        for clazz in (7, 2):
            for region in (1, 2, 3, 4):
                for seed in (1, 2, 3, 4):
                    rounds = _matchups(clazz, region=region, seed=seed)
                    r1 = rounds[0]
                    assert r1.round_name == "First Round"
                    assert len(r1.entries) == 1, (
                        f"class={clazz} region={region} seed={seed}: "
                        f"expected 1 R1 entry, got {len(r1.entries)}"
                    )

    def test_r2_exactly_two_entries(self):
        """R2 has two possible opponents (home or away from adjacent R1 slot)."""
        for region in range(1, 9):
            for seed in (1, 2, 3, 4):
                rounds = _matchups(2, region=region, seed=seed)
                r2 = rounds[1]
                assert r2.round_name == "Second Round"
                assert len(r2.entries) == 2, (
                    f"region={region} seed={seed}: expected 2 R2 entries, got {len(r2.entries)}"
                )

    def test_qf_entry_count_5a_7a(self):
        """5A-7A QF has at least 2 entries (one adjacent slot × 2 teams)."""
        for seed in (1, 2, 3, 4):
            rounds = _matchups(7, region=1, seed=seed)
            qf = rounds[1]
            assert qf.round_name == "Quarterfinals"
            assert len(qf.entries) >= 2, (
                f"seed={seed}: expected at least 2 QF entries, got {len(qf.entries)}"
            )

    def test_sf_entry_count_5a_7a(self):
        """5A-7A SF has 4 entries (2 slots × 2 teams from opposing QF game)."""
        for seed in (1, 2, 3, 4):
            rounds = _matchups(7, region=1, seed=seed)
            sf = rounds[2]
            assert sf.round_name == "Semifinals"
            assert len(sf.entries) == 4, (
                f"seed={seed}: expected 4 SF entries, got {len(sf.entries)}"
            )

    def test_qf_entry_count_1a_4a_at_least_4(self):
        """1A-4A QF has at least 4 entries; ambiguous R2 paths can add more."""
        rounds = _matchups(2, region=8, seed=1)
        qf = rounds[2]
        assert qf.round_name == "Quarterfinals"
        assert len(qf.entries) >= 4

    def test_sf_entry_count_1a_4a(self):
        """1A-4A SF has 8 entries (4 slots × 2 teams from the opposing QF group)."""
        rounds = _matchups(2, region=8, seed=1)
        sf = rounds[3]
        assert sf.round_name == "Semifinals"
        assert len(sf.entries) == 8


# ---------------------------------------------------------------------------
# 4. p_conditional sums to 1.0
# ---------------------------------------------------------------------------


class TestConditionalOddsSums:
    """Verify that p_conditional values sum to 1.0 across all entries in a round."""

    def test_sum_to_one_5a_7a(self):
        """p_conditional values must sum to 1.0 in every round for 5A-7A."""
        for region in (1, 2, 3, 4):
            for seed in (1, 2, 3, 4):
                rounds = _matchups(7, region=region, seed=seed)
                for rnd in rounds:
                    total = sum(e.p_conditional for e in rnd.entries if e.p_conditional is not None)
                    assert abs(total - 1.0) < 1e-9, (
                        f"region={region} seed={seed} {rnd.round_name}: "
                        f"p_conditional sum={total}"
                    )

    def test_sum_to_one_1a_4a(self):
        """p_conditional values must sum to 1.0 in every round for 1A-4A."""
        for region in range(1, 9):
            for seed in (1, 2, 3, 4):
                rounds = _matchups(2, region=region, seed=seed)
                for rnd in rounds:
                    total = sum(e.p_conditional for e in rnd.entries if e.p_conditional is not None)
                    assert abs(total - 1.0) < 1e-9, (
                        f"region={region} seed={seed} {rnd.round_name}: "
                        f"p_conditional sum={total}"
                    )


# ---------------------------------------------------------------------------
# 5. R1 correctness
# ---------------------------------------------------------------------------


class TestR1Correctness:
    """Verify the R1 opponent and home status against the FormatSlot definitions."""

    @pytest.mark.parametrize("clazz,region,seed,exp_opp_region,exp_opp_seed,exp_home", [
        # 5A-7A: slot 1 → home=(1,1), away=(2,4)
        (7, 1, 1, 2, 4, True),
        (7, 2, 4, 1, 1, False),
        # slot 5 → home=(3,1), away=(4,4)
        (7, 3, 1, 4, 4, True),
        (7, 4, 4, 3, 1, False),
        # 1A-4A: slot 15 → home=(8,1), away=(7,4)
        (2, 8, 1, 7, 4, True),
        (2, 7, 4, 8, 1, False),
        # slot 9 → home=(5,1), away=(6,4)
        (2, 5, 1, 6, 4, True),
        (2, 6, 4, 5, 1, False),
    ])
    def test_r1_opponent_and_home(self, clazz, region, seed, exp_opp_region, exp_opp_seed, exp_home):
        """R1 entry must match the opponent and home status from the FormatSlot definition."""
        rounds = _matchups(clazz, region=region, seed=seed)
        r1 = rounds[0]
        assert len(r1.entries) == 1
        entry = r1.entries[0]
        assert entry.opponent_region == exp_opp_region
        assert entry.opponent_seed == exp_opp_seed
        assert entry.home == exp_home
        assert entry.p_conditional == pytest.approx(1.0)

    def test_r1_entry_has_explanation(self):
        """R1 entry must carry a non-None explanation string."""
        rounds = _matchups(7, region=1, seed=1)
        assert rounds[0].entries[0].explanation is not None


# ---------------------------------------------------------------------------
# 6. R2 correctness (1A-4A)
# ---------------------------------------------------------------------------


class TestR2Correctness:
    """Verify R2 opponent pool and odds against 2025 bracket data."""

    def test_r2_opponents_from_adjacent_slot(self):
        """Region 8 #1's R2 opponents come from slot 16: (6,2) and (5,3)."""
        rounds = _matchups(2, region=8, seed=1)
        r2 = rounds[1]
        opp_pairs = {(e.opponent_region, e.opponent_seed) for e in r2.entries}
        assert opp_pairs == {(6, 2), (5, 3)}

    def test_r2_equal_probability(self):
        """Each R2 entry should have p_conditional == 0.5."""
        rounds = _matchups(2, region=8, seed=1)
        r2 = rounds[1]
        for entry in r2.entries:
            assert entry.p_conditional == pytest.approx(0.5)

    def test_r2_actual_2025_home_7a_class(self):
        """For all 1A-4A classes, actual 2025 R2 games must appear as home=True."""
        for clazz in (1, 2, 3, 4):
            for hr, hs, ar, as_ in PLAYOFF_BRACKETS_2025.get(clazz, {}).get("second_round", []):
                rounds = _matchups(clazz, region=hr, seed=hs)
                r2 = rounds[1]
                home_opps = {(e.opponent_region, e.opponent_seed) for e in r2.entries if e.home}
                assert (ar, as_) in home_opps, (
                    f"class={clazz}: ({hr},{hs}) vs ({ar},{as_}) R2 — "
                    f"opponent not in home_opps={home_opps}"
                )


# ---------------------------------------------------------------------------
# 7. QF / SF actual-game validation
# ---------------------------------------------------------------------------


class TestActualGameValidation:
    """Verify that 2025 QF and SF opponents appear with correct home status."""

    def _check_actual(self, clazz: int, round_key: str, round_idx: int):
        """Assert that each 2025 game appears with the correct home/away orientation."""
        for hr, hs, ar, as_ in PLAYOFF_BRACKETS_2025.get(clazz, {}).get(round_key, []):
            # Check from home team's perspective
            rounds = _matchups(clazz, region=hr, seed=hs)
            rnd = rounds[round_idx]
            home_opps = {(e.opponent_region, e.opponent_seed) for e in rnd.entries if e.home}
            assert (ar, as_) in home_opps, (
                f"class={clazz} {round_key}: home=({hr},{hs}) vs away=({ar},{as_}): "
                f"opponent not found in home_opps={home_opps}"
            )
            # Check from away team's perspective
            rounds_away = _matchups(clazz, region=ar, seed=as_)
            rnd_away = rounds_away[round_idx]
            away_opps = {(e.opponent_region, e.opponent_seed) for e in rnd_away.entries if not e.home}
            assert (hr, hs) in away_opps, (
                f"class={clazz} {round_key}: away=({ar},{as_}) vs home=({hr},{hs}): "
                f"home team not found in away_opps={away_opps}"
            )

    def test_qf_5a_7a(self):
        """All 2025 5A-7A QF games must appear with the correct home/away teams."""
        for clazz in (5, 6, 7):
            self._check_actual(clazz, "quarterfinals", round_idx=1)

    def test_sf_5a_7a(self):
        """All 2025 5A-7A SF games must appear with the correct home/away teams."""
        for clazz in (5, 6, 7):
            self._check_actual(clazz, "semifinals", round_idx=2)

    def test_qf_1a_4a(self):
        """All 2025 1A-4A QF games must appear with the correct home/away teams."""
        for clazz in (1, 2, 3, 4):
            self._check_actual(clazz, "quarterfinals", round_idx=2)

    def test_sf_1a_4a(self):
        """All 2025 1A-4A SF games must appear with the correct home/away teams."""
        for clazz in (1, 2, 3, 4):
            self._check_actual(clazz, "semifinals", round_idx=3)


# ---------------------------------------------------------------------------
# 8. Round-level odds passthrough
# ---------------------------------------------------------------------------


class TestOddsPassthrough:
    """Verify that round-level and per-matchup odds are attached to the correct objects."""

    def test_round_level_odds_attached(self):
        """Round-level p_reach and p_host_conditional must appear on each RoundMatchups."""
        p_reach = {"First Round": 1.0, "Quarterfinals": 0.5, "Semifinals": 0.25}
        p_host_cond = {"First Round": 1.0, "Quarterfinals": 0.5, "Semifinals": 0.75}
        rounds = enumerate_team_matchups(
            region=1, seed=1,
            slots=SLOTS_5A_7A_2025, season=SEASON,
            p_reach_by_round=p_reach,
            p_host_conditional_by_round=p_host_cond,
        )
        r1, qf, sf = rounds
        assert r1.p_reach == pytest.approx(1.0)
        assert qf.p_reach == pytest.approx(0.5)
        assert sf.p_reach == pytest.approx(0.25)
        assert r1.p_host_conditional == pytest.approx(1.0)
        assert qf.p_host_conditional == pytest.approx(0.5)
        assert sf.p_host_conditional == pytest.approx(0.75)

    def test_marginal_computed_from_p_conditional_times_p_reach(self):
        """p_marginal for each entry must equal p_conditional × p_reach."""
        p_reach = {"First Round": 1.0, "Quarterfinals": 0.5, "Semifinals": 0.25}
        rounds = enumerate_team_matchups(
            region=1, seed=1,
            slots=SLOTS_5A_7A_2025, season=SEASON,
            p_reach_by_round=p_reach,
        )
        for rnd in rounds:
            for entry in rnd.entries:
                if entry.p_conditional is not None and rnd.p_reach is not None:
                    expected = entry.p_conditional * rnd.p_reach
                    assert entry.p_marginal == pytest.approx(expected)

    def test_all_odds_none_when_not_provided(self):
        """All odds fields must be None when no odds dicts are passed."""
        rounds = _matchups(7, region=1, seed=1)
        for rnd in rounds:
            assert rnd.p_reach is None
            assert rnd.p_host_conditional is None
            for entry in rnd.entries:
                assert entry.p_marginal is None
                assert entry.p_conditional_weighted is None


# ---------------------------------------------------------------------------
# 9. Weighted placeholder
# ---------------------------------------------------------------------------


class TestWeightedPlaceholder:
    """Verify the weighted per-matchup odds placeholder wires up correctly."""

    def test_weighted_matchup_odds_attached(self):
        """p_conditional_weighted_by_matchup values must appear on the matching entry."""
        weighted = {
            "First Round": {(2, 4, True): 1.0},
        }
        rounds = enumerate_team_matchups(
            region=1, seed=1,
            slots=SLOTS_5A_7A_2025, season=SEASON,
            p_conditional_weighted_by_matchup=weighted,
        )
        r1 = rounds[0]
        entry = r1.entries[0]
        assert entry.p_conditional_weighted == pytest.approx(1.0)

    def test_weighted_marginal_computed(self):
        """p_marginal_weighted must equal p_conditional_weighted × p_reach_weighted."""
        weighted = {
            "First Round": {(2, 4, True): 1.0},
        }
        rounds = enumerate_team_matchups(
            region=1, seed=1,
            slots=SLOTS_5A_7A_2025, season=SEASON,
            p_reach_weighted_by_round={"First Round": 0.9},
            p_conditional_weighted_by_matchup=weighted,
        )
        r1 = rounds[0]
        entry = r1.entries[0]
        assert entry.p_marginal_weighted == pytest.approx(0.9)

    def test_weighted_none_when_not_provided(self):
        """Weighted fields must be None when no weighted dict is passed."""
        rounds = _matchups(7, region=1, seed=1)
        for rnd in rounds:
            for entry in rnd.entries:
                assert entry.p_conditional_weighted is None
                assert entry.p_marginal_weighted is None


# ---------------------------------------------------------------------------
# 10. Dict renderer
# ---------------------------------------------------------------------------


class TestDictRenderer:
    """Verify that team_matchups_as_dict produces the expected structure."""

    def test_keys_5a_7a(self):
        """5A-7A dict must have exactly three round keys (no second_round)."""
        rounds = _matchups(7, region=1, seed=1)
        d = team_matchups_as_dict(rounds)
        assert set(d.keys()) == {"first_round", "quarterfinals", "semifinals"}

    def test_keys_1a_4a(self):
        """1A-4A dict must have exactly four round keys including second_round."""
        rounds = _matchups(2, region=8, seed=1)
        d = team_matchups_as_dict(rounds)
        assert set(d.keys()) == {"first_round", "second_round", "quarterfinals", "semifinals"}

    def test_round_level_odds_in_dict(self):
        """Round-level odds provided to the function must appear in the dict."""
        rounds = enumerate_team_matchups(
            region=1, seed=1, slots=SLOTS_5A_7A_2025, season=SEASON,
            p_reach_by_round={"First Round": 1.0},
        )
        d = team_matchups_as_dict(rounds)
        assert d["first_round"]["p_reach"] == pytest.approx(1.0)
        assert d["first_round"]["p_host_conditional"] is None

    def test_matchup_entry_structure(self):
        """Each matchup entry must contain exactly the expected set of keys."""
        rounds = _matchups(7, region=1, seed=1)
        d = team_matchups_as_dict(rounds)
        matchups = d["first_round"]["matchups"]
        assert len(matchups) == 1
        entry = matchups[0]
        expected_keys = {
            "opponent", "opponent_region", "opponent_seed", "home",
            "p_conditional", "p_conditional_weighted",
            "p_marginal", "p_marginal_weighted", "explanation",
        }
        assert set(entry.keys()) == expected_keys

    def test_matchup_home_flag_correct(self):
        """R1 home flag must be True for the designated home team (Region 1 #1)."""
        rounds = _matchups(7, region=1, seed=1)
        d = team_matchups_as_dict(rounds)
        assert d["first_round"]["matchups"][0]["home"] is True

    def test_matchup_home_first_ordering(self):
        """Entries must be ordered home-first within each round."""
        rounds = _matchups(7, region=1, seed=1)
        d = team_matchups_as_dict(rounds)
        for key in ("quarterfinals", "semifinals"):
            matchups = d[key]["matchups"]
            home_flags = [m["home"] for m in matchups]
            # All True values must come before any False value
            saw_false = False
            for flag in home_flags:
                if not flag:
                    saw_false = True
                if saw_false and flag:
                    pytest.fail(f"{key}: home matchup appears after away matchup")


# ---------------------------------------------------------------------------
# 11. Text renderer
# ---------------------------------------------------------------------------


class TestTextRenderer:
    """Verify the human-readable text output of render_team_matchups."""

    def test_team_name_in_header(self):
        """The team name must appear as the first line of the rendered output."""
        rounds = _matchups(7, region=1, seed=1)
        lookup = _team_lookup(7)
        team = lookup.get((1, 1), "Region 1 #1 Seed")
        text = render_team_matchups(team, rounds)
        assert text.startswith(team)

    def test_round_names_in_output(self):
        """All applicable round names must appear as section headers."""
        rounds = _matchups(7, region=1, seed=1)
        text = render_team_matchups("Oak Grove", rounds)
        assert "First Round" in text
        assert "Quarterfinals" in text
        assert "Semifinals" in text

    def test_home_matchup_format(self):
        """Home matchup lines must end with the team name (' at <team>')."""
        rounds = _matchups(7, region=1, seed=1)
        text = render_team_matchups("Oak Grove", rounds)
        # R1: Region 1 #1 is always home (slot 1), so the line should end in "Oak Grove"
        lines = text.splitlines()
        r1_lines = [l for l in lines if " at Oak Grove" in l]
        assert len(r1_lines) >= 1

    def test_away_matchup_format(self):
        """Away matchup lines must start with the team name ('<team> at ...')."""
        # Region 2 #4 is always away in R1 (slot 1: away_region=2, away_seed=4)
        rounds = _matchups(7, region=2, seed=4)
        text = render_team_matchups("Some School", rounds)
        lines = text.splitlines()
        r1_lines = [l for l in lines if l.strip().startswith("Some School at ")]
        assert len(r1_lines) >= 1

    def test_percentage_suffix_with_odds(self):
        """When odds are supplied, a formatted percentage suffix must appear in output."""
        rounds = enumerate_team_matchups(
            region=1, seed=1, slots=SLOTS_5A_7A_2025, season=SEASON,
            p_reach_by_round={"First Round": 1.0},
        )
        text = render_team_matchups("Oak Grove", rounds)
        assert "100.0%" in text

    def test_no_second_round_in_5a_7a(self):
        """5A-7A output must not contain a 'Second Round' section."""
        rounds = _matchups(7, region=1, seed=1)
        text = render_team_matchups("Oak Grove", rounds)
        assert "Second Round" not in text

    def test_second_round_present_in_1a_4a(self):
        """1A-4A output must include a 'Second Round' section."""
        rounds = _matchups(2, region=8, seed=1)
        text = render_team_matchups("Taylorsville", rounds)
        assert "Second Round" in text


# ---------------------------------------------------------------------------
# Ground truth: Taylorsville 2025 (1A, Region 8 #1)
# ---------------------------------------------------------------------------


class TestTaylorsville2025:
    """Full ground-truth snapshot for Taylorsville (1A Region 8 #1) in 2025.

    Odds supplied match the existing taylorsville_home_scenarios_2025.md
    odds table (equal win probability):
      First Round:   reach=100%, host|reach=100%, marginal=100%
      Second Round:  reach=50%,  host|reach=100%, marginal=50%
      Quarterfinals: reach=25%,  host|reach=37.5%, marginal=9.375%
      Semifinals:    reach=12.5%, host|reach=75%,  marginal=9.375%
    """

    EXPECTED_TEXT = (
        "Taylorsville\n"
        "\n"
        "First Round (100.0%):\n"
        "  Region 7 #4 West Lincoln at Taylorsville (100.0%)"
        "  [Designated home team in bracket]\n"
        "\n"
        "Second Round (50.0%):\n"
        "  Region 5 #3 Ethel at Taylorsville (50.0%)  [Higher seed (#1) hosts]\n"
        "  Region 6 #2 South Delta at Taylorsville (50.0%)  [Higher seed (#1) hosts]\n"
        "\n"
        "Quarterfinals (25.0%):\n"
        "  Region 5 #2 Leake County at Taylorsville (16.7%)  [Higher seed (#1) hosts]\n"
        "  Region 8 #4 Richton at Taylorsville (16.7%)"
        "  [Same-region game \u2014 higher seed (#1) hosts]\n"
        "  Taylorsville at Region 5 #2 Leake County (16.7%)"
        "  [Fewer home games played (1 vs 2) \u2014 opponent hosts]\n"
        "  Taylorsville at Region 6 #3 Shaw (33.3%)"
        "  [Fewer home games played (1 vs 2) \u2014 opponent hosts]\n"
        "  Taylorsville at Region 7 #1 Bogue Chitto (16.7%)"
        "  [Equal seed (#1) \u2014 region tiebreak: odd year, lower region# hosts (Region 7)]\n"
        "\n"
        "Semifinals (12.5%):\n"
        "  Region 5 #4 Noxapater at Taylorsville (12.5%)  [Higher seed (#1) hosts]\n"
        "  Region 6 #4 West Bolivar at Taylorsville (12.5%)  [Higher seed (#1) hosts]\n"
        "  Region 7 #2 Salem at Taylorsville (12.5%)  [Higher seed (#1) hosts]\n"
        "  Region 7 #3 Mount Olive at Taylorsville (12.5%)  [Higher seed (#1) hosts]\n"
        "  Region 8 #2 Stringer at Taylorsville (12.5%)"
        "  [Same-region game \u2014 higher seed (#1) hosts]\n"
        "  Region 8 #3 Lumberton at Taylorsville (12.5%)"
        "  [Same-region game \u2014 higher seed (#1) hosts]\n"
        "  Taylorsville at Region 5 #1 Nanih Waiya (12.5%)"
        "  [Equal seed (#1) \u2014 region tiebreak: odd year, lower region# hosts (Region 5)]\n"
        "  Taylorsville at Region 6 #1 Simmons (12.5%)"
        "  [Equal seed (#1) \u2014 region tiebreak: odd year, lower region# hosts (Region 6)]"
    )

    @pytest.fixture
    def lookup(self):
        """Build the 1A (region, seed) → school-name mapping from 2025 ground-truth data."""
        result: dict[tuple[int, int], str] = {}
        for region in range(1, 9):
            for seed, school in REGION_RESULTS_2025[(1, region)]["seeds"].items():
                result[(region, seed)] = school
        return result

    @pytest.fixture
    def taylorsville_rounds(self, lookup):
        """Enumerate Taylorsville's 2025 matchups with the documented odds values."""
        return enumerate_team_matchups(
            region=8,
            seed=1,
            slots=SLOTS_1A_4A_2025,
            season=2025,
            p_reach_by_round={
                "First Round": 1.0,
                "Second Round": 0.5,
                "Quarterfinals": 0.25,
                "Semifinals": 0.125,
            },
            p_host_conditional_by_round={
                "First Round": 1.0,
                "Second Round": 1.0,
                "Quarterfinals": 0.375,
                "Semifinals": 0.75,
            },
            p_host_marginal_by_round={
                "First Round": 1.0,
                "Second Round": 0.5,
                "Quarterfinals": 0.09375,
                "Semifinals": 0.09375,
            },
            team_lookup=lookup,
        )

    def test_render_text(self, taylorsville_rounds):
        """render_team_matchups must produce the exact documented text output."""
        text = render_team_matchups("Taylorsville", taylorsville_rounds)
        assert text == self.EXPECTED_TEXT

    def test_dict_round_level_odds(self, taylorsville_rounds):
        """Round-level odds in the dict must match the documented odds table."""
        d = team_matchups_as_dict(taylorsville_rounds)
        assert d["first_round"]["p_reach"] == pytest.approx(1.0)
        assert d["first_round"]["p_host_conditional"] == pytest.approx(1.0)
        assert d["second_round"]["p_reach"] == pytest.approx(0.5)
        assert d["second_round"]["p_host_conditional"] == pytest.approx(1.0)
        assert d["quarterfinals"]["p_reach"] == pytest.approx(0.25)
        assert d["quarterfinals"]["p_host_conditional"] == pytest.approx(0.375)
        assert d["semifinals"]["p_reach"] == pytest.approx(0.125)
        assert d["semifinals"]["p_host_conditional"] == pytest.approx(0.75)

    def test_dict_first_round(self, taylorsville_rounds):
        """First-round dict entry must show West Lincoln as the sole home opponent."""
        d = team_matchups_as_dict(taylorsville_rounds)
        matchups = d["first_round"]["matchups"]
        assert len(matchups) == 1
        m = matchups[0]
        assert m["opponent"] == "West Lincoln"
        assert m["opponent_region"] == 7
        assert m["opponent_seed"] == 4
        assert m["home"] is True
        assert m["p_conditional"] == pytest.approx(1.0)
        assert m["p_marginal"] == pytest.approx(1.0)
        assert m["explanation"] == "Designated home team in bracket"

    def test_dict_second_round(self, taylorsville_rounds):
        """Second-round dict must show Ethel and South Delta as home opponents at 50% each."""
        d = team_matchups_as_dict(taylorsville_rounds)
        matchups = d["second_round"]["matchups"]
        assert len(matchups) == 2
        assert all(m["home"] is True for m in matchups)
        opponents = {m["opponent"] for m in matchups}
        assert opponents == {"Ethel", "South Delta"}
        for m in matchups:
            assert m["p_conditional"] == pytest.approx(0.5)
            assert m["p_marginal"] == pytest.approx(0.25)
            assert m["explanation"] == "Higher seed (#1) hosts"

    def test_dict_quarterfinals(self, taylorsville_rounds):
        """QF dict must show 5 entries including Leake County twice (R2-path split)."""
        d = team_matchups_as_dict(taylorsville_rounds)
        matchups = d["quarterfinals"]["matchups"]

        # 5 entries: Leake County appears twice (one home, one away)
        assert len(matchups) == 5
        lc = [m for m in matchups if m["opponent"] == "Leake County"]
        assert len(lc) == 2
        assert any(m["home"] is True for m in lc)
        assert any(m["home"] is False for m in lc)

        # Richton: home (same-region, higher seed)
        richton = next(m for m in matchups if m["opponent"] == "Richton")
        assert richton["home"] is True
        assert richton["p_conditional"] == pytest.approx(1 / 6)

        # Shaw: away, 2 paths → p_conditional = 2/6 = 1/3
        shaw = next(m for m in matchups if m["opponent"] == "Shaw")
        assert shaw["home"] is False
        assert shaw["p_conditional"] == pytest.approx(1 / 3)

        # Bogue Chitto: away (equal seed, odd-year tiebreak)
        bc = next(m for m in matchups if m["opponent"] == "Bogue Chitto")
        assert bc["home"] is False
        assert bc["p_conditional"] == pytest.approx(1 / 6)
        assert "lower region# hosts (Region 7)" in bc["explanation"]

    def test_dict_semifinals(self, taylorsville_rounds):
        """SF dict must show 8 entries: 6 home, 2 away (Nanih Waiya and Simmons)."""
        d = team_matchups_as_dict(taylorsville_rounds)
        matchups = d["semifinals"]["matchups"]

        assert len(matchups) == 8
        home_opps = {m["opponent"] for m in matchups if m["home"]}
        away_opps = {m["opponent"] for m in matchups if not m["home"]}
        assert home_opps == {"Noxapater", "West Bolivar", "Salem", "Mount Olive", "Stringer", "Lumberton"}
        assert away_opps == {"Nanih Waiya", "Simmons"}

        # All have equal p_conditional = 1/8
        for m in matchups:
            assert m["p_conditional"] == pytest.approx(0.125)
            assert m["p_marginal"] == pytest.approx(0.015625)


# ---------------------------------------------------------------------------
# Ground truth: Taylorsville 2025 post-first-round (1A, Region 8 #1)
# ---------------------------------------------------------------------------


class TestTaylorsville2025PostFirstRound:
    """Ground-truth snapshot for Taylorsville after all first-round results are known.

    All R1 South-half results are known; R2 has not been played.

    R1 winners (South half):
      Taylorsville's QF group:  Taylorsville (R8s1), South Delta (R6s2),
                                Leake County (R5s2), Bogue Chitto (R7s1)
      Taylorsville's SF group:  Nanih Waiya (R5s1), Lumberton (R8s3),
                                Simmons (R6s1), Stringer (R8s2)
    R1 losers eliminated:       West Lincoln, Ethel, Richton, Shaw,
                                Noxapater, West Bolivar, Salem, Mount Olive

    Post-first-round odds:
      Second Round:  reach=100%, host|reach=100%, marginal=100%
      Quarterfinals: reach=50%,  host|reach=0%,   marginal=0%
      Semifinals:    reach=25%,  host|reach=75%,  marginal=18.75%

    QF host|reach=0% because both remaining QF opponents always host:
    Bogue Chitto (R7<R8, odd-year seed tiebreak) and Leake County (fewer
    home games in all bracket paths).  This matches the actual 2025 outcome
    where Leake County hosted Taylorsville in the QF.
    """

    EXPECTED_TEXT = (
        "Taylorsville\n"
        "\n"
        "Second Round (100.0%):\n"
        "  Region 6 #2 South Delta at Taylorsville (100.0%)  [Higher seed (#1) hosts]\n"
        "\n"
        "Quarterfinals (50.0%):\n"
        "  Taylorsville at Region 5 #2 Leake County (50.0%)"
        "  [Fewer home games played (1 vs 2) \u2014 opponent hosts]\n"
        "  Taylorsville at Region 7 #1 Bogue Chitto (50.0%)"
        "  [Equal seed (#1) \u2014 region tiebreak: odd year, lower region# hosts (Region 7)]\n"
        "\n"
        "Semifinals (25.0%):\n"
        "  Region 8 #2 Stringer at Taylorsville (25.0%)"
        "  [Same-region game \u2014 higher seed (#1) hosts]\n"
        "  Region 8 #3 Lumberton at Taylorsville (25.0%)"
        "  [Same-region game \u2014 higher seed (#1) hosts]\n"
        "  Taylorsville at Region 5 #1 Nanih Waiya (25.0%)"
        "  [Equal seed (#1) \u2014 region tiebreak: odd year, lower region# hosts (Region 5)]\n"
        "  Taylorsville at Region 6 #1 Simmons (25.0%)"
        "  [Equal seed (#1) \u2014 region tiebreak: odd year, lower region# hosts (Region 6)]"
    )

    # R1 winners in the South half — all other teams are eliminated.
    _SURVIVORS: set[tuple[int, int]] = {
        (5, 1), (5, 2),       # Nanih Waiya, Leake County
        (6, 1), (6, 2),       # Simmons, South Delta
        (7, 1),               # Bogue Chitto
        (8, 1), (8, 2), (8, 3),  # Taylorsville, Stringer, Lumberton
    }

    @pytest.fixture
    def lookup(self):
        """Build the 1A (region, seed) → school-name mapping from 2025 ground-truth data."""
        result: dict[tuple[int, int], str] = {}
        for region in range(1, 9):
            for seed, school in REGION_RESULTS_2025[(1, region)]["seeds"].items():
                result[(region, seed)] = school
        return result

    @pytest.fixture
    def taylorsville_rounds(self, lookup):
        """Enumerate Taylorsville's post-first-round 2025 matchups."""
        return enumerate_team_matchups(
            region=8,
            seed=1,
            slots=SLOTS_1A_4A_2025,
            season=2025,
            p_reach_by_round={
                "Second Round": 1.0,
                "Quarterfinals": 0.5,
                "Semifinals": 0.25,
            },
            p_host_conditional_by_round={
                "Second Round": 1.0,
                "Quarterfinals": 0.0,
                "Semifinals": 0.75,
            },
            p_host_marginal_by_round={
                "Second Round": 1.0,
                "Quarterfinals": 0.0,
                "Semifinals": 0.1875,
            },
            team_lookup=lookup,
            state=PlayoffState(known_survivors=self._SURVIVORS, r1_survivors=self._SURVIVORS, completed_rounds={"First Round"}),
        )

    def test_render_text(self, taylorsville_rounds):
        """render_team_matchups must produce the exact documented text output."""
        text = render_team_matchups("Taylorsville", taylorsville_rounds)
        assert text == self.EXPECTED_TEXT

    def test_round_names(self, taylorsville_rounds):
        """Output must contain exactly 3 rounds; First Round is omitted."""
        names = [r.round_name for r in taylorsville_rounds]
        assert names == ["Second Round", "Quarterfinals", "Semifinals"]

    def test_dict_round_level_odds(self, taylorsville_rounds):
        """Round-level odds must reflect post-first-round state."""
        d = team_matchups_as_dict(taylorsville_rounds)
        assert "first_round" not in d
        assert d["second_round"]["p_reach"] == pytest.approx(1.0)
        assert d["second_round"]["p_host_conditional"] == pytest.approx(1.0)
        assert d["quarterfinals"]["p_reach"] == pytest.approx(0.5)
        assert d["quarterfinals"]["p_host_conditional"] == pytest.approx(0.0)
        assert d["semifinals"]["p_reach"] == pytest.approx(0.25)
        assert d["semifinals"]["p_host_conditional"] == pytest.approx(0.75)

    def test_dict_second_round(self, taylorsville_rounds):
        """R2 must show only South Delta (Ethel eliminated); p_conditional=1.0."""
        d = team_matchups_as_dict(taylorsville_rounds)
        matchups = d["second_round"]["matchups"]
        assert len(matchups) == 1
        m = matchups[0]
        assert m["opponent"] == "South Delta"
        assert m["home"] is True
        assert m["p_conditional"] == pytest.approx(1.0)
        assert m["p_marginal"] == pytest.approx(1.0)
        assert m["explanation"] == "Higher seed (#1) hosts"

    def test_dict_quarterfinals(self, taylorsville_rounds):
        """QF shows 2 entries after R1 survivors fix R2 home counts — Taylorsville always away."""
        d = team_matchups_as_dict(taylorsville_rounds)
        matchups = d["quarterfinals"]["matchups"]

        assert len(matchups) == 2
        assert d["quarterfinals"]["p_host_conditional"] == pytest.approx(0.0)
        assert all(m["home"] is False for m in matchups)

        # Leake County: away only — R1 results fix Leake County's R2 opp to Bogue Chitto,
        # giving Leake County at most 1 home game vs Taylorsville's 2 → always hosts.
        lc = next(m for m in matchups if m["opponent"] == "Leake County")
        assert lc["home"] is False
        assert lc["p_conditional"] == pytest.approx(0.5)
        assert "Fewer home games" in lc["explanation"]

        # Bogue Chitto: always away, odd-year seed tiebreak
        bc = next(m for m in matchups if m["opponent"] == "Bogue Chitto")
        assert bc["home"] is False
        assert bc["p_conditional"] == pytest.approx(0.5)
        assert "lower region# hosts (Region 7)" in bc["explanation"]

    def test_dict_semifinals(self, taylorsville_rounds):
        """SF shows 4 entries (R1 losers eliminated): 2 home, 2 away."""
        d = team_matchups_as_dict(taylorsville_rounds)
        matchups = d["semifinals"]["matchups"]

        assert len(matchups) == 4
        home_opps = {m["opponent"] for m in matchups if m["home"]}
        away_opps = {m["opponent"] for m in matchups if not m["home"]}
        assert home_opps == {"Stringer", "Lumberton"}
        assert away_opps == {"Nanih Waiya", "Simmons"}

        for m in matchups:
            assert m["p_conditional"] == pytest.approx(0.25)
            assert m["p_marginal"] == pytest.approx(0.0625)


# ---------------------------------------------------------------------------
# Ground truth: Taylorsville 2025 post-second-round (1A, Region 8 #1)
# ---------------------------------------------------------------------------


class TestTaylorsville2025PostSecondRound:
    """Ground-truth snapshot for Taylorsville after all second-round results are known.

    R2 South results (actual 2025):
      (5,1,8,3): Nanih Waiya beats Lumberton
      (6,1,8,2): Simmons beats Stringer
      (7,1,5,2): Bogue Chitto hosts → Leake County WINS
      (8,1,6,2): Taylorsville beats South Delta

    R2 survivors: Taylorsville (R8s1), Leake County (R5s2),
                  Nanih Waiya (R5s1), Simmons (R6s1)

    Post-second-round odds:
      Quarterfinals: reach=100%, host|reach=0%,  marginal=0%
      Semifinals:    reach=50%,  host|reach=0%,  marginal=0%

    QF: Leake County is the only opponent (Bogue Chitto eliminated in R2).
    Taylorsville is always away — Leake County had 1 home game vs Taylorsville's 2.
    SF: Nanih Waiya and Simmons are the only opponents (Lumberton and Stringer
    eliminated in R2).  Both are seed #1 from lower-numbered regions; in an odd
    year the lower region# hosts, so Taylorsville is always away.
    """

    # R1 winners in the South half (needed for accurate QF R2 home-status computation).
    _R1_SURVIVORS: set[tuple[int, int]] = {
        (5, 1), (5, 2),
        (6, 1), (6, 2),
        (7, 1),
        (8, 1), (8, 2), (8, 3),
    }
    # Teams still alive after R2.
    _R2_SURVIVORS: set[tuple[int, int]] = {(5, 1), (5, 2), (6, 1), (8, 1)}

    EXPECTED_TEXT = (
        "Taylorsville\n"
        "\n"
        "Quarterfinals (100.0%):\n"
        "  Taylorsville at Region 5 #2 Leake County (100.0%)"
        "  [Fewer home games played (1 vs 2) \u2014 opponent hosts]\n"
        "\n"
        "Semifinals (50.0%):\n"
        "  Taylorsville at Region 5 #1 Nanih Waiya (50.0%)"
        "  [Equal seed (#1) \u2014 region tiebreak: odd year, lower region# hosts (Region 5)]\n"
        "  Taylorsville at Region 6 #1 Simmons (50.0%)"
        "  [Equal seed (#1) \u2014 region tiebreak: odd year, lower region# hosts (Region 6)]"
    )

    @pytest.fixture
    def lookup(self):
        """Build the 1A (region, seed) → school-name mapping from 2025 ground-truth data."""
        result: dict[tuple[int, int], str] = {}
        for region in range(1, 9):
            for seed, school in REGION_RESULTS_2025[(1, region)]["seeds"].items():
                result[(region, seed)] = school
        return result

    @pytest.fixture
    def taylorsville_rounds(self, lookup):
        """Enumerate Taylorsville's post-second-round 2025 matchups."""
        return enumerate_team_matchups(
            region=8,
            seed=1,
            slots=SLOTS_1A_4A_2025,
            season=2025,
            p_reach_by_round={"Quarterfinals": 1.0, "Semifinals": 0.5},
            p_host_conditional_by_round={"Quarterfinals": 0.0, "Semifinals": 0.0},
            p_host_marginal_by_round={"Quarterfinals": 0.0, "Semifinals": 0.0},
            team_lookup=lookup,
            state=PlayoffState(known_survivors=self._R2_SURVIVORS, r1_survivors=self._R1_SURVIVORS, completed_rounds={"First Round", "Second Round"}),
        )

    def test_render_text(self, taylorsville_rounds):
        """render_team_matchups must produce the exact documented text output."""
        text = render_team_matchups("Taylorsville", taylorsville_rounds)
        assert text == self.EXPECTED_TEXT

    def test_round_names(self, taylorsville_rounds):
        """Output must contain exactly 2 rounds; First Round and Second Round are omitted."""
        names = [r.round_name for r in taylorsville_rounds]
        assert names == ["Quarterfinals", "Semifinals"]

    def test_dict_round_level_odds(self, taylorsville_rounds):
        """Round-level odds must reflect post-second-round state."""
        d = team_matchups_as_dict(taylorsville_rounds)
        assert "first_round" not in d
        assert "second_round" not in d
        assert d["quarterfinals"]["p_reach"] == pytest.approx(1.0)
        assert d["quarterfinals"]["p_host_conditional"] == pytest.approx(0.0)
        assert d["semifinals"]["p_reach"] == pytest.approx(0.5)
        assert d["semifinals"]["p_host_conditional"] == pytest.approx(0.0)

    def test_dict_quarterfinals(self, taylorsville_rounds):
        """QF shows exactly one entry — Leake County always hosts (fewer home games)."""
        d = team_matchups_as_dict(taylorsville_rounds)
        matchups = d["quarterfinals"]["matchups"]
        assert len(matchups) == 1
        m = matchups[0]
        assert m["opponent"] == "Leake County"
        assert m["home"] is False
        assert m["p_conditional"] == pytest.approx(1.0)
        assert m["p_marginal"] == pytest.approx(1.0)
        assert "Fewer home games" in m["explanation"]

    def test_dict_semifinals(self, taylorsville_rounds):
        """SF shows 2 entries (Lumberton and Stringer eliminated in R2); both away."""
        d = team_matchups_as_dict(taylorsville_rounds)
        matchups = d["semifinals"]["matchups"]
        assert len(matchups) == 2
        assert all(m["home"] is False for m in matchups)
        opponents = {m["opponent"] for m in matchups}
        assert opponents == {"Nanih Waiya", "Simmons"}
        for m in matchups:
            assert m["p_conditional"] == pytest.approx(0.5)
            assert m["p_marginal"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# Ground truth: Taylorsville 2025 post-quarterfinals (1A, Region 8 #1)
# ---------------------------------------------------------------------------


class TestTaylorsville2025PostQuarterfinals:
    """Ground-truth snapshot for Taylorsville after all quarterfinal results are known.

    QF South results (actual 2025):
      (5,1,6,1): Nanih Waiya hosts → Simmons WINS
      (5,2,8,1): Leake County hosts → Taylorsville WINS

    QF survivors: Taylorsville (R8s1), Simmons (R6s1)

    Semifinals: Taylorsville vs Simmons; Simmons hosts (seed #1 equal,
    odd year → lower region# = R6 hosts).  Actual result: (6,1,8,1).

    Post-quarterfinals odds:
      Semifinals: reach=100%, host|reach=0%, marginal=0%
    """

    _R1_SURVIVORS: set[tuple[int, int]] = {
        (5, 1), (5, 2),
        (6, 1), (6, 2),
        (7, 1),
        (8, 1), (8, 2), (8, 3),
    }
    _QF_SURVIVORS: set[tuple[int, int]] = {(6, 1), (8, 1)}

    EXPECTED_TEXT = (
        "Taylorsville\n"
        "\n"
        "Semifinals (100.0%):\n"
        "  Taylorsville at Region 6 #1 Simmons (100.0%)"
        "  [Equal seed (#1) \u2014 region tiebreak: odd year, lower region# hosts (Region 6)]"
    )

    @pytest.fixture
    def lookup(self):
        """Build the 1A (region, seed) → school-name mapping from 2025 ground-truth data."""
        result: dict[tuple[int, int], str] = {}
        for region in range(1, 9):
            for seed, school in REGION_RESULTS_2025[(1, region)]["seeds"].items():
                result[(region, seed)] = school
        return result

    @pytest.fixture
    def taylorsville_rounds(self, lookup):
        """Enumerate Taylorsville's post-quarterfinals 2025 matchups."""
        return enumerate_team_matchups(
            region=8,
            seed=1,
            slots=SLOTS_1A_4A_2025,
            season=2025,
            p_reach_by_round={"Semifinals": 1.0},
            p_host_conditional_by_round={"Semifinals": 0.0},
            p_host_marginal_by_round={"Semifinals": 0.0},
            team_lookup=lookup,
            state=PlayoffState(known_survivors=self._QF_SURVIVORS, r1_survivors=self._R1_SURVIVORS, completed_rounds={"First Round", "Second Round", "Quarterfinals"}),
        )

    def test_render_text(self, taylorsville_rounds):
        """render_team_matchups must produce the exact documented text output."""
        text = render_team_matchups("Taylorsville", taylorsville_rounds)
        assert text == self.EXPECTED_TEXT

    def test_round_names(self, taylorsville_rounds):
        """Output must contain exactly 1 round; all earlier rounds are omitted."""
        names = [r.round_name for r in taylorsville_rounds]
        assert names == ["Semifinals"]

    def test_dict_round_level_odds(self, taylorsville_rounds):
        """Round-level odds must reflect post-quarterfinals state."""
        d = team_matchups_as_dict(taylorsville_rounds)
        assert "quarterfinals" not in d
        assert d["semifinals"]["p_reach"] == pytest.approx(1.0)
        assert d["semifinals"]["p_host_conditional"] == pytest.approx(0.0)

    def test_dict_semifinals(self, taylorsville_rounds):
        """SF shows exactly one entry — Simmons always hosts (lower region#, odd year)."""
        d = team_matchups_as_dict(taylorsville_rounds)
        matchups = d["semifinals"]["matchups"]
        assert len(matchups) == 1
        m = matchups[0]
        assert m["opponent"] == "Simmons"
        assert m["home"] is False
        assert m["p_conditional"] == pytest.approx(1.0)
        assert m["p_marginal"] == pytest.approx(1.0)
        assert "lower region# hosts (Region 6)" in m["explanation"]


# ---------------------------------------------------------------------------
# 12a. completed_rounds — Semifinals omitted
# ---------------------------------------------------------------------------


class TestCompletedRoundsSemifinals:
    """Verify that Semifinals is omitted when included in completed_rounds."""

    def test_5a_7a_semifinals_omitted(self):
        """5A-7A: passing completed_rounds={'Semifinals'} returns only R1 and QF."""
        rounds = _matchups(7, region=1, seed=1, state=PlayoffState(completed_rounds={"Semifinals"}))
        names = [r.round_name for r in rounds]
        assert names == ["First Round", "Quarterfinals"]

    def test_1a_4a_semifinals_omitted(self):
        """1A-4A: passing completed_rounds={'Semifinals'} returns R1, R2, and QF."""
        rounds = _matchups(2, region=8, seed=1, state=PlayoffState(completed_rounds={"Semifinals"}))
        names = [r.round_name for r in rounds]
        assert names == ["First Round", "Second Round", "Quarterfinals"]

    def test_all_rounds_completed_returns_empty(self):
        """Marking every round as completed yields an empty list."""
        rounds = _matchups(
            7,
            region=1,
            seed=1,
            state=PlayoffState(completed_rounds={"First Round", "Quarterfinals", "Semifinals"}),
        )
        assert rounds == []


# ---------------------------------------------------------------------------
# 12. Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Verify that invalid inputs raise appropriate errors."""

    def test_unknown_region_raises(self):
        """A region not present in slots must raise ValueError."""
        with pytest.raises(ValueError, match="not found"):
            enumerate_team_matchups(region=99, seed=1, slots=SLOTS_5A_7A_2025, season=SEASON)

    def test_unknown_seed_raises(self):
        """A seed not present in slots must raise ValueError."""
        with pytest.raises(ValueError, match="not found"):
            enumerate_team_matchups(region=1, seed=9, slots=SLOTS_5A_7A_2025, season=SEASON)
