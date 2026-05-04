"""Unit tests for backend/helpers/insights.py — targeting ~100% coverage."""

import pytest

from backend.helpers.data_classes import (
    CoinFlipResult,
    CompletedGame,
    GameResult,
    MarginCondition,
    PDRankCondition,
    RemainingGame,
    StandingsOdds,
)
from backend.helpers.insights import (
    KeyInsight,
    _atom_is_simple_game_results,
    _cond_game_indices,
    _conditions_frozenset,
    _deduplicate,
    _extract_clinch_playoffs_insights,
    _extract_clinch_seed_insights,
    _extract_elimination_insights,
    _masks_satisfying_conditions,
    _render_insight,
    _sort_key,
    _verify_insight_margins,
    deserialize_insights,
    extract_insights,
    serialize_insights,
)

# ---------------------------------------------------------------------------
# Minimal 3-team fixture
# ---------------------------------------------------------------------------
# Alpha beat Beta and Gamma already (2-0). Beta vs Gamma is remaining (R=1).
# Regardless of Beta/Gamma game, Alpha is 1st.
# Beta at seed 2 iff Beta beats Gamma; Gamma at seed 2 iff Gamma beats Beta.

_TEAMS_3 = ["Alpha", "Beta", "Gamma"]

_COMPLETED_3: list[CompletedGame] = [
    CompletedGame(a="Alpha", b="Beta", res_a=1, pd_a=7, pa_a=14, pa_b=21),
    CompletedGame(a="Alpha", b="Gamma", res_a=1, pd_a=7, pa_a=7, pa_b=14),
]

# Beta < Gamma alphabetically → RemainingGame("Beta","Gamma"), bit 0=1 means Beta wins
_REMAINING_1: list[RemainingGame] = [RemainingGame("Beta", "Gamma")]

# Synthetic atoms for the 3-team R=1 region (manually constructed, matches
# what build_scenario_atoms would produce). Alpha always seeds 1st (empty atom).
# Beta or Gamma seeds 2nd or 3rd depending on who wins the remaining game.
# No team can finish outside top 3, so no elimination atoms in this fixture.

_GR_BETA_BEATS_GAMMA = GameResult("Beta", "Gamma")
_GR_GAMMA_BEATS_BETA = GameResult("Gamma", "Beta")

_ATOMS_3: dict = {
    "Alpha": {1: [[]]},
    "Beta": {
        2: [[_GR_BETA_BEATS_GAMMA]],
        3: [[_GR_GAMMA_BEATS_BETA]],
    },
    "Gamma": {
        2: [[_GR_GAMMA_BEATS_BETA]],
        3: [[_GR_BETA_BEATS_GAMMA]],
    },
}

# Convenience odds: no team is clinched or eliminated
_ODDS_NONE: dict[str, StandingsOdds] = {
    t: StandingsOdds(t, 0.5, 0.25, 0.25, 0.0, 1.0, 1.0, False, False) for t in _TEAMS_3
}


def _make_odds(team: str, *, clinched: bool = False, eliminated: bool = False) -> StandingsOdds:
    if clinched:
        p = 1.0
    elif eliminated:
        p = 0.0
    else:
        p = 0.5
    return StandingsOdds(
        school=team,
        p1=p,
        p2=0.0,
        p3=0.0,
        p4=0.0,
        p_playoffs=p,
        final_playoffs=p,
        clinched=clinched,
        eliminated=eliminated,
    )


# ---------------------------------------------------------------------------
# _render_insight
# ---------------------------------------------------------------------------


def test_render_already_clinched():
    assert _render_insight("already_clinched", "Pearl", None, ()) == "Pearl has clinched a playoff spot"


def test_render_already_eliminated():
    assert _render_insight("already_eliminated", "Murrah", None, ()) == "Murrah has been eliminated from the playoffs"


def test_render_clinch_seed_1st():
    conds = (GameResult("Taylorsville", "Stringer"),)
    rendered = _render_insight("clinch_seed", "Taylorsville", 1, conds)
    assert rendered == "Taylorsville clinches 1st seed: Taylorsville beats Stringer"


def test_render_clinch_seed_2nd():
    conds = (GameResult("Pearl", "Petal"),)
    assert _render_insight("clinch_seed", "Pearl", 2, conds) == "Pearl clinches 2nd seed: Pearl beats Petal"


def test_render_clinch_seed_3rd():
    conds = (GameResult("A", "B"),)
    assert "3rd seed" in _render_insight("clinch_seed", "A", 3, conds)


def test_render_clinch_seed_4th():
    conds = (GameResult("A", "B"),)
    assert "4th seed" in _render_insight("clinch_seed", "A", 4, conds)


def test_render_clinch_seed_fallback_ordinal():
    conds = (GameResult("A", "B"),)
    rendered = _render_insight("clinch_seed", "A", 5, conds)
    assert "5th seed" in rendered


