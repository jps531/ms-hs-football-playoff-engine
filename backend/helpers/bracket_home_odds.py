"""Playoff home-game probability for rounds beyond the first.

``compute_first_round_home_odds`` (in scenarios.py) handles the first round
(and the second round for 1A-4A, where the same higher-seed-hosts rule applies).
This module handles the remaining rounds:

* **Second round (1A-4A only)**: higher seed hosts.  Equal cross-region seeds use the same
  odd/even year tiebreak as QF/SF (odd years: lower region# hosts; even years: higher region#).
* **Quarterfinals**: if both teams are from the same region, the higher seed
  (lower number) always hosts (golden rule, supersedes all other steps).
  Otherwise: fewer home games played hosts; equal home games → higher seed
  hosts; equal seed → region-number tiebreak (odd years: lower region#;
  even years: higher region#).  Each team's home-game count entering the QF is
  computed exactly from the bracket: R1 home/away is deterministic from each
  team's slot position, and R2 home/away is derived from the seed comparison
  with the possible R2 opponents (each weighted by their win probability).
* **Semifinals**: same-region opponents → higher seed always hosts (golden
  rule).  Cross-region: higher seed hosts; equal seed → same region-number
  tiebreak as quarterfinals.  Home games played do **not** factor in at this
  round per MHSAA rules.

All three public functions return a MARGINAL probability:
    P(team reaches round) x P(team is home | team reaches round)

This matches the semantics of ``compute_first_round_home_odds``.

Win probability
---------------
All public functions accept an optional ``win_prob_fn`` parameter of type
``MatchupProbFn``.  The default (``equal_matchup_prob``) returns 0.5 for every
game, reproducing the original equal-probability behaviour.

The function is called as ``win_prob_fn(home_region, home_seed, away_region,
away_seed)`` and returns P(home team wins).  For rounds beyond R1—where the
home/away designation is determined by seed—the team with the lower seed
number (better seed) is passed as ``home``; equal seeds use the lower region
number as ``home``.

Bracket structure assumed
-------------------------
Slots are arranged as a binary tournament.  Adjacent pairs of first-round
slots feed the same second-round game; adjacent pairs of those games feed
the third-round game, and so on.  The ``playoff_format_slots`` table
preserves this ordering via its 1-based slot numbers.

Official round names and within-half slot offsets:

5A-7A (4 rounds total: First Round → Quarterfinals → Semifinals → Championship):
    * 4 slots per half (8 teams per half)
    * QF  = Round 2  (round_offset 1 from the first-round slot)
    * SF  = Round 3  (round_offset 2) — winner advances to Championship

1A-4A (5 rounds total: First Round → Second Round → Quarterfinals → Semifinals → Championship):
    * 8 slots per half (16 teams per half)
    * R2  = Round 2  (round_offset 1)
    * QF  = Round 3  (round_offset 2)
    * SF  = Round 4  (round_offset 3) — winner advances to Championship

The Championship Game (Round 4 for 5A-7A, Round 5 for 1A-4A) is cross-half and
is handled by ``compute_bracket_advancement_odds``, not the home-game functions.
"""

from backend.helpers.data_classes import (  # noqa: F401
    BracketOdds,
    FormatSlot,
    MatchupProbFn,
    StandingsOdds,
    equal_matchup_prob,
)

# ---------------------------------------------------------------------------
# Public bracket-navigation helpers
# (also used by home_game_scenarios.py)
# ---------------------------------------------------------------------------


def half_slots_for_region(region: int, slots: list[FormatSlot]) -> list[FormatSlot]:
    """Return all slots in the same bracket half as *region*, sorted by slot number.

    Args:
        region: Region number to look up.
        slots:  Full list of ``FormatSlot`` objects for the class/season.

    Returns:
        Sorted list of ``FormatSlot`` objects belonging to the same
        North/South bracket half as *region*, or an empty list if not found.
    """
    half: str | None = None
    for s in slots:
        if s.home_region == region or s.away_region == region:
            half = s.north_south
            break
    if half is None:
        return []
    return sorted((s for s in slots if s.north_south == half), key=lambda s: s.slot)


def slot_index_for(region: int, seed: int, half_slots: list[FormatSlot]) -> int | None:
    """Return the 0-based index into *half_slots* where *(region, seed)* appears.

    Args:
        region:     Region number of the team.
        seed:       Region seed of the team (1 = best).
        half_slots: Slots for one bracket half, sorted by slot number.

    Returns:
        0-based index, or ``None`` if the team is not found in *half_slots*.
    """
    for i, s in enumerate(half_slots):
        if (s.home_region == region and s.home_seed == seed) or (s.away_region == region and s.away_seed == seed):
            return i
    return None


def opponent_slot_indices(team_idx: int, round_offset: int) -> list[int]:
    """Return indices into the bracket half for the opponent pool *round_offset* rounds ahead.

    Uses the binary tournament structure: adjacent slot pairs feed the same
    next-round game, pairs of those games feed the round after, etc.

    Args:
        team_idx:     0-based index of the team's slot within its bracket half.
        round_offset: How many rounds ahead to look (1 = next round, 2 = two rounds, ...).

    Returns:
        List of 0-based indices from which the opponent may emerge.
    """
    group_size = 2 ** (round_offset - 1)
    team_group = team_idx // group_size
    opp_group = team_group ^ 1
    start = opp_group * group_size
    return list(range(start, start + group_size))


