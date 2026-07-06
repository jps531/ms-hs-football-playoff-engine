"""Pure helpers for building API response objects and transforming request data.

All functions are free of database I/O.  They operate on in-memory data
(dataclass instances, plain tuples, Pydantic response models) and are designed
to be fully unit-testable without a running database or Prefect environment.
"""

from __future__ import annotations

from collections import defaultdict

from backend.api.models.responses import (
    BracketAdvancementOdds,
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
    marginal_home_odds,
)
from backend.helpers.data_classes import (
    AppliedGameResult,
    BracketOdds,
    BracketTeam,
    CompletedGame,
    FormatSlot,
    MatchupProbFn,
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
                p1=row[7], p2=row[8], p3=row[9], p4=row[10], p_playoffs=row[11],
                p1_weighted=row[16], p2_weighted=row[17], p3_weighted=row[18],
                p4_weighted=row[19], p_playoffs_weighted=row[20],
            )
            clinched, eliminated = row[12], row[13]
            coin_flip = row[14]
            bracket_odds = BracketAdvancementOdds(
                second_round=row[21], quarterfinals=row[22], semifinals=row[23],
                finals=row[24], champion=row[25],
                second_round_weighted=row[26], quarterfinals_weighted=row[27],
                semifinals_weighted=row[28], finals_weighted=row[29],
                champion_weighted=row[30],
            )
            home_game_odds = HomeGameOdds(
                first_round=row[31], second_round=row[32],
                quarterfinals=row[33], semifinals=row[34],
                first_round_weighted=row[35], second_round_weighted=row[36],
                quarterfinals_weighted=row[37], semifinals_weighted=row[38],
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
            p1=p1, p2=p2, p3=p3, p4=p4,
            p_playoffs=p_playoffs, final_playoffs=p_playoffs,
            clinched=False, eliminated=False,
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
        adv_odds = compute_bracket_advancement_odds(region, region_odds, slots, rounds_completed=rounds_completed, wins_confirmed=wins_confirmed)
        qf_home = compute_quarterfinal_home_odds(region, region_odds, slots, season, rounds_completed=rounds_completed, wins_confirmed=wins_confirmed, all_region_odds=all_region_odds, cross_region_wins=cross_region_wins)
        sf_home = compute_semifinal_home_odds(region, region_odds, slots, season, rounds_completed=rounds_completed, wins_confirmed=wins_confirmed, all_region_odds=all_region_odds, cross_region_wins=cross_region_wins)
        r2_home_dict = compute_second_round_home_odds(region, region_odds, slots, season, rounds_completed=rounds_completed, wins_confirmed=wins_confirmed) if is_1a_4a else {}
        r1_home_seeds = {s.home_seed for s in slots if s.home_region == region}

        if win_prob_fn_weighted is not None:
            rw = region_odds_weighted if region_odds_weighted is not None else region_odds
            adv_odds_w = compute_bracket_advancement_odds(region, rw, slots, win_prob_fn=win_prob_fn_weighted, rounds_completed=rounds_completed, wins_confirmed=wins_confirmed)
            qf_home_w = compute_quarterfinal_home_odds(region, rw, slots, season, win_prob_fn=win_prob_fn_weighted, rounds_completed=rounds_completed, wins_confirmed=wins_confirmed, all_region_odds=all_region_odds, cross_region_wins=cross_region_wins)
            sf_home_w = compute_semifinal_home_odds(region, rw, slots, season, win_prob_fn=win_prob_fn_weighted, rounds_completed=rounds_completed, wins_confirmed=wins_confirmed, all_region_odds=all_region_odds, cross_region_wins=cross_region_wins)
            r2_home_dict_w: dict[str, float] = compute_second_round_home_odds(region, rw, slots, season, win_prob_fn=win_prob_fn_weighted, rounds_completed=rounds_completed, wins_confirmed=wins_confirmed) if is_1a_4a else {}
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
