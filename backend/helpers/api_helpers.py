"""Helpers for building API response objects, transforming request data, and shared bracket state.

Pure response-builder functions are free of database I/O.  The playoff bracket
state helpers (``_load_elo_ratings``, ``_load_and_build_playoff_bracket_state``)
are async and require a database connection; they are centralized here so both
the bracket and hosting routers can share them without duplication.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from backend.api.models.requests import BracketGameResultRequest, ParticipantRef
from backend.api.models.responses import (
    BracketAdvancementOdds,
    BracketGame,
    BracketGameResult,
    BracketLayout,
    BracketParticipant,
    BracketSlotHosting,
    ChampionshipGame,
    HomeGameOdds,
    RecordModel,
    RemainingGameModel,
    RoundHostingOdds,
    ScenarioEntry,
    ScenarioGameOutcome,
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
    half_slots_for_region,
    marginal_home_odds,
    opponent_slots,
    qf_home_team,
    r2_home_team,
    sf_home_team,
    slot_index_for,
    was_home_r1,
)
from backend.helpers.data_classes import (
    AppliedGameResult,
    BracketOdds,
    CompletedGame,
    FormatSlot,
    MatchupProbFn,
    RemainingGame,
    StandingsOdds,
)
from backend.helpers.win_probability import EloConfig, make_matchup_prob_fn

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

    ``winner_score`` and ``loser_score`` default to ``12`` and ``0`` respectively
    when not provided by the caller (same as a forfeit).
    """
    return [
        AppliedGameResult(
            team_a=r.winner,
            team_b=r.loser,
            score_a=r.winner_score if r.winner_score is not None else 12,
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
        result.append(
            ScenarioEntry(
                scenario_num=sc["scenario_num"],
                sub_label=sc["sub_label"],
                game_winners=[ScenarioGameOutcome(winner=w, loser=l) for w, l in sc.get("game_winners", [])],
                tiebreaker_groups=sc.get("tiebreaker_groups"),
                coinflip_groups=sc.get("coinflip_groups"),
                outcomes={team: str(idx + 1) for idx, team in enumerate(seeding)},
            )
        )
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
            bracket_odds = None
            home_game_odds = None
        else:
            odds = SeedingOddsModel(
                p1=row[7],
                p2=row[8],
                p3=row[9],
                p4=row[10],
                p_playoffs=row[11],
                p1_weighted=row[16],
                p2_weighted=row[17],
                p3_weighted=row[18],
                p4_weighted=row[19],
                p_playoffs_weighted=row[20],
            )
            clinched, eliminated = row[12], row[13]
            coin_flip = row[14]
            bracket_odds = BracketAdvancementOdds(
                second_round=row[21],
                quarterfinals=row[22],
                semifinals=row[23],
                finals=row[24],
                champion=row[25],
                second_round_weighted=row[26],
                quarterfinals_weighted=row[27],
                semifinals_weighted=row[28],
                finals_weighted=row[29],
                champion_weighted=row[30],
            )
            home_game_odds = HomeGameOdds(
                first_round=row[31],
                second_round=row[32],
                quarterfinals=row[33],
                semifinals=row[34],
                first_round_weighted=row[35],
                second_round_weighted=row[36],
                quarterfinals_weighted=row[37],
                semifinals_weighted=row[38],
            )
        entries.append(
            TeamStandingsEntry(
                school=school,
                record=record,
                odds=odds,
                bracket_odds=bracket_odds,
                home_game_odds=home_game_odds,
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
# Seeding odds helpers — used by simulate endpoint weighted computation
# ---------------------------------------------------------------------------


def build_seeding_by_region(
    simulated_region: int,
    simulated_odds: dict[str, StandingsOdds],
    other_region_rows: list[tuple[str, int, float, float, float, float]],
) -> dict[int, dict[str, StandingsOdds]]:
    """Combine hypothetical odds for one region with stored odds for all others.

    Used by the regular-season simulate path to build the full
    ``seeding_odds_by_region`` argument required by ``make_matchup_prob_fn``.

    Args:
        simulated_region:  The region whose odds come from the what-if simulation.
        simulated_odds:    Updated ``StandingsOdds`` for that region (may be
                           fractional / probabilistic).
        other_region_rows: Rows from ``region_standings`` for every other region:
                           ``(school, region, odds_1st, odds_2nd, odds_3rd, odds_4th)``.

    Returns:
        ``dict[int, dict[str, StandingsOdds]]`` covering all regions present in
        the inputs, suitable for passing directly to ``make_matchup_prob_fn``.
    """
    result: dict[int, dict[str, StandingsOdds]] = {simulated_region: simulated_odds}
    for school, reg, p1, p2, p3, p4 in other_region_rows:
        p_playoffs = p1 + p2 + p3 + p4
        result.setdefault(reg, {})[school] = StandingsOdds(
            school=school,
            p1=p1,
            p2=p2,
            p3=p3,
            p4=p4,
            p_playoffs=p_playoffs,
            final_playoffs=p_playoffs,
            clinched=False,
            eliminated=False,
        )
    return result


# ---------------------------------------------------------------------------
# Response builders — hosting
# ---------------------------------------------------------------------------


def build_hosting_entries(  # NOSONAR — wide interface needed to cover GET (stored) and simulate (on-the-fly) paths
    region_odds: dict[str, StandingsOdds],
    slots: list[FormatSlot],
    region: int,
    season: int,
    clazz: int,
    home_cond: dict[str, tuple[float, float, float, float]] | None = None,
    home_cond_w: dict[str, tuple[float, float, float, float]] | None = None,
    stored_adv: dict[str, tuple[float, float, float, float]] | None = None,
    stored_adv_w: dict[str, tuple[float, float, float, float]] | None = None,
    rounds_completed: int = 0,
    wins_confirmed: dict[str, int] | None = None,
    win_prob_fn_weighted: MatchupProbFn | None = None,
    region_odds_weighted: dict[str, StandingsOdds] | None = None,
    all_region_odds: dict[int, dict[str, StandingsOdds]] | None = None,
    cross_region_wins: dict[tuple[int, int], int] | None = None,
    eliminated_hosting: dict[str, tuple[float | None, float | None, float | None, float | None]] | None = None,
) -> list[TeamHostingEntry]:
    """Compute per-round playoff hosting odds for all teams in a region.

    When *home_cond* and *stored_adv* are provided (GET endpoint), values are
    read directly from the DB snapshot — this correctly reflects rounds already
    played and advancement probabilities after each playoff round.

    When not provided (simulate endpoint, unit tests), falls back to on-the-fly
    computation from seeding odds.  R1 conditional is 0.0 in the fallback path
    since home-seed data is not available without a DB lookup.

    *eliminated_hosting* overrides both paths for eliminated teams: supply a
    ``(r1, r2, qf, sf)`` tuple of 1.0/0.0/None per team so that rounds they
    actually played show a deterministic conditional rather than null.

    1A–4A have four hosting rounds; 5A–7A skip ``second_round`` (null).

    Tuple layout for *home_cond*, *home_cond_w*, *stored_adv*, *stored_adv_w*:
        index 0 → R1 / p_playoffs
        index 1 → R2 / odds_second_round
        index 2 → QF / odds_quarterfinals
        index 3 → SF / odds_semifinals
    """
    is_1a_4a = clazz <= 4
    use_stored = home_cond is not None and stored_adv is not None

    if not use_stored:
        adv_odds = compute_bracket_advancement_odds(
            region, region_odds, slots, rounds_completed=rounds_completed, wins_confirmed=wins_confirmed
        )
        qf_home = compute_quarterfinal_home_odds(
            region,
            region_odds,
            slots,
            season,
            rounds_completed=rounds_completed,
            wins_confirmed=wins_confirmed,
            all_region_odds=all_region_odds,
            cross_region_wins=cross_region_wins,
        )
        sf_home = compute_semifinal_home_odds(
            region,
            region_odds,
            slots,
            season,
            rounds_completed=rounds_completed,
            wins_confirmed=wins_confirmed,
            all_region_odds=all_region_odds,
            cross_region_wins=cross_region_wins,
        )
        r2_home_dict = (
            compute_second_round_home_odds(
                region, region_odds, slots, season, rounds_completed=rounds_completed, wins_confirmed=wins_confirmed
            )
            if is_1a_4a
            else {}
        )
        r1_home_seeds = {s.home_seed for s in slots if s.home_region == region}

        if win_prob_fn_weighted is not None:
            rw = region_odds_weighted if region_odds_weighted is not None else region_odds
            adv_odds_w = compute_bracket_advancement_odds(
                region,
                rw,
                slots,
                win_prob_fn=win_prob_fn_weighted,
                rounds_completed=rounds_completed,
                wins_confirmed=wins_confirmed,
            )
            qf_home_w = compute_quarterfinal_home_odds(
                region,
                rw,
                slots,
                season,
                win_prob_fn=win_prob_fn_weighted,
                rounds_completed=rounds_completed,
                wins_confirmed=wins_confirmed,
                all_region_odds=all_region_odds,
                cross_region_wins=cross_region_wins,
            )
            sf_home_w = compute_semifinal_home_odds(
                region,
                rw,
                slots,
                season,
                win_prob_fn=win_prob_fn_weighted,
                rounds_completed=rounds_completed,
                wins_confirmed=wins_confirmed,
                all_region_odds=all_region_odds,
                cross_region_wins=cross_region_wins,
            )
            r2_home_dict_w: dict[str, float] = (
                compute_second_round_home_odds(
                    region,
                    rw,
                    slots,
                    season,
                    win_prob_fn=win_prob_fn_weighted,
                    rounds_completed=rounds_completed,
                    wins_confirmed=wins_confirmed,
                )
                if is_1a_4a
                else {}
            )
        else:
            adv_odds_w = qf_home_w = sf_home_w = None
            r2_home_dict_w = {}

    entries = []
    for school, o in region_odds.items():
        if o.eliminated and eliminated_hosting is not None and school in eliminated_hosting:
            r1_det, r2_det, qf_det, sf_det = eliminated_hosting[school]

            def _det(val: float | None) -> RoundHostingOdds:
                """Wrap a deterministic hosting value as RoundHostingOdds (marginal = conditional since p_reach = 1)."""
                return RoundHostingOdds(
                    conditional=val,
                    marginal=val if val is not None else 0.0,
                    conditional_weighted=val,
                    marginal_weighted=val if val is not None else 0.0,
                )

            r1_odds = _det(r1_det)
            r2_odds = _det(r2_det) if is_1a_4a else RoundHostingOdds(conditional=None, marginal=None)
            qf_odds = _det(qf_det)
            sf_odds = _det(sf_det)
        elif use_stored:
            r1_c, r2_c, qf_c, sf_c = home_cond.get(school, (0.0, 0.0, 0.0, 0.0))  # type: ignore[union-attr]
            a_r1, a_r2, a_qf, a_sf = stored_adv.get(school, (0.0, 0.0, 0.0, 0.0))  # type: ignore[union-attr]
            r1_c_w, r2_c_w, qf_c_w, sf_c_w = (home_cond_w or {}).get(school, (0.0, 0.0, 0.0, 0.0))
            a_r1_w, a_r2_w, a_qf_w, a_sf_w = (stored_adv_w or {}).get(school, (0.0, 0.0, 0.0, 0.0))

            r1_gate = o.p_playoffs > 0 or o.clinched
            eff_a_r1 = a_r1 if a_r1 > 0 else (1.0 if o.clinched else 0.0)
            eff_a_r1_w = a_r1_w if a_r1_w > 0 else (1.0 if o.clinched else 0.0)
            r1_odds = RoundHostingOdds(
                conditional=r1_c if r1_gate else None,
                marginal=r1_c * eff_a_r1,
                conditional_weighted=r1_c_w if r1_gate else None,
                marginal_weighted=r1_c_w * eff_a_r1_w,
            )
            if is_1a_4a:
                r2_odds = RoundHostingOdds(
                    conditional=r2_c if a_r2 > 0 else None,
                    marginal=r2_c * a_r2,
                    conditional_weighted=r2_c_w if a_r2 > 0 else None,
                    marginal_weighted=r2_c_w * a_r2_w,
                )
            else:
                r2_odds = RoundHostingOdds(conditional=None, marginal=None)
            qf_odds = RoundHostingOdds(
                conditional=qf_c if a_qf > 0 else None,
                marginal=qf_c * a_qf,
                conditional_weighted=qf_c_w if a_qf > 0 else None,
                marginal_weighted=qf_c_w * a_qf_w,
            )
            sf_odds = RoundHostingOdds(
                conditional=sf_c if a_sf > 0 else None,
                marginal=sf_c * a_sf,
                conditional_weighted=sf_c_w if a_sf > 0 else None,
                marginal_weighted=sf_c_w * a_sf_w,
            )
        else:
            # On-the-fly fallback (simulate endpoint / unit tests).
            adv = adv_odds.get(school)  # type: ignore[possibly-undefined]
            p_qf_cond = qf_home.get(school, 0.0)  # type: ignore[possibly-undefined]
            p_sf_cond = sf_home.get(school, 0.0)  # type: ignore[possibly-undefined]

            adv_w = adv_odds_w.get(school) if adv_odds_w else None  # type: ignore[possibly-undefined]
            p_qf_cond_w = qf_home_w.get(school, 0.0) if qf_home_w else 0.0  # type: ignore[possibly-undefined]
            p_sf_cond_w = sf_home_w.get(school, 0.0) if sf_home_w else 0.0  # type: ignore[possibly-undefined]

            r1_cond = sum(
                getattr(o, f"p{seed}") * (1.0 if seed in r1_home_seeds else 0.0)  # type: ignore[possibly-undefined]
                for seed in (1, 2, 3, 4)
            )
            if is_1a_4a:
                p_r2_cond = r2_home_dict.get(school, 0.0)  # type: ignore[possibly-undefined]
                p_r1_adv = adv.second_round if adv else 0.0
                p_r2_adv = adv.quarterfinals if adv else 0.0
                p_qf_adv = adv.semifinals if adv else 0.0
                p_r2_cond_w = r2_home_dict_w.get(school, 0.0)  # type: ignore[possibly-undefined]
                p_r1_adv_w = adv_w.second_round if adv_w else 0.0
                p_r2_adv_w = adv_w.quarterfinals if adv_w else 0.0
                p_qf_adv_w = adv_w.semifinals if adv_w else 0.0
                r1_odds = RoundHostingOdds(
                    conditional=r1_cond if o.p_playoffs > 0 else None,
                    marginal=marginal_home_odds(r1_cond, o.p_playoffs),
                    conditional_weighted=r1_cond if (o.p_playoffs > 0 and adv_w) else None,
                    marginal_weighted=marginal_home_odds(r1_cond, o.p_playoffs) if adv_w else None,
                )
                r2_odds = RoundHostingOdds(
                    conditional=p_r2_cond / p_r1_adv if p_r1_adv > 0 else None,
                    marginal=p_r2_cond if p_r1_adv > 0 else 0.0,
                    conditional_weighted=p_r2_cond_w / p_r1_adv_w if p_r1_adv_w > 0 else None,
                    marginal_weighted=p_r2_cond_w if p_r1_adv_w > 0 else 0.0,
                )
                qf_odds = RoundHostingOdds(
                    conditional=p_qf_cond / p_r2_adv if p_r2_adv > 0 else None,
                    marginal=p_qf_cond if p_r2_adv > 0 else 0.0,
                    conditional_weighted=p_qf_cond_w / p_r2_adv_w if p_r2_adv_w > 0 else None,
                    marginal_weighted=p_qf_cond_w if p_r2_adv_w > 0 else 0.0,
                )
                sf_odds = RoundHostingOdds(
                    conditional=p_sf_cond / p_qf_adv if p_qf_adv > 0 else None,
                    marginal=p_sf_cond if p_qf_adv > 0 else 0.0,
                    conditional_weighted=p_sf_cond_w / p_qf_adv_w if p_qf_adv_w > 0 else None,
                    marginal_weighted=p_sf_cond_w if p_qf_adv_w > 0 else 0.0,
                )
            else:
                p_qf_adv = adv.quarterfinals if adv else 0.0
                p_sf_adv = adv.semifinals if adv else 0.0
                p_qf_adv_w = adv_w.quarterfinals if adv_w else 0.0
                p_sf_adv_w = adv_w.semifinals if adv_w else 0.0
                r1_odds = RoundHostingOdds(
                    conditional=r1_cond if o.p_playoffs > 0 else None,
                    marginal=marginal_home_odds(r1_cond, o.p_playoffs),
                    conditional_weighted=r1_cond if (o.p_playoffs > 0 and adv_w) else None,
                    marginal_weighted=marginal_home_odds(r1_cond, o.p_playoffs) if adv_w else None,
                )
                r2_odds = RoundHostingOdds(conditional=None, marginal=None)
                qf_odds = RoundHostingOdds(
                    conditional=p_qf_cond / p_qf_adv if p_qf_adv > 0 else None,
                    marginal=p_qf_cond if p_qf_adv > 0 else 0.0,
                    conditional_weighted=p_qf_cond_w / p_qf_adv_w if p_qf_adv_w > 0 else None,
                    marginal_weighted=p_qf_cond_w if p_qf_adv_w > 0 else 0.0,
                )
                sf_odds = RoundHostingOdds(
                    conditional=p_sf_cond / p_sf_adv if p_sf_adv > 0 else None,
                    marginal=p_sf_cond if p_sf_adv > 0 else 0.0,
                    conditional_weighted=p_sf_cond_w / p_sf_adv_w if p_sf_adv_w > 0 else None,
                    marginal_weighted=p_sf_cond_w if p_sf_adv_w > 0 else 0.0,
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
# Participant reference resolution helpers
# ---------------------------------------------------------------------------


def _resolve_ref_to_school(
    ref: ParticipantRef,
    seed_to_school: dict[tuple[int, int], str],
) -> str | None:
    """Return the school name for *ref*, or ``None`` if the slot is not yet clinched."""
    if ref.school is not None:
        return ref.school
    return seed_to_school.get((ref.region, ref.seed))  # type: ignore[index]


def _resolve_ref_to_slot_id(ref: ParticipantRef) -> str | None:
    """Return a slot ID (e.g. ``"R1S2"``) for a slot ref; ``None`` for school-name refs."""
    if ref.region is not None and ref.seed is not None:
        return f"R{ref.region}S{ref.seed}"
    return None


# ---------------------------------------------------------------------------
# Playoff bracket state helpers
# ---------------------------------------------------------------------------


def _find_bracket_survivor(
    opp_slots: list[FormatSlot],
    min_wins: int,
    seed_to_school: dict[tuple[int, int], str],
    wins_by_team: dict[str, int],
) -> tuple[int, int] | None:
    """Return (region, seed) of the team from opp_slots with the most confirmed wins >= min_wins."""
    best: tuple[int, int] | None = None
    best_w = -1
    for slot in opp_slots:
        for r, s in ((slot.home_region, slot.home_seed), (slot.away_region, slot.away_seed)):
            school = seed_to_school.get((r, s))
            if school:
                w = wins_by_team.get(school, 0)
                if w >= min_wins and w > best_w:
                    best = (r, s)
                    best_w = w
    return best


def eliminated_team_hosting(
    region: int,
    seed: int,
    rounds_played: int,
    slots: list[FormatSlot],
    seed_to_school: dict[tuple[int, int], str],
    wins_by_team: dict[str, int],
    season: int,
    clazz: int,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Deterministic (r1, r2, qf, sf) hosting tuple for an eliminated team.

    Values: 1.0 = hosted, 0.0 = away, None = round not played.
    rounds_played = confirmed_wins + 1.
    """
    is_1a_4a = clazz <= 4
    half = half_slots_for_region(region, slots)
    idx = slot_index_for(region, seed, half)
    if idx is None:
        return (None, None, None, None)

    r1_home_us = was_home_r1(region, seed, half[idx])
    r1 = 1.0 if r1_home_us else 0.0
    if rounds_played < 2:
        return (r1, None, None, None)

    r2: float | None = None
    r2_home_us = False
    if is_1a_4a:
        r2_opp = _find_bracket_survivor(opponent_slots(idx, 1, half), 1, seed_to_school, wins_by_team)
        if r2_opp is None:
            return (r1, None, None, None)
        r2_result = r2_home_team(region, seed, r2_opp[0], r2_opp[1], season)
        r2_home_us = r2_result == (region, seed)
        r2 = 1.0 if r2_home_us else 0.0
        if rounds_played < 3:
            return (r1, r2, None, None)

    qf_offset = 2 if is_1a_4a else 1
    min_wins_qf = 2 if is_1a_4a else 1
    qf_opp = _find_bracket_survivor(opponent_slots(idx, qf_offset, half), min_wins_qf, seed_to_school, wins_by_team)
    if qf_opp is None:
        return (r1, r2, None, None)
    qf_r, qf_s = qf_opp
    qf_half = half_slots_for_region(qf_r, slots)
    qf_idx = slot_index_for(qf_r, qf_s, qf_half)
    r1_home_opp = was_home_r1(qf_r, qf_s, qf_half[qf_idx]) if qf_idx is not None else False
    r2_home_opp = False
    if is_1a_4a and qf_idx is not None:
        r2_opp_of_opp = _find_bracket_survivor(opponent_slots(qf_idx, 1, qf_half), 1, seed_to_school, wins_by_team)
        if r2_opp_of_opp:
            r2_home_opp = r2_home_team(qf_r, qf_s, r2_opp_of_opp[0], r2_opp_of_opp[1], season) == (qf_r, qf_s)
    qf_home = qf_home_team(region, seed, r1_home_us, r2_home_us, qf_r, qf_s, r1_home_opp, r2_home_opp, season)
    qf = 1.0 if qf_home == (region, seed) else 0.0
    rounds_for_sf = 4 if is_1a_4a else 3
    if rounds_played < rounds_for_sf:
        return (r1, r2, qf, None)

    sf_offset = 3 if is_1a_4a else 2
    min_wins_sf = 3 if is_1a_4a else 2
    sf_opp = _find_bracket_survivor(opponent_slots(idx, sf_offset, half), min_wins_sf, seed_to_school, wins_by_team)
    if sf_opp is None:
        return (r1, r2, qf, None)
    sf_home = sf_home_team(region, seed, sf_opp[0], sf_opp[1], season)
    sf = 1.0 if sf_home == (region, seed) else 0.0
    return (r1, r2, qf, sf)


@dataclass
class PlayoffBracketState:
    """Pre-computed bracket survivor state after applying submitted hypothetical results."""

    school_to_seed: dict[str, tuple[int, int]]
    wins_by_team: dict[str, int]
    all_region_odds: dict[int, dict[str, StandingsOdds]]
    cross_region_wins: dict[tuple[int, int], int]
    eliminated_hosting_map: dict[str, tuple]
    matchup_fn: MatchupProbFn | None
    confirmed_game_results: list[tuple[str, str, int | None, int | None]]
    round_ceiling: dict[tuple[int, int], str]


# Advancement round order for ceiling comparisons and _apply_round_ceilings.
_ROUND_ADVANCEMENT_ORDER = ["second_round", "quarterfinals", "semifinals", "finals", "champion"]
# Hosting round order (no 'finals'/'champion' — championship has its own node).
_ROUND_HOSTING_ORDER = ["first_round", "second_round", "quarterfinals", "semifinals"]


def _collect_possible_opponents(
    layout: BracketLayout,
    winner_region: int,
    winner_seed: int,
    round_name: str,
) -> set[tuple[int, int]]:
    """Return all R1 (region, seed) slots that could have been the opponent
    of (winner_region, winner_seed) in *round_name*.

    Used when a simulated result omits the loser: every team that could have
    faced the winner in the specified round is marked eliminated.
    """
    # 1. Find which half and R1 game index holds the winner.
    winner_half: str | None = None
    winner_r1_idx: int | None = None
    for ns, rounds in layout.halves.items():
        for idx, game in enumerate(rounds[0]):
            for p in (game.participant_a, game.participant_b):
                if p and p.region == winner_region and p.seed == winner_seed:
                    winner_half = ns
                    winner_r1_idx = idx
                    break
            if winner_r1_idx is not None:
                break
        if winner_half is not None:
            break

    if winner_half is None or winner_r1_idx is None:
        return set()

    rounds = layout.halves[winner_half]
    total_rounds = len(rounds)

    # 2. Map round_name → round_idx using the same logic as build_enriched_bracket_layout.
    round_name_to_idx: dict[str, int] = {"first_round": 0}
    for i in range(1, total_rounds):
        rfe = total_rounds - i
        name = {1: "semifinals", 2: "quarterfinals"}.get(rfe, "second_round")
        round_name_to_idx[name] = i

    target_idx = round_name_to_idx.get(round_name)
    if target_idx is None or target_idx == 0:
        return set()

    # 3. Walk round 1 → target_idx, tracking winner's game index at each round.
    winner_game_at: dict[int, int] = {0: winner_r1_idx}
    for ri in range(1, target_idx + 1):
        prev = winner_game_at[ri - 1]
        for gi, game in enumerate(rounds[ri]):
            if game.feeds_from and prev in game.feeds_from:
                winner_game_at[ri] = gi
                break
        if ri not in winner_game_at:
            return set()  # winner's path not found (shouldn't happen with valid input)

    # 4. Find the opponent branch index at the target round.
    target_game = rounds[target_idx][winner_game_at[target_idx]]
    assert target_game.feeds_from is not None
    winner_prev = winner_game_at[target_idx - 1]
    opp_prev_idx = next(f for f in target_game.feeds_from if f != winner_prev)

    # 5. Recursively collect all R1 seeds reachable from the opponent branch.
    def _r1_seeds(ri: int, gi: int) -> set[tuple[int, int]]:
        if ri == 0:
            g = rounds[0][gi]
            result: set[tuple[int, int]] = set()
            for p in (g.participant_a, g.participant_b):
                if p:
                    result.add((p.region, p.seed))
            return result
        g = rounds[ri][gi]
        out: set[tuple[int, int]] = set()
        for fi in (g.feeds_from or []):
            out |= _r1_seeds(ri - 1, fi)
        return out

    return _r1_seeds(target_idx - 1, opp_prev_idx)


def build_playoff_bracket_state(
    school_to_seed: dict[str, tuple[int, int]],
    db_wins: dict[str, int],
    db_losers: set[str],
    submitted_results: list[BracketGameResultRequest],
    elo_ratings: dict[str, float],
    slots: list[FormatSlot],
    season: int,
    clazz: int,
    layout: BracketLayout | None = None,
) -> PlayoffBracketState:
    """Derive bracket survivor state from clinched seeds, confirmed results, and hypothetical results.

    Pure function — all inputs are in-memory; no I/O.  Used by both the bracket
    and hosting simulate endpoints via ``_load_and_build_playoff_bracket_state``.

    Args:
        school_to_seed:    All clinched seeds: ``school → (region, seed)``.
        db_wins:           Confirmed playoff win counts from the DB.
        db_losers:         Schools confirmed eliminated by the DB (before hypothetical results).
        submitted_results: Hypothetical winner/loser pairs from the request body.
        elo_ratings:       Current Elo ratings keyed by school name.
        slots:             First-round playoff format slots for this class.
        season:            Football season year.
        clazz:             Classification (1–7).
    """
    wins_by_team: dict[str, int] = dict(db_wins)
    seed_to_school: dict[tuple[int, int], str] = {v: k for k, v in school_to_seed.items()}

    submitted_winners: set[str] = set()
    for r in submitted_results:
        w = _resolve_ref_to_school(r.winner, seed_to_school)
        if w is not None and w in school_to_seed:
            submitted_winners.add(w)

    losers_known: set[tuple[int, int]] = set()
    round_ceiling: dict[tuple[int, int], str] = {}
    for school in db_losers:
        if school not in submitted_winners:
            losers_known.add(school_to_seed[school])
    for r in submitted_results:
        w = _resolve_ref_to_school(r.winner, seed_to_school)
        if w is not None and w in school_to_seed:
            wins_by_team[w] = wins_by_team.get(w, 0) + 1
        if r.loser is not None:
            ll = _resolve_ref_to_school(r.loser, seed_to_school)
            if ll is not None and ll in school_to_seed:
                losers_known.add(school_to_seed[ll])
        elif r.round is not None and w is not None and w in school_to_seed and layout is not None:
            winner_region, winner_seed = school_to_seed[w]
            for opp in _collect_possible_opponents(layout, winner_region, winner_seed, r.round):
                # Keep the more-restrictive (earlier) ceiling if already set.
                if opp in round_ceiling:
                    existing_idx = _ROUND_ADVANCEMENT_ORDER.index(round_ceiling[opp]) \
                        if round_ceiling[opp] in _ROUND_ADVANCEMENT_ORDER else len(_ROUND_ADVANCEMENT_ORDER)
                    new_idx = _ROUND_ADVANCEMENT_ORDER.index(r.round) \
                        if r.round in _ROUND_ADVANCEMENT_ORDER else len(_ROUND_ADVANCEMENT_ORDER)
                    if new_idx < existing_idx:
                        round_ceiling[opp] = r.round
                else:
                    round_ceiling[opp] = r.round

    all_region_odds: dict[int, dict[str, StandingsOdds]] = {}
    for school, (reg, seed) in school_to_seed.items():
        is_loser = (reg, seed) in losers_known
        so = StandingsOdds(
            school=school,
            p1=1.0 if seed == 1 else 0.0,
            p2=1.0 if seed == 2 else 0.0,
            p3=1.0 if seed == 3 else 0.0,
            p4=1.0 if seed == 4 else 0.0,
            p_playoffs=0.0 if is_loser else 1.0,
            final_playoffs=0.0 if is_loser else 1.0,
            clinched=True,
            eliminated=is_loser,
        )
        all_region_odds.setdefault(reg, {})[school] = so

    cross_region_wins: dict[tuple[int, int], int] = {
        school_to_seed[school]: wins
        for school, wins in wins_by_team.items()
        if school in school_to_seed
    }
    seed_to_school_map = {v: k for k, v in school_to_seed.items()}
    eliminated_hosting_map: dict[str, tuple] = {
        school: eliminated_team_hosting(
            reg, seed, wins_by_team.get(school, 0) + 1,
            slots, seed_to_school_map, wins_by_team, season, clazz,
        )
        for school, (reg, seed) in school_to_seed.items()
        if (reg, seed) in losers_known
    }
    matchup_fn = make_matchup_prob_fn(elo_ratings, all_region_odds, EloConfig()) if elo_ratings else None
    return PlayoffBracketState(
        school_to_seed=school_to_seed,
        wins_by_team=wins_by_team,
        all_region_odds=all_region_odds,
        cross_region_wins=cross_region_wins,
        eliminated_hosting_map=eliminated_hosting_map,
        matchup_fn=matchup_fn,
        confirmed_game_results=[],
        round_ceiling=round_ceiling,
    )


async def _load_elo_ratings(conn, season: int, as_of: date) -> dict[str, float]:
    """Return the most-recent Elo rating per school as of *as_of*."""
    rows = await conn.execute(
        """
        SELECT DISTINCT ON (school) school, elo
        FROM team_ratings
        WHERE season = %s AND as_of_date <= %s
        ORDER BY school, as_of_date DESC
        """,
        (season, as_of),
    )
    return {r[0]: r[1] async for r in rows}


async def _load_and_build_playoff_bracket_state(
    conn,
    season: int,
    clazz: int,
    as_of: date,
    submitted_results: list[BracketGameResultRequest],
    elo_ratings: dict[str, float],
    slots: list[FormatSlot],
) -> PlayoffBracketState | None:
    """Load clinched seeds + confirmed bracket results from DB, then build PlayoffBracketState.

    Returns ``None`` when no clinched seeds exist (caller should raise 404).
    """
    seed_rows = await conn.execute(
        """
        SELECT DISTINCT ON (rs.school) rs.school, rs.region,
               CASE WHEN rs.odds_1st > 0.99 THEN 1
                    WHEN rs.odds_2nd > 0.99 THEN 2
                    WHEN rs.odds_3rd > 0.99 THEN 3
                    WHEN rs.odds_4th > 0.99 THEN 4
               END AS seed
        FROM region_standings rs
        WHERE rs.season = %s AND rs.class = %s
          AND rs.clinched = TRUE
          AND (rs.odds_1st > 0.99 OR rs.odds_2nd > 0.99 OR rs.odds_3rd > 0.99 OR rs.odds_4th > 0.99)
          AND rs.as_of_date <= %s
        ORDER BY rs.school, rs.as_of_date DESC
        """,
        (season, clazz, as_of),
    )
    school_to_seed: dict[str, tuple[int, int]] = {}
    async for school, reg, seed in seed_rows:
        if seed is not None:
            school_to_seed[school] = (reg, seed)

    if not school_to_seed:
        return None

    db_wins: dict[str, int] = {}
    db_losers: set[str] = set()
    db_rows = await conn.execute(
        """
        SELECT school,
               SUM(CASE WHEN points_for > points_against THEN 1 ELSE 0 END)::int AS wins,
               SUM(CASE WHEN points_for < points_against THEN 1 ELSE 0 END)::int AS losses
        FROM games_effective
        WHERE season = %s AND final = TRUE AND round IS NOT NULL
          AND date <= %s AND school = ANY(%s)
        GROUP BY school
        """,
        (season, as_of, list(school_to_seed.keys())),
    )
    async for school, wins, losses in db_rows:
        if wins:
            db_wins[school] = wins
        if losses:
            db_losers.add(school)

    game_rows = await conn.execute(
        """
        SELECT g.school, g.opponent, g.points_for, g.points_against
        FROM games_effective g
        WHERE g.season = %s AND g.final = TRUE AND g.round IS NOT NULL
          AND g.date <= %s AND g.school = ANY(%s)
          AND g.points_for > g.points_against
        """,
        (season, as_of, list(school_to_seed.keys())),
    )
    confirmed_game_results: list[tuple[str, str, int | None, int | None]] = []
    async for winner, loser, winner_score, loser_score in game_rows:
        confirmed_game_results.append((winner, loser, winner_score, loser_score))

    state = build_playoff_bracket_state(
        school_to_seed, db_wins, db_losers, submitted_results, elo_ratings, slots, season, clazz,
        layout=build_bracket_layout(slots),
    )
    state.confirmed_game_results = confirmed_game_results
    return state


# ---------------------------------------------------------------------------
# Response builders — bracket
# ---------------------------------------------------------------------------


def build_bracket_layout(slots: list[FormatSlot]) -> BracketLayout:
    """Build a UI-ready bracket tree from first-round format slots.

    Returns a ``BracketLayout`` with two halves ('N' and 'S').  Each half is a
    list of rounds; ``rounds[0]`` contains ``BracketGame`` leaf nodes (one per
    first-round format slot) with ``slot`` set and ``participant_a``/
    ``participant_b`` pre-populated with region and seed (school null).
    Subsequent rounds contain interior nodes with ``feeds_from`` referencing the
    two previous-round game indices whose winners meet there.  The last entry in
    each half's round list is the Semifinal.

    ``championship`` has ``feeds_from_halves: ["N", "S"]`` — the two Semifinal
    winners meet there.
    """
    halves: dict[str, list[list[BracketGame]]] = {}
    for ns in ("N", "S"):
        half = sorted([s for s in slots if s.north_south == ns], key=lambda s: s.slot)
        if not half:
            continue
        rounds: list[list[BracketGame]] = [
            [BracketGame(
                slot=s.slot,
                participant_a=BracketParticipant(region=s.home_region, seed=s.home_seed),
                participant_b=BracketParticipant(region=s.away_region, seed=s.away_seed),
                home_team=BracketParticipant(region=s.home_region, seed=s.home_seed),
            ) for s in half]
        ]
        while len(rounds[-1]) > 1:
            prev = rounds[-1]
            rounds.append([BracketGame(feeds_from=[i, i + 1]) for i in range(0, len(prev), 2)])
        halves[ns] = rounds
    return BracketLayout(halves=halves, championship=ChampionshipGame())


def build_enriched_bracket_layout(
    layout: BracketLayout,
    seed_to_school: dict[tuple[int, int], str] | None,
    confirmed_results: list[tuple[str, str, int | None, int | None]],
    simulated_results: list[tuple[str, str | None, int | None, int | None, str | None]],
    hosting_conditional: dict[str, dict[str, float | None]] | None = None,
) -> BracketLayout:
    """Enrich a ``BracketLayout`` with per-game participants and results.

    Each ``BracketGame`` node gains ``round``, ``participant_a``,
    ``participant_b``, ``home_school``, and ``result``.  Confirmed DB results
    take priority over simulated results for the same pair.

    ``participant_a`` is positional (format home slot on R1, feeds_from[0]
    winner on R2+), not a hosting indicator.  ``home_school`` is set when one
    participant's conditional hosting odds for the round are 1.0.

    Participants propagate round-by-round: R1 participants come from
    ``seed_to_school``; later-round participants are the winners of the
    ``feeds_from`` games in the previous round.  When ``seed_to_school`` is
    ``None`` (pre-playoff, no clinched seeds), all participants are ``None``.

    The championship node is similarly enriched from the two Semifinal winners.
    """
    def _make_participant(region: int, seed: int) -> BracketParticipant:
        school = seed_to_school.get((region, seed)) if seed_to_school else None
        return BracketParticipant(region=region, seed=seed, school=school)

    # Build results lookup keyed by the frozenset of the two schools.
    # Confirmed (DB) results are inserted first; simulated results only fill gaps.
    # winner_only holds simulated entries where the loser was unspecified; keyed
    # by (school, round_name) so the result only applies to the specific round.
    results_by_pair: dict[frozenset, BracketGameResult] = {}
    winner_only: dict[tuple[str, str], BracketGameResult] = {}
    for winner, loser, ws, ls in confirmed_results:
        key = frozenset((winner, loser))
        if key not in results_by_pair:
            results_by_pair[key] = BracketGameResult(
                winner=BracketParticipant(region=0, seed=0, school=winner),
                loser=BracketParticipant(region=0, seed=0, school=loser),
                winner_score=ws,
                loser_score=ls,
                simulated=False,
            )
    for winner, loser, ws, ls, rnd in simulated_results:
        if loser is None:
            wo_key = (winner, rnd or "")
            if wo_key not in winner_only:
                winner_only[wo_key] = BracketGameResult(
                    winner=BracketParticipant(region=0, seed=0, school=winner),
                    loser=None,
                    winner_score=ws,
                    loser_score=ls,
                    simulated=True,
                )
        else:
            key = frozenset((winner, loser))
            if key not in results_by_pair:
                results_by_pair[key] = BracketGameResult(
                    winner=BracketParticipant(region=0, seed=0, school=winner),
                    loser=BracketParticipant(region=0, seed=0, school=loser),
                    winner_score=ws,
                    loser_score=ls,
                    simulated=True,
                )

    def _find_result(
        home_p: BracketParticipant | None,
        away_p: BracketParticipant | None,
        round_name: str,
    ) -> BracketGameResult | None:
        # Pair-based lookup (both participants known).
        if home_p and away_p and home_p.school and away_p.school:
            raw = results_by_pair.get(frozenset((home_p.school, away_p.school)))
            if raw is not None:
                # Re-attach region/seed to winner and loser from the participants.
                if raw.winner.school == home_p.school:
                    w_p, l_p = home_p, away_p
                else:
                    w_p, l_p = away_p, home_p
                return BracketGameResult(
                    winner=w_p, loser=l_p,
                    winner_score=raw.winner_score, loser_score=raw.loser_score,
                    simulated=raw.simulated,
                )
        # Winner-only lookup: keyed by (school, round_name) so it only fires for
        # the specific round the result was submitted for.
        for p in (home_p, away_p):
            if p and p.school:
                raw = winner_only.get((p.school, round_name))
                if raw is not None:
                    return BracketGameResult(
                        winner=p, loser=None,
                        winner_score=raw.winner_score, loser_score=raw.loser_score,
                        simulated=raw.simulated,
                    )
        return None

    enriched_halves: dict[str, list[list[BracketGame]]] = {}
    half_sf_winners: dict[str, BracketParticipant | None] = {}

    for ns, rounds in layout.halves.items():
        total_rounds = len(rounds)
        # round_winners[i] = winner BracketParticipant from game i in that round (or None)
        prev_round_winners: list[BracketParticipant | None] = []
        enriched_rounds: list[list[BracketGame]] = []

        for round_idx, games in enumerate(rounds):
            if round_idx == 0:
                round_name = "first_round"
            else:
                rounds_from_end = total_rounds - round_idx
                round_name = {1: "semifinals", 2: "quarterfinals"}.get(
                    rounds_from_end, "second_round"
                )

            cur_round_winners: list[BracketParticipant | None] = []
            enriched_games: list[BracketGame] = []

            for game in games:
                if game.slot is not None:  # R1 leaf
                    assert game.participant_a is not None and game.participant_b is not None
                    p_a = _make_participant(game.participant_a.region, game.participant_a.seed)
                    p_b = _make_participant(game.participant_b.region, game.participant_b.seed)
                else:  # later-round interior node
                    assert game.feeds_from is not None
                    p_a = prev_round_winners[game.feeds_from[0]]
                    p_b = prev_round_winners[game.feeds_from[1]]

                result = _find_result(p_a, p_b, round_name)
                winner_p: BracketParticipant | None = None
                if result is not None:
                    winner_p = result.winner

                if game.slot is not None:  # R1: participant_a is always the format home
                    home_team: BracketParticipant | None = p_a
                else:
                    home_team = None
                    if hosting_conditional:
                        if p_a and p_a.school:
                            a_cond = (hosting_conditional.get(p_a.school) or {}).get(round_name)
                            if a_cond is not None and a_cond > 0.99:
                                home_team = p_a
                        if home_team is None and p_b and p_b.school:
                            b_cond = (hosting_conditional.get(p_b.school) or {}).get(round_name)
                            if b_cond is not None and b_cond > 0.99:
                                home_team = p_b

                enriched_games.append(BracketGame(
                    slot=game.slot, feeds_from=game.feeds_from,
                    round=round_name,
                    participant_a=p_a, participant_b=p_b,
                    home_team=home_team,
                    result=result,
                ))
                cur_round_winners.append(winner_p)

            enriched_rounds.append(enriched_games)
            prev_round_winners = cur_round_winners

        enriched_halves[ns] = enriched_rounds
        # SF winner is the single winner from the last round in this half
        half_sf_winners[ns] = prev_round_winners[0] if prev_round_winners else None

    north_p = half_sf_winners.get("N")
    south_p = half_sf_winners.get("S")
    championship_result = _find_result(north_p, south_p, "finals")
    championship = ChampionshipGame(
        north_participant=north_p,
        south_participant=south_p,
        result=championship_result,
    )

    return BracketLayout(halves=enriched_halves, championship=championship)


# Advancement fields that should be zeroed for rounds strictly after the ceiling.
_ADVANCEMENT_FIELDS_AFTER: dict[str, list[str]] = {
    "second_round": ["quarterfinals", "semifinals", "finals", "champion",
                     "quarterfinals_weighted", "semifinals_weighted", "finals_weighted", "champion_weighted"],
    "quarterfinals": ["semifinals", "finals", "champion",
                      "semifinals_weighted", "finals_weighted", "champion_weighted"],
    "semifinals": ["finals", "champion", "finals_weighted", "champion_weighted"],
    "finals": ["champion", "champion_weighted"],
}
# Hosting rounds that should be nulled/zeroed for rounds strictly after the ceiling.
_HOSTING_ROUNDS_AFTER: dict[str, list[str]] = {
    "second_round": ["quarterfinals", "semifinals"],
    "quarterfinals": ["semifinals"],
    "semifinals": [],
    "finals": [],
}


def _apply_round_ceilings(
    entries: list[TeamBracketEntry],
    round_ceiling: dict[tuple[int, int], str],
) -> list[TeamBracketEntry]:
    """Zero advancement/hosting odds beyond each team's ceiling round.

    Teams in *round_ceiling* are possible opponents of a winner-only simulated
    result; they participate normally up through their ceiling round and have
    zero odds beyond it.
    """
    if not round_ceiling:
        return entries

    result: list[TeamBracketEntry] = []
    for entry in entries:
        ceiling = round_ceiling.get((entry.region, entry.seed))
        if ceiling is None:
            result.append(entry)
            continue

        adv_fields = _ADVANCEMENT_FIELDS_AFTER.get(ceiling, [])
        hosting_rounds = _HOSTING_ROUNDS_AFTER.get(ceiling, [])

        new_entry = entry.model_copy(update=dict.fromkeys(adv_fields, 0.0))

        if new_entry.hosting and hosting_rounds:
            hosting_updates: dict[str, RoundHostingOdds] = {}
            for rnd in hosting_rounds:
                cur = getattr(new_entry.hosting, rnd, None)
                if cur is not None:
                    hosting_updates[rnd] = cur.model_copy(update={
                        "conditional": None,
                        "marginal": 0.0,
                        "conditional_weighted": None,
                        "marginal_weighted": 0.0,
                    })
            if hosting_updates:
                new_entry = new_entry.model_copy(
                    update={"hosting": new_entry.hosting.model_copy(update=hosting_updates)}
                )

        result.append(new_entry)
    return result


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
    odds_map_weighted: dict[str, BracketOdds] | None = None,
    hosting_by_slot: dict[str, BracketSlotHosting] | None = None,
    seed_to_school: dict[tuple[int, int], str] | None = None,
) -> list[TeamBracketEntry]:
    """Build ``TeamBracketEntry`` list from pre-computed bracket advancement odds.

    *odds_map* maps slot IDs (e.g. ``"R1S2"``) to ``BracketOdds``.  Slots absent
    from *odds_map* are skipped.  ``school`` is populated only when a team has
    clinched that seed position.  *seed_to_school* provides a fallback for
    eliminated teams whose ``by_region`` odds have been zeroed post-elimination.
    Used by both the snapshot path (via ``build_bracket_entries``) and the
    simulation path.
    """
    entries: list[TeamBracketEntry] = []
    for region_num, region_odds in sorted(by_region.items()):
        for seed in (1, 2, 3, 4):
            slot_id = f"R{region_num}S{seed}"
            bo = odds_map.get(slot_id)
            if bo is None:
                continue
            bo_w = odds_map_weighted.get(slot_id) if odds_map_weighted is not None else None
            school = clinched_school(region_odds, seed)
            if school is None and seed_to_school is not None:
                school = seed_to_school.get((region_num, seed))
            entries.append(
                TeamBracketEntry(
                    region=region_num,
                    seed=seed,
                    school=school,
                    second_round=bo.second_round,
                    quarterfinals=bo.quarterfinals,
                    semifinals=bo.semifinals,
                    finals=bo.finals,
                    champion=bo.champion,
                    second_round_weighted=bo_w.second_round if bo_w is not None else None,
                    quarterfinals_weighted=bo_w.quarterfinals if bo_w is not None else None,
                    semifinals_weighted=bo_w.semifinals if bo_w is not None else None,
                    finals_weighted=bo_w.finals if bo_w is not None else None,
                    champion_weighted=bo_w.champion if bo_w is not None else None,
                    hosting=hosting_by_slot.get(slot_id) if hosting_by_slot is not None else None,
                )
            )
    return entries


def _slot_odds_for_region(
    region_num: int,
    source_odds: dict[str, StandingsOdds] | None,
) -> dict[str, StandingsOdds]:
    """Build slot-ID-keyed StandingsOdds for one region.

    When *source_odds* is provided (simulate path with clinched schools), seed
    probs and eliminated status are inferred from each school's StandingsOdds.
    Otherwise (GET path), synthetic certainty odds are created for each seed slot.
    """
    slot_odds: dict[str, StandingsOdds] = {}
    if source_odds is not None:
        for o in source_odds.values():
            seed = next((s for s, p in ((1, o.p1), (2, o.p2), (3, o.p3), (4, o.p4)) if p > 0.5), None)
            if seed is not None:
                slot_id = f"R{region_num}S{seed}"
                slot_odds[slot_id] = StandingsOdds(
                    school=slot_id,
                    p1=o.p1, p2=o.p2, p3=o.p3, p4=o.p4,
                    p_playoffs=o.p_playoffs,
                    final_playoffs=o.p_playoffs,
                    clinched=True,
                    eliminated=o.eliminated,
                )
    else:
        for seed in (1, 2, 3, 4):
            slot_id = f"R{region_num}S{seed}"
            slot_odds[slot_id] = StandingsOdds(
                school=slot_id,
                p1=1.0 if seed == 1 else 0.0,
                p2=1.0 if seed == 2 else 0.0,
                p3=1.0 if seed == 3 else 0.0,
                p4=1.0 if seed == 4 else 0.0,
                p_playoffs=1.0,
                final_playoffs=1.0,
                clinched=True,
                eliminated=False,
            )
    return slot_odds


def _det_round_hosting(val: float | None) -> RoundHostingOdds:
    """Wrap a deterministic hosting value (1.0/0.0/None) as RoundHostingOdds."""
    return RoundHostingOdds(
        conditional=val,
        marginal=val if val is not None else 0.0,
        conditional_weighted=val,
        marginal_weighted=val if val is not None else 0.0,
    )


def _cond_round_odds(
    marginal: float,
    advancement: float,
    marginal_w: float | None,
    adv_w_val: float | None,
) -> RoundHostingOdds:
    """Build RoundHostingOdds from marginal + advancement for one round."""
    have_w = marginal_w is not None
    adv_w_pos = bool(adv_w_val and adv_w_val > 0)
    if have_w and adv_w_pos:
        marg_w_out: float | None = marginal_w
    elif have_w:
        marg_w_out = 0.0
    else:
        marg_w_out = None
    return RoundHostingOdds(
        conditional=marginal / advancement if advancement > 0 else None,
        marginal=marginal if advancement > 0 else 0.0,
        conditional_weighted=marginal_w / adv_w_val if (have_w and adv_w_pos) else None,  # type: ignore[operator]
        marginal_weighted=marg_w_out,
    )


def _hosting_for_slot(
    slot_id: str,
    region_num: int,
    seed: int,
    all_slot_odds: dict[int, dict[str, StandingsOdds]],
    slots: list[FormatSlot],
    season: int,
    is_1a_4a: bool,
    wins_by_slot: dict[str, int],
    cross_region_wins: dict[tuple[int, int], int] | None,
    adv: BracketOdds,
    adv_w: BracketOdds | None,
    eliminated_by_slot: dict[str, tuple] | None,
    win_prob_fn_weighted: MatchupProbFn | None,
) -> BracketSlotHosting:
    """Compute BracketSlotHosting for one (region, seed) slot."""
    slot_odds = all_slot_odds[region_num]
    null_r2 = RoundHostingOdds(conditional=None, marginal=None)

    if eliminated_by_slot and slot_id in eliminated_by_slot:
        r1_det, r2_det, qf_det, sf_det = eliminated_by_slot[slot_id]
        return BracketSlotHosting(
            first_round=_det_round_hosting(r1_det),
            second_round=_det_round_hosting(r2_det) if is_1a_4a else null_r2,
            quarterfinals=_det_round_hosting(qf_det),
            semifinals=_det_round_hosting(sf_det),
        )

    # R1: structural — home/away determined by bracket format
    half = half_slots_for_region(region_num, slots)
    idx = slot_index_for(region_num, seed, half)
    r1_cond = 1.0 if (idx is not None and was_home_r1(region_num, seed, half[idx])) else 0.0
    slot_o = slot_odds.get(slot_id)
    p_playoffs = slot_o.p_playoffs if slot_o is not None else 0.0
    r1_marg = r1_cond * p_playoffs
    r1_odds = RoundHostingOdds(
        conditional=r1_cond if p_playoffs > 0 else None,
        marginal=r1_marg,
        conditional_weighted=r1_cond if (p_playoffs > 0 and adv_w is not None) else None,
        marginal_weighted=r1_marg if adv_w is not None else None,
    )

    if is_1a_4a:
        r2_map = compute_second_round_home_odds(
            region_num, slot_odds, slots, season, wins_confirmed=wins_by_slot, all_region_odds=all_slot_odds
        )
        r2_marg = r2_map.get(slot_id, 0.0)
        r2_marg_w = compute_second_round_home_odds(
            region_num, slot_odds, slots, season,
            win_prob_fn=win_prob_fn_weighted, wins_confirmed=wins_by_slot, all_region_odds=all_slot_odds,
        ).get(slot_id, 0.0) if win_prob_fn_weighted is not None else None
        r2_odds = _cond_round_odds(r2_marg, adv.second_round, r2_marg_w, adv_w.second_round if adv_w else None)
    else:
        r2_odds = null_r2

    qf_map = compute_quarterfinal_home_odds(
        region_num, slot_odds, slots, season,
        wins_confirmed=wins_by_slot, all_region_odds=all_slot_odds, cross_region_wins=cross_region_wins,
    )
    qf_marg = qf_map.get(slot_id, 0.0)
    qf_marg_w = compute_quarterfinal_home_odds(
        region_num, slot_odds, slots, season,
        win_prob_fn=win_prob_fn_weighted, wins_confirmed=wins_by_slot,
        all_region_odds=all_slot_odds, cross_region_wins=cross_region_wins,
    ).get(slot_id, 0.0) if win_prob_fn_weighted is not None else None
    qf_odds = _cond_round_odds(qf_marg, adv.quarterfinals, qf_marg_w, adv_w.quarterfinals if adv_w else None)

    sf_map = compute_semifinal_home_odds(
        region_num, slot_odds, slots, season,
        wins_confirmed=wins_by_slot, all_region_odds=all_slot_odds, cross_region_wins=cross_region_wins,
    )
    sf_marg = sf_map.get(slot_id, 0.0)
    sf_marg_w = compute_semifinal_home_odds(
        region_num, slot_odds, slots, season,
        win_prob_fn=win_prob_fn_weighted, wins_confirmed=wins_by_slot,
        all_region_odds=all_slot_odds, cross_region_wins=cross_region_wins,
    ).get(slot_id, 0.0) if win_prob_fn_weighted is not None else None
    sf_odds = _cond_round_odds(sf_marg, adv.semifinals, sf_marg_w, adv_w.semifinals if adv_w else None)

    return BracketSlotHosting(
        first_round=r1_odds,
        second_round=r2_odds,
        quarterfinals=qf_odds,
        semifinals=sf_odds,
    )


def build_bracket_entries(
    by_region: dict[int, dict[str, StandingsOdds]],
    slots: list[FormatSlot],
    season: int | None = None,
    clazz: int | None = None,
    win_prob_fn_weighted: MatchupProbFn | None = None,
    wins_by_team: dict[str, int] | None = None,
    all_region_odds: dict[int, dict[str, StandingsOdds]] | None = None,
    cross_region_wins: dict[tuple[int, int], int] | None = None,
    eliminated_hosting: dict[str, tuple] | None = None,
    wins_by_slot: dict[str, int] | None = None,
    school_to_seed: dict[str, tuple[int, int]] | None = None,
) -> list[TeamBracketEntry]:
    """Build ``TeamBracketEntry`` list with advancement and hosting odds per bracket slot.

    Each (region, seed) slot is keyed by a synthetic slot ID (e.g. ``"R1S2"``).
    Advancement odds are computed structurally (50/50 matchups) and, when
    *win_prob_fn_weighted* is supplied, also Elo-weighted.  Hosting odds follow
    the same MHSAA rules used by the hosting endpoints.

    GET path: pass *by_region* only; all slots are treated as certainties.
    Simulate path (playoff mode): also pass *all_region_odds* (real school names, clinched),
    *wins_by_team* (school → confirmed wins), *cross_region_wins*, and
    *eliminated_hosting* (school → (r1,r2,qf,sf) deterministic tuple).
    Simulate path (pre-clinching mode): pass *wins_by_slot* (slot ID → confirmed wins)
    directly; school→slot mapping is not available so *wins_by_team* is not used.

    When *season* or *clazz* is ``None``, hosting computation is skipped and
    ``hosting`` is ``None`` on every entry.
    """
    is_1a_4a = clazz is not None and clazz <= 4
    compute_hosting = season is not None and clazz is not None
    seed_to_school: dict[tuple[int, int], str] | None = (
        {(r, s): sch for sch, (r, s) in school_to_seed.items()} if school_to_seed else None
    )

    # Build slot-ID-keyed odds and wins for all regions in one pass
    all_slot_odds: dict[int, dict[str, StandingsOdds]] = {}
    _wins_by_slot: dict[str, int] = {}
    school_to_slot: dict[str, str] = {}

    for region_num in sorted(by_region):
        source = all_region_odds.get(region_num) if all_region_odds is not None else None
        slot_odds = _slot_odds_for_region(region_num, source)
        all_slot_odds[region_num] = slot_odds

        if wins_by_team and source is not None:
            for school, o in source.items():
                seed = next((s for s, p in ((1, o.p1), (2, o.p2), (3, o.p3), (4, o.p4)) if p > 0.5), None)
                if seed is not None:
                    sid = f"R{region_num}S{seed}"
                    school_to_slot[school] = sid
                    if school in wins_by_team:
                        _wins_by_slot[sid] = wins_by_team[school]

    # Merge in directly-supplied slot wins (pre-clinching mode)
    if wins_by_slot:
        for sid, w in wins_by_slot.items():
            if sid not in _wins_by_slot:
                _wins_by_slot[sid] = w

    # Map eliminated_hosting (school-name keys) → slot IDs
    eliminated_by_slot: dict[str, tuple] | None = None
    if eliminated_hosting and school_to_slot:
        eliminated_by_slot = {
            school_to_slot[school]: tup
            for school, tup in eliminated_hosting.items()
            if school in school_to_slot
        }

    # Compute advancement odds for all regions
    all_odds: dict[str, BracketOdds] = {}
    all_odds_w: dict[str, BracketOdds] = {}
    for region_num, slot_odds in all_slot_odds.items():
        all_odds.update(
            compute_bracket_advancement_odds(region_num, slot_odds, slots, wins_confirmed=_wins_by_slot)
        )
        if win_prob_fn_weighted is not None:
            all_odds_w.update(
                compute_bracket_advancement_odds(
                    region_num, slot_odds, slots,
                    win_prob_fn=win_prob_fn_weighted, wins_confirmed=_wins_by_slot,
                )
            )

    # Compute hosting odds per slot and build entries
    hosting_by_slot: dict[str, BracketSlotHosting] = {}
    if compute_hosting:
        for region_num, slot_odds in all_slot_odds.items():
            for seed in (1, 2, 3, 4):
                slot_id = f"R{region_num}S{seed}"
                adv = all_odds.get(slot_id)
                if adv is None:
                    continue
                adv_w = all_odds_w.get(slot_id) if win_prob_fn_weighted is not None else None
                hosting_by_slot[slot_id] = _hosting_for_slot(
                    slot_id, region_num, seed, all_slot_odds, slots,
                    season, is_1a_4a, _wins_by_slot, cross_region_wins,  # type: ignore[arg-type]
                    adv, adv_w, eliminated_by_slot, win_prob_fn_weighted,
                )

    return build_bracket_entries_from_odds_map(
        by_region, all_odds,
        odds_map_weighted=all_odds_w if win_prob_fn_weighted is not None else None,
        hosting_by_slot=hosting_by_slot if compute_hosting else None,
        seed_to_school=seed_to_school,
    )