def opponent_slots(team_idx: int, round_offset: int, half_slots: list[FormatSlot]) -> list[FormatSlot]:
    """Return the slots from which the team's opponent arrives *round_offset* rounds ahead.

    Args:
        team_idx:     0-based index of the team's slot within its bracket half.
        round_offset: How many rounds ahead to look (1 = next round, 2 = two rounds, ...).
        half_slots:   Slots for one bracket half, sorted by slot number.

    Returns:
        List of ``FormatSlot`` objects from which the opponent emerges.
    """
    return [half_slots[i] for i in opponent_slot_indices(team_idx, round_offset)]


def was_home_r1(region: int, seed: int, slot: FormatSlot) -> bool:
    """Return True if *(region, seed)* occupies the home position in *slot*.

    Args:
        region: Region number of the team.
        seed:   Region seed of the team (1 = best).
        slot:   The first-round ``FormatSlot`` for this team's game.

    Returns:
        ``True`` if the team is the designated home team in *slot*.
    """
    return slot.home_region == region and slot.home_seed == seed


# ---------------------------------------------------------------------------
# Private aliases kept for internal use within this module
# ---------------------------------------------------------------------------

_half_slots_for_region = half_slots_for_region
_slot_index_for = slot_index_for
_opponent_slot_indices = opponent_slot_indices
_opponent_slots = opponent_slots
_was_home_r1 = was_home_r1


# ---------------------------------------------------------------------------
# Internal helpers — win probability
# ---------------------------------------------------------------------------


def _p_team_r1_win(region: int, seed: int, slot: FormatSlot, win_prob_fn: MatchupProbFn) -> float:
    """P(team at *(region, seed)* wins the R1 game in *slot*."""
    p = win_prob_fn(slot.home_region, slot.home_seed, slot.away_region, slot.away_seed)
    return p if _was_home_r1(region, seed, slot) else 1.0 - p


def _p_beat_by_seed(r1: int, s1: int, r2: int, s2: int, win_prob_fn: MatchupProbFn) -> float:
    """P(team 1 beats team 2) using lower seed number (better seed) as home.

    Equal seeds: lower region number is treated as home for the win-prob call.
    """
    if s1 < s2 or (s1 == s2 and r1 <= r2):
        return win_prob_fn(r1, s1, r2, s2)
    return 1.0 - win_prob_fn(r2, s2, r1, s1)


def _p_team_reach(
    region: int,
    seed: int,
    slot_idx: int,
    num_wins: int,
    half_slots: list[FormatSlot],
    win_prob_fn: MatchupProbFn,
    skip_wins: int = 0,
) -> float:
    """P(team wins the next *num_wins* games from their bracket position).

    Supports num_wins in {0, 1, 2, 3, 4}.  Home/away for games beyond R1 is
    determined by seed (lower number = home) for win-probability purposes.

    Round mapping by num_wins:

    * 0 → already there (trivially 1.0)
    * 1 → win First Round (advance to Second Round / Quarterfinals)
    * 2 → win through Second Round (5A-7A: advance to Semifinals after QF;
           1A-4A: advance to Quarterfinals)
    * 3 → win through Quarterfinals (5A-7A: advance to Championship after
           winning Semifinals; 1A-4A: advance to Semifinals)
    * 4 → win through Semifinals (1A-4A only; 4th within-half win, opponent
           emerges from the opposite 4-slot quarter) — advance to Championship

    num_wins=4 is used by ``compute_bracket_advancement_odds`` both to compute
    the Elo-weighted ``finals`` (Championship Game appearance) probability for
    1A-4A teams and to compute each other-half team's probability of reaching
    the Championship as the opponent.

    Args:
        region:    Team's region number.
        seed:      Team's region seed (1 = best).
        slot_idx:  0-based index of team's slot in *half_slots*.
        num_wins:  Number of consecutive wins required (0–4).
        half_slots: All slots in the bracket half, sorted by slot number.
        win_prob_fn: Win-probability function.

    Returns:
        Probability in [0.0, 1.0].
    """
    if num_wins == 0:
        return 1.0

    slot = half_slots[slot_idx]
    p_r1 = 1.0 if skip_wins >= 1 else _p_team_r1_win(region, seed, slot, win_prob_fn)
    if num_wins == 1:
        return p_r1

    # R2 opponent is the winner of the adjacent slot.
    r2_opp_slot = _opponent_slots(slot_idx, 1, half_slots)[0]
    p_adj_home_r1 = win_prob_fn(
        r2_opp_slot.home_region,
        r2_opp_slot.home_seed,
        r2_opp_slot.away_region,
        r2_opp_slot.away_seed,
    )
    p_r2 = p_adj_home_r1 * _p_beat_by_seed(
        region, seed, r2_opp_slot.home_region, r2_opp_slot.home_seed, win_prob_fn
    ) + (1.0 - p_adj_home_r1) * _p_beat_by_seed(
        region, seed, r2_opp_slot.away_region, r2_opp_slot.away_seed, win_prob_fn
    )
    if num_wins == 2:
        return p_r1 * p_r2

    # QF opponent is the winner of the R2 game from the adjacent slot pair.
    qf_opp_indices = _opponent_slot_indices(slot_idx, 2)
    slot_a_idx, slot_b_idx = qf_opp_indices[0], qf_opp_indices[1]
    slot_a = half_slots[slot_a_idx]
    slot_b = half_slots[slot_b_idx]

    p_qf = 0.0
    for opp_slot, partner_slot in (
        (slot_a, slot_b),
        (slot_b, slot_a),
    ):
        p_opp_home_r1 = win_prob_fn(
            opp_slot.home_region,
            opp_slot.home_seed,
            opp_slot.away_region,
            opp_slot.away_seed,
        )
        p_partner_home_r1 = win_prob_fn(
            partner_slot.home_region,
            partner_slot.home_seed,
            partner_slot.away_region,
            partner_slot.away_seed,
        )
        for opp_r, opp_s, p_opp_r1 in (
            (opp_slot.home_region, opp_slot.home_seed, p_opp_home_r1),
            (opp_slot.away_region, opp_slot.away_seed, 1.0 - p_opp_home_r1),
        ):
            # P(this candidate reaches QF) = P(wins R1) × P(wins R2 vs partner winner)
            p_cand_r2 = p_partner_home_r1 * _p_beat_by_seed(
                opp_r, opp_s, partner_slot.home_region, partner_slot.home_seed, win_prob_fn
            ) + (1.0 - p_partner_home_r1) * _p_beat_by_seed(
                opp_r, opp_s, partner_slot.away_region, partner_slot.away_seed, win_prob_fn
            )
            p_cand_reach_qf = p_opp_r1 * p_cand_r2
            p_qf += p_cand_reach_qf * _p_beat_by_seed(region, seed, opp_r, opp_s, win_prob_fn)

    if num_wins == 3:
        return p_r1 * p_r2 * p_qf

    # SF opponent (num_wins == 4) emerges from the opposite 4-slot quarter.
    # Each of the 8 teams there must win 3 games in their sub-bracket to reach
    # the SF, so we reuse _p_team_reach(num_wins=3) on that sub-bracket.
    sf_opp_global = _opponent_slot_indices(slot_idx, 3)  # 4 indices into half_slots
    sf_opp_slots = [half_slots[i] for i in sf_opp_global]

    p_sf_win = 0.0
    for local_idx, opp_slot in enumerate(sf_opp_slots):
        for opp_r, opp_s in (
            (opp_slot.home_region, opp_slot.home_seed),
            (opp_slot.away_region, opp_slot.away_seed),
        ):
            p_opp_wins_sub = _p_team_reach(opp_r, opp_s, local_idx, 3, sf_opp_slots, win_prob_fn)
            p_sf_win += p_opp_wins_sub * _p_beat_by_seed(region, seed, opp_r, opp_s, win_prob_fn)

    return p_r1 * p_r2 * p_qf * p_sf_win