def test_render_clinch_playoffs():
    conds = (GameResult("Richland", "Brandon"),)
    rendered = _render_insight("clinch_playoffs", "Richland", None, conds)
    assert rendered == "Richland clinches a playoff spot: Richland beats Brandon"


def test_render_eliminated_if():
    conds = (GameResult("Starkville", "Terry"),)
    rendered = _render_insight("eliminated_if", "Murrah", None, conds)
    assert rendered == "Murrah is eliminated from the playoffs: Starkville beats Terry"


def test_render_unknown_type_fallback():
    conds = (GameResult("A", "B"),)
    rendered = _render_insight("unknown_type", "A", None, conds)
    assert "A" in rendered and "A beats B" in rendered


def test_render_multiple_conditions_joined_with_semicolon():
    conds = (GameResult("A", "B"), GameResult("C", "D"))
    rendered = _render_insight("clinch_seed", "A", 1, conds)
    assert "A beats B; C beats D" in rendered


# ---------------------------------------------------------------------------
# _atom_is_simple_game_results
# ---------------------------------------------------------------------------


def test_atom_simple_one_game_result():
    assert _atom_is_simple_game_results([GameResult("A", "B")]) is True


def test_atom_simple_two_game_results():
    assert _atom_is_simple_game_results([GameResult("A", "B"), GameResult("C", "D")]) is True


def test_atom_simple_three_game_results():
    gr = GameResult("A", "B")
    assert _atom_is_simple_game_results([gr, gr, gr]) is True


def test_atom_too_many_conditions():
    gr = GameResult("A", "B")
    assert _atom_is_simple_game_results([gr, gr, gr, gr]) is False


def test_atom_empty_is_not_simple():
    assert _atom_is_simple_game_results([]) is False


def test_atom_contains_margin_condition():
    mc = MarginCondition(add=(("A", "B"),), sub=(), op=">=", threshold=3)
    assert _atom_is_simple_game_results([GameResult("A", "B"), mc]) is False


def test_atom_contains_coin_flip():
    assert _atom_is_simple_game_results([GameResult("A", "B"), CoinFlipResult("X", "Y")]) is False


def test_atom_contains_pd_rank_condition():
    pdr = PDRankCondition(team="A", rank=1, group=("A", "B"))
    assert _atom_is_simple_game_results([GameResult("A", "B"), pdr]) is False


def test_atom_only_pd_rank_condition():
    pdr = PDRankCondition(team="A", rank=1, group=("A", "B"))
    assert _atom_is_simple_game_results([pdr]) is False


# ---------------------------------------------------------------------------
# _masks_satisfying_conditions
# ---------------------------------------------------------------------------


def test_masks_satisfying_single_condition_a_wins():
    # remaining[0] = ("Beta","Gamma"); bit 0=1 means Beta(a) wins
    conds = (GameResult("Beta", "Gamma"),)
    masks = _masks_satisfying_conditions(conds, _REMAINING_1)
    assert masks == [1]


def test_masks_satisfying_single_condition_b_wins():
    conds = (GameResult("Gamma", "Beta"),)
    masks = _masks_satisfying_conditions(conds, _REMAINING_1)
    assert masks == [0]


def test_masks_satisfying_two_games():
    remaining = [RemainingGame("A", "B"), RemainingGame("C", "D")]
    # bit 0=1 means A wins, bit 1=1 means C wins
    conds = (GameResult("A", "B"), GameResult("C", "D"))
    masks = _masks_satisfying_conditions(conds, remaining)
    assert masks == [3]  # binary 11


def test_masks_satisfying_partial_constraint():
    remaining = [RemainingGame("A", "B"), RemainingGame("C", "D")]
    conds = (GameResult("A", "B"),)  # only game 0 fixed
    masks = _masks_satisfying_conditions(conds, remaining)
    assert set(masks) == {1, 3}  # bit 0=1, bit 1 varies


def test_masks_satisfying_no_conditions_returns_all():
    remaining = [RemainingGame("A", "B"), RemainingGame("C", "D")]
    masks = _masks_satisfying_conditions((), remaining)
    assert len(masks) == 4


def test_masks_satisfying_condition_matches_second_game():
    # Condition on game index 1 — inner loop skips game 0 (no match) before matching game 1
    remaining = [RemainingGame("A", "B"), RemainingGame("C", "D")]
    conds = (GameResult("C", "D"),)
    masks = _masks_satisfying_conditions(conds, remaining)
    assert set(masks) == {2, 3}  # bit 1=1 means C wins; bit 0 varies


