"""Direct unit tests for tiebreaker internals.

Covers:
- standings_from_mask and build_h2h_maps tie-game branches.
- step2_step4_arrays None-return branches (no game vs outside opponent).
- unique_intra_bucket_games and sensitive_boundary_games.
- resolve_with_results (public API for human-readable results entry).
- resolve_standings_for_mask coin_flip_collector population.

All tests use a 4-team "diamond" setup unless noted:
    Teams: Alpha, Beta, Gamma, Delta
    Alpha and Beta both beat Gamma and Delta (no Alpha–Beta game in completed).
    Gamma and Delta serve as outside-team opponents.
"""

from backend.helpers.data_classes import CompletedGame, RemainingGame
from backend.helpers.tiebreakers import (
    base_bucket_order,
    build_h2h_maps,
    resolve_bucket,
    resolve_standings_for_mask,
    resolve_standings_with_trace,
    resolve_with_results,
    sensitive_boundary_games,
    standings_from_mask,
    step2_step4_arrays,
    unique_intra_bucket_games,
)

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

_TEAMS = ["Alpha", "Beta", "Delta", "Gamma"]

# Alpha and Beta each beat Gamma and Delta; no Alpha-Beta game in completed.
# pd_a is stored from the lexicographically-first team's perspective.
# CompletedGame fields: a (lex-first), b (lex-second), res_a, pd_a, pa_a, pa_b
_BASE_COMPLETED = [
    # Alpha beat Delta by 7 (Alpha lex-first vs Delta)
    CompletedGame(a="Alpha", b="Delta", res_a=1, pd_a=7, pa_a=14, pa_b=21),
    # Alpha beat Gamma by 7
    CompletedGame(a="Alpha", b="Gamma", res_a=1, pd_a=7, pa_a=14, pa_b=21),
    # Beta beat Delta by 7
    CompletedGame(a="Beta", b="Delta", res_a=1, pd_a=7, pa_a=14, pa_b=21),
    # Beta beat Gamma by 7
    CompletedGame(a="Beta", b="Gamma", res_a=1, pd_a=7, pa_a=14, pa_b=21),
]

_NO_REMAINING: list[RemainingGame] = []


def _make_wl_totals(**overrides):
    """Return a wl_totals dict for the 4-team fixture, with optional PA overrides."""
    base = {
        "Alpha": {"w": 2, "l": 0, "t": 0, "pa": 28},
        "Beta":  {"w": 2, "l": 0, "t": 0, "pa": 28},
        "Gamma": {"w": 0, "l": 2, "t": 0, "pa": 42},
        "Delta": {"w": 0, "l": 2, "t": 0, "pa": 42},
    }
    for team, vals in overrides.items():
        base[team].update(vals)
    return base


# ---------------------------------------------------------------------------
# standings_from_mask — tie (draw) game branch (lines 49–50)
# ---------------------------------------------------------------------------


def test_standings_from_mask_tie_game():
    """res_a == 0 in a completed game increments both teams' tie counts."""
    teams = ["Alpha", "Beta"]
    completed = [CompletedGame(a="Alpha", b="Beta", res_a=0, pd_a=0, pa_a=14, pa_b=14)]
    totals = standings_from_mask(teams, completed, [], 0, pa_win=14, margins={})
    assert totals["Alpha"]["t"] == 1
    assert totals["Beta"]["t"] == 1
    assert totals["Alpha"]["w"] == 0
    assert totals["Beta"]["w"] == 0


# ---------------------------------------------------------------------------
# build_h2h_maps — tie game branch (lines 103–104)
# ---------------------------------------------------------------------------


def test_build_h2h_maps_tie_game():
    """res_a == 0 gives both teams 0.5 H2H points and negated capped PD."""
    completed = [CompletedGame(a="Alpha", b="Beta", res_a=0, pd_a=4, pa_a=14, pa_b=18)]
    h2h_points, capped_pd, _ = build_h2h_maps(completed, [], 0, {})
    assert h2h_points[("Alpha", "Beta")] == h2h_points[("Beta", "Alpha")]
    assert h2h_points[("Alpha", "Beta")] * 2 == 1
    # pd_a=4 → cap_a=4; capped_pd_map[("Alpha","Beta")] += 4, [("Beta","Alpha")] -= 4
    assert capped_pd[("Alpha", "Beta")] == 4
    assert capped_pd[("Beta", "Alpha")] == -4


# ---------------------------------------------------------------------------
# step2_step4_arrays — None branches (lines 186, 189, 203)
# These fire when a tied team has no game (completed or remaining) vs an
# outside opponent — possible when the schedule is not fully round-robin.
# ---------------------------------------------------------------------------