# ---------------------------------------------------------------------------
# Internal helpers — home determination
# ---------------------------------------------------------------------------


def _p_home_in_r2(
    team_seed: int,
    team_region: int,
    r2_opp_slot: FormatSlot,
    season: int,
    win_prob_fn: MatchupProbFn,
) -> float:
    """P(team was home in R2) given R2 opponent is the winner of *r2_opp_slot*.

    R2 rule: higher seed (lower number) hosts.  Equal cross-region seeds use
    the odd/even year region-number tiebreak (same as QF/SF).
    Each possible R2 opponent is weighted by their R1 win probability.

    Args:
        team_seed:    Team's region seed (1 = best).
        team_region:  Team's region number.
        r2_opp_slot:  The slot whose winner the team faces in R2.
        season:       Football season year (used for odd/even tiebreak).
        win_prob_fn:  Win-probability function.

    Returns:
        Probability in [0.0, 1.0] that the team hosted their R2 game.
    """
    p_adj_home_r1 = win_prob_fn(
        r2_opp_slot.home_region,
        r2_opp_slot.home_seed,
        r2_opp_slot.away_region,
        r2_opp_slot.away_seed,
    )
    odd_year = season % 2 == 1
    p = 0.0
    for opp_region, opp_seed, p_opp_r1 in (
        (r2_opp_slot.home_region, r2_opp_slot.home_seed, p_adj_home_r1),
        (r2_opp_slot.away_region, r2_opp_slot.away_seed, 1.0 - p_adj_home_r1),
    ):
        if team_seed < opp_seed:
            p += p_opp_r1
        elif team_seed == opp_seed:
            # equal cross-region seed: odd year → lower region# hosts; even → higher
            if odd_year:
                p += p_opp_r1 if team_region < opp_region else 0.0
            else:
                p += p_opp_r1 if team_region > opp_region else 0.0
    return p


def _p_host_seed_rule(
    team_seed: int,
    team_region: int,
    opp_indices: list[int],
    opp_num_wins: int,
    half_slots: list[FormatSlot],
    odd_year: bool,
    use_region_tiebreak: bool,
    win_prob_fn: MatchupProbFn,
) -> float:
    """P(team hosts | reaches this round). Home rule: seed, then optionally region.

    Weights each opponent candidate by P(they reach this round), computed via
    ``_p_team_reach``.  The weights sum to 1.0, so the return value is a
    proper conditional probability.

    Args:
        team_seed:           Team's region seed (1 = best).
        team_region:         Team's region number.
        opp_indices:         Indices into *half_slots* for opponent candidate slots.
        opp_num_wins:        Wins each opponent needed to reach this round.
        half_slots:          All slots in the bracket half, sorted by slot number.
        odd_year:            True if the season year is odd.
        use_region_tiebreak: Apply region-number tiebreak for equal seeds.
        win_prob_fn:         Win-probability function.

    Returns:
        Probability in [0.0, 1.0] that the team is the home team.
    """
    p = 0.0
    for opp_slot_idx in opp_indices:
        opp_slot = half_slots[opp_slot_idx]
        for opp_seed, opp_region in (
            (opp_slot.home_seed, opp_slot.home_region),
            (opp_slot.away_seed, opp_slot.away_region),
        ):
            w = _p_team_reach(opp_region, opp_seed, opp_slot_idx, opp_num_wins, half_slots, win_prob_fn)
            if team_region == opp_region:
                # Golden rule: same-region opponents → higher seed (lower number) always hosts.
                if team_seed < opp_seed:
                    p += w
            elif team_seed < opp_seed:
                p += w
            elif team_seed == opp_seed and use_region_tiebreak:
                if odd_year:
                    p += w if team_region < opp_region else 0.0
                else:
                    p += w if team_region > opp_region else 0.0
    return p