def test_masks_satisfying_condition_game_not_in_remaining():
    # Condition references a game absent from remaining — inner loop exhausts all items
    # without break (covering the 98->97 "loop exhausted" branch), no constraint added
    remaining = [RemainingGame("A", "B")]
    conds = (GameResult("X", "Y"),)
    masks = _masks_satisfying_conditions(conds, remaining)
    assert set(masks) == {0, 1}  # no constraint from X vs Y, so all masks valid


# ---------------------------------------------------------------------------
# _cond_game_indices
# ---------------------------------------------------------------------------


def test_cond_game_indices_single():
    indices = _cond_game_indices((GameResult("Beta", "Gamma"),), _REMAINING_1)
    assert indices == [0]


def test_cond_game_indices_two_different_games():
    remaining = [RemainingGame("A", "B"), RemainingGame("C", "D")]
    conds = (GameResult("A", "B"), GameResult("C", "D"))
    assert _cond_game_indices(conds, remaining) == [0, 1]


def test_cond_game_indices_deduplicates():
    remaining = [RemainingGame("A", "B"), RemainingGame("C", "D")]
    conds = (GameResult("A", "B"), GameResult("A", "B"))
    assert _cond_game_indices(conds, remaining) == [0]


def test_cond_game_indices_reversed_pair():
    # condition winner/loser may be reversed vs RemainingGame a/b order
    remaining = [RemainingGame("Beta", "Gamma")]
    conds = (GameResult("Gamma", "Beta"),)  # Gamma(b) wins
    assert _cond_game_indices(conds, remaining) == [0]


# ---------------------------------------------------------------------------
# _conditions_frozenset
# ---------------------------------------------------------------------------


def test_conditions_frozenset_basic():
    conds = (GameResult("A", "B"), GameResult("C", "D"))
    fs = _conditions_frozenset(conds)
    assert ("A", "B", 1, None) in fs
    assert ("C", "D", 1, None) in fs


def test_conditions_frozenset_same_regardless_of_order():
    c1 = (GameResult("A", "B"), GameResult("C", "D"))
    c2 = (GameResult("C", "D"), GameResult("A", "B"))
    assert _conditions_frozenset(c1) == _conditions_frozenset(c2)


# ---------------------------------------------------------------------------
# _verify_insight_margins
# ---------------------------------------------------------------------------


def test_verify_margins_skipped_at_r4_or_less():
    # With r_computed=4, should return True without calling tiebreaker
    result = _verify_insight_margins(
        (GameResult("Beta", "Gamma"),),
        "Beta",
        _TEAMS_3,
        _COMPLETED_3,
        _REMAINING_1,
        r_computed=4,
        expected_seed=2,
    )
    assert result is True


def test_verify_margins_r0_skipped():
    result = _verify_insight_margins(
        (),
        "Alpha",
        _TEAMS_3,
        _COMPLETED_3,
        _REMAINING_1,
        r_computed=0,
        expected_in_playoffs=True,
    )
    assert result is True


def test_verify_margins_clinch_seed_correct(r5_region):
    """Beta clinches seed 2 when Beta beats Gamma — should pass for all margins."""
    teams, completed, remaining = r5_region
    conds = (GameResult("Beta", "Gamma"),)
    result = _verify_insight_margins(
        conds,
        "Beta",
        teams,
        completed,
        remaining,
        r_computed=5,
        expected_seed=2,
    )
    assert result is True


def test_verify_margins_clinch_seed_wrong_team(r5_region):
    """Condition says Beta beats Gamma, but we check if *Alpha* is at seed 2 — should fail."""
    teams, completed, remaining = r5_region
    conds = (GameResult("Beta", "Gamma"),)
    result = _verify_insight_margins(
        conds,
        "Alpha",
        teams,
        completed,
        remaining,
        r_computed=5,
        expected_seed=2,
    )
    # Alpha is at seed 1 when Beta beats Gamma, not seed 2
    assert result is False


def test_verify_margins_clinch_playoffs_true(r5_region):
    """Beta makes playoffs when Beta beats Gamma."""
    teams, completed, remaining = r5_region
    conds = (GameResult("Beta", "Gamma"),)
    result = _verify_insight_margins(
        conds,
        "Beta",
        teams,
        completed,
        remaining,
        r_computed=5,
        expected_in_playoffs=True,
    )
    assert result is True


def test_verify_margins_eliminated_false_correct(r5_region):
    """Gamma is NOT in playoffs when Beta beats Gamma (3-team region, top 3 are in playoffs —
    but if playoff_seeds=2 and Gamma loses, they're out)."""
    teams, completed, remaining = r5_region
    conds = (GameResult("Beta", "Gamma"),)
    # With playoff_seeds=2, only Alpha and Beta make it when Beta beats Gamma
    result = _verify_insight_margins(
        conds,
        "Gamma",
        teams,
        completed,
        remaining,
        r_computed=5,
        expected_in_playoffs=False,
        playoff_seeds=2,
    )
    assert result is True


