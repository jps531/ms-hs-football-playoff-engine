"""Playoff home-game scenario enumeration for human-readable output.

For each team that qualifies for the playoffs this module enumerates, for
every applicable round (First Round, optionally Second Round, Quarterfinals,
Semifinals), the exact conditions under which the team would be the designated
home team — as well as the conditions under which they would be the away team.

Bracket depth is inferred from the number of first-round slots per bracket
half:

* **4 slots per half** → 5A-7A (16-team bracket).
  Rounds with home-team designation: First Round, Quarterfinals, Semifinals.
* **8 slots per half** → 1A-4A (32-team bracket).
  Rounds with home-team designation: First Round, Second Round, Quarterfinals,
  Semifinals.

The State Championship game is excluded; its home-site rule (South hosts odd
years, North hosts even years) is handled separately.

Public API
----------
``enumerate_home_game_scenarios`` — the single entry point; returns one
``RoundHomeScenarios`` object per applicable round.

Dependencies
------------
* ``bracket_home_odds`` — public navigation helpers (``half_slots_for_region``,
  ``slot_index_for``, ``opponent_slots``, ``was_home_r1``) and deterministic
  home-team functions (``r2_home_team``, ``qf_home_team``, ``sf_home_team``).
* ``data_classes`` — ``FormatSlot``, ``HomeGameCondition``, ``HomeGameScenario``,
  ``RoundHomeScenarios``.

Pre-playoff extension
---------------------
When ``seed`` is ``None`` the bracket has not yet been set.  Pass
``seed_scenarios`` (a dict mapping each possible seed the team could achieve
to the list of seeding-scenario condition atoms from ``build_scenario_atoms``)
to generate home-game scenarios that are further conditioned on the team's
seeding outcome.  Each seeding path produces a ``HomeGameCondition`` with
``kind="seed_required"`` prepended to all downstream home-game conditions.

Team-name resolution
--------------------
Pass ``team_lookup`` as a ``dict`` mapping ``(region, seed)`` to a school
name.  When an entry exists the school name is used in conditions; otherwise
the renderer falls back to ``"Region X #Y Seed"``.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import NamedTuple

from backend.helpers.bracket_home_odds import (
    half_slots_for_region,
    opponent_slots,
    qf_home_team,
    r2_home_team,
    sf_home_team,
    slot_index_for,
    was_home_r1,
)
from backend.helpers.data_classes import (
    FormatSlot,
    HomeGameCondition,
    HomeGameScenario,
    MatchupEntry,
    RoundHomeScenarios,
    RoundMatchups,
)

# ---------------------------------------------------------------------------
# Round-name constants
# ---------------------------------------------------------------------------

_ROUND_NAMES_5A_7A = ("First Round", "Quarterfinals", "Semifinals")
_ROUND_NAMES_1A_4A = ("First Round", "Second Round", "Quarterfinals", "Semifinals")


class _RoundOdds(NamedTuple):
    """Bundle of per-round odds values; passed to internal ``_enumerate_*`` helpers."""

    p_reach: float | None
    p_host_conditional: float | None
    p_host_marginal: float | None
    p_reach_weighted: float | None
    p_host_conditional_weighted: float | None
    p_host_marginal_weighted: float | None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _team_label(region: int, seed: int, lookup: dict[tuple[int, int], str] | None) -> str:
    """Return the school name for *(region, seed)*, or a generic label.

    Args:
        region: Region number.
        seed:   Region seed (1 = best).
        lookup: Optional mapping of ``(region, seed)`` to school name.

    Returns:
        School name when found in *lookup*; otherwise ``"Region {region} #{seed} Seed"``.
    """
    if lookup and (region, seed) in lookup:
        return lookup[(region, seed)]
    return f"Region {region} #{seed} Seed"


def _advances(
    team_name: str | None,
    region: int | None,
    seed: int | None,
    round_name: str,
) -> HomeGameCondition:
    """Build an ``"advances"`` condition for the given team and round."""
    return HomeGameCondition(
        kind="advances",
        round_name=round_name,
        region=region,
        seed=seed,
        team_name=team_name,
    )


def _explain_r1(is_home: bool) -> str:
    """Return a short explanation for the first-round home designation."""
    return "Designated home team in bracket" if is_home else "Designated away team in bracket"


def _explain_r2(
    team_region: int,
    team_seed: int,
    opp_region: int,
    opp_seed: int,
    season: int,
) -> str:
    """Return the explanation for a second-round home outcome."""

    if team_region == opp_region:
        winner = min(team_seed, opp_seed)
        return f"Same-region game — higher seed (#{winner}) hosts"
    if team_seed != opp_seed:
        winner_seed = min(team_seed, opp_seed)
        return f"Higher seed (#{winner_seed}) hosts"
    # equal cross-region seed — odd/even year tiebreak (same as QF/SF)
    odd_year = season % 2 == 1
    if odd_year:
        host_region = min(team_region, opp_region)
        return f"Equal seed (#{team_seed}) — region tiebreak: odd year, lower region# hosts (Region {host_region})"
    host_region = max(team_region, opp_region)
    return f"Equal seed (#{team_seed}) — region tiebreak: even year, higher region# hosts (Region {host_region})"


def _explain_qf(
    region1: int,
    seed1: int,
    r1_home1: bool,
    r2_home1: bool | None,
    region2: int,
    seed2: int,
    r1_home2: bool,
    r2_home2: bool | None,
    season: int,
) -> str:
    """Return the explanation for a quarterfinal home outcome.

    Mirrors the logic of ``qf_home_team`` to produce a human-readable reason.

    Args:
        region1, seed1:         Target team.
        r1_home1, r2_home1:     Target team's R1/R2 home status.  ``r2_home1``
                                is ``None`` for 5A-7A (no R2 round).
        region2, seed2:         Opponent.
        r1_home2, r2_home2:     Opponent's R1/R2 home status.
        season:                 Football season year (for odd/even tiebreak).

    Returns:
        Human-readable explanation string.
    """
    if region1 == region2:
        winner = min(seed1, seed2)
        return f"Same-region game — higher seed (#{winner}) hosts"

    home1 = (1 if r1_home1 else 0) + (1 if r2_home1 else 0)
    home2 = (1 if r1_home2 else 0) + (1 if r2_home2 else 0)
    if home1 != home2:
        fewer = home1 if home1 < home2 else home2
        more = max(home1, home2)
        host_label = "target team" if home1 < home2 else "opponent"
        return f"Fewer home games played ({fewer} vs {more}) — {host_label} hosts"
    if seed1 != seed2:
        winner_seed = min(seed1, seed2)
        return f"Higher seed (#{winner_seed}) hosts"
    # equal seed, cross-region tiebreak
    odd_year = season % 2 == 1
    if odd_year:
        host_region = min(region1, region2)
        return f"Equal seed (#{seed1}) — region tiebreak: odd year, lower region# hosts (Region {host_region})"
    host_region = max(region1, region2)
    return f"Equal seed (#{seed1}) — region tiebreak: even year, higher region# hosts (Region {host_region})"


def _explain_sf(
    region1: int,
    seed1: int,
    region2: int,
    seed2: int,
    season: int,
) -> str:
    """Return the explanation for a semifinal home outcome.

    Mirrors the logic of ``sf_home_team`` to produce a human-readable reason.

    Args:
        region1, seed1: Target team.
        region2, seed2: Opponent.
        season:         Football season year (for odd/even tiebreak).

    Returns:
        Human-readable explanation string.
    """
    if region1 == region2:
        winner = min(seed1, seed2)
        return f"Same-region game — higher seed (#{winner}) hosts"
    if seed1 != seed2:
        winner_seed = min(seed1, seed2)
        return f"Higher seed (#{winner_seed}) hosts"
    odd_year = season % 2 == 1
    if odd_year:
        host_region = min(region1, region2)
        return f"Equal seed (#{seed1}) — region tiebreak: odd year, lower region# hosts (Region {host_region})"
    host_region = max(region1, region2)
    return f"Equal seed (#{seed1}) — region tiebreak: even year, higher region# hosts (Region {host_region})"


def _r2_home_status(team_seed: int, opp_seed: int) -> bool:
    """Return True if the team (with *team_seed*) is home in a cross-region R2 game.

    Second-round home designation is purely seed-based (higher seed = lower
    number hosts) for cross-region matchups.  Same-region matchups do not
    arise in R2 under the current bracket structure.

    Args:
        team_seed: The target team's region seed.
        opp_seed:  The opponent's region seed.

    Returns:
        ``True`` if the target team is the home team.
    """
    return team_seed <= opp_seed  # lower seed number = better seed = home


# ---------------------------------------------------------------------------
# Per-round enumeration helpers
# ---------------------------------------------------------------------------


def _enumerate_r1(
    region: int,
    seed: int,
    half_slots: list[FormatSlot],
    slot_idx: int,
    round_name: str,
    odds: _RoundOdds,
) -> RoundHomeScenarios:
    """Build the ``RoundHomeScenarios`` for the first round.

    R1 home status is fully deterministic: the bracket slot designates one
    team as home and the other as away, with no conditions required.

    Args:
        region, seed: Target team's identity.
        half_slots:   Slots for the team's bracket half.
        slot_idx:     0-based index of the team's slot in *half_slots*.
        round_name:   Display label (always ``"First Round"``).
        odds:         Bundled hosting probabilities for this round.

    Returns:
        A ``RoundHomeScenarios`` with a single unconditional scenario.
    """
    slot = half_slots[slot_idx]
    is_home = was_home_r1(region, seed, slot)
    scenario = HomeGameScenario(
        conditions=(),
        explanation=_explain_r1(is_home),
    )
    return RoundHomeScenarios(
        round_name=round_name,
        will_host=(scenario,) if is_home else (),
        will_not_host=() if is_home else (scenario,),
        **odds._asdict(),
    )


def _enumerate_r2(
    region: int,
    seed: int,
    half_slots: list[FormatSlot],
    slot_idx: int,
    season: int,
    round_name: str,
    odds: _RoundOdds,
    team_lookup: dict[tuple[int, int], str] | None,
) -> RoundHomeScenarios:
    """Build the ``RoundHomeScenarios`` for the second round (1A-4A only).

    The R2 opponent is the winner of the single adjacent first-round slot.
    Two possible opponents exist (the home and away teams from that slot);
    each is checked independently.

    When both opponents produce the same hosting outcome (which is the common
    case when the target team has a clearly better or worse seed), the two
    cases are merged into a single scenario whose only condition is that the
    target team advances.

    Args:
        region, seed: Target team's identity.
        half_slots:   Slots for the team's bracket half.
        slot_idx:     0-based index of the team's slot in *half_slots*.
        round_name:   Display label (always ``"Second Round"``).
        odds:         Bundled hosting probabilities for this round.
        team_lookup:  Optional ``(region, seed) → school name`` mapping.

    Returns:
        A ``RoundHomeScenarios`` with scenarios grouped by hosting outcome.
    """
    adj_slots = opponent_slots(slot_idx, round_offset=1, half_slots=half_slots)
    adj_slot = adj_slots[0]  # exactly one adjacent slot in R2
    candidates = [
        (adj_slot.home_region, adj_slot.home_seed),
        (adj_slot.away_region, adj_slot.away_seed),
    ]

    will_host: list[HomeGameScenario] = []
    will_not_host: list[HomeGameScenario] = []

    team_cond = _advances(None, None, None, round_name)

    for opp_r, opp_s in candidates:
        home_r, home_s = r2_home_team(region, seed, opp_r, opp_s, season)
        is_home = home_r == region and home_s == seed
        explanation = _explain_r2(region, seed, opp_r, opp_s, season)
        opp_name = _team_label(opp_r, opp_s, team_lookup)
        opp_cond = _advances(opp_name, opp_r, opp_s, round_name)
        scenario = HomeGameScenario(
            conditions=(team_cond, opp_cond),
            explanation=explanation,
        )
        (will_host if is_home else will_not_host).append(scenario)

    # Merge: if both opponents lead to the same outcome with the same
    # explanation, collapse into a single "team advances" condition.
    def _try_merge(scenarios: list[HomeGameScenario]) -> tuple[HomeGameScenario, ...]:
        """Collapse two identical-explanation scenarios into one without opponent condition."""
        if len(scenarios) == 2 and scenarios[0].explanation == scenarios[1].explanation:
            return (HomeGameScenario(conditions=(team_cond,), explanation=scenarios[0].explanation),)
        return tuple(scenarios)

    return RoundHomeScenarios(
        round_name=round_name,
        will_host=_try_merge(will_host),
        will_not_host=_try_merge(will_not_host),
        **odds._asdict(),
    )


def _enumerate_qf(
    region: int,
    seed: int,
    half_slots: list[FormatSlot],
    slot_idx: int,
    season: int,
    is_1a_4a: bool,
    round_name: str,
    odds: _RoundOdds,
    team_lookup: dict[tuple[int, int], str] | None,
) -> RoundHomeScenarios:
    """Build the ``RoundHomeScenarios`` for the quarterfinals.

    For 5A-7A the QF is round 2 (one prior game per team); each team has
    exactly one prior home/away result.  For 1A-4A the QF is round 3 (two
    prior games per team), so R2 home status must also be computed.

    The opponent pool comes from the opposing group of slots within the same
    bracket half: 2 candidates for 5A-7A, 4 candidates for 1A-4A.

    For each candidate the function computes:

    * R1 home status (deterministic from slot assignment).
    * R2 home status (1A-4A only; seed-based, so deterministic once the
      candidate is known).

    When a QF opponent's R2 home status depends on *which* of two possible
    R2 rivals they faced (i.e. the two sub-cases give different R2 home
    values) **and** those sub-cases produce different QF hosting outcomes,
    the function enumerates both sub-cases and attaches an additional
    condition identifying which team won R1 in the opponent's adjacent slot.
    When both sub-cases produce the same QF outcome the scenarios are
    collapsed to a single entry (no extra condition needed).

    Then calls ``qf_home_team`` and groups results.

    Args:
        region, seed:       Target team's identity.
        half_slots:         Slots for the team's bracket half.
        slot_idx:           0-based index of the team's slot in *half_slots*.
        season:             Football season year (odd/even tiebreak).
        is_1a_4a:           ``True`` for 1A-4A (two prior rounds); ``False``
                            for 5A-7A (one prior round).
        round_name:  Display label (e.g. ``"Quarterfinals"``).
        odds:        Bundled hosting probabilities for this round.
        team_lookup: Optional ``(region, seed) → school name`` mapping.

    Returns:
        A ``RoundHomeScenarios`` with scenarios grouped by hosting outcome.
    """
    round_offset = 2 if is_1a_4a else 1
    opp_slot_list = opponent_slots(slot_idx, round_offset=round_offset, half_slots=half_slots)

    # Team's own R1/R2 home status
    team_slot = half_slots[slot_idx]
    r1_home_team = was_home_r1(region, seed, team_slot)
    # For 1A-4A R2: the target team's R2 opponent is the winner of the single
    # adjacent slot.  Since R2 home is seed-based, the team is home in R2
    # whenever their seed is ≤ any possible R2 opponent's seed.  Rather than
    # iterating over R2 sub-cases (which would explode combinations), we use
    # the pessimistic/optimistic approach: if the team's seed is strictly
    # better than both possible R2 opponents they were always home; if worse,
    # always away; if mixed, we enumerate both.
    #
    # In practice, with seeds 1-4 and the bracket structure, cases are almost
    # always unambiguous. We handle the mixed case by generating separate
    # scenarios per R2 outcome.

    if is_1a_4a:
        adj_slots = opponent_slots(slot_idx, round_offset=1, half_slots=half_slots)
        adj_slot = adj_slots[0]
        r2_opp_candidates = [
            (adj_slot.home_region, adj_slot.home_seed),
            (adj_slot.away_region, adj_slot.away_seed),
        ]
        # Determine R2 home status for each possible R2 opponent
        r2_home_options: list[bool] = [_r2_home_status(seed, opp_s) for _, opp_s in r2_opp_candidates]
        r2_home_unique = list(dict.fromkeys(r2_home_options))  # deduplicate, preserve order
    else:
        r2_home_unique = [False]  # 5A-7A has no R2; pass False as placeholder

    will_host: list[HomeGameScenario] = []
    will_not_host: list[HomeGameScenario] = []

    team_cond = _advances(None, None, None, round_name)

    # Enumerate all (QF opponent, R2 home status for team) combinations.
    # For 5A-7A r2_home_unique = [False] (sentinel), so the outer loop runs once.
    for r2_home_team_val in r2_home_unique:
        for opp_slot in opp_slot_list:
            for opp_r, opp_s in (
                (opp_slot.home_region, opp_slot.home_seed),
                (opp_slot.away_region, opp_slot.away_seed),
            ):
                opp_r1_home = was_home_r1(opp_r, opp_s, opp_slot)
                if is_1a_4a:
                    r2_home_t = r2_home_team_val
                    # Opponent's R2 opponent comes from THEIR adjacent slot.
                    # Their R2 home status (seed-based) may depend on which of
                    # the two possible R2 opponents they face.  When both give
                    # the same QF outcome for the target team, collapse to a
                    # single scenario.  When they differ, enumerate both sub-
                    # cases and add a condition identifying which team won R1 in
                    # the adjacent slot (to clarify the path to the fan).
                    opp_adj = opponent_slots(
                        slot_index_for(opp_r, opp_s, half_slots),  # type: ignore[arg-type]
                        round_offset=1,
                        half_slots=half_slots,
                    )[0]
                    opp_r2_home_opts = [
                        _r2_home_status(opp_s, opp_adj.home_seed),
                        _r2_home_status(opp_s, opp_adj.away_seed),
                    ]
                    if len(set(opp_r2_home_opts)) == 1:
                        # Unambiguous: same R2 home result regardless of R2 rival.
                        opp_r2_sub_cases: list[tuple[bool, HomeGameCondition | None]] = [(opp_r2_home_opts[0], None)]
                    else:
                        # Ambiguous: check whether the two sub-cases produce
                        # different QF hosting outcomes for the target team.
                        qf_out_0 = qf_home_team(
                            region,
                            seed,
                            r1_home_team,
                            r2_home_t,
                            opp_r,
                            opp_s,
                            opp_r1_home,
                            opp_r2_home_opts[0],
                            season,
                        )
                        qf_out_1 = qf_home_team(
                            region,
                            seed,
                            r1_home_team,
                            r2_home_t,
                            opp_r,
                            opp_s,
                            opp_r1_home,
                            opp_r2_home_opts[1],
                            season,
                        )
                        if qf_out_0 == qf_out_1:
                            # Different R2 paths, same QF result: no split.
                            opp_r2_sub_cases = [(opp_r2_home_opts[0], None)]
                        else:
                            # Different R2 paths produce different QF results:
                            # enumerate both, conditioned on who won R1 in the
                            # opponent's adjacent slot.
                            opp_r2_sub_cases = [
                                (
                                    opp_r2_home_opts[0],
                                    _advances(
                                        _team_label(
                                            opp_adj.home_region,
                                            opp_adj.home_seed,
                                            team_lookup,
                                        ),
                                        opp_adj.home_region,
                                        opp_adj.home_seed,
                                        _ROUND_NAMES_1A_4A[1],
                                    ),
                                ),
                                (
                                    opp_r2_home_opts[1],
                                    _advances(
                                        _team_label(
                                            opp_adj.away_region,
                                            opp_adj.away_seed,
                                            team_lookup,
                                        ),
                                        opp_adj.away_region,
                                        opp_adj.away_seed,
                                        _ROUND_NAMES_1A_4A[1],
                                    ),
                                ),
                            ]
                else:
                    r2_home_t = False  # 5A-7A sentinel
                    opp_r2_sub_cases = [(False, None)]

                opp_name = _team_label(opp_r, opp_s, team_lookup)
                opp_cond = _advances(opp_name, opp_r, opp_s, round_name)

                for opp_r2_home, r1_winner_cond in opp_r2_sub_cases:
                    home_r, home_s = qf_home_team(
                        region,
                        seed,
                        r1_home_team,
                        r2_home_t,
                        opp_r,
                        opp_s,
                        opp_r1_home,
                        opp_r2_home,
                        season,
                    )
                    is_home = home_r == region and home_s == seed
                    explanation = _explain_qf(
                        region,
                        seed,
                        r1_home_team,
                        r2_home_t if is_1a_4a else None,
                        opp_r,
                        opp_s,
                        opp_r1_home,
                        opp_r2_home if is_1a_4a else None,
                        season,
                    )
                    if r1_winner_cond is not None:
                        conditions: tuple[HomeGameCondition, ...] = (team_cond, r1_winner_cond, opp_cond)
                    else:
                        conditions = (team_cond, opp_cond)
                    scenario = HomeGameScenario(
                        conditions=conditions,
                        explanation=explanation,
                    )
                    (will_host if is_home else will_not_host).append(scenario)

    return RoundHomeScenarios(
        round_name=round_name,
        will_host=tuple(will_host),
        will_not_host=tuple(will_not_host),
        **odds._asdict(),
    )


def _enumerate_sf(
    region: int,
    seed: int,
    half_slots: list[FormatSlot],
    slot_idx: int,
    season: int,
    round_name: str,
    odds: _RoundOdds,
    team_lookup: dict[tuple[int, int], str] | None,
) -> RoundHomeScenarios:
    """Build the ``RoundHomeScenarios`` for the semifinals.

    The Semifinals (North/South Championship) is an intra-bracket-half game:
    the two quarter-bracket winners within the same half meet.  The SF
    opponent pool is therefore derived with ``opponent_slots`` at the
    maximum round offset (``log2(len(half_slots))``), which selects all
    first-round slots in the opposing quarter of the same half.

    * 5A-7A (4 slots/half, round_offset=2): 2 opponent slots → 4 candidates.
    * 1A-4A (8 slots/half, round_offset=3): 4 opponent slots → 8 candidates.

    Home-game history does **not** factor into the SF home rule per MHSAA
    rules, so the determination depends only on seeds and the region-number
    tiebreak.

    Args:
        region, seed: Target team's identity.
        half_slots:   Slots for the team's bracket half, sorted by slot.
        slot_idx:     0-based index of the team's slot in *half_slots*.
        season:       Football season year (odd/even tiebreak).
        round_name:   Display label (always ``"Semifinals"``).
        odds:         Bundled hosting probabilities for this round.
        team_lookup:  Optional ``(region, seed) → school name`` mapping.

    Returns:
        A ``RoundHomeScenarios`` with one scenario per possible opponent.
    """
    # SF is the final intra-half round; round_offset = log2(number of slots/half)
    sf_round_offset = int(math.log2(len(half_slots)))
    opp_slot_list = opponent_slots(slot_idx, round_offset=sf_round_offset, half_slots=half_slots)

    will_host: list[HomeGameScenario] = []
    will_not_host: list[HomeGameScenario] = []

    team_cond = _advances(None, None, None, round_name)

    seen: set[tuple[int, int]] = set()
    for slot in opp_slot_list:
        for opp_r, opp_s in (
            (slot.home_region, slot.home_seed),
            (slot.away_region, slot.away_seed),
        ):
            if (opp_r, opp_s) in seen:
                continue
            seen.add((opp_r, opp_s))
            home_r, home_s = sf_home_team(region, seed, opp_r, opp_s, season)
            is_home = home_r == region and home_s == seed
            explanation = _explain_sf(region, seed, opp_r, opp_s, season)
            opp_name = _team_label(opp_r, opp_s, team_lookup)
            opp_cond = _advances(opp_name, opp_r, opp_s, round_name)
            scenario = HomeGameScenario(
                conditions=(team_cond, opp_cond),
                explanation=explanation,
            )
            (will_host if is_home else will_not_host).append(scenario)

    return RoundHomeScenarios(
        round_name=round_name,
        will_host=tuple(will_host),
        will_not_host=tuple(will_not_host),
        **odds._asdict(),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enumerate_home_game_scenarios(
    region: int,
    seed: int,
    slots: list[FormatSlot],
    season: int,
    p_reach_by_round: dict[str, float] | None = None,
    p_host_conditional_by_round: dict[str, float] | None = None,
    p_host_marginal_by_round: dict[str, float] | None = None,
    p_reach_weighted_by_round: dict[str, float] | None = None,
    p_host_conditional_weighted_by_round: dict[str, float] | None = None,
    p_host_marginal_weighted_by_round: dict[str, float] | None = None,
    team_lookup: dict[tuple[int, int], str] | None = None,
) -> list[RoundHomeScenarios]:
    """Enumerate all home-game scenarios for a team across every applicable round.

    For each round the function determines the full set of conditions under
    which the team is the designated home team (``will_host``) and the
    conditions under which they are the away team (``will_not_host``).

    Bracket depth is inferred from the number of first-round slots per
    bracket half:

    * 4 slots → 5A-7A: First Round, Quarterfinals, Semifinals.
    * 8 slots → 1A-4A: First Round, Second Round, Quarterfinals, Semifinals.

    Args:
        region: The team's region number.
        seed:   The team's region seed (1 = best).
        slots:  All first-round ``FormatSlot`` objects for the class/season,
                as returned by ``fetch_all_format_slots`` (or the test
                fixture equivalents ``SLOTS_5A_7A_2025`` /
                ``SLOTS_1A_4A_2025``).
        season: Football season year (e.g. ``2025``).  Determines the
                odd/even region-number tiebreak for QF and SF.
        p_reach_by_round: Optional mapping of round name →
            P(team reaches round) under equal win probabilities.
        p_host_conditional_by_round: Optional mapping of round name →
            P(hosts | reaches) under equal win probabilities.
        p_host_marginal_by_round: Optional mapping of round name →
            P(reaches AND hosts) under equal win probabilities.
        p_reach_weighted_by_round: Weighted equivalent of
            *p_reach_by_round*.
        p_host_conditional_weighted_by_round: Weighted equivalent of
            *p_host_conditional_by_round*.
        p_host_marginal_weighted_by_round: Weighted equivalent of
            *p_host_marginal_by_round*.
        team_lookup: Optional mapping of ``(region, seed)`` → school name.
            When an entry exists the school name is substituted for the
            generic ``"Region X #Y Seed"`` label in condition objects.
            Typically built from ``REGION_RESULTS_2025`` seeds dicts in
            tests, or from the DB in production.

    Returns:
        List of ``RoundHomeScenarios``, one per applicable round, in
        chronological order (First Round first, Semifinals last).

    Raises:
        ValueError: If the team's ``(region, seed)`` is not found in *slots*.
    """
    half_slots = half_slots_for_region(region, slots)
    slot_idx = slot_index_for(region, seed, half_slots)
    if slot_idx is None:
        raise ValueError(f"(region={region}, seed={seed}) not found in provided slots")

    is_1a_4a = len(half_slots) == 8
    round_names = _ROUND_NAMES_1A_4A if is_1a_4a else _ROUND_NAMES_5A_7A

    def _odds(rname: str) -> _RoundOdds:
        """Build a ``_RoundOdds`` bundle for *rname* from the caller's dicts."""
        def _get(d: dict[str, float] | None) -> float | None:
            """Return ``d[rname]`` if *d* is not None, otherwise ``None``."""
            return d.get(rname) if d else None
        return _RoundOdds(
            p_reach=_get(p_reach_by_round),
            p_host_conditional=_get(p_host_conditional_by_round),
            p_host_marginal=_get(p_host_marginal_by_round),
            p_reach_weighted=_get(p_reach_weighted_by_round),
            p_host_conditional_weighted=_get(p_host_conditional_weighted_by_round),
            p_host_marginal_weighted=_get(p_host_marginal_weighted_by_round),
        )

    results: list[RoundHomeScenarios] = []

    # --- First Round ---
    r1_name = round_names[0]  # "First Round"
    results.append(_enumerate_r1(region, seed, half_slots, slot_idx, r1_name, _odds(r1_name)))

    if is_1a_4a:
        # --- Second Round (1A-4A only) ---
        r2_name = round_names[1]  # "Second Round"
        results.append(
            _enumerate_r2(region, seed, half_slots, slot_idx, season, r2_name, _odds(r2_name), team_lookup)
        )

    # --- Quarterfinals ---
    qf_name = round_names[2] if is_1a_4a else round_names[1]  # "Quarterfinals"
    results.append(
        _enumerate_qf(
            region, seed, half_slots, slot_idx, season, is_1a_4a, qf_name, _odds(qf_name), team_lookup
        )
    )

    # --- Semifinals ---
    sf_name = round_names[-1]  # "Semifinals" — always the last round in both formats
    results.append(
        _enumerate_sf(region, seed, half_slots, slot_idx, season, sf_name, _odds(sf_name), team_lookup)
    )

    return results