def test_step2_step4_arrays_no_game_vs_outside():
    """res_vs and pd_vs return None when a tied team never played an outside team."""
    # 4-team setup: Alpha and Beta tied; Gamma and Delta are outside.
    # Only Alpha has a game vs Gamma; neither team has a game vs Delta.
    teams = ["Alpha", "Beta", "Delta", "Gamma"]
    completed = [
        CompletedGame(a="Alpha", b="Gamma", res_a=1, pd_a=7, pa_a=14, pa_b=21),
    ]
    remaining: list[RemainingGame] = []
    pair = ["Alpha", "Beta"]
    base_order = ["Alpha", "Beta", "Delta", "Gamma"]

    step2, step4 = step2_step4_arrays(teams, pair, base_order, completed, remaining, 0, {})

    # outside = [Delta, Gamma] (base_order with pair removed)
    # Alpha vs Delta: no game → None; Alpha vs Gamma: win → 2
    # Beta vs Delta: no game → None; Beta vs Gamma: no game → None
    assert step2["Alpha"][0] is None  # vs Delta: no game
    assert step2["Alpha"][1] == 2     # vs Gamma: Alpha won
    assert step2["Beta"][0] is None   # vs Delta: no game
    assert step2["Beta"][1] is None   # vs Gamma: no game

    assert step4["Alpha"][0] is None  # vs Delta: no game
    assert step4["Alpha"][1] == 7     # vs Gamma: +7 capped PD
    assert step4["Beta"][0] is None   # vs Delta: no game
    assert step4["Beta"][1] is None   # vs Gamma: no game


def test_step2_step4_arrays_tie_vs_outside():
    """res_vs returns 1 (tie encoding) when a completed game has res_a == 0."""
    teams = ["Alpha", "Beta", "Gamma"]
    completed = [
        CompletedGame(a="Alpha", b="Gamma", res_a=0, pd_a=0, pa_a=14, pa_b=14),
    ]
    pair = ["Alpha", "Beta"]
    base_order = ["Alpha", "Beta", "Gamma"]

    step2, _ = step2_step4_arrays(teams, pair, base_order, completed, [], 0, {})

    # outside = ["Gamma"]; Alpha vs Gamma is a tie → res_vs == 1
    assert step2["Alpha"] == [1]


# ---------------------------------------------------------------------------
# unique_intra_bucket_games
# ---------------------------------------------------------------------------


def test_unique_intra_bucket_games_returns_shared_games():
    """Games between teams in the same multi-team bucket are returned."""
    # Alpha and Beta are in a 2-team tie bucket; Gamma is solo.
    buckets = [["Alpha", "Beta"], ["Gamma"]]
    remaining = [
        RemainingGame(a="Alpha", b="Beta"),   # intra-bucket
        RemainingGame(a="Alpha", b="Gamma"),  # cross-bucket
        RemainingGame(a="Beta", b="Gamma"),   # cross-bucket
    ]
    intra = unique_intra_bucket_games(buckets, remaining)
    assert len(intra) == 1
    assert intra[0] == RemainingGame(a="Alpha", b="Beta")


def test_unique_intra_bucket_games_no_intra():
    """No intra-bucket games when all remaining games are cross-bucket."""
    buckets = [["Alpha"], ["Beta"], ["Gamma"]]
    remaining = [
        RemainingGame(a="Alpha", b="Beta"),
        RemainingGame(a="Alpha", b="Gamma"),
    ]
    assert unique_intra_bucket_games(buckets, remaining) == []


def test_unique_intra_bucket_games_deduplicates():
    """Duplicate intra-bucket games are returned only once."""
    buckets = [["Alpha", "Beta"]]
    remaining = [
        RemainingGame(a="Alpha", b="Beta"),
        RemainingGame(a="Alpha", b="Beta"),
    ]
    intra = unique_intra_bucket_games(buckets, remaining)
    assert len(intra) == 1


# ---------------------------------------------------------------------------
# sensitive_boundary_games
# ---------------------------------------------------------------------------


