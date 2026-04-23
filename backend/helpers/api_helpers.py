"""Pure helpers for building API response objects and transforming request data.

All functions are free of database I/O.  They operate on in-memory data
(dataclass instances, plain tuples, Pydantic response models) and are designed
to be fully unit-testable without a running database or Prefect environment.
"""

from __future__ import annotations

from collections import defaultdict

from backend.api.models.responses import (
    RecordModel,
    RemainingGameModel,
    RoundHostingOdds,
    ScenarioEntry,
    SeedingOddsModel,
    TeamBracketEntry,
    TeamHostingEntry,
    TeamStandingsEntry,
)
from backend.helpers.bracket_home_odds import (
    compute_bracket_advancement_odds,
    compute_quarterfinal_home_odds,
    compute_second_round_home_odds,
    compute_semifinal_home_odds,
    marginal_home_odds,
)
from backend.helpers.data_classes import (
    AppliedGameResult,
    BracketOdds,
    BracketTeam,
    CompletedGame,
    FormatSlot,
    RemainingGame,
    StandingsOdds,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DISPLAY_THRESHOLD = 6
"""Maximum remaining games for which the human-readable scenario list is shown."""

CLINCHED_THRESHOLD = 0.999
"""Minimum seeding probability required to consider a seed position clinched."""

# ---------------------------------------------------------------------------
# Game data parsing
# ---------------------------------------------------------------------------


def parse_completed_games(rows: list[tuple]) -> list[CompletedGame]:
    """Deduplicate and normalise school-perspective game rows into CompletedGame objects.

    Each row must be ``(school, opponent, points_for, points_against, game_date)``.
    Rows with ``None`` scores are skipped.  Symmetric pairs are deduplicated so
    each contest produces exactly one ``CompletedGame``.  Teams are stored in
    alphabetical order (``a < b``); ``res_a``, ``pd_a``, ``pa_a``, ``pa_b``
    are computed from team ``a``'s perspective.
    """
    seen: set[frozenset] = set()
    result: list[CompletedGame] = []
    for school, opponent, pf, pa, _game_date in rows:
        pair: frozenset = frozenset([school, opponent])
        if pair in seen or pf is None or pa is None:
            continue
        seen.add(pair)
        a, b = (school, opponent) if school < opponent else (opponent, school)
        sa = pf if school == a else pa  # score of lexicographically first team
        sb = pa if school == a else pf  # score of lexicographically second team
        if sa > sb:
            res_a = 1
        elif sa < sb:
            res_a = -1
        else:
            res_a = 0
        result.append(CompletedGame(a=a, b=b, res_a=res_a, pd_a=sa - sb, pa_a=sb, pa_b=sa))
    return result


def compute_remaining_games(teams: list[str], completed: list[CompletedGame]) -> list[RemainingGame]:
    """Return sorted list of unplayed (a, b) game pairs from all possible team combinations."""
    all_pairs = {frozenset([t1, t2]) for i, t1 in enumerate(teams) for t2 in teams[i + 1 :]}
    done_pairs = {frozenset([c.a, c.b]) for c in completed}
    return [
        RemainingGame(a=min(*pair), b=max(*pair))
        for pair in sorted(all_pairs - done_pairs, key=lambda p: tuple(sorted(p)))
    ]


# ---------------------------------------------------------------------------
# Simulation helpers
# ---------------------------------------------------------------------------


def results_to_applied(body_results) -> list[AppliedGameResult]:
    """Convert a list of ``GameResultRequest`` objects to ``AppliedGameResult`` objects.

    ``winner_score`` and ``loser_score`` default to ``1`` and ``0`` respectively
    when not provided by the caller.
    """
    return [
        AppliedGameResult(
            team_a=r.winner,
            team_b=r.loser,
            score_a=r.winner_score if r.winner_score is not None else 1,
            score_b=r.loser_score if r.loser_score is not None else 0,
        )
        for r in body_results
    ]


def filter_remaining_after_simulation(
    remaining: list[RemainingGame],
    body_results,
) -> list[RemainingGame]:
    """Remove games from *remaining* whose team pair appears in *body_results*."""
    applied_pairs = [{r.winner, r.loser} for r in body_results]
    return [rg for rg in remaining if {rg.a, rg.b} not in applied_pairs]


def bracket_results_to_applied(body_results) -> list[AppliedGameResult]:
    """Convert ``BracketGameResultRequest`` objects to ``AppliedGameResult`` using slot IDs.

    Slot identifiers follow the ``"R{region}S{seed}"`` format (e.g. ``"R1S2"``).
    """
    return [
        AppliedGameResult(
            team_a=f"R{r.home_region}S{r.home_seed}",
            team_b=f"R{r.away_region}S{r.away_seed}",
            score_a=1 if r.home_wins else 0,
            score_b=0 if r.home_wins else 1,
        )
        for r in body_results
    ]


def build_bracket_teams(by_region: dict, season: int) -> list[BracketTeam]:
    """Build a ``BracketTeam`` list using ``R{region}S{seed}`` slot IDs as school names."""
    return [
        BracketTeam(bracket_id=0, school=f"R{region}S{seed}", season=season, seed=seed, region=region)
        for region in sorted(by_region)
        for seed in (1, 2, 3, 4)
    ]


def num_rounds_for_class(clazz: int) -> int:
    """Return the playoff round count: 5 for 1A–4A (32-team), 4 for 5A–7A (16-team)."""
    return 5 if clazz <= 4 else 4


# ---------------------------------------------------------------------------
# Record helpers
# ---------------------------------------------------------------------------


def records_from_completed(teams: list[str], completed: list[CompletedGame]) -> dict[str, tuple]:
    """Build region W/L records from completed games for the on-demand computation path.

    Returns ``{team: (0, 0, 0, region_wins, region_losses, 0)}`` for each team.
    Overall wins/losses/ties are not available on the on-demand path and default to 0.
    """
    wins: dict[str, int] = defaultdict(int)
    losses: dict[str, int] = defaultdict(int)
    for g in completed:
        if g.res_a == 1:
            wins[g.a] += 1
            losses[g.b] += 1
        elif g.res_a == -1:
            wins[g.b] += 1
            losses[g.a] += 1
    return {t: (0, 0, 0, wins[t], losses[t], 0) for t in teams}


# ---------------------------------------------------------------------------
# Response builders — standings
# ---------------------------------------------------------------------------


def remaining_to_models(remaining: list[RemainingGame]) -> list[RemainingGameModel]:
    """Convert ``RemainingGame`` dataclasses to ``RemainingGameModel`` response objects."""
    return [RemainingGameModel(team_a=r.a, team_b=r.b, location_a=r.location_a) for r in remaining]


def scenarios_to_entries(complete_scenarios: list[dict] | None) -> list[ScenarioEntry] | None:
    """Convert complete scenario dicts to ``ScenarioEntry`` response objects, or ``None`` if empty."""
    if not complete_scenarios:
        return None
    result = []
    for sc in complete_scenarios:
        seeding = sc.get("seeding", ())
        result.append(ScenarioEntry(outcomes={team: str(idx + 1) for idx, team in enumerate(seeding)}))
    return result


def build_team_entries(
    standings_rows: list[tuple],
    odds_override: dict[str, StandingsOdds] | None,
    coinflip_override: set[str] | None,
) -> list[TeamStandingsEntry]:
    """Build per-team standings response entries from DB rows, with optional odds override.

    When *odds_override* contains an entry for a school, its values replace the
    DB-stored odds (used after on-demand recomputation or simulation).
    *coinflip_override* replaces the DB ``coin_flip_needed`` field when provided.
    """
    entries = []
    for row in standings_rows:
        school = row[0]
        record = RecordModel(
            wins=row[1],
            losses=row[2],
            ties=row[3],
            region_wins=row[4],
            region_losses=row[5],
            region_ties=row[6],
        )
        if odds_override and school in odds_override:
            o = odds_override[school]
            odds = SeedingOddsModel(p1=o.p1, p2=o.p2, p3=o.p3, p4=o.p4, p_playoffs=o.p_playoffs)
            clinched, eliminated = o.clinched, o.eliminated
            coin_flip = school in (coinflip_override or set())
        else:
            odds = SeedingOddsModel(p1=row[7], p2=row[8], p3=row[9], p4=row[10], p_playoffs=row[11])
            clinched, eliminated = row[12], row[13]
            coin_flip = row[14]
        entries.append(
            TeamStandingsEntry(
                school=school,
                record=record,
                odds=odds,
                clinched=clinched,
                eliminated=eliminated,
                coin_flip_needed=coin_flip,
            )
        )
    return entries


def standings_from_odds(
    odds_map: dict[str, StandingsOdds],
    coinflip_teams: set[str],
    records: dict[str, tuple],
) -> list[TeamStandingsEntry]:
    """Build standings entries from on-demand computation when no DB snapshot is available.

    Teams are returned sorted alphabetically.  Overall W/L/T default to 0 when
    not available (see ``records_from_completed``).
    """
    entries = []
    for school in sorted(odds_map):
        rec = records.get(school, (0, 0, 0, 0, 0, 0))
        o = odds_map[school]
        entries.append(
            TeamStandingsEntry(
                school=school,
                record=RecordModel(
                    wins=rec[0],
                    losses=rec[1],
                    ties=rec[2],
                    region_wins=rec[3],
                    region_losses=rec[4],
                    region_ties=rec[5],
                ),
                odds=SeedingOddsModel(p1=o.p1, p2=o.p2, p3=o.p3, p4=o.p4, p_playoffs=o.p_playoffs),
                clinched=o.clinched,
                eliminated=o.eliminated,
                coin_flip_needed=school in coinflip_teams,
            )
        )
    return entries


# ---------------------------------------------------------------------------
# Response builders — hosting
# ---------------------------------------------------------------------------


def build_hosting_entries(
    region_odds: dict[str, StandingsOdds],
    slots: list[FormatSlot],
    region: int,
    season: int,
    clazz: int,
) -> list[TeamHostingEntry]:
    """Compute per-round playoff hosting odds for all teams in a region.

    1A–4A have four hosting rounds (first round, second round, quarterfinals,
    semifinals).  5A–7A have three (first round IS the quarterfinal; ``second_round``
    is returned with ``None`` odds).
    """
    is_1a_4a = clazz <= 4
    adv_odds = compute_bracket_advancement_odds(region, region_odds, slots)
    qf_home = compute_quarterfinal_home_odds(region, region_odds, slots, season)
    sf_home = compute_semifinal_home_odds(region, region_odds, slots, season)

    entries = []
    for school, o in region_odds.items():
        adv = adv_odds.get(school)
        p_qf_cond = qf_home.get(school, 0.0)
        p_sf_cond = sf_home.get(school, 0.0)

        if is_1a_4a:
            r2_home_dict = compute_second_round_home_odds(region, region_odds, slots, season)
            p_r2_cond = r2_home_dict.get(school, 0.0)
            p_r1_adv = adv.second_round if adv else 0.0
            p_r2_adv = adv.quarterfinals if adv else 0.0
            p_qf_adv = adv.semifinals if adv else 0.0
            r1_odds = RoundHostingOdds(conditional=1.0, marginal=marginal_home_odds(1.0, o.p_playoffs))
            r2_odds = RoundHostingOdds(
                conditional=p_r2_cond / p_r1_adv if p_r1_adv > 0 else None,
                marginal=marginal_home_odds(p_r2_cond, p_r1_adv) if p_r1_adv > 0 else 0.0,
            )
            qf_odds = RoundHostingOdds(
                conditional=p_qf_cond / p_r2_adv if p_r2_adv > 0 else None,
                marginal=marginal_home_odds(p_qf_cond, p_r2_adv) if p_r2_adv > 0 else 0.0,
            )
            sf_odds = RoundHostingOdds(
                conditional=p_sf_cond / p_qf_adv if p_qf_adv > 0 else None,
                marginal=marginal_home_odds(p_sf_cond, p_qf_adv) if p_qf_adv > 0 else 0.0,
            )
        else:
            p_qf_adv = adv.quarterfinals if adv else 0.0
            p_sf_adv = adv.semifinals if adv else 0.0
            r1_odds = RoundHostingOdds(conditional=1.0, marginal=marginal_home_odds(1.0, o.p_playoffs))
            r2_odds = RoundHostingOdds(conditional=None, marginal=None)
            qf_odds = RoundHostingOdds(
                conditional=p_qf_cond / p_qf_adv if p_qf_adv > 0 else None,
                marginal=marginal_home_odds(p_qf_cond, p_qf_adv) if p_qf_adv > 0 else 0.0,
            )
            sf_odds = RoundHostingOdds(
                conditional=p_sf_cond / p_sf_adv if p_sf_adv > 0 else None,
                marginal=marginal_home_odds(p_sf_cond, p_sf_adv) if p_sf_adv > 0 else 0.0,
            )
        entries.append(
            TeamHostingEntry(
                school=school,
                first_round=r1_odds,
                second_round=r2_odds,
                quarterfinals=qf_odds,
                semifinals=sf_odds,
            )
        )
    return entries


# ---------------------------------------------------------------------------
# Response builders — bracket
# ---------------------------------------------------------------------------


def clinched_school(region_odds: dict[str, StandingsOdds], seed: int) -> str | None:
    """Return the school whose seed-*seed* probability meets the clinched threshold, or ``None``."""
    attr = f"p{seed}"
    return next(
        (s for s, o in region_odds.items() if getattr(o, attr) >= CLINCHED_THRESHOLD),
        None,
    )


def build_bracket_entries_from_odds_map(
    by_region: dict[int, dict[str, StandingsOdds]],
    odds_map: dict[str, BracketOdds],
) -> list[TeamBracketEntry]:
    """Build ``TeamBracketEntry`` list from pre-computed bracket advancement odds.

    *odds_map* maps slot IDs (e.g. ``"R1S2"``) to ``BracketOdds``.  Slots absent
    from *odds_map* are skipped.  ``school`` is populated only when a team has
    clinched that seed position.  Used by both the snapshot path (via
    ``build_bracket_entries``) and the simulation path.
    """
    entries: list[TeamBracketEntry] = []
    for region_num, region_odds in sorted(by_region.items()):
        for seed in (1, 2, 3, 4):
            slot_id = f"R{region_num}S{seed}"
            bo = odds_map.get(slot_id)
            if bo is None:
                continue
            entries.append(
                TeamBracketEntry(
                    region=region_num,
                    seed=seed,
                    school=clinched_school(region_odds, seed),
                    second_round=bo.second_round,
                    quarterfinals=bo.quarterfinals,
                    semifinals=bo.semifinals,
                    finals=bo.finals,
                    champion=bo.champion,
                )
            )
    return entries


def build_bracket_entries(
    by_region: dict[int, dict[str, StandingsOdds]],
    slots: list[FormatSlot],
) -> list[TeamBracketEntry]:
    """Build ``TeamBracketEntry`` list from regional odds using slot IDs as bracket keys.

    Each (region, seed) slot is treated as a certainty so advancement odds
    reflect the structural bracket position, independent of which team fills it.
    Delegates entry construction to ``build_bracket_entries_from_odds_map``.
    """
    all_odds: dict[str, BracketOdds] = {}
    for region_num in sorted(by_region):
        slot_odds: dict[str, StandingsOdds] = {
            f"R{region_num}S{seed}": StandingsOdds(
                school=f"R{region_num}S{seed}",
                p1=1.0 if seed == 1 else 0.0,
                p2=1.0 if seed == 2 else 0.0,
                p3=1.0 if seed == 3 else 0.0,
                p4=1.0 if seed == 4 else 0.0,
                p_playoffs=1.0,
                final_playoffs=1.0,
                clinched=True,
                eliminated=False,
            )
            for seed in (1, 2, 3, 4)
        }
        all_odds.update(compute_bracket_advancement_odds(region_num, slot_odds, slots))
    return build_bracket_entries_from_odds_map(by_region, all_odds)