def test_verify_margins_eliminated_fails_when_team_in_playoffs(r5_region):
    """Claim Beta is eliminated when Gamma beats Beta — but Beta is in top 3 (not top 2)."""
    teams, completed, remaining = r5_region
    conds = (GameResult("Gamma", "Beta"),)
    # With playoff_seeds=3, even if Gamma beats Beta, Beta finishes 3rd = still in playoffs
    result = _verify_insight_margins(
        conds,
        "Beta",
        teams,
        completed,
        remaining,
        r_computed=5,
        expected_in_playoffs=False,
        playoff_seeds=3,
    )
    assert result is False


def test_verify_margins_clinch_playoffs_fails_when_team_not_in_top_k(r5_region):
    """expected_in_playoffs=True fails when team finishes outside top-k (covers line 170)."""
    teams, completed, remaining = r5_region
    conds = (GameResult("Beta", "Gamma"),)
    # With playoff_seeds=2, Gamma finishes 3rd when Beta beats Gamma → NOT in top 2
    result = _verify_insight_margins(
        conds,
        "Gamma",
        teams,
        completed,
        remaining,
        r_computed=5,
        expected_in_playoffs=True,
        playoff_seeds=2,
    )
    assert result is False


def test_verify_margins_no_check_returns_true(r5_region):
    """Neither expected_seed nor expected_in_playoffs set — loop runs but never checks (covers 171->157)."""
    teams, completed, remaining = r5_region
    conds = (GameResult("Beta", "Gamma"),)
    result = _verify_insight_margins(
        conds,
        "Beta",
        teams,
        completed,
        remaining,
        r_computed=5,
    )
    assert result is True


@pytest.fixture
def r5_region():
    """Simple 3-team region with 1 remaining game; r_computed=5 triggers margin check."""
    return _TEAMS_3, _COMPLETED_3, _REMAINING_1


# ---------------------------------------------------------------------------
# _extract_clinch_seed_insights
# ---------------------------------------------------------------------------


def test_extract_clinch_seed_basic():
    insights = _extract_clinch_seed_insights(_ATOMS_3, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=3)
    # Beta seed 2 and seed 3 atoms are each 1-condition GameResult → emit
    beta_seed2 = [i for i in insights if i.team == "Beta" and i.seed == 2]
    assert len(beta_seed2) == 1
    assert beta_seed2[0].insight_type == "clinch_seed"
    assert beta_seed2[0].conditions == (_GR_BETA_BEATS_GAMMA,)
    assert beta_seed2[0].margin_verified is True


def test_extract_clinch_seed_skips_already_clinched():
    odds_clinched = {**_ODDS_NONE, "Beta": _make_odds("Beta", clinched=True)}
    insights = _extract_clinch_seed_insights(
        _ATOMS_3, _TEAMS_3, _COMPLETED_3, _REMAINING_1, odds_clinched, r_computed=3
    )
    assert not any(i.team == "Beta" for i in insights)


def test_extract_clinch_seed_skips_empty_atom():
    # Alpha's atom has empty conditions — not a valid clinch_seed insight
    insights = _extract_clinch_seed_insights(_ATOMS_3, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=3)
    assert not any(i.team == "Alpha" for i in insights)


def test_extract_clinch_seed_skips_margin_condition():
    atoms = {
        "Beta": {
            2: [[GameResult("Beta", "Gamma"), MarginCondition(add=(("Beta", "Gamma"),), sub=(), op=">=", threshold=3)]]
        }
    }
    insights = _extract_clinch_seed_insights(atoms, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=3)
    assert not any(i.team == "Beta" and i.seed == 2 for i in insights)


def test_extract_clinch_seed_skips_too_many_conditions():
    gr = GameResult("Beta", "Gamma")
    atoms = {"Beta": {2: [[gr, gr, gr, gr]]}}  # 4 conditions
    insights = _extract_clinch_seed_insights(atoms, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=3)
    assert not any(i.team == "Beta" for i in insights)


def test_extract_clinch_seed_skips_pd_rank_condition():
    pdr = PDRankCondition(team="Beta", rank=1, group=("Beta", "Gamma"))
    atoms = {"Beta": {2: [[GameResult("Beta", "Gamma"), pdr]]}}
    insights = _extract_clinch_seed_insights(atoms, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=3)
    assert not any(i.team == "Beta" for i in insights)


def test_extract_clinch_seed_skips_coin_flip():
    atoms = {"Beta": {2: [[GameResult("Beta", "Gamma"), CoinFlipResult("Beta", "Gamma")]]}}
    insights = _extract_clinch_seed_insights(atoms, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=3)
    assert not any(i.team == "Beta" for i in insights)


