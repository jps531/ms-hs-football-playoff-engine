"""Bracket advancement odds endpoints."""

from datetime import date
from datetime import date as _date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request

from backend.api.db import get_conn
from backend.api.limiter import limiter
from backend.api.models.requests import SimulateBracketRequest
from backend.api.models.responses import BracketResponse, SlotOutlookResponse, TeamBracketEntry
from backend.helpers.api_helpers import (
    _apply_round_ceilings,
    _candidate_seeds_by_region,
    _compute_seed_atoms_if_pre_playoff,
    _load_all_region_odds,
    _load_and_build_playoff_bracket_state,
    _load_elo_ratings,
    _load_format_slots,
    _resolve_ref_to_school,
    _resolve_ref_to_slot_id,
    _resolve_slot_group,
    build_bracket_entries,
    build_bracket_layout,
    build_enriched_bracket_layout,
    build_slot_outlook_teams,
    clinched_school,
    load_championship_venue,
    load_home_venues,
    load_remaining_game_dates,
    today,
)
from backend.helpers.data_classes import MatchupProbFn
from backend.helpers.win_probability import EloConfig, make_matchup_prob_fn

router = APIRouter(prefix="/api/v1", tags=["bracket"])

SeasonQ = Annotated[int, Query(ge=1980, le=2040)]
ClassQ = Annotated[int, Query(alias="class", ge=1, le=7)]
RoundQ = Annotated[
    Literal["first_round", "second_round", "quarterfinals", "semifinals"],
    Query(),
]
IncludeConditionsQ = Annotated[bool, Query()]
_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


def _invert_school_to_seed(school_to_seed: dict[str, tuple[int, int]]) -> dict[tuple[int, int], str]:
    """Invert a school -> (region, seed) map into (region, seed) -> school."""
    return {(r, s): sch for sch, (r, s) in school_to_seed.items()}


def _build_p_host_given_reach_by_team(entries: list[TeamBracketEntry]) -> dict[str, dict[str, float | None]]:
    """Extract per-round p_host_given_reach for each clinched entry with hosting odds."""
    return {
        e.school: {
            "first_round": e.hosting.first_round.p_host_given_reach,
            "second_round": e.hosting.second_round.p_host_given_reach if e.hosting.second_round else None,
            "quarterfinals": e.hosting.quarterfinals.p_host_given_reach,
            "semifinals": e.hosting.semifinals.p_host_given_reach,
        }
        for e in entries if e.school and e.hosting
    }


@router.get("/bracket", responses=_404)
async def get_bracket(
    season: SeasonQ,
    class_: ClassQ,
    date: Annotated[date | None, Query()] = None,
) -> BracketResponse:
    """Return bracket advancement odds for all seed slots in *class_* for *season*.

    Each entry represents one (region, seed) slot.  ``school`` is set only when
    the team has clinched that seed position; otherwise it is null.

    Weighted fields use Elo-based win probabilities; ``null`` when no Elo ratings
    exist for the season.  ``hosting`` contains ``p_host_given_reach`` and
    ``p_host_overall`` hosting odds per round; ``hosting.second_round`` is
    ``null`` for 5A–7A (no second round).
    """
    as_of = date or today()
    async with get_conn() as conn:
        slots = await _load_format_slots(conn, season, class_)
        if not slots:
            raise HTTPException(status_code=404, detail=f"No playoff format for {class_}A season {season}")
        by_region = await _load_all_region_odds(conn, season, class_, as_of)
        if not by_region:
            raise HTTPException(status_code=404, detail=f"No standings data for {class_}A season {season}")
        elo_ratings = await _load_elo_ratings(conn, season, as_of)
        state = await _load_and_build_playoff_bracket_state(
            conn, season, class_, as_of, [], elo_ratings, slots
        )
        venue = await load_championship_venue(conn, season, class_)
        home_venues = await load_home_venues(conn) if state is not None else {}

    if state is not None:
        entries = build_bracket_entries(
            by_region, slots,
            season=season, clazz=class_,
            win_prob_fn_weighted=state.matchup_fn,
            wins_by_team=state.wins_by_team,
            all_region_odds=state.all_region_odds,
            cross_region_wins=state.cross_region_wins,
            eliminated_hosting=state.eliminated_hosting_map,
            school_to_seed=state.school_to_seed,
        )
        seed_to_school = _invert_school_to_seed(state.school_to_seed)
        p_host_given_reach_by_team = _build_p_host_given_reach_by_team(entries)
        bracket_layout = build_enriched_bracket_layout(
            build_bracket_layout(slots), seed_to_school,
            state.confirmed_game_results, simulated_results=[],
            p_host_given_reach_by_team=p_host_given_reach_by_team,
            game_venues=state.game_venues,
            home_venue_by_team=home_venues,
        )
    else:
        matchup_fn = make_matchup_prob_fn(elo_ratings, by_region, EloConfig()) if elo_ratings else None
        entries = build_bracket_entries(
            by_region, slots,
            season=season, clazz=class_,
            win_prob_fn_weighted=matchup_fn,
        )
        bracket_layout = build_bracket_layout(slots)
    bracket_layout.championship.venue = venue
    return BracketResponse(
        season=season, class_=class_,
        bracket_layout=bracket_layout,
        teams=entries,
    )


