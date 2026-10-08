"""The one-sentence headline that leads a region's page.

Picks the single most interesting fact about a region's playoff race right now
and states it in plain English, e.g. "Taylorsville clinches the region with a
win over Mize — no help needed." The sentence is built only from data the
standings response already carries — per-team seeding odds, the
pre-computed, margin-verified key insights, and (with five or fewer games
left, where they're margin-accurate) each team's exact scenario paths — so it
never claims anything the scenario engine hasn't proven.

Precedence, most specific first:

1. Every playoff seed is locked: name the champion and the rest of the field.
2. The region title is still open: lead with the simplest proven way for a
   contender to clinch it, else say how many teams can still win it.
3. The title is decided: say so, then lead with the simplest proven way to
   clinch one of the remaining playoff spots, else name who's still chasing
   them.
"""

from typing import NamedTuple

from backend.api.models.responses import KeyInsightModel, TeamStandingsEntry
from backend.helpers.scenario_renderer import margin_phrase

_PLAYOFF_SEEDS = 4
# Odds are floats summed over enumerated outcomes; a certainty can land a hair
# above or below 1.0, so "locked" means within this tolerance of it.
_CERTAIN = 1 - 1e-9

# Scenario paths are margin-accurate only at R <= 5 (see SCENARIO_COMPUTATION.md);
# at R = 6 they're win/loss-only, so they can't be stated as guarantees.
_PATHS_MARGIN_ACCURATE_MAX_R = 5
_MAX_HEADLINE_CONDITIONS = 3

_NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


def _seed_prob(entry: TeamStandingsEntry, seed: int) -> float:
    """Return the team's probability of finishing at exactly *seed*."""
    return getattr(entry.odds, f"p{seed}")


def _locked_seed(entry: TeamStandingsEntry) -> int | None:
    """Return the seed this team has mathematically locked in, if any."""
    for seed in range(1, _PLAYOFF_SEEDS + 1):
        if _seed_prob(entry, seed) >= _CERTAIN:
            return seed
    return None


def _join_names(names: list[str]) -> str:
    """Join names newspaper-style: "A", "A and B", "A, B and C"."""
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _count(n: int) -> str:
    """Spell out small counts, as a story would."""
    return _NUMBER_WORDS.get(n, str(n))


def _record(entry: TeamStandingsEntry) -> str:
    """Region record as "W–L" (with "–T" only when the team has a tie)."""
    r = entry.record
    base = f"{r.region_wins}–{r.region_losses}"
    return f"{base}–{r.region_ties}" if r.region_ties else base


class _Result(NamedTuple):
    """One required game result: *winner* beats *loser* by a margin in [lo, hi)."""

    winner: str
    loser: str
    min_margin: int = 1
    max_margin: int | None = None


class _Clinch(NamedTuple):
    """A proven way for *team* to secure an outcome: all *results* happening."""

    team: str
    results: list[_Result]


def _insight_clinches(insights: list[KeyInsightModel], accept) -> list[_Clinch]:
    """Clinch candidates from margin-verified key insights."""
    return [
        _Clinch(i.team, [_Result(c.winner, c.loser, c.min_margin, c.max_margin) for c in i.conditions])
        for i in insights
        if i.conditions and accept(i)
    ]


def _path_clinches(teams: list[TeamStandingsEntry], outcome_type: str, seed: int | None) -> list[_Clinch]:
    """Clinch candidates from scenario paths that have exactly one way through.

    A single OR-group is both necessary and sufficient, so it reads as a
    plain "clinches with ..." statement. This covers teams the key insights
    skip, such as a title contender that has already clinched a playoff spot.
    """
    found = []
    for t in teams:
        for path in t.paths or []:
            if path.outcome.type != outcome_type or (seed is not None and path.outcome.value != seed):
                continue
            if len(path.conditions) != 1:
                continue
            group = path.conditions[0]
            if not group or len(group) > _MAX_HEADLINE_CONDITIONS:
                continue
            if any(c.type != "game_result" or c.school is None or c.opponent is None for c in group):
                continue
            found.append(
                _Clinch(t.school, [_Result(c.school, c.opponent, c.min_margin or 1, c.max_margin) for c in group])
            )
    return found


def _simplest(candidates: list[_Clinch], by_team: dict[str, TeamStandingsEntry], likelihood) -> _Clinch | None:
    """Pick the simplest clinch: fewest conditions, then the most likely team."""
    eligible = [c for c in candidates if c.team in by_team]
    if not eligible:
        return None
    return min(eligible, key=lambda c: (len(c.results), -likelihood(by_team[c.team])))