def test_extract_clinch_seed_margin_fail_suppresses(monkeypatch):
    """Insight is suppressed when margin verification returns False."""
    monkeypatch.setattr("backend.helpers.insights._verify_insight_margins", lambda *a, **kw: False)
    insights = _extract_clinch_seed_insights(_ATOMS_3, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=8)
    # All conditional insights suppressed
    assert insights == []


def test_extract_clinch_seed_empty_atoms():
    insights = _extract_clinch_seed_insights({}, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=3)
    assert insights == []


def test_extract_clinch_seed_multiple_seeds_for_same_team():
    insights = _extract_clinch_seed_insights(_ATOMS_3, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=3)
    beta_insights = [i for i in insights if i.team == "Beta"]
    seeds = {i.seed for i in beta_insights}
    assert 2 in seeds and 3 in seeds  # both atoms qualify


# ---------------------------------------------------------------------------
# _extract_clinch_playoffs_insights
# ---------------------------------------------------------------------------


def test_extract_clinch_playoffs_deduplicates_against_clinch_seed():
    """clinch_playoffs insight with same conditions as a clinch_seed is suppressed."""
    clinch_seed = _extract_clinch_seed_insights(
        _ATOMS_3, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=3
    )
    clinch_p = _extract_clinch_playoffs_insights(
        _ATOMS_3,
        _TEAMS_3,
        _COMPLETED_3,
        _REMAINING_1,
        _ODDS_NONE,
        r_computed=3,
        clinch_seed_insights=clinch_seed,
    )
    # The atoms in _ATOMS_3 each clinch a specific seed → clinch_playoffs should be empty
    assert clinch_p == []


def test_extract_clinch_playoffs_emits_when_no_seed_insight():
    """clinch_playoffs emitted when atom verified but no matching clinch_seed insight."""
    clinch_p = _extract_clinch_playoffs_insights(
        _ATOMS_3,
        _TEAMS_3,
        _COMPLETED_3,
        _REMAINING_1,
        _ODDS_NONE,
        r_computed=3,
        clinch_seed_insights=[],  # no prior clinch_seed insights
    )
    # Now the atom (Beta→Gamma for seed 2) is NOT covered by a clinch_seed insight
    beta_p = [i for i in clinch_p if i.team == "Beta"]
    assert len(beta_p) >= 1
    assert all(i.insight_type == "clinch_playoffs" for i in beta_p)


def test_extract_clinch_playoffs_skips_already_clinched():
    odds_clinched = {**_ODDS_NONE, "Beta": _make_odds("Beta", clinched=True)}
    clinch_p = _extract_clinch_playoffs_insights(
        _ATOMS_3,
        _TEAMS_3,
        _COMPLETED_3,
        _REMAINING_1,
        odds_clinched,
        r_computed=3,
        clinch_seed_insights=[],
    )
    assert not any(i.team == "Beta" for i in clinch_p)


def test_extract_clinch_playoffs_deduplicates_same_conditions_across_seeds():
    """Same atom appearing for seeds 2 and 3 should only emit one clinch_playoffs insight."""
    gr = GameResult("Beta", "Gamma")
    atoms = {
        "Beta": {
            2: [[gr]],
            3: [[gr]],  # same atom for different seeds
        }
    }
    clinch_p = _extract_clinch_playoffs_insights(
        atoms,
        _TEAMS_3,
        _COMPLETED_3,
        _REMAINING_1,
        _ODDS_NONE,
        r_computed=3,
        clinch_seed_insights=[],
    )
    beta_p = [i for i in clinch_p if i.team == "Beta"]
    # Only one clinch_playoffs insight for the same conditions
    assert len(beta_p) == 1


def test_extract_clinch_playoffs_margin_fail_suppresses(monkeypatch):
    monkeypatch.setattr("backend.helpers.insights._verify_insight_margins", lambda *a, **kw: False)
    clinch_p = _extract_clinch_playoffs_insights(
        _ATOMS_3,
        _TEAMS_3,
        _COMPLETED_3,
        _REMAINING_1,
        _ODDS_NONE,
        r_computed=8,
        clinch_seed_insights=[],
    )
    assert clinch_p == []


def test_extract_clinch_playoffs_skips_non_game_result_atom():
    atoms = {"Beta": {2: [[GameResult("Beta", "Gamma"), PDRankCondition("Beta", 1, ("Beta", "Gamma"))]]}}
    clinch_p = _extract_clinch_playoffs_insights(
        atoms,
        _TEAMS_3,
        _COMPLETED_3,
        _REMAINING_1,
        _ODDS_NONE,
        r_computed=3,
        clinch_seed_insights=[],
    )
    assert not any(i.team == "Beta" for i in clinch_p)


# ---------------------------------------------------------------------------
# _extract_elimination_insights
# ---------------------------------------------------------------------------