@router.get("/bracket/slots/{slot}", responses=_404)
async def get_bracket_slot(
    slot: Annotated[int, Path(ge=1)],
    season: SeasonQ,
    class_: ClassQ,
    round: RoundQ = "first_round",
    date: Annotated[date | None, Query()] = None,
    include_conditions: IncludeConditionsQ = False,
) -> SlotOutlookResponse:
    """Return every team still alive for one bracket slot's game, ranked by chance of reaching it.

    ``slot`` identifies a first-round slot from ``playoff_format_slots``.
    ``round`` (default ``first_round``) addresses the derived round-2+ game
    implied by the group of first-round slots feeding it; ``second_round`` is
    only valid for 1A-4A (5A-7A goes straight from First Round to Quarterfinals).

    Unlike ``GET /bracket``, which shows one occupant per (region, seed) slot,
    this returns every team still mathematically alive for the slot pre-clinch.
    ``p_host_overall`` is always ``p_reach * p_host_given_reach``.

    Pass ``include_conditions=true`` to populate each team's
    ``host_conditions`` (the conditions under which they'd host, given they
    reach the round) — mirroring ``/hosting``'s ``include_scenarios``, this is
    opt-in since it runs the same combinatorially-guarded scenario-atom
    computation, once per region feeding this slot. ``reach_conditions`` is
    always ``null`` for now — a separate, undesigned follow-up.
    """
    as_of = date or today()
    seed_atoms_by_region: dict[int, dict | None] = {}
    game_dates_by_region: dict[int, dict[tuple[str, str], _date | None]] = {}
    team_lookup: dict[tuple[int, int], str] = {}
    async with get_conn() as conn:
        slots = await _load_format_slots(conn, season, class_)
        if not slots:
            raise HTTPException(status_code=404, detail=f"No playoff format for {class_}A season {season}")
        by_region = await _load_all_region_odds(conn, season, class_, as_of)
        if not by_region:
            raise HTTPException(status_code=404, detail=f"No standings data for {class_}A season {season}")
        elo_ratings = await _load_elo_ratings(conn, season, as_of)
        state = await _load_and_build_playoff_bracket_state(
            conn, season, class_, as_of, [], elo_ratings, slots
        )

        if include_conditions:
            group_slots = _resolve_slot_group(slot, round, slots)
            if group_slots is not None:
                if round == "first_round":
                    seeds_by_region = {
                        group_slots[0].home_region: {group_slots[0].home_seed},
                        group_slots[0].away_region: {group_slots[0].away_seed},
                    }
                else:
                    seeds_by_region = _candidate_seeds_by_region(group_slots)
                for region, seeds in seeds_by_region.items():
                    seed_atoms, remaining = await _compute_seed_atoms_if_pre_playoff(
                        conn, season, class_, region, as_of
                    )
                    seed_atoms_by_region[region] = seed_atoms
                    game_dates_by_region[region] = (
                        await load_remaining_game_dates(conn, season, remaining) if seed_atoms is not None else {}
                    )
                    for seed in seeds:
                        occupant = clinched_school(by_region.get(region, {}), seed)
                        if occupant is not None:
                            team_lookup[(region, seed)] = occupant

    if state is not None:
        win_prob_fn_weighted = state.matchup_fn
        wins_confirmed = state.wins_by_team
        all_region_odds = state.all_region_odds
        cross_region_wins = state.cross_region_wins
    else:
        win_prob_fn_weighted = make_matchup_prob_fn(elo_ratings, by_region, EloConfig()) if elo_ratings else None
        wins_confirmed = None
        all_region_odds = None
        cross_region_wins = None

    teams = build_slot_outlook_teams(
        slot, round, by_region, slots, season,
        win_prob_fn_weighted=win_prob_fn_weighted,
        wins_confirmed=wins_confirmed,
        all_region_odds=all_region_odds,
        cross_region_wins=cross_region_wins,
        seed_atoms_by_region=seed_atoms_by_region if include_conditions else None,
        game_dates_by_region=game_dates_by_region if include_conditions else None,
        team_lookup=team_lookup if include_conditions else None,
    )
    if teams is None:
        raise HTTPException(
            status_code=404,
            detail=f"No slot {slot} for {class_}A season {season}, or no {round} for this class",
        )
    return SlotOutlookResponse(
        season=season, class_=class_, round=round, slot=slot, as_of_date=as_of, teams=teams,
    )