def _p_host_qf_given_seed(
    team_seed: int,
    team_region: int,
    team_slot_idx: int,
    half_slots: list[FormatSlot],
    qf_offset: int,
    odd_year: bool,
    season: int,
    win_prob_fn: MatchupProbFn,
) -> float:
    """P(team hosts QF | team reaches QF at *team_seed*).

    Golden rule (supersedes all steps below): when the two QF teams are from
    the same region, the higher seed (lower number) always hosts.

    For cross-region opponents, applies the three-step QF home rule:

    1. Fewer playoff home games so far → that team hosts.
    2. Equal home games → higher seed (lower number) hosts.
    3. Equal seed → region-number tiebreak.

    Home-game history per team:

    * R1 home/away is deterministic from each team's slot position.
    * R2 home/away (1A-4A only) is derived probabilistically from seed
      comparison with each possible R2 opponent, weighted by win probability.

    QF opponent candidates are weighted by P(they reach the QF).

    Args:
        team_seed:      Team's region seed (1 = best).
        team_region:    Team's region number.
        team_slot_idx:  0-based index of the team's slot in *half_slots*.
        half_slots:     All slots in the bracket half, sorted by slot number.
        qf_offset:      Rounds from R1 to QF (1 for 5A-7A, 2 for 1A-4A).
        odd_year:       True if the season year is odd.
        win_prob_fn:    Win-probability function.

    Returns:
        Probability in [0.0, 1.0] that the team is the QF home team.
    """
    team_slot = half_slots[team_slot_idx]
    team_h1 = 1 if _was_home_r1(team_region, team_seed, team_slot) else 0

    if qf_offset >= 2:
        r2_opp_slot = _opponent_slots(team_slot_idx, 1, half_slots)[0]
        p_team_h2 = _p_home_in_r2(team_seed, team_region, r2_opp_slot, season, win_prob_fn)
    else:
        p_team_h2 = 0.0

    qf_opp_indices = _opponent_slot_indices(team_slot_idx, qf_offset)
    p = 0.0

    for i, opp_slot_idx in enumerate(qf_opp_indices):
        opp_slot = half_slots[opp_slot_idx]
        # The opponent's R2 partner is the other slot in the same QF pair.
        # For 5A-7A (qf_offset=1) there is no R2, so this value is guarded below.
        opp_r2_partner = half_slots[qf_opp_indices[1 - i]] if qf_offset >= 2 else opp_slot

        for opp_seed, opp_region, opp_r1_home in (
            (opp_slot.home_seed, opp_slot.home_region, True),
            (opp_slot.away_seed, opp_slot.away_region, False),
        ):
            opp_h1 = 1 if opp_r1_home else 0

            if qf_offset >= 2:
                p_opp_h2 = _p_home_in_r2(opp_seed, opp_region, opp_r2_partner, season, win_prob_fn)
                p_cand_reach = _p_team_reach(opp_region, opp_seed, opp_slot_idx, qf_offset, half_slots, win_prob_fn)
            else:
                p_opp_h2 = 0.0
                p_cand_reach = _p_team_r1_win(opp_region, opp_seed, opp_slot, win_prob_fn)

            if team_region == opp_region:
                # Golden rule: same-region opponents → higher seed (lower number) always hosts,
                # superseding home-games-played and all other tiebreakers.
                p_host = 1.0 if team_seed < opp_seed else 0.0
            else:
                p_host = 0.0
                for team_h2, p_th2 in ((0, 1.0 - p_team_h2), (1, p_team_h2)):
                    for opp_h2, p_oh2 in ((0, 1.0 - p_opp_h2), (1, p_opp_h2)):
                        weight = p_th2 * p_oh2
                        team_total = team_h1 + team_h2
                        opp_total = opp_h1 + opp_h2
                        if team_total < opp_total:
                            p_host += weight
                        elif team_total == opp_total:
                            if team_seed < opp_seed:
                                p_host += weight
                            elif team_seed == opp_seed:
                                if odd_year:
                                    p_host += weight if team_region < opp_region else 0.0
                                else:
                                    p_host += weight if team_region > opp_region else 0.0

            p += p_cand_reach * p_host

    return p


# ---------------------------------------------------------------------------
# Helpers for deterministic override (rounds_completed path)
# ---------------------------------------------------------------------------


def _alive_in_slots(
    opp_slots: list[FormatSlot],
    all_region_odds: "dict[int, dict[str, StandingsOdds]]",
) -> "tuple[int, int] | None":
    """Return (region, seed) of the one alive team across *opp_slots*, or None.

    A team is considered alive when any school in their region has the matching
    seed probability > 0.5 (post-round seedings are deterministic: 0.0 or 1.0).
    """
    for slot in opp_slots:
        for r, s in ((slot.home_region, slot.home_seed), (slot.away_region, slot.away_seed)):
            if any(getattr(o, f"p{s}", 0.0) > 0.5 for o in all_region_odds.get(r, {}).values()):
                return (r, s)
    return None