def test_extract_elimination_basic():
    # playoff_seeds=2 → elim_seed = playoff_seeds + 1 = 3
    atoms = {"Gamma": {3: [[GameResult("Beta", "Gamma")]]}}
    insights = _extract_elimination_insights(
        atoms, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=3, playoff_seeds=2
    )
    gamma_elim = [i for i in insights if i.team == "Gamma"]
    assert len(gamma_elim) == 1
    assert gamma_elim[0].insight_type == "eliminated_if"
    assert gamma_elim[0].conditions == (GameResult("Beta", "Gamma"),)


def test_extract_elimination_skips_already_eliminated():
    atoms = {"Gamma": {3: [[GameResult("Beta", "Gamma")]]}}
    odds = {**_ODDS_NONE, "Gamma": _make_odds("Gamma", eliminated=True)}
    insights = _extract_elimination_insights(
        atoms, _TEAMS_3, _COMPLETED_3, _REMAINING_1, odds, r_computed=3, playoff_seeds=2
    )
    assert not any(i.team == "Gamma" for i in insights)


def test_extract_elimination_skips_margin_condition():
    mc = MarginCondition(add=(("Beta", "Gamma"),), sub=(), op=">=", threshold=3)
    # playoff_seeds=2 → elim_seed=3
    atoms = {"Gamma": {3: [[GameResult("Beta", "Gamma"), mc]]}}
    insights = _extract_elimination_insights(
        atoms, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=3, playoff_seeds=2
    )
    assert insights == []


def test_extract_elimination_skips_too_many_conditions():
    gr = GameResult("Beta", "Gamma")
    atoms = {"Gamma": {3: [[gr, gr, gr, gr]]}}
    insights = _extract_elimination_insights(
        atoms, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=3, playoff_seeds=2
    )
    assert insights == []


def test_extract_elimination_skips_pd_rank_condition():
    pdr = PDRankCondition("Gamma", 1, ("Beta", "Gamma"))
    atoms = {"Gamma": {3: [[GameResult("Beta", "Gamma"), pdr]]}}
    insights = _extract_elimination_insights(
        atoms, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=3, playoff_seeds=2
    )
    assert insights == []


def test_extract_elimination_margin_fail_suppresses(monkeypatch):
    monkeypatch.setattr("backend.helpers.insights._verify_insight_margins", lambda *a, **kw: False)
    atoms = {"Gamma": {3: [[GameResult("Beta", "Gamma")]]}}
    insights = _extract_elimination_insights(
        atoms, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=8, playoff_seeds=2
    )
    assert insights == []


def test_extract_elimination_empty_atoms():
    insights = _extract_elimination_insights({}, _TEAMS_3, _COMPLETED_3, _REMAINING_1, _ODDS_NONE, r_computed=3)
    assert insights == []


# ---------------------------------------------------------------------------
# _sort_key
# ---------------------------------------------------------------------------


def _make_insight(insight_type, team="A", seed=None, num_conditions=1):
    conds = tuple(GameResult("A", "B") for _ in range(num_conditions))
    return KeyInsight(
        insight_type=insight_type,
        team=team,
        seed=seed,
        conditions=conds,
        margin_verified=True,
        rendered="x",
        r_computed=3,
    )


def test_sort_key_type_ordering():
    a_clinched = _make_insight("already_clinched")
    a_elim = _make_insight("already_eliminated")
    cs = _make_insight("clinch_seed", seed=1)
    cp = _make_insight("clinch_playoffs")
    ei = _make_insight("eliminated_if")
    ordered = sorted([ei, cp, cs, a_elim, a_clinched], key=_sort_key)
    types = [i.insight_type for i in ordered]
    assert types == ["already_clinched", "already_eliminated", "clinch_seed", "clinch_playoffs", "eliminated_if"]


def test_sort_key_fewer_conditions_first():
    i1 = _make_insight("clinch_seed", seed=1, num_conditions=2)
    i2 = _make_insight("clinch_seed", seed=1, num_conditions=1)
    assert _sort_key(i2) < _sort_key(i1)


def test_sort_key_higher_seed_first():
    s1 = _make_insight("clinch_seed", seed=1)
    s2 = _make_insight("clinch_seed", seed=2)
    assert _sort_key(s1) < _sort_key(s2)


def test_sort_key_alphabetical_by_team():
    ia = _make_insight("clinch_seed", team="Alpha", seed=1)
    ib = _make_insight("clinch_seed", team="Beta", seed=1)
    assert _sort_key(ia) < _sort_key(ib)


def test_sort_key_none_seed_placed_last():
    cp = _make_insight("clinch_playoffs")  # seed=None
    cs = _make_insight("clinch_seed", seed=4)
    assert _sort_key(cs) < _sort_key(cp)


# ---------------------------------------------------------------------------
# _deduplicate
# ---------------------------------------------------------------------------