# ---------------------------------------------------------------------------
# Matchup enumeration helpers (opponent-centric view)
# ---------------------------------------------------------------------------
#
# These private helpers each return a flat list of raw tuples:
#   (opp_region, opp_seed, is_home, explanation)
#
# Under equal win probability every tuple is one equiprobable path, so the
# caller can compute per-matchup conditional odds as count/total after
# grouping duplicate (opp_r, opp_s, is_home) entries.


def _matchup_raw_r1(
    region: int,
    seed: int,
    half_slots: list[FormatSlot],
    slot_idx: int,
) -> list[tuple[int, int, bool, str | None]]:
    """Raw matchup entries for the first round.  Always exactly one entry."""
    slot = half_slots[slot_idx]
    is_home = was_home_r1(region, seed, slot)
    if slot.home_region == region and slot.home_seed == seed:
        opp_r, opp_s = slot.away_region, slot.away_seed
    else:
        opp_r, opp_s = slot.home_region, slot.home_seed
    return [(opp_r, opp_s, is_home, _explain_r1(is_home))]


def _matchup_raw_r2(
    region: int,
    seed: int,
    half_slots: list[FormatSlot],
    slot_idx: int,
    season: int,
) -> list[tuple[int, int, bool, str | None]]:
    """Raw matchup entries for the second round (1A-4A only).  Two entries."""
    adj_slot = opponent_slots(slot_idx, round_offset=1, half_slots=half_slots)[0]
    result: list[tuple[int, int, bool, str | None]] = []
    for opp_r, opp_s in (
        (adj_slot.home_region, adj_slot.home_seed),
        (adj_slot.away_region, adj_slot.away_seed),
    ):
        home_r, home_s = r2_home_team(region, seed, opp_r, opp_s, season)
        is_home = home_r == region and home_s == seed
        result.append((opp_r, opp_s, is_home, _explain_r2(region, seed, opp_r, opp_s, season)))
    return result