@router.post("/bracket/simulate", responses=_404)
@limiter.limit("10/minute")
async def simulate_bracket(
    request: Request,
    body: SimulateBracketRequest,
    season: SeasonQ,
    class_: ClassQ,
    date: Annotated[date | None, Query()] = None,
) -> BracketResponse:
    """Apply hypothetical bracket game results and return updated advancement odds.

    Participants are identified by school name, (region, seed) slot ref, or a mix.
    A plain string is shorthand for ``{"school": "Name"}`` and is backward-compatible.

    Works in two modes:
    - Playoff mode (seedings clinched): school names and slot refs both resolve to known teams.
    - Pre-clinching mode (no seedings yet): only slot refs are meaningful; school-name refs
      are silently skipped.
    """
    as_of = date or today()
    matchup_fn_pre: MatchupProbFn | None = None
    async with get_conn() as conn:
        slots = await _load_format_slots(conn, season, class_)
        if not slots:
            raise HTTPException(status_code=404, detail=f"No playoff format for {class_}A season {season}")
        elo_ratings = await _load_elo_ratings(conn, season, as_of)
        state = await _load_and_build_playoff_bracket_state(
            conn, season, class_, as_of, body.results, elo_ratings, slots
        )
        by_region = await _load_all_region_odds(conn, season, class_, as_of)
        if not by_region:
            raise HTTPException(
                status_code=404,
                detail=f"No standings data for {class_}A season {season}",
            )
        if state is None:
            matchup_fn_pre = make_matchup_prob_fn(elo_ratings, by_region, EloConfig()) if elo_ratings else None
        venue = await load_championship_venue(conn, season, class_)
        home_venues = await load_home_venues(conn) if state is not None else {}

    if state is not None:
        entries = build_bracket_entries(
            by_region, slots,
            season=season, clazz=class_,
            win_prob_fn_weighted=state.matchup_fn,
            wins_by_team=state.wins_by_team,
            all_region_odds=state.all_region_odds,
            cross_region_wins=state.cross_region_wins,
            eliminated_hosting=state.eliminated_hosting_map,
            school_to_seed=state.school_to_seed,
        )
        entries = _apply_round_ceilings(entries, state.round_ceiling)
        seed_to_school = _invert_school_to_seed(state.school_to_seed)
        simulated: list[tuple[str, str | None, int | None, int | None, str | None]] = []
        for r in body.results:
            w = _resolve_ref_to_school(r.winner, seed_to_school)
            if r.loser is not None:
                lo = _resolve_ref_to_school(r.loser, seed_to_school)
                if w is not None and lo is not None:
                    simulated.append((w, lo, r.winner_score or 12, r.loser_score or 0, None))
            else:
                if w is not None:
                    simulated.append((w, None, r.winner_score or 12, r.loser_score or 0, r.round))
        p_host_given_reach_by_team = _build_p_host_given_reach_by_team(entries)
        bracket_layout = build_enriched_bracket_layout(
            build_bracket_layout(slots), seed_to_school,
            state.confirmed_game_results, simulated,
            p_host_given_reach_by_team=p_host_given_reach_by_team,
            game_venues=state.game_venues,
            home_venue_by_team=home_venues,
        )
    else:
        slot_wins: dict[str, int] = {}
        for r in body.results:
            w_sid = _resolve_ref_to_slot_id(r.winner)
            if w_sid:
                slot_wins[w_sid] = slot_wins.get(w_sid, 0) + 1
        entries = build_bracket_entries(
            by_region, slots, season=season, clazz=class_,
            win_prob_fn_weighted=matchup_fn_pre, wins_by_slot=slot_wins,
        )
        bracket_layout = build_bracket_layout(slots)

    bracket_layout.championship.venue = venue
    return BracketResponse(
        season=season, class_=class_,
        bracket_layout=bracket_layout,
        teams=entries,
    )
