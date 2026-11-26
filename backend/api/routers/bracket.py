"""Bracket advancement odds endpoints."""

from datetime import date
from datetime import date as _date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from backend.api.auth import require_owner
from backend.api.db import get_conn
from backend.api.limiter import limiter
from backend.api.models.requests import SimulateBracketRequest
from backend.api.models.responses import (
    BracketMatchupsResponse,
    BracketResponse,
    SlotOutlookResponse,
    TeamBracketEntry,
)
from backend.helpers.api_helpers import (
    _candidate_seeds_by_region,
    _compute_seed_atoms_if_pre_playoff,
    _load_all_region_odds,
    _load_playoff_bracket_state,
    _resolve_slot_group,
    as_standings_odds,
    build_bracket_layout,
    build_enriched_bracket_layout,
    build_simulated_bracket_results,
    build_slot_outlook_teams,
    class_bracket_entries,
    clinched_school,
    load_championship_venue,
    load_class_bracket_inputs,
    load_home_venues,
    load_remaining_game_dates,
    today,
    what_if_results,
)
from backend.helpers.bracket_home_odds import equal_matchup_prob
from backend.helpers.bracket_matchups import (
    bracket_outlook,
    forced_wins,
    merge_modes,
    pairs_for_regions,
    slot_playoff_odds,
)
from backend.helpers.data_classes import FormatSlot, StandingsOdds

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


def _seeds_by_region_for_slot(group_slots: list[FormatSlot], round: str) -> dict[int, set[int]]:
    """Return the candidate ``{region: {seed, ...}}`` map for a bracket slot group.

    For ``first_round``, exactly the two (region, seed) positions occupying the
    group's single slot (home and away). For later rounds, every seed that
    could reach the slot via any first-round matchup in the group (see
    ``_candidate_seeds_by_region``).
    """
    if round == "first_round":
        return {
            group_slots[0].home_region: {group_slots[0].home_seed},
            group_slots[0].away_region: {group_slots[0].away_seed},
        }
    return _candidate_seeds_by_region(group_slots)


@router.get("/bracket", responses=_404)
async def get_bracket(
    season: SeasonQ,
    class_: ClassQ,
    date: Annotated[date | None, Query()] = None,
) -> BracketResponse:
    """Return bracket advancement odds for all seed slots in *class_* for *season*.

    Each entry represents one (region, seed) slot.  ``school`` is set only when
    the team has clinched that seed position; otherwise it is null.  Every slot
    a team can still take is listed, clinched or not, with the odds of whoever
    holds it: the bracket's own figures (``slot_playoff_odds``, the recursion
    ``/bracket/matchups`` uses), so byes are known and played games fixed. A
    team's own odds are its seed odds times its slots', summed over the seeds:
    its ``bracket_odds`` in the region standings.

    Weighted fields use Elo-based win probabilities; ``null`` when no Elo ratings
    exist for the season.  ``hosting`` contains ``p_host_given_reach`` and
    ``p_host_overall`` hosting odds per round (the first round's given playing a
    first-round game, so a slot facing a bye has none); ``hosting.second_round``
    is ``null`` for 5A–7A (no second round).
    """
    as_of = date or today()
    async with get_conn() as conn:
        c = await load_class_bracket_inputs(conn, season, class_, as_of)
        by_region = await _load_all_region_odds(conn, season, class_, as_of)
        if not by_region:
            raise HTTPException(status_code=404, detail=f"No standings data for {class_}A season {season}")
        state = await _load_playoff_bracket_state(conn, season, class_, as_of)
        venue = await load_championship_venue(conn, season, class_)
        home_venues = await load_home_venues(conn) if state is not None else {}

    slots = c.slots
    tossup = slot_playoff_odds(slots, season, c.odds_t, equal_matchup_prob, c.results)
    projected = (
        slot_playoff_odds(slots, season, c.odds_w, c.matchup_fn, c.results) if c.matchup_fn is not None else None
    )
    seed_to_school = _invert_school_to_seed(state.school_to_seed) if state is not None else None
    entries = class_bracket_entries(by_region, tossup, projected, class_, seed_to_school)
    if state is not None:
        assert seed_to_school is not None
        p_host_given_reach_by_team = _build_p_host_given_reach_by_team(entries)
        bracket_layout = build_enriched_bracket_layout(
            build_bracket_layout(slots), seed_to_school,
            state.confirmed_game_results, simulated_results=[],
            p_host_given_reach_by_team=p_host_given_reach_by_team,
            game_venues=state.game_venues,
            home_venue_by_team=home_venues,
            byes=bye_positions(by_region, slots),
        )
    else:
        bracket_layout = build_bracket_layout(slots)
    bracket_layout.championship.venue = venue
    return BracketResponse(
        season=season, class_=class_,
        bracket_layout=bracket_layout,
        teams=entries,
    )


def bye_positions(by_region: dict[int, dict[str, StandingsOdds]], slots: list[FormatSlot]) -> set[tuple[int, int]]:
    """The first-round (region, seed) positions that are byes: a seed no team in its region can take while
    the region has teams (it has fewer teams than playoff seeds). The same rule as /bracket/matchups'
    ``bye``; a region without standings has no byes."""
    positions = {(s.home_region, s.home_seed) for s in slots} | {(s.away_region, s.away_seed) for s in slots}
    return {
        (region, seed)
        for region, seed in positions
        if (teams := by_region.get(region)) and not any(getattr(o, f"p{seed}", 0) > 0 for o in teams.values())
    }