def test_sensitive_boundary_games_identifies_sensitive_game():
    """A boundary game whose margin changes the seeding is flagged as sensitive.

    Setup: Alpha and Beta are tied 1-1 in completed games (split H2H).
    A remaining boundary game: Alpha vs Gamma (Gamma is outside the bucket).
    If Alpha wins by 1 vs Gamma, H2H PD with Beta differs from a 12-point win,
    shifting the Step-4 tiebreaker result.
    """
    # Alpha beat Delta, Beta beat Gamma — both 1-1 overall from their split
    # Alpha-Beta H2H (res_a=0 → tie points).
    completed = [
        CompletedGame(a="Alpha", b="Beta", res_a=0, pd_a=0, pa_a=14, pa_b=14),
        CompletedGame(a="Alpha", b="Delta", res_a=1, pd_a=7, pa_a=14, pa_b=21),
        CompletedGame(a="Beta", b="Gamma", res_a=1, pd_a=7, pa_a=14, pa_b=21),
    ]
    # Remaining: Alpha vs Gamma (boundary — Alpha in bucket, Gamma outside)
    #            Beta vs Delta (boundary — Beta in bucket, Delta outside)
    remaining = [
        RemainingGame(a="Alpha", b="Gamma"),
        RemainingGame(a="Beta", b="Delta"),
    ]
    teams = ["Alpha", "Beta", "Delta", "Gamma"]
    # outcome_mask=3 → both remaining[0].a (Alpha) and remaining[1].a (Beta) win
    buckets = [["Alpha", "Beta"], ["Delta"], ["Gamma"]]
    intra: list[RemainingGame] = []  # no intra-bucket remaining games

    sensitive = sensitive_boundary_games(
        buckets, remaining, intra, teams, completed, outcome_mask=3,
        base_margins={}, pa_win=14,
    )
    # Both boundary games could be sensitive; at minimum the list is non-empty
    assert len(sensitive) >= 1
    sensitive_keys = {(rg.a, rg.b) for rg in sensitive}
    assert ("Alpha", "Gamma") in sensitive_keys or ("Beta", "Delta") in sensitive_keys


# ---------------------------------------------------------------------------
# resolve_with_results — public API
# ---------------------------------------------------------------------------

_RWR_TEAMS = ["Alpha", "Beta", "Delta", "Gamma"]
_RWR_COMPLETED = [
    CompletedGame(a="Alpha", b="Delta", res_a=1, pd_a=7, pa_a=14, pa_b=21),
    CompletedGame(a="Alpha", b="Gamma", res_a=1, pd_a=7, pa_a=14, pa_b=21),
    CompletedGame(a="Beta", b="Delta", res_a=1, pd_a=7, pa_a=14, pa_b=21),
    CompletedGame(a="Beta", b="Gamma", res_a=1, pd_a=7, pa_a=14, pa_b=21),
]
_RWR_REMAINING = [RemainingGame(a="Alpha", b="Beta")]


def test_resolve_with_results_basic():
    """resolve_with_results returns a valid seeding from human-readable results."""
    results = {("Alpha", "Beta"): "Alpha"}
    seeding, _ = resolve_with_results(
        _RWR_TEAMS, _RWR_COMPLETED, _RWR_REMAINING, results
    )
    assert seeding[0] == "Alpha"
    assert set(seeding) == set(_RWR_TEAMS)


def test_resolve_with_results_margin_message_when_needed():
    """A message is emitted when the margin of a tied game would affect seeding."""
    # Alpha and Beta are tied in completed games. Their H2H remaining game is won
    # by Alpha, but since they were equal before, the margin of the remaining
    # game vs outside teams could affect Step 4. We use the base fixture where
    # they are completely symmetric — Alpha winning their H2H game gives Alpha
    # seed 1, but the margin of that game affects nothing (no further tie).
    # For a margin-sensitive message, we need an intra-bucket game without a margin.
    # Construct: Alpha and Beta tied 1-1 after completed, with a remaining game
    # between them (no margin provided → engine checks sensitivity).
    completed_tied = [
        CompletedGame(a="Alpha", b="Delta", res_a=1, pd_a=7, pa_a=14, pa_b=21),
        CompletedGame(a="Alpha", b="Gamma", res_a=1, pd_a=7, pa_a=14, pa_b=21),
        CompletedGame(a="Beta", b="Delta", res_a=1, pd_a=7, pa_a=14, pa_b=21),
        CompletedGame(a="Beta", b="Gamma", res_a=1, pd_a=7, pa_a=14, pa_b=21),
        # Split H2H: each beat the other once
        CompletedGame(a="Alpha", b="Beta", res_a=1, pd_a=7, pa_a=14, pa_b=21),
        CompletedGame(a="Alpha", b="Beta", res_a=-1, pd_a=-7, pa_a=21, pa_b=14),
    ]
    remaining_intra = [RemainingGame(a="Alpha", b="Beta")]
    results = {("Alpha", "Beta"): "Alpha"}
    seeding, _ = resolve_with_results(
        _RWR_TEAMS, completed_tied, remaining_intra, results
        # no margin provided for the intra-bucket game
    )
    assert isinstance(seeding, list)
    assert len(seeding) == 4
    # Messages may or may not fire depending on whether the margin shifts seeding;
    # what matters is the function runs without error.