def test_deduplicate_keeps_subset_drops_superset():
    conds_small = (GameResult("A", "B"),)
    conds_large = (GameResult("A", "B"), GameResult("C", "D"))
    small = KeyInsight("clinch_seed", "T", 1, conds_small, True, "x", 3)
    large = KeyInsight("clinch_seed", "T", 1, conds_large, True, "x", 3)
    result = _deduplicate([small, large])
    assert small in result
    assert large not in result


def test_deduplicate_keeps_both_when_no_subset_relation():
    c1 = (GameResult("A", "B"),)
    c2 = (GameResult("C", "D"),)
    i1 = KeyInsight("clinch_seed", "T", 1, c1, True, "x", 3)
    i2 = KeyInsight("clinch_seed", "T", 2, c2, True, "x", 3)
    result = _deduplicate([i1, i2])
    assert len(result) == 2


def test_deduplicate_different_types_not_compared():
    conds = (GameResult("A", "B"),)
    cs = KeyInsight("clinch_seed", "T", 1, conds, True, "x", 3)
    cp = KeyInsight("clinch_playoffs", "T", None, conds, True, "x", 3)
    # Different types — neither dominates the other
    result = _deduplicate([cs, cp])
    assert len(result) == 2


def test_deduplicate_different_teams_not_compared():
    conds_small = (GameResult("A", "B"),)
    conds_large = (GameResult("A", "B"), GameResult("C", "D"))
    t1 = KeyInsight("clinch_seed", "Team1", 1, conds_small, True, "x", 3)
    t2 = KeyInsight("clinch_seed", "Team2", 1, conds_large, True, "x", 3)
    result = _deduplicate([t1, t2])
    assert len(result) == 2


def test_deduplicate_equal_conditions_both_kept():
    conds = (GameResult("A", "B"),)
    i1 = KeyInsight("clinch_seed", "T", 1, conds, True, "x", 3)
    i2 = KeyInsight("clinch_seed", "T", 2, conds, True, "x", 3)
    result = _deduplicate([i1, i2])
    assert len(result) == 2


# ---------------------------------------------------------------------------
# extract_insights (top-level integration)
# ---------------------------------------------------------------------------


def test_extract_insights_already_clinched_emitted():
    odds = {**_ODDS_NONE, "Alpha": _make_odds("Alpha", clinched=True)}
    insights = extract_insights(_ATOMS_3, _TEAMS_3, _COMPLETED_3, _REMAINING_1, odds, r_computed=3)
    alpha_facts = [i for i in insights if i.team == "Alpha"]
    assert any(i.insight_type == "already_clinched" for i in alpha_facts)


def test_extract_insights_already_eliminated_emitted():
    odds = {**_ODDS_NONE, "Gamma": _make_odds("Gamma", eliminated=True)}
    insights = extract_insights(_ATOMS_3, _TEAMS_3, _COMPLETED_3, _REMAINING_1, odds, r_computed=3)
    gamma_facts = [i for i in insights if i.team == "Gamma"]
    assert any(i.insight_type == "already_eliminated" for i in gamma_facts)


def test_extract_insights_none_odds_default():
    # Passing odds=None should not crash
    insights = extract_insights(_ATOMS_3, _TEAMS_3, _COMPLETED_3, _REMAINING_1, odds=None, r_computed=3)
    assert isinstance(insights, list)


def test_extract_insights_region_cap():
    """Total insights capped at _MAX_TOTAL_REGION (8)."""
    # Fabricate lots of insights by having 10 teams each with a clinch_seed atom
    teams = [f"Team{i}" for i in range(10)]
    atoms = {t: {1: [[GameResult(t, "Opponent")]]} for t in teams}
    remaining = [RemainingGame(t, "Opponent") for t in teams[:3]]
    insights = extract_insights(atoms, teams, [], remaining, odds=None, r_computed=3)
    assert len(insights) <= 8


def test_extract_insights_per_team_clinch_cap(monkeypatch):
    """No more than 3 clinch insights per team."""
    monkeypatch.setattr("backend.helpers.insights._verify_insight_margins", lambda *a, **kw: True)
    atoms = {
        "Beta": {
            1: [[GameResult("A", "B")]],
            2: [[GameResult("C", "D")]],
            3: [[GameResult("E", "F")]],
            4: [[GameResult("G", "H")]],
        }
    }
    remaining = [
        RemainingGame("A", "B"),
        RemainingGame("C", "D"),
        RemainingGame("E", "F"),
        RemainingGame("G", "H"),
    ]
    insights = extract_insights(atoms, ["Beta"], [], remaining, r_computed=3)
    beta_clinch = [i for i in insights if i.team == "Beta" and i.insight_type == "clinch_seed"]
    assert len(beta_clinch) <= 3