async def matchups_outlook(conn, season: int, class_: int, as_of: date) -> tuple[date | None, list[dict]]:
    """The newest standings date, and every game of *class_*'s bracket as ``/bracket/matchups`` gives it.

    Also what a playoff score report is checked against (``submissions.submit_score``).

    Raises:
        HTTPException 404: no playoff format, or no standings, for the class and season.
    """
    c = await load_class_bracket_inputs(conn, season, class_, as_of)
    tossup = bracket_outlook(
        c.slots,
        season,
        c.odds_t,
        pairs_for_regions(c.odds_t, c.standings_dates, c.stored_t),
        equal_matchup_prob,
        c.results,
    )
    projected = None
    if c.matchup_fn is not None:
        projected = bracket_outlook(
            c.slots,
            season,
            c.odds_w,
            pairs_for_regions(c.odds_w, c.standings_dates, c.stored_w),
            c.matchup_fn,
            c.results,
        )
    return max(c.standings_dates.values()) if c.standings_dates else None, merge_modes(tossup, projected)


@router.get("/bracket/matchups", responses=_404)
async def get_bracket_matchups(
    season: SeasonQ,
    class_: ClassQ,
    date: Annotated[date | None, Query()] = None,
) -> BracketMatchupsResponse:
    """Who might play whom, and where, in every game of *class_*'s bracket.

    For each game: the teams that could fill each side with their chance of
    being there (each side sums to 1), and the likeliest specific matchups
    with the chance of that exact game and of side A hosting it. Pairings
    under 0.5% in both modes are combined in ``other``.

    Matchup odds come from the regions' joint seeding (``region_seed_pairs``)
    and the same position-level bracket model as ``/bracket``'s reach and
    hosting odds, so they add up to those numbers; they are never two teams'
    separate odds multiplied. Played games are fixed. ``*_weighted`` fields
    are Projected (Elo) odds, null when no ratings exist.
    """
    as_of = date or today()
    async with get_conn() as conn:
        as_of_date, games = await matchups_outlook(conn, season, class_, as_of)
    return BracketMatchupsResponse(season=season, class_=class_, as_of_date=as_of_date, games=games)


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
    The odds are the bracket's own for that game (``game_playoff_odds``, the
    recursion ``/bracket/matchups`` uses): played games are fixed, and a side
    facing a bye plays no first-round game. ``p_host_overall`` is always
    ``p_reach * p_host_given_reach``.

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
        c = await load_class_bracket_inputs(conn, season, class_, as_of)
        slots = c.slots
        by_region = await _load_all_region_odds(conn, season, class_, as_of)
        if not by_region:
            raise HTTPException(status_code=404, detail=f"No standings data for {class_}A season {season}")

        if include_conditions:
            group_slots = _resolve_slot_group(slot, round, slots)
            if group_slots is not None:
                seeds_by_region = _seeds_by_region_for_slot(group_slots, round)
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

    teams = build_slot_outlook_teams(
        slot, round, by_region, slots, season,
        win_prob_fn_weighted=c.matchup_fn,
        by_region_weighted=as_standings_odds(c.odds_w),
        results=c.results,
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


@router.post("/bracket/simulate", dependencies=[Depends(require_owner)], responses=_404)
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

    The odds are ``GET /bracket``'s, worked out with the results added (``forced_wins``): a
    result's winner wins that game, and both teams won every game before it to get there; a
    result with only a ``round`` has the winner win its game in that round, whoever it plays. A
    game already played keeps its real result. Every slot a team can still take
    is listed, clinched or not, and the Projected odds rate each slot by the teams that could
    take it (``projected_matchup_fn``).
    """
    as_of = date or today()
    async with get_conn() as conn:
        c = await load_class_bracket_inputs(conn, season, class_, as_of)
        slots = c.slots
        state = await _load_playoff_bracket_state(conn, season, class_, as_of)
        by_region = await _load_all_region_odds(conn, season, class_, as_of)
        if not by_region:
            raise HTTPException(
                status_code=404,
                detail=f"No standings data for {class_}A season {season}",
            )
        venue = await load_championship_venue(conn, season, class_)
        home_venues = await load_home_venues(conn) if state is not None else {}

    what_ifs = what_if_results(body.results, c.odds_t)
    forced = forced_wins(slots, what_ifs)
    tossup = slot_playoff_odds(slots, season, c.odds_t, equal_matchup_prob, c.results, forced)
    projected = (
        slot_playoff_odds(slots, season, c.odds_w, c.matchup_fn, c.results, forced) if c.matchup_fn is not None else None
    )
    seed_to_school = _invert_school_to_seed(state.school_to_seed) if state is not None else None
    entries = class_bracket_entries(by_region, tossup, projected, class_, seed_to_school)
    if state is not None:
        assert seed_to_school is not None
        simulated = build_simulated_bracket_results(body.results, seed_to_school)
        p_host_given_reach_by_team = _build_p_host_given_reach_by_team(entries)
        bracket_layout = build_enriched_bracket_layout(
            build_bracket_layout(slots), seed_to_school,
            state.confirmed_game_results, simulated,
            p_host_given_reach_by_team=p_host_given_reach_by_team,
            game_venues=state.game_venues,
            home_venue_by_team=home_venues,
            byes=bye_positions(by_region, slots),
        )
    else:
        bracket_layout = build_bracket_layout(slots)

    bracket_layout.championship.venue = venue
    return BracketResponse(
        season=season, class_=class_,
        bracket_layout=bracket_layout,
        teams=entries,
    )