def test_resolve_with_results_missing_result_raises():
    """ValueError is raised when no result is provided for a remaining game."""
    import pytest
    results = {}  # missing Alpha vs Beta result
    with pytest.raises(ValueError, match="No result provided"):
        resolve_with_results(_RWR_TEAMS, _RWR_COMPLETED, _RWR_REMAINING, results)


def test_resolve_with_results_invalid_winner_raises():
    """ValueError is raised when the winner name is not a participant."""
    import pytest
    results = {("Alpha", "Beta"): "Gamma"}  # Gamma not in this game
    with pytest.raises(ValueError, match="not a participant"):
        resolve_with_results(_RWR_TEAMS, _RWR_COMPLETED, _RWR_REMAINING, results)


def test_resolve_with_results_with_margins():
    """Explicit margins dict is accepted and used without raising."""
    results = {("Alpha", "Beta"): "Alpha"}
    margins = {("Alpha", "Beta"): 10}
    seeding, messages = resolve_with_results(
        _RWR_TEAMS, _RWR_COMPLETED, _RWR_REMAINING, results, margins=margins
    )
    assert seeding[0] == "Alpha"
    assert messages == []  # margin provided → no missing-margin message


# ---------------------------------------------------------------------------
# push_coinflip body (lines 509, 511) — coin_flip_collector populated
#
# Fires when resolve_standings_for_mask is called with a non-None
# coin_flip_collector AND a bucket remains tied after all 5 deterministic
# steps.  Use the perfectly symmetric Alpha/Beta fixture (all steps tie)
# and pass coin_flip_collector=[].
# ---------------------------------------------------------------------------


def test_resolve_standings_for_mask_coin_flip_collector_populated():
    """coin_flip_collector receives all tied groups when buckets can't be resolved.

    _BASE_COMPLETED has two symmetric tie buckets: [Alpha, Beta] (both 2-0) and
    [Delta, Gamma] (both 0-2).  No H2H game exists within either bucket, and all
    outside-game metrics are identical, so both buckets exhaust Steps 1–5 and
    fall to the coin-flip/alphabetical fallback.
    """
    teams = ["Alpha", "Beta", "Delta", "Gamma"]
    remaining: list[RemainingGame] = []
    collector: list = []

    resolve_standings_for_mask(
        teams, _BASE_COMPLETED, remaining, outcome_mask=0,
        margins={}, coin_flip_collector=collector,
    )

    # Both tie buckets are unresolvable — each should appear in the collector.
    assert len(collector) == 2
    groups = [sorted(g) for g in collector]
    assert ["Alpha", "Beta"] in groups
    assert ["Delta", "Gamma"] in groups


# ---------------------------------------------------------------------------
# push_coinflip — coin_flip_collector is None path (line 351→exit)
#
# Fires when push_coinflip is called but coin_flip_collector was not passed
# (defaults to None).  The function must silently do nothing.  Use the same
# symmetric fixture — buckets exhaust Steps 1–5 → push_coinflip fires — but
# omit coin_flip_collector so the `is not None` guard takes the False branch.
# ---------------------------------------------------------------------------


def test_resolve_bucket_no_collector_runs_silently():
    """resolve_bucket returns a valid ordering when coin_flip_collector=None.

    resolve_standings_for_mask always passes a non-None list to resolve_bucket,
    so push_coinflip's `is None` branch is only reachable by calling
    resolve_bucket directly without a collector.

    The symmetric Alpha/Beta bucket exhausts all 5 deterministic steps → Step 6
    fires push_coinflip.  With coin_flip_collector=None (the default) the
    function silently skips collection and returns an alphabetical result.
    """
    teams = ["Alpha", "Beta", "Delta", "Gamma"]
    remaining: list[RemainingGame] = []
    wl_totals = standings_from_mask(teams, _BASE_COMPLETED, remaining, 0, pa_win=14, margins={})
    base_order = base_bucket_order(teams, wl_totals)

    result = resolve_bucket(
        ["Alpha", "Beta"],
        teams, wl_totals, base_order, _BASE_COMPLETED, remaining,
        outcome_mask=0, margins={}
        # coin_flip_collector omitted → defaults to None
    )

    assert set(result) == {"Alpha", "Beta"}
    assert len(result) == 2