def _matchup_raw_qf(
    region: int,
    seed: int,
    half_slots: list[FormatSlot],
    slot_idx: int,
    season: int,
    is_1a_4a: bool,
    r1_survivors: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int, bool, str | None]]:
    """Raw matchup entries for the quarterfinals.

    Enumerates every distinct path to a QF matchup, including both possible
    R2 home-status variants for the target team (1A-4A only) and both
    possible R2 opponents for each QF candidate (1A-4A only).  Duplicate
    ``(opp_r, opp_s, is_home)`` entries from different paths are intentional:
    the caller weights them to derive equal-probability conditional odds.

    When *r1_survivors* is provided (the set of teams that won their R1 game),
    only those teams are considered as R2 opponents for both the target team and
    each QF candidate.  This collapses the R2-home-status split to a single
    known value.  Note: *r1_survivors* must reflect R1 results specifically —
    passing post-R2 survivors would incorrectly exclude teams eliminated in R2.
    """
    round_offset = 2 if is_1a_4a else 1
    opp_slot_list = opponent_slots(slot_idx, round_offset=round_offset, half_slots=half_slots)

    team_slot = half_slots[slot_idx]
    r1_home_team_val = was_home_r1(region, seed, team_slot)

    if is_1a_4a:
        adj_slot = opponent_slots(slot_idx, round_offset=1, half_slots=half_slots)[0]
        r2_adj_candidates: list[tuple[int, int]] = [
            (adj_slot.home_region, adj_slot.home_seed),
            (adj_slot.away_region, adj_slot.away_seed),
        ]
        if r1_survivors is not None:
            r2_adj_candidates = [(r, s) for r, s in r2_adj_candidates if (r, s) in r1_survivors]
        r2_home_unique = list(dict.fromkeys(
            _r2_home_status(seed, s) for _, s in r2_adj_candidates
        ))
    else:
        r2_home_unique = [False]  # sentinel for 5A-7A (no R2)

    result: list[tuple[int, int, bool, str | None]] = []

    for r2_home_t in r2_home_unique:
        for opp_slot in opp_slot_list:
            for opp_r, opp_s in (
                (opp_slot.home_region, opp_slot.home_seed),
                (opp_slot.away_region, opp_slot.away_seed),
            ):
                opp_r1_home = was_home_r1(opp_r, opp_s, opp_slot)

                if is_1a_4a:
                    opp_adj = opponent_slots(
                        slot_index_for(opp_r, opp_s, half_slots),  # type: ignore[arg-type]
                        round_offset=1,
                        half_slots=half_slots,
                    )[0]
                    opp_r2_candidates: list[tuple[int, int]] = [
                        (opp_adj.home_region, opp_adj.home_seed),
                        (opp_adj.away_region, opp_adj.away_seed),
                    ]
                    if r1_survivors is not None:
                        opp_r2_candidates = [
                            (r, s) for r, s in opp_r2_candidates if (r, s) in r1_survivors
                        ]
                    opp_r2_vals = list(dict.fromkeys(
                        _r2_home_status(opp_s, s) for _, s in opp_r2_candidates
                    ))
                else:
                    opp_r2_vals = [False]  # sentinel for 5A-7A

                for opp_r2_home in opp_r2_vals:
                    home_r, home_s = qf_home_team(
                        region, seed, r1_home_team_val,
                        r2_home_t if is_1a_4a else False,
                        opp_r, opp_s, opp_r1_home, opp_r2_home, season,
                    )
                    is_home = home_r == region and home_s == seed
                    explanation = _explain_qf(
                        region, seed, r1_home_team_val,
                        r2_home_t if is_1a_4a else None,
                        opp_r, opp_s, opp_r1_home,
                        opp_r2_home if is_1a_4a else None,
                        season,
                    )
                    result.append((opp_r, opp_s, is_home, explanation))

    return result