def _r2_home_if_deterministic(
    region: int,
    seed: int,
    idx: int,
    half_slots: list[FormatSlot],
    season: int,
) -> "bool | None":
    """True/False if team's R2 home status is the same regardless of which R1 candidate advanced.

    Returns None when the two possible R2 opponents give different r2_home_team results
    (rare even-year same-cross-region-seed case), indicating the caller should fall back
    to the probabilistic path.
    """
    opp_slot = half_slots[_opponent_slot_indices(idx, 1)[0]]
    r2h_a = r2_home_team(region, seed, opp_slot.home_region, opp_slot.home_seed, season) == (region, seed)
    r2h_b = r2_home_team(region, seed, opp_slot.away_region, opp_slot.away_seed, season) == (region, seed)
    return r2h_a if r2h_a == r2h_b else None


# ---------------------------------------------------------------------------
# Deterministic home-team rules
# ---------------------------------------------------------------------------


def r2_home_team(
    region1: int,
    seed1: int,
    region2: int,
    seed2: int,
    season: int,
) -> tuple[int, int]:
    """Return ``(region, seed)`` of the second-round home team.

    Golden rule: same-region opponents → higher seed (lower number) hosts.
    Cross-region: higher seed hosts.  Equal cross-region seeds use the same
    odd/even year region-number tiebreak as QF/SF.

    Args:
        region1: Region number of the first team.
        seed1:   Region seed of the first team (1 = best).
        region2: Region number of the second team.
        seed2:   Region seed of the second team.
        season:  Football season year (used for odd/even tiebreak).

    Returns:
        ``(region, seed)`` tuple identifying the home team.
    """
    if region1 == region2:
        return (region1, seed1) if seed1 < seed2 else (region2, seed2)
    if seed1 < seed2:
        return (region1, seed1)
    if seed2 < seed1:
        return (region2, seed2)
    # equal cross-region seed — odd/even year tiebreak (same as QF/SF)
    odd_year = season % 2 == 1
    if odd_year:
        return (region1, seed1) if region1 < region2 else (region2, seed2)
    return (region1, seed1) if region1 > region2 else (region2, seed2)


def qf_home_team(
    region1: int,
    seed1: int,
    r1_home1: bool,
    r2_home1: bool,
    region2: int,
    seed2: int,
    r1_home2: bool,
    r2_home2: bool,
    season: int,
) -> tuple[int, int]:
    """Return ``(region, seed)`` of the quarterfinal home team.

    Golden rule: same-region opponents → higher seed (lower number) hosts,
    superseding all other steps.

    Cross-region rule (applied in order):

    1. Fewer playoff home games played so far → that team hosts.
    2. Equal home games → higher seed (lower number) hosts.
    3. Equal seed → region-number tiebreak: odd years lower region# hosts;
       even years higher region# hosts.

    Args:
        region1:  Region number of the first team.
        seed1:    Region seed of the first team (1 = best).
        r1_home1: True if the first team was the home team in round 1.
        r2_home1: True if the first team was the home team in round 2.
        region2:  Region number of the second team.
        seed2:    Region seed of the second team.
        r1_home2: True if the second team was the home team in round 1.
        r2_home2: True if the second team was the home team in round 2.
        season:   Football season year (used for odd/even tiebreak).

    Returns:
        ``(region, seed)`` tuple identifying the home team.
    """
    if region1 == region2:
        return (region1, seed1) if seed1 < seed2 else (region2, seed2)
    home1 = (1 if r1_home1 else 0) + (1 if r2_home1 else 0)
    home2 = (1 if r1_home2 else 0) + (1 if r2_home2 else 0)
    if home1 < home2:
        return (region1, seed1)
    if home2 < home1:
        return (region2, seed2)
    if seed1 < seed2:
        return (region1, seed1)
    if seed2 < seed1:
        return (region2, seed2)
    odd_year = season % 2 == 1
    if odd_year:
        return (region1, seed1) if region1 < region2 else (region2, seed2)
    return (region1, seed1) if region1 > region2 else (region2, seed2)