def _beats(result: _Result, also: bool = False) -> str:
    """Render one outside result, e.g. "Mize beats Raleigh by 8 or more"."""
    verb = "also beats" if also else "beats"
    return f"{result.winner} {verb} {result.loser}{margin_phrase(result.min_margin, result.max_margin)}"


def _phrase_with_help(clinch: _Clinch, achievement: str) -> str:
    """Render "<team> <achievement> ..." from a clinch's required results.

    The team's own wins read as "with a win over X"; results it needs from
    elsewhere read as "if Y (also) beats Z". A clinch that depends on nobody
    else's result earns the "no help needed" tag.
    """
    team = clinch.team
    own = [r for r in clinch.results if r.winner == team]
    others = [r for r in clinch.results if r.winner != team]
    phrase = f"{team} {achievement}"
    if own:
        wins = [f"{r.loser}{margin_phrase(r.min_margin, r.max_margin)}" for r in own]
        phrase += (" with a win" if len(own) == 1 else " with wins") + f" over {_join_names(wins)}"
        if others:
            phrase += " if " + _join_names([_beats(r, also=(i == 0)) for i, r in enumerate(others)])
        else:
            phrase += " \u2014 no help needed"
    else:
        phrase += " if " + _join_names([_beats(r) for r in others])
    return phrase


def build_region_headline(
    teams: list[TeamStandingsEntry],
    key_insights: list[KeyInsightModel] | None,
    remaining_games: int,
) -> str | None:
    """Return the headline sentence for a region, or ``None`` with no teams.

    Args:
        teams: Team entries in current standings order (leader first). Their
            ``paths`` are used when populated (``include_team_scenarios``).
        key_insights: The region's pre-computed key insights (``None`` when
            none were computed, e.g. too many games remain).
        remaining_games: Number of unplayed region games.
    """
    if not teams:
        return None
    insights = key_insights or []
    by_team = {t.school: t for t in teams}
    paths_usable = 0 < remaining_games <= _PATHS_MARGIN_ACCURATE_MAX_R

    holders: dict[int, str] = {}
    for entry in teams:
        seed = _locked_seed(entry)
        if seed is not None:
            holders[seed] = entry.school

    # 1. Field and seeding fully settled.
    if all(seed in holders for seed in range(1, _PLAYOFF_SEEDS + 1)):
        champion = holders[1]
        rest = _join_names([holders[s] for s in range(2, _PLAYOFF_SEEDS + 1)])
        verb = "won" if remaining_games == 0 else "has won"
        return f"{champion} {verb} the region, with {rest} joining it in the playoffs."

    # 2. Region title still open.
    if 1 not in holders:
        candidates = _insight_clinches(insights, lambda i: i.insight_type == "clinch_seed" and i.seed == 1)
        if paths_usable:
            candidates += _path_clinches(teams, "seed", 1)
        clinch = _simplest(candidates, by_team, likelihood=lambda e: e.odds.p1)
        if clinch is not None:
            return _phrase_with_help(clinch, "clinches the region") + "."
        contenders = [t for t in teams if t.odds.p1 > 0]
        leader = teams[0]
        if len(contenders) <= 1:
            return f"{leader.school} leads the region at {_record(leader)}."
        return (
            f"{_count(len(contenders)).capitalize()} teams can still win the region, "
            f"and {leader.school} leads at {_record(leader)}."
        )

    # 3. Title decided; the rest of the field (or just its seeding) isn't.
    champion = holders[1]
    clinched = [t for t in teams if t.clinched]
    open_spots = _PLAYOFF_SEEDS - len(clinched)
    if open_spots <= 0:
        return f"{champion} has the region won, and the playoff field is set with seeding still to decide."

    chasers = [t for t in teams if not t.clinched and not t.eliminated]
    candidates = _insight_clinches(insights, lambda i: i.insight_type in ("clinch_playoffs", "clinch_seed"))
    if paths_usable:
        candidates += _path_clinches(chasers, "playoffs", None)
    clinch = _simplest(candidates, {t.school: t for t in chasers}, likelihood=lambda e: e.odds.p_playoffs)
    spot_noun = "the last playoff spot" if open_spots == 1 else f"the last {_count(open_spots)} playoff spots"
    if clinch is not None:
        achievement = "clinches the last playoff spot" if open_spots == 1 else "clinches a playoff spot"
        return f"{champion} has the region won, and " + _phrase_with_help(clinch, achievement) + "."
    if len(chasers) <= 3:
        names = _join_names([t.school for t in chasers])
        verb = "is" if len(chasers) == 1 else "are"
        return f"{champion} has the region won, and {names} {verb} playing for {spot_noun}."
    return f"{champion} has the region won, and {_count(len(chasers))} teams are chasing {spot_noun}."