def _matchup_raw_sf(
    region: int,
    seed: int,
    half_slots: list[FormatSlot],
    slot_idx: int,
    season: int,
) -> list[tuple[int, int, bool, str | None]]:
    """Raw matchup entries for the semifinals.  One entry per distinct opponent."""
    sf_round_offset = int(math.log2(len(half_slots)))
    opp_slot_list = opponent_slots(slot_idx, round_offset=sf_round_offset, half_slots=half_slots)

    result: list[tuple[int, int, bool, str | None]] = []
    seen: set[tuple[int, int]] = set()
    for slot in opp_slot_list:
        for opp_r, opp_s in (
            (slot.home_region, slot.home_seed),
            (slot.away_region, slot.away_seed),
        ):
            if (opp_r, opp_s) in seen:
                continue
            seen.add((opp_r, opp_s))
            home_r, home_s = sf_home_team(region, seed, opp_r, opp_s, season)
            is_home = home_r == region and home_s == seed
            result.append((opp_r, opp_s, is_home, _explain_sf(region, seed, opp_r, opp_s, season)))

    return result


def enumerate_team_matchups(
    region: int,
    seed: int,
    slots: list[FormatSlot],
    season: int,
    p_reach_by_round: dict[str, float] | None = None,
    p_host_conditional_by_round: dict[str, float] | None = None,
    p_host_marginal_by_round: dict[str, float] | None = None,
    p_reach_weighted_by_round: dict[str, float] | None = None,
    p_host_conditional_weighted_by_round: dict[str, float] | None = None,
    p_host_marginal_weighted_by_round: dict[str, float] | None = None,
    p_conditional_weighted_by_matchup: dict[str, dict[tuple[int, int, bool], float]] | None = None,
    team_lookup: dict[tuple[int, int], str] | None = None,
    known_survivors: set[tuple[int, int]] | None = None,
    r1_survivors: set[tuple[int, int]] | None = None,
    completed_rounds: set[str] | None = None,
) -> list[RoundMatchups]:
    """Enumerate all possible playoff matchups for a team across every round.

    Returns one ``RoundMatchups`` per applicable round.  Each entry in a round
    represents a unique ``(opponent, home/away)`` combination; under equal win
    probability the ``p_conditional`` values sum to ``1.0`` within a round.

    Equal-probability per-matchup conditional odds are computed from the
    bracket structure: every distinct path through the bracket is treated as
    equiprobable (50/50 game outcomes), so each ``(opp_r, opp_s, is_home)``
    combination receives a weight proportional to how many of the total
    enumerated paths lead to it.  This correctly handles the 1A-4A case where
    the same opponent may appear via two different R2 sub-paths.

    Args:
        region: The team's region number.
        seed:   The team's region seed (1 = best).
        slots:  All first-round ``FormatSlot`` objects for the class/season.
        season: Football season year (odd/even tiebreak for QF/SF).
        p_reach_by_round:                    Round name → P(team reaches).
        p_host_conditional_by_round:         Round name → P(hosts | reaches).
        p_host_marginal_by_round:            Round name → P(reaches AND hosts).
        p_reach_weighted_by_round:           Weighted equivalents (placeholder
                                             for ``WinProbFn`` integration).
        p_host_conditional_weighted_by_round: Weighted.
        p_host_marginal_weighted_by_round:   Weighted.
        p_conditional_weighted_by_matchup:   Weighted per-matchup conditional
                                             odds; keyed as
                                             ``round_name → (opp_region,
                                             opp_seed, is_home) → float``.
                                             Placeholder for ``WinProbFn``
                                             integration; pass ``None`` to
                                             leave weighted fields as ``None``.
        team_lookup: Optional ``(region, seed)`` → school name mapping.
        known_survivors: Optional set of ``(region, seed)`` pairs currently
            alive in the tournament.  Opponent entries not in this set are
            dropped and ``p_conditional`` values are renormalized.  Use the
            survivors of the most recently completed round.
        r1_survivors: Optional set of ``(region, seed)`` pairs that won their
            first-round game.  Used inside the QF path enumeration to fix each
            team's R2 opponent (and thus their R2 home-game count) to the
            actual R1 winner.  Must reflect R1 results only — do not pass
            post-R2 survivors here, as teams eliminated in R2 still need to be
            included.  Typically set to the same value as *known_survivors*
            when calling after R1; set explicitly when calling after later
            rounds.
        completed_rounds: Optional set of round names to exclude from the
            returned list.  Use this to omit already-played rounds from the
            output (e.g. ``{"First Round"}`` after R1 is complete).

    Returns:
        List of ``RoundMatchups``, one per applicable round, in chronological
        order.  Rounds named in *completed_rounds* are omitted.

    Raises:
        ValueError: If the team's ``(region, seed)`` is not found in *slots*.
    """
    half_slots = half_slots_for_region(region, slots)
    slot_idx = slot_index_for(region, seed, half_slots)
    if slot_idx is None:
        raise ValueError(f"(region={region}, seed={seed}) not found in provided slots")

    is_1a_4a = len(half_slots) == 8
    round_names = _ROUND_NAMES_1A_4A if is_1a_4a else _ROUND_NAMES_5A_7A

    def _round_odds(rname: str) -> _RoundOdds:
        """Build a ``_RoundOdds`` bundle for *rname* from the caller's dicts."""
        def _get(d: dict[str, float] | None) -> float | None:
            """Return ``d[rname]`` if *d* is not None, otherwise ``None``."""
            return d.get(rname) if d else None
        return _RoundOdds(
            p_reach=_get(p_reach_by_round),
            p_host_conditional=_get(p_host_conditional_by_round),
            p_host_marginal=_get(p_host_marginal_by_round),
            p_reach_weighted=_get(p_reach_weighted_by_round),
            p_host_conditional_weighted=_get(p_host_conditional_weighted_by_round),
            p_host_marginal_weighted=_get(p_host_marginal_weighted_by_round),
        )

    _completed = completed_rounds or set()

    def _build_round(
        round_name: str,
        raw: list[tuple[int, int, bool, str | None]],
    ) -> RoundMatchups:
        """Convert raw path tuples into a ``RoundMatchups`` with computed odds."""
        odds = _round_odds(round_name)
        p_reach = odds.p_reach
        p_reach_w = odds.p_reach_weighted

        # Drop paths for eliminated opponents before counting.
        if known_survivors is not None:
            raw = [(r, s, h, e) for r, s, h, e in raw if (r, s) in known_survivors]

        # Count how many raw paths lead to each (opp_r, opp_s, is_home) outcome.
        # Under equal probability every path is equiprobable, so the fraction of
        # paths gives the correct conditional probability.  Filtering eliminates
        # impossible paths; the remaining counts renormalize automatically.
        path_counts: Counter[tuple[int, int, bool]] = Counter()
        path_explanations: dict[tuple[int, int, bool], str | None] = {}
        for opp_r, opp_s, is_home, explanation in raw:
            key = (opp_r, opp_s, is_home)
            path_counts[key] += 1
            path_explanations[key] = explanation

        total = sum(path_counts.values())
        round_weighted = (p_conditional_weighted_by_matchup or {}).get(round_name, {})

        entries: list[MatchupEntry] = []
        for (opp_r, opp_s, is_home), count in path_counts.items():
            p_cond = count / total if total > 0 else None
            p_cond_w = round_weighted.get((opp_r, opp_s, is_home))
            p_marg = (p_cond * p_reach) if (p_cond is not None and p_reach is not None) else None
            p_marg_w = (p_cond_w * p_reach_w) if (p_cond_w is not None and p_reach_w is not None) else None
            entries.append(MatchupEntry(
                opponent=_team_label(opp_r, opp_s, team_lookup),
                opponent_region=opp_r,
                opponent_seed=opp_s,
                home=is_home,
                p_conditional=p_cond,
                p_conditional_weighted=p_cond_w,
                p_marginal=p_marg,
                p_marginal_weighted=p_marg_w,
                explanation=path_explanations[(opp_r, opp_s, is_home)],
            ))

        # Sort: home matchups first, then by (opponent_region, opponent_seed)
        entries.sort(key=lambda e: (not e.home, e.opponent_region, e.opponent_seed))
        return RoundMatchups(round_name=round_name, **odds._asdict(), entries=tuple(entries))

    results: list[RoundMatchups] = []

    r1_name = round_names[0]
    if r1_name not in _completed:
        results.append(_build_round(r1_name, _matchup_raw_r1(region, seed, half_slots, slot_idx)))

    if is_1a_4a:
        r2_name = round_names[1]
        if r2_name not in _completed:
            results.append(_build_round(r2_name, _matchup_raw_r2(region, seed, half_slots, slot_idx, season)))

    qf_name = round_names[2] if is_1a_4a else round_names[1]
    if qf_name not in _completed:
        results.append(_build_round(qf_name, _matchup_raw_qf(region, seed, half_slots, slot_idx, season, is_1a_4a, r1_survivors)))

    sf_name = round_names[-1]
    if sf_name not in _completed:
        results.append(_build_round(sf_name, _matchup_raw_sf(region, seed, half_slots, slot_idx, season)))

    return results