def test_extract_insights_per_team_elim_cap(monkeypatch):
    """No more than 3 elimination insights per team."""
    monkeypatch.setattr("backend.helpers.insights._verify_insight_margins", lambda *a, **kw: True)
    atoms = {
        "Beta": {
            5: [
                [GameResult("A", "B")],
                [GameResult("C", "D")],
                [GameResult("E", "F")],
                [GameResult("G", "H")],
            ]
        }
    }
    remaining = [
        RemainingGame("A", "B"),
        RemainingGame("C", "D"),
        RemainingGame("E", "F"),
        RemainingGame("G", "H"),
    ]
    insights = extract_insights(atoms, ["Beta"], [], remaining, r_computed=3)
    beta_elim = [i for i in insights if i.team == "Beta" and i.insight_type == "eliminated_if"]
    assert len(beta_elim) <= 3


def test_extract_insights_sorted_clinch_before_elim():
    odds = {**_ODDS_NONE, "Alpha": _make_odds("Alpha", clinched=True)}
    atoms = {
        "Beta": {5: [[GameResult("Beta", "Gamma")]]},
        "Gamma": {2: [[GameResult("Gamma", "Beta")]]},
    }
    insights = extract_insights(atoms, _TEAMS_3, _COMPLETED_3, _REMAINING_1, odds, r_computed=3, playoff_seeds=2)
    types = [i.insight_type for i in insights]
    # already_clinched comes first
    if "already_clinched" in types and "eliminated_if" in types:
        assert types.index("already_clinched") < types.index("eliminated_if")


def test_extract_insights_returns_list_when_no_atoms():
    insights = extract_insights({}, _TEAMS_3, _COMPLETED_3, _REMAINING_1, odds=None, r_computed=10)
    assert insights == []


# ---------------------------------------------------------------------------
# Serialization round-trips
# ---------------------------------------------------------------------------


def test_serialize_deserialize_clinch_seed():
    ins = KeyInsight(
        insight_type="clinch_seed",
        team="Taylorsville",
        seed=1,
        conditions=(GameResult("Taylorsville", "Stringer"),),
        margin_verified=True,
        rendered="Taylorsville clinches 1st seed: Taylorsville beats Stringer",
        r_computed=8,
    )
    assert deserialize_insights(serialize_insights([ins])) == [ins]


def test_serialize_deserialize_clinch_playoffs():
    ins = KeyInsight(
        insight_type="clinch_playoffs",
        team="Richland",
        seed=None,
        conditions=(GameResult("Richland", "Brandon"),),
        margin_verified=True,
        rendered="Richland clinches a playoff spot: Richland beats Brandon",
        r_computed=8,
    )
    assert deserialize_insights(serialize_insights([ins])) == [ins]


def test_serialize_deserialize_eliminated_if():
    ins = KeyInsight(
        insight_type="eliminated_if",
        team="Murrah",
        seed=None,
        conditions=(GameResult("Starkville", "Terry"),),
        margin_verified=True,
        rendered="Murrah is eliminated from the playoffs: Starkville beats Terry",
        r_computed=9,
    )
    assert deserialize_insights(serialize_insights([ins])) == [ins]


def test_serialize_deserialize_already_clinched():
    ins = KeyInsight(
        insight_type="already_clinched",
        team="Pearl",
        seed=None,
        conditions=(),
        margin_verified=True,
        rendered="Pearl has clinched a playoff spot",
        r_computed=2,
    )
    assert deserialize_insights(serialize_insights([ins])) == [ins]


def test_serialize_deserialize_already_eliminated():
    ins = KeyInsight(
        insight_type="already_eliminated",
        team="Murrah",
        seed=None,
        conditions=(),
        margin_verified=True,
        rendered="Murrah has been eliminated from the playoffs",
        r_computed=5,
    )
    assert deserialize_insights(serialize_insights([ins])) == [ins]


def test_serialize_deserialize_seed_none_preserved():
    ins = KeyInsight(
        insight_type="clinch_playoffs",
        team="A",
        seed=None,
        conditions=(GameResult("A", "B"),),
        margin_verified=False,
        rendered="A clinches a playoff spot: A beats B",
        r_computed=7,
    )
    result = deserialize_insights(serialize_insights([ins]))
    assert result[0].seed is None


def test_serialize_deserialize_multi_condition():
    ins = KeyInsight(
        insight_type="clinch_seed",
        team="A",
        seed=2,
        conditions=(GameResult("A", "B"), GameResult("C", "D", min_margin=3)),
        margin_verified=True,
        rendered="A clinches 2nd seed: A beats B; C beats D by 3 or more",
        r_computed=4,
    )
    result = deserialize_insights(serialize_insights([ins]))
    assert result == [ins]


def test_serialize_empty_list():
    assert serialize_insights([]) == []


def test_deserialize_empty_list():
    assert deserialize_insights([]) == []
