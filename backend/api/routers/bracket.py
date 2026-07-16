"""Bracket advancement odds endpoints."""

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request

from backend.api.db import get_conn
from backend.api.limiter import limiter
from backend.api.models.requests import SimulateBracketRequest
from backend.api.models.responses import BracketResponse
from backend.helpers.api_helpers import (
    _load_and_build_playoff_bracket_state,
    _load_elo_ratings,
    _resolve_ref_to_school,
    _resolve_ref_to_slot_id,
    build_bracket_entries,
    build_bracket_layout,
    build_enriched_bracket_layout,
)
from backend.helpers.data_classes import FormatSlot, MatchupProbFn, StandingsOdds
from backend.helpers.win_probability import EloConfig, make_matchup_prob_fn

router = APIRouter(prefix="/api/v1", tags=["bracket"])

SeasonQ = Annotated[int, Query(ge=1980, le=2040)]
ClassQ = Annotated[int, Query(alias="class", ge=1, le=7)]
_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


def _today() -> date:
    """Return today's date (injectable seam for tests)."""
    return datetime.now().date()


async def _load_format_slots(conn, season: int, clazz: int) -> list[FormatSlot]:
    """Return all playoff format slots for *clazz* in *season*."""
    rows = await conn.execute(
        """
        SELECT pfs.slot, pfs.home_region, pfs.home_seed,
               pfs.away_region, pfs.away_seed, pfs.north_south
        FROM playoff_format_slots pfs
        JOIN playoff_formats pf ON pfs.format_id = pf.id
        WHERE pf.season = %s AND pf.class = %s
        ORDER BY pfs.slot
        """,
        (season, clazz),
    )
    return [
        FormatSlot(slot=r[0], home_region=r[1], home_seed=r[2], away_region=r[3], away_seed=r[4], north_south=r[5])
        async for r in rows
    ]


async def _load_all_region_odds(conn, season: int, clazz: int, as_of: date) -> dict[int, dict[str, StandingsOdds]]:
    """Return {region: {school: StandingsOdds}} for all regions in *clazz*."""
    rows = await conn.execute(
        """
        SELECT DISTINCT ON (school)
            school, region, odds_1st, odds_2nd, odds_3rd, odds_4th,
            odds_playoffs, clinched, eliminated
        FROM region_standings
        WHERE season = %s AND class = %s AND as_of_date <= %s
        ORDER BY school, as_of_date DESC
        """,
        (season, clazz, as_of),
    )
    by_region: dict[int, dict[str, StandingsOdds]] = {}
    async for r in rows:
        school, region = r[0], r[1]
        by_region.setdefault(region, {})[school] = StandingsOdds(
            school=school,
            p1=r[2],
            p2=r[3],
            p3=r[4],
            p4=r[5],
            p_playoffs=r[6],
            final_playoffs=r[6],
            clinched=r[7],
            eliminated=r[8],
        )
    return by_region


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
    exist for the season.  ``hosting`` contains conditional and marginal hosting odds
    per round; ``hosting.second_round`` is ``null`` for 5A–7A (no second round).
    """
    as_of = date or _today()
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
        seed_to_school = {(r, s): sch for sch, (r, s) in state.school_to_seed.items()}
        hosting_conditional = {
            e.school: {
                "first_round": e.hosting.first_round.conditional,
                "second_round": e.hosting.second_round.conditional if e.hosting.second_round else None,
                "quarterfinals": e.hosting.quarterfinals.conditional,
                "semifinals": e.hosting.semifinals.conditional,
            }
            for e in entries if e.school and e.hosting
        }
        bracket_layout = build_enriched_bracket_layout(
            build_bracket_layout(slots), seed_to_school,
            state.confirmed_game_results, simulated_results=[],
            hosting_conditional=hosting_conditional,
        )
    else:
        matchup_fn = make_matchup_prob_fn(elo_ratings, by_region, EloConfig()) if elo_ratings else None
        entries = build_bracket_entries(
            by_region, slots,
            season=season, clazz=class_,
            win_prob_fn_weighted=matchup_fn,
        )
        bracket_layout = build_bracket_layout(slots)
    return BracketResponse(
        season=season, class_=class_,
        bracket_layout=bracket_layout,
        teams=entries,
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
    as_of = date or _today()
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
        seed_to_school = {(r, s): sch for sch, (r, s) in state.school_to_seed.items()}
        simulated: list[tuple[str, str | None, int | None, int | None]] = []
        for r in body.results:
            w = _resolve_ref_to_school(r.winner, seed_to_school)
            if r.loser is not None:
                lo = _resolve_ref_to_school(r.loser, seed_to_school)
                if w is not None and lo is not None:
                    simulated.append((w, lo, r.winner_score or 12, r.loser_score or 0))
            else:
                if w is not None:
                    simulated.append((w, None, r.winner_score or 12, r.loser_score or 0))
        hosting_conditional = {
            e.school: {
                "first_round": e.hosting.first_round.conditional,
                "second_round": e.hosting.second_round.conditional if e.hosting.second_round else None,
                "quarterfinals": e.hosting.quarterfinals.conditional,
                "semifinals": e.hosting.semifinals.conditional,
            }
            for e in entries if e.school and e.hosting
        }
        bracket_layout = build_enriched_bracket_layout(
            build_bracket_layout(slots), seed_to_school,
            state.confirmed_game_results, simulated,
            hosting_conditional=hosting_conditional,
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

    return BracketResponse(
        season=season, class_=class_,
        bracket_layout=bracket_layout,
        teams=entries,
    )