def sf_home_team(
    region1: int,
    seed1: int,
    region2: int,
    seed2: int,
    season: int,
) -> tuple[int, int]:
    """Return ``(region, seed)`` of the semifinal home team.

    Golden rule: same-region opponents → higher seed (lower number) hosts.
    Home games played do **not** factor in at this round per MHSAA rules.

    Cross-region rule (applied in order):

    1. Higher seed (lower number) hosts.
    2. Equal seed → region-number tiebreak: odd years lower region# hosts;
       even years higher region# hosts.

    Args:
        region1: Region number of the first team.
        seed1:   Region seed of the first team (1 = best).
        region2: Region number of the second team.
        seed2:   Region seed of the second team.
        season:  Football season year (used for odd/even tiebreak).

    Returns:
        ``(region, seed)`` tuple identifying the home team.
    """
    if region1 == region2:
        return (region1, seed1) if seed1 < seed2 else (region2, seed2)
    if seed1 < seed2:
        return (region1, seed1)
    if seed2 < seed1:
        return (region2, seed2)
    odd_year = season % 2 == 1
    if odd_year:
        return (region1, seed1) if region1 < region2 else (region2, seed2)
    return (region1, seed1) if region1 > region2 else (region2, seed2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_second_round_home_odds(
    region: int,
    region_odds: dict[str, StandingsOdds],
    slots: list[FormatSlot],
    season: int,
    win_prob_fn: MatchupProbFn = equal_matchup_prob,
    rounds_completed: int = 0,
    all_region_odds: "dict[int, dict[str, StandingsOdds]] | None" = None,
) -> dict[str, float]:
    """Compute each team's marginal probability of hosting their second-round game.

    Applies to 1A-4A only (5A-7A teams go straight to the quarterfinal).

    Rule: higher seed hosts.  Equal cross-region seeds use the odd/even year
    region-number tiebreak (same as QF/SF).

    When *rounds_completed* >= 1 and *all_region_odds* is provided, bypasses
    probabilistic computation and returns exactly 0.0 or 1.0 per team by
    finding the one alive opponent in the adjacent slot and applying
    ``r2_home_team`` directly.

    Args:
        region:          Region number for the teams in *region_odds*.
        region_odds:     Dict mapping team name to ``StandingsOdds``.
        slots:           All first-round format slots for this class (all regions).
        season:          Football season year (used for odd/even tiebreak).
        win_prob_fn:     Optional win-probability function.  Defaults to 0.5 for
                         every game.
        all_region_odds: Cross-region seeding odds after completed rounds.
                         When provided alongside *rounds_completed* >= 1, enables
                         deterministic 0/1 results for the R2 home decision.

    Returns:
        Dict mapping team name to marginal P(hosting round 2) in [0.0, 1.0].
    """
    half_slots = _half_slots_for_region(region, slots)
    if rounds_completed >= 1 and all_region_odds is not None:
        result: dict[str, float] = {}
        for school, o in region_odds.items():
            seed = next((s for s, p in ((1, o.p1), (2, o.p2), (3, o.p3), (4, o.p4)) if p > 0.5), None)
            if seed is None or o.p_playoffs <= 0:
                result[school] = 0.0
                continue
            idx = _slot_index_for(region, seed, half_slots)
            if idx is None:
                result[school] = 0.0
                continue
            opp_slots = [half_slots[i] for i in _opponent_slot_indices(idx, 1)]
            opp = _alive_in_slots(opp_slots, all_region_odds)
            result[school] = (
                1.0 if opp and r2_home_team(region, seed, opp[0], opp[1], season) == (region, seed) else 0.0
            )
        return result
    odd_year = season % 2 == 1
    result = {}
    for school, o in region_odds.items():
        p_home = 0.0
        for seed, p_seed in ((1, o.p1), (2, o.p2), (3, o.p3), (4, o.p4)):
            if p_seed <= 0.0:
                continue
            idx = _slot_index_for(region, seed, half_slots)
            if idx is None:
                continue
            p_r1 = 1.0 if rounds_completed >= 1 else _p_team_r1_win(region, seed, half_slots[idx], win_prob_fn)
            opp_indices = _opponent_slot_indices(idx, round_offset=1)
            p_r2_home = _p_host_seed_rule(
                seed,
                region,
                opp_indices,
                opp_num_wins=1,
                half_slots=half_slots,
                odd_year=odd_year,
                use_region_tiebreak=True,
                win_prob_fn=win_prob_fn,
            )
            p_home += p_seed * p_r1 * p_r2_home
        result[school] = p_home
    return result


def compute_quarterfinal_home_odds(
    region: int,
    region_odds: dict[str, StandingsOdds],
    slots: list[FormatSlot],
    season: int,
    win_prob_fn: MatchupProbFn = equal_matchup_prob,
    rounds_completed: int = 0,
    all_region_odds: "dict[int, dict[str, StandingsOdds]] | None" = None,
) -> dict[str, float]:
    """Compute each team's marginal probability of hosting their quarterfinal game.

    For 5A-7A the quarterfinal is round 2 (one win required after R1).
    For 1A-4A the quarterfinal is round 3 (two wins required).

    Rule: fewer home games hosted in prior rounds → hosts; equal home games →
    higher seed hosts; equal seed → region-number tiebreak (odd years: lower
    region# hosts; even years: higher region# hosts).

    When *rounds_completed* >= qf_offset and *all_region_odds* is provided,
    attempts deterministic 0/1 computation via ``qf_home_team``.  Falls back to
    probabilistic for teams where ``_r2_home_if_deterministic`` returns None
    (even-year same-cross-region-seed edge case).

    Args:
        region:          Region number for the teams in *region_odds*.
        region_odds:     Dict mapping team name to ``StandingsOdds``.
        slots:           All first-round format slots for this class (all regions).
        season:          Football season year (used for odd/even year tiebreak).
        win_prob_fn:     Optional win-probability function.  Defaults to 0.5 for
                         every game.
        all_region_odds: Cross-region seeding odds after completed rounds.

    Returns:
        Dict mapping team name to marginal P(hosting quarterfinal) in [0.0, 1.0].
    """
    half_slots = _half_slots_for_region(region, slots)
    qf_offset = 1 if len(half_slots) == 4 else 2
    odd_year = season % 2 == 1
    result: dict[str, float] = {}
    for school, o in region_odds.items():
        p_home = 0.0
        for seed, p_seed in ((1, o.p1), (2, o.p2), (3, o.p3), (4, o.p4)):
            if p_seed <= 0.0:
                continue
            idx = _slot_index_for(region, seed, half_slots)
            if idx is None:
                continue
            if rounds_completed >= qf_offset and all_region_odds is not None:
                r1h = _was_home_r1(region, seed, half_slots[idx])
                # For 5A-7A (qf_offset=1) there is no R2; r2_home is always False.
                # For 1A-4A (qf_offset=2) derive r2_home, falling back to probabilistic if ambiguous.
                r2h: "bool | None" = False if qf_offset == 1 else _r2_home_if_deterministic(region, seed, idx, half_slots, season)
                opp_slots = [half_slots[i] for i in _opponent_slot_indices(idx, qf_offset)]
                opp = _alive_in_slots(opp_slots, all_region_odds)
                if r2h is not None and opp is not None:
                    opp_idx = _slot_index_for(opp[0], opp[1], half_slots)
                    if opp_idx is not None:
                        opp_r1h = _was_home_r1(opp[0], opp[1], half_slots[opp_idx])
                        opp_r2h: "bool | None" = False if qf_offset == 1 else _r2_home_if_deterministic(opp[0], opp[1], opp_idx, half_slots, season)
                        if opp_r2h is not None:
                            host = qf_home_team(region, seed, r1h, r2h, opp[0], opp[1], opp_r1h, opp_r2h, season)
                            p_home += p_seed * (1.0 if host == (region, seed) else 0.0)
                            continue
            p_reach = _p_team_reach(region, seed, idx, qf_offset, half_slots, win_prob_fn, skip_wins=rounds_completed)
            p_qf_home = _p_host_qf_given_seed(seed, region, idx, half_slots, qf_offset, odd_year, season, win_prob_fn)
            p_home += p_seed * p_reach * p_qf_home
        result[school] = p_home
    return result


def compute_semifinal_home_odds(
    region: int,
    region_odds: dict[str, StandingsOdds],
    slots: list[FormatSlot],
    season: int,
    win_prob_fn: MatchupProbFn = equal_matchup_prob,
    rounds_completed: int = 0,
    all_region_odds: "dict[int, dict[str, StandingsOdds]] | None" = None,
) -> dict[str, float]:
    """Compute each team's marginal probability of hosting their semifinal game.

    For 5A-7A the semifinal is Round 3 (two wins after First Round).
    For 1A-4A the semifinal is Round 4 (three wins after First Round).

    Rule: higher seed hosts.  Equal-seed tiebreak: in odd years the
    lower-numbered region hosts; in even years the higher-numbered region hosts.
    Home games played do **not** factor in at this round.

    When *rounds_completed* >= sf_offset and *all_region_odds* is provided,
    returns exactly 0.0 or 1.0 per team by finding the one alive SF opponent
    and applying ``sf_home_team`` directly.

    Args:
        region:          Region number for the teams in *region_odds*.
        region_odds:     Dict mapping team name to ``StandingsOdds``.
        slots:           All first-round format slots for this class (all regions).
        season:          Football season year (used for odd/even year tiebreak).
        win_prob_fn:     Optional win-probability function.  Defaults to 0.5 for
                         every game.
        all_region_odds: Cross-region seeding odds after completed rounds.

    Returns:
        Dict mapping team name to marginal P(hosting semifinal) in [0.0, 1.0].
    """
    half_slots = _half_slots_for_region(region, slots)
    sf_offset = 2 if len(half_slots) == 4 else 3
    if rounds_completed >= sf_offset and all_region_odds is not None:
        result: dict[str, float] = {}
        for school, o in region_odds.items():
            seed = next((s for s, p in ((1, o.p1), (2, o.p2), (3, o.p3), (4, o.p4)) if p > 0.5), None)
            if seed is None or o.p_playoffs <= 0:
                result[school] = 0.0
                continue
            idx = _slot_index_for(region, seed, half_slots)
            if idx is None:
                result[school] = 0.0
                continue
            opp_slots = [half_slots[i] for i in _opponent_slot_indices(idx, sf_offset)]
            opp = _alive_in_slots(opp_slots, all_region_odds)
            result[school] = (
                1.0 if opp and sf_home_team(region, seed, opp[0], opp[1], season) == (region, seed) else 0.0
            )
        return result
    odd_year = season % 2 == 1
    result = {}
    for school, o in region_odds.items():
        p_home = 0.0
        for seed, p_seed in ((1, o.p1), (2, o.p2), (3, o.p3), (4, o.p4)):
            if p_seed <= 0.0:
                continue
            idx = _slot_index_for(region, seed, half_slots)
            if idx is None:
                continue
            p_reach = _p_team_reach(region, seed, idx, sf_offset, half_slots, win_prob_fn, skip_wins=rounds_completed)
            opp_indices = _opponent_slot_indices(idx, round_offset=sf_offset)
            p_sf_home = _p_host_seed_rule(
                seed,
                region,
                opp_indices,
                opp_num_wins=sf_offset,
                half_slots=half_slots,
                odd_year=odd_year,
                use_region_tiebreak=True,
                win_prob_fn=win_prob_fn,
            )
            p_home += p_seed * p_reach * p_sf_home
        result[school] = p_home
    return result


def compute_bracket_advancement_odds(
    region: int,
    region_odds: dict[str, StandingsOdds],
    slots: list[FormatSlot],
    win_prob_fn: MatchupProbFn = equal_matchup_prob,
    rounds_completed: int = 0,
) -> dict[str, BracketOdds]:
    """Compute each team's probability of advancing to successive playoff rounds.

    Unlike ``compute_bracket_odds`` (which uses a simple geometric formula and
    requires no slot data), this function traverses the actual bracket structure
    via ``_p_team_reach``, allowing a custom ``win_prob_fn`` to be applied.
    When called with the default ``equal_matchup_prob`` the results are
    numerically identical to ``compute_bracket_odds``.

    All five ``BracketOdds`` fields are fully Elo-weighted.  ``finals``
    (reaching the Championship Game) uses ``_p_team_reach(wins_to_win_half)``
    for the within-half bracket, and ``champion`` (winning the Championship)
    weights each possible opponent from the other bracket half by their own
    probability of winning that half.

    BracketOdds field semantics:

    * ``second_round``  — P(advance past First Round to Second Round) [1A-4A only]
    * ``quarterfinals`` — P(advance to Quarterfinals: Round 3 for 1A-4A, Round 2 for 5A-7A)
    * ``semifinals``    — P(advance to Semifinals: Round 4 for 1A-4A, Round 3 for 5A-7A)
    * ``finals``        — P(advance to Championship Game by winning Semifinals)
    * ``champion``      — P(win the Championship Game)

    Args:
        region:            Region number for the teams in *region_odds*.
        region_odds:       Dict mapping team name to ``StandingsOdds``.
        slots:             All first-round format slots for this class (all regions).
        win_prob_fn:       Win-probability function.  Defaults to ``equal_matchup_prob``
                           (0.5 for every game).
        rounds_completed:  Playoff rounds already played (0 during regular season).
                           Alive teams will show 1.0 for within-half rounds already
                           played and correct forward-looking odds for remaining rounds.

    Returns:
        Dict mapping team name to ``BracketOdds`` with per-round advancement
        probabilities.
    """
    half_slots = _half_slots_for_region(region, slots)
    is_1a_4a = len(half_slots) == 8
    qf_offset = 2 if is_1a_4a else 1
    sf_offset = 3 if is_1a_4a else 2
    wins_to_win_half = sf_offset + 1  # 4 for 1A-4A, 3 for 5A-7A

    # Build the other-half slot list and precompute each other-half team's
    # probability of winning their entire bracket half.
    my_ns = half_slots[0].north_south if half_slots else None
    other_half_slots = sorted(
        [s for s in slots if s.north_south != my_ns],
        key=lambda s: s.slot,
    ) if my_ns is not None else []

    other_half_win_probs: dict[tuple[int, int], float] = {}
    for local_idx, opp_slot in enumerate(other_half_slots):
        for opp_r, opp_s in (
            (opp_slot.home_region, opp_slot.home_seed),
            (opp_slot.away_region, opp_slot.away_seed),
        ):
            key = (opp_r, opp_s)
            if key not in other_half_win_probs:
                other_half_win_probs[key] = _p_team_reach(
                    opp_r, opp_s, local_idx, wins_to_win_half, other_half_slots, win_prob_fn
                )

    result: dict[str, BracketOdds] = {}
    for school, o in region_odds.items():
        p_r2 = 0.0
        p_qf = 0.0
        p_sf = 0.0
        p_finals = 0.0
        p_champion = 0.0

        for seed, p_seed in ((1, o.p1), (2, o.p2), (3, o.p3), (4, o.p4)):
            if p_seed <= 0.0:
                continue
            idx = _slot_index_for(region, seed, half_slots)
            if idx is None:
                continue

            if is_1a_4a:
                p_r2 += p_seed * _p_team_r1_win(region, seed, half_slots[idx], win_prob_fn)
            p_qf += p_seed * _p_team_reach(region, seed, idx, qf_offset, half_slots, win_prob_fn)
            p_sf += p_seed * _p_team_reach(region, seed, idx, sf_offset, half_slots, win_prob_fn)

            p_wins_half = _p_team_reach(region, seed, idx, wins_to_win_half, half_slots, win_prob_fn)
            p_finals += p_seed * p_wins_half

            # Championship: team wins their half, then beats the other-half winner.
            p_beat_other = sum(
                p_opp * _p_beat_by_seed(region, seed, opp_r, opp_s, win_prob_fn)
                for (opp_r, opp_s), p_opp in other_half_win_probs.items()
            )
            p_champion += p_seed * p_wins_half * p_beat_other

        # For rounds already played, alive teams (p_playoffs > 0) get 1.0 for each
        # past milestone. Eliminated teams stay at 0.0 since their p_playoffs = 0.
        p = o.p_playoffs
        eff_r2 = p if (is_1a_4a and rounds_completed >= 1) else p_r2
        eff_qf = p if rounds_completed >= qf_offset else p_qf
        eff_sf = p if rounds_completed >= sf_offset else p_sf
        eff_finals = p if rounds_completed >= wins_to_win_half else p_finals
        eff_champion = p if rounds_completed > wins_to_win_half else p_champion

        result[school] = BracketOdds(
            school=school,
            second_round=eff_r2 if is_1a_4a else 0.0,
            quarterfinals=eff_qf,
            semifinals=eff_sf,
            finals=eff_finals,
            champion=eff_champion,
        )
    return result


def marginal_home_odds(conditional: float, advancement: float) -> float:
    """Return the marginal probability of hosting a playoff round.

    Marginal = P(reaches round) × P(hosts | reaches round).

    This is the complement of ``_safe_cond`` used when storing odds: the DB
    stores the two components separately (advancement in ``odds_*`` and
    conditional in ``odds_*_home``), and this function reconstructs the
    combined probability for display or further calculation.

    Args:
        conditional:  P(hosts round | reaches round) — the stored
                      ``odds_*_home`` value.
        advancement:  P(reaches round) — the stored ``odds_*`` value.

    Returns:
        P(reaches round AND hosts round) in [0.0, 1.0].
    """
    return conditional * advancement