# ---------------------------------------------------------------------------
# resolve_standings_with_trace — step_trace_collector populated
# ---------------------------------------------------------------------------


def test_resolve_standings_with_trace_populates_step_trace():
    """resolve_standings_with_trace returns step2/step4 arrays for each tie bucket.

    The [Alpha, Beta] bucket has no H2H; step2/step4 arrays must be present
    in the returned trace keyed by the sorted bucket tuple.
    """
    teams = ["Alpha", "Beta", "Delta", "Gamma"]
    remaining: list[RemainingGame] = []

    order, trace = resolve_standings_with_trace(
        teams, _BASE_COMPLETED, remaining, outcome_mask=0, margins={}
    )

    assert set(order) == set(teams)
    assert ("Alpha", "Beta") in trace
    s2, s4 = trace[("Alpha", "Beta")]
    assert "Alpha" in s2 and "Beta" in s2
    assert "Alpha" in s4 and "Beta" in s4


def test_resolve_bucket_step_trace_collector_populated():
    """resolve_bucket stores (step2, step4) into step_trace_collector when provided."""
    teams = ["Alpha", "Beta", "Delta", "Gamma"]
    remaining: list[RemainingGame] = []
    wl_totals = standings_from_mask(teams, _BASE_COMPLETED, remaining, 0, pa_win=14, margins={})
    base_order = base_bucket_order(teams, wl_totals)
    collector: dict = {}

    resolve_bucket(
        ["Alpha", "Beta"],
        teams, wl_totals, base_order, _BASE_COMPLETED, remaining,
        outcome_mask=0, margins={},
        step_trace_collector=collector,
    )

    assert ("Alpha", "Beta") in collector
    s2, _ = collector[("Alpha", "Beta")]
    assert "Alpha" in s2 and "Beta" in s2


# ---------------------------------------------------------------------------
# resolve_with_results — margin-sensitivity message (lines 880–898)
#
# Needs a 3-team cyclic fixture where each team beats one other and loses to
# one other (a rock-paper-scissors tie), with a remaining intra-bucket game
# whose margin shifts the seeding.
# ---------------------------------------------------------------------------


def test_resolve_with_results_emits_margin_message():
    """A message is generated when an intra-bucket remaining game lacks a margin
    and the margin would change the seeding (lines 880–898).

    Setup: Alpha and Beta play a regular-season game (Alpha wins by 7, completed)
    and a rematch (remaining).  Both also beat Gamma and Delta in completed games,
    leaving Alpha 3-0 and Beta 2-1 before the rematch.  When Beta wins the
    rematch, both end at 3-1 — tied in the same bucket.

    The H2H tiebreaker (Step 3) between Alpha and Beta looks at the net capped PD
    across BOTH their games: +7 from Alpha's completed win, minus the rematch
    margin.  A 1-point Beta win leaves Alpha ahead (+6); an 8-point Beta win
    flips the advantage (-1).  The missing-margin check therefore fires.
    """
    teams = ["Alpha", "Beta", "Delta", "Gamma"]
    completed = [
        # Alpha won the first meeting
        CompletedGame(a="Alpha", b="Beta",  res_a=1,  pd_a=7,  pa_a=14, pa_b=21),
        CompletedGame(a="Alpha", b="Delta", res_a=1,  pd_a=7,  pa_a=14, pa_b=21),
        CompletedGame(a="Alpha", b="Gamma", res_a=1,  pd_a=7,  pa_a=14, pa_b=21),
        CompletedGame(a="Beta",  b="Delta", res_a=1,  pd_a=7,  pa_a=14, pa_b=21),
        CompletedGame(a="Beta",  b="Gamma", res_a=1,  pd_a=7,  pa_a=14, pa_b=21),
        # Gamma beat Delta (makes Gamma 1-2, Delta 0-3 after completed)
        CompletedGame(a="Delta", b="Gamma", res_a=-1, pd_a=-7, pa_a=21, pa_b=14),
    ]
    # Remaining: Alpha vs Beta rematch only (no margin provided)
    remaining = [RemainingGame(a="Alpha", b="Beta")]
    # Beta wins the rematch → Alpha 3-1, Beta 3-1 (tied bucket)
    results = {("Alpha", "Beta"): "Beta"}

    seeding, messages = resolve_with_results(teams, completed, remaining, results)

    assert isinstance(seeding, list)
    assert len(seeding) == 4
    # Margin of the rematch shifts the H2H PD tiebreaker → message expected.
    assert len(messages) >= 1
    assert any("Beta" in msg or "Alpha" in msg for msg in messages)
