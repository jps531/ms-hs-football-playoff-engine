"""How a region's ties are broken, step by step, in words.

``explain_tiebreaks`` (finished standings) and ``explain_scenario_ties`` (one result of the games still
to play) run the tiebreaker (``resolve_standings_for_mask``) with a ``trace_collector`` and write
each step it applied, in the order it applied them, from what that step compared: head-to-head
results among the tied teams, results against the highest-placed teams outside the tie, the capped
point differentials, points allowed, and a coin flip when all of those leave teams level. Nothing
is reconstructed: a step that didn't decide anything is stated as not separating the teams, and a
tie partly broken starts over at head-to-head among the teams still level, as the rules require.

Once every region game is played, every step is stated with its actual numbers. With games left,
a game still to play is stated as the result being explained ("Raleigh beats Magee"), and a tie is
followed only as far as the steps who wins decides: the first step that turns on a margin or a
score still to come (point differential or points allowed counting a game still to play, or
results against the teams above when their order turns on margins) ends it with what decides it
from there. So the words for a tie are the same whatever the margins: they depend only on who wins.
"""

from dataclasses import dataclass

from backend.helpers.data_classes import CompletedGame, RemainingGame
from backend.helpers.data_helpers import normalize_pair
from backend.helpers.tiebreakers import TiebreakStep, resolve_standings_for_mask, standings_from_mask, tie_bucket_groups


def _ordinal(n: int) -> str:
    """1 → '1st', 2 → '2nd', 11 → '11th', 22 → '22nd'."""
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _join(names) -> str:
    """'A', 'A and B', 'A, B and C'."""
    names = list(names)
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _record(wl: dict) -> str:
    """'3-2', or '3-1-1' with a tie."""
    return f"{wl['w']}-{wl['l']}-{wl['t']}" if wl["t"] else f"{wl['w']}-{wl['l']}"


def _signed(n: int) -> str:
    """'+5', '0', '−3' (a true minus sign)."""
    return f"+{n}" if n > 0 else ("0" if n == 0 else f"−{-n}")


@dataclass(frozen=True)
class TieExplanation:
    """How one tie in finished standings was broken.

    ``teams`` are the tied teams in the order they finished; ``records`` their region records, in
    the same order (level in the standings means the same winning percentage and losses, so a team
    with a game unplayed can be level at 1-0 with one at 2-0; empty for a result of games still to
    play, where the explanation doesn't state them); ``places`` the places they took; ``steps`` one
    sentence per tiebreaker step applied, in order; ``coin_flip`` the groups still level after every
    step, whose order a coin flip decides (their places in ``places`` are the places between them,
    not a decided order); ``undecided`` the groups the explanation stops at because what decides
    them isn't settled (a margin, a score, or the order of teams above them), with no order stated.
    """

    teams: tuple[str, ...]
    records: tuple[str, ...]
    places: tuple[int, ...]
    steps: tuple[str, ...]
    coin_flip: tuple[tuple[str, ...], ...] = ()
    undecided: tuple[tuple[str, ...], ...] = ()


class _Region:
    """The region's results (played, and the ones being explained), for wording the steps."""

    def __init__(
        self,
        completed: list[CompletedGame],
        wl: dict,
        place: dict[str, int],
        remaining: list[RemainingGame] = (),
        mask: int = 0,
        scenario: bool = False,
    ):
        self.games = {(g.a, g.b): g for g in completed}
        # A game still to play: who wins it in the result being explained (+1 a wins, -1 b).
        self.to_play = {(g.a, g.b): (1 if mask >> i & 1 else -1) for i, g in enumerate(remaining)}
        self.wl = wl
        self.place = place
        self.scenario = scenario

    def game(self, team: str, opp: str) -> tuple[int, int | None, int | None] | None:
        """(result, points for, points against) of *team*'s game against *opp*, result 1/0/-1, the
        points None for a game still to play; None if they don't play."""
        a, b, _ = normalize_pair(team, opp)
        g = self.games.get((a, b))
        if g is None:
            res = self.to_play.get((a, b))
            if res is None:
                return None
            return (res if team == a else -res), None, None
        if team == a:
            return g.res_a, g.pa_b, g.pa_a
        return -g.res_a, g.pa_a, g.pa_b

    def played(self, team: str, opp: str) -> bool:
        """True when *team* and *opp*'s game is played (not one still to play, or none)."""
        return normalize_pair(team, opp)[:2] in self.games

    def score(self, team: str, opp: str) -> str:
        """' 21-14' from *team*'s side, or '' when the score isn't recorded or the game is still to play."""
        r = self.game(team, opp)
        if r is None or r[1] is None or (r[1] == 0 and r[2] == 0):
            return ""
        return f" {r[1]}-{r[2]}"

    def result(self, x: str, y: str) -> str:
        """'Raleigh beat Magee 21-14' (played), 'Raleigh beats Magee' (still to play), 'X and Y tied 14-14'."""
        r = self.game(x, y)
        if r[0] == 0:
            return f"{x} and {y} tied{self.score(x, y)}"
        w, lo = (x, y) if r[0] == 1 else (y, x)
        return f"{w} beat {lo}{self.score(w, lo)}" if self.played(w, lo) else f"{w} beats {lo}"

    def record_vs(self, team: str, opps) -> str:
        """*team*'s record against *opps* (games played only)."""
        w = l = t = 0
        for o in opps:
            r = self.game(team, o)
            if r is None:
                continue
            w, l, t = w + (r[0] == 1), l + (r[0] == -1), t + (r[0] == 0)
        return f"{w}-{l}-{t}" if t else f"{w}-{l}"

    def outside_label(self, group, below: int) -> str:
        """'Madison Central (1st)', or 'Florence and Lanier (both 3-2, counted together)'.

        For a result of games still to play, a team's place is said only when it's above the tie
        (*below* is the tie's best place), and records not at all: those are what the explanation
        holds for whatever happens in the games it doesn't depend on.
        """
        if len(group) == 1:
            if self.scenario and self.place[group[0]] > below:
                return group[0]
            return f"{group[0]} ({_ordinal(self.place[group[0]])})"
        if self.scenario:
            return f"{_join(group)} (level on record, counted together)"
        records = {_record(self.wl[t]) for t in group}
        if len(records) == 1:
            each = "both" if len(group) == 2 else "all"
            return f"{_join(group)} ({each} {records.pop()}, counted together)"
        return f"{_join(group)} (level in the standings, counted together)"

    def place_phrase(self, part) -> str:
        """'Oak Grove finishes 2nd', or 'Brandon and Pearl are still tied'."""
        if len(part) == 1:
            return f"{part[0]} finishes {_ordinal(self.place[part[0]])}"
        return f"{_join(part)} are still tied"


def _outcome(step: TiebreakStep, region: _Region) -> str:
    """What the step decided: who it placed, who it left tied."""
    if len(step.parts) == 1:
        return "That doesn't separate them."
    return "; ".join(region.place_phrase(p) for p in step.parts) + "."


def _key(v):
    """Order a step 2/4 entry the tiebreaker's way: higher is better, no game worst."""
    return v if v is not None else float("-inf")


def _against(step: TiebreakStep, region: _Region, describe) -> str:
    """Steps 2 and 4: the teams outside the tie, best first, down to the first one that separates them.

    The step goes down the outside teams one at a time and stops at the first where the tied teams
    differ (teams still level there start over at step 1), so that's as far as this goes.
    """
    clauses = []
    best = min(region.place[t] for t in step.group)
    for i, og in enumerate(step.outside):
        clauses.append(f"against {region.outside_label(og, best)}: {describe(list(step.group), og, i)}")
        if len({_key(step.values[t][i]) for t in step.group}) > 1:
            break
    return "; ".join(clauses)


def _results_vs(step: TiebreakStep, region: _Region):
    """Step 2's wording for one outside group: who won, lost, tied or didn't play."""

    def describe(shown, og, i):
        if len(og) == 1:
            past = {2: "won", 1: "tied", 0: "lost", None: "didn't play them"}
            now = {2: "win", 1: "tie", 0: "lose", None: "don't play them"}
            by: dict = {}
            for t in shown:
                by.setdefault(step.values[t][i], []).append(t)
            order = sorted(by, key=_key, reverse=True)
            # A game still to play reads as this result ("Petal wins"); several teams take "win".
            clauses = []
            for v in order:
                names = by[v]
                if v is None or all(region.played(t, og[0]) for t in names):
                    clauses.append(f"{_join(names)} {past[v]}")
                else:
                    verb = now[v] if len(names) > 1 else {"win": "wins", "tie": "ties", "lose": "loses"}[now[v]]
                    clauses.append(f"{_join(names)} {verb}")
            return ", ".join(clauses)
        return ", ".join(
            f"{t} {region.record_vs(t, og)}" if step.values[t][i] is not None else f"{t} didn't play them"
            for t in sorted(shown, key=lambda t: _key(step.values[t][i]), reverse=True)
        )

    return describe


def _pd_vs(step: TiebreakStep):
    """Step 4's wording for one outside group: each team's capped point differential."""

    def describe(shown, _og, i):
        return ", ".join(
            f"{t} {_signed(step.values[t][i])}" if step.values[t][i] is not None else f"{t} didn't play them"
            for t in sorted(shown, key=lambda t: _key(step.values[t][i]), reverse=True)
        )

    return describe


def _head_to_head(step: TiebreakStep, region: _Region) -> str:
    """Step 1's facts: the game between two teams, or each team's record against the others (and,
    for three teams, the three games)."""
    g = list(step.group)
    if len(g) == 2:
        a, b = g
        if region.game(a, b) is None:
            return "they didn't play each other"
        return region.result(a, b)
    ranked = sorted(g, key=lambda t: -step.values[t])
    records = ", ".join(f"{t} {region.record_vs(t, [o for o in g if o != t])}" for t in ranked)
    pairs = [(x, y) for i, x in enumerate(g) for y in g[i + 1 :]]
    if len(pairs) > 3:
        return records
    games = [f"{x} and {y} didn't play" if region.game(x, y) is None else region.result(x, y) for x, y in pairs]
    return f"{records} ({'; '.join(games)})"


def _sentence(step: TiebreakStep, region: _Region, restart: bool) -> str:
    """One step as a sentence: what it compares, the actual numbers, and what it decided."""
    names = _join(step.group)
    lead = ""
    if step.step == 1:
        if len(step.group) == 2:
            how = f"{names} start over at head-to-head" if restart else "Head-to-head"
        else:
            how = f"{names} start over with their head-to-head records" if restart else "Head-to-head records"
            how += " against each other"
        facts = f"{how}: {_head_to_head(step, region)}."
    elif step.step == 2:
        if len(step.parts) == 1:
            facts = "Results against the highest-placed region teams outside the tie: the same for each."
        else:
            facts = (
                "Results against the highest-placed region teams outside the tie, working down: "
                f"{_against(step, region, _results_vs(step, region))}."
            )
    elif step.step == 3:
        values = ", ".join(f"{t} {_signed(step.values[t])}" for t in sorted(step.group, key=lambda t: -step.values[t]))
        facts = f"Point differential in their games against each other, capped at 12 a game: {values}."
    elif step.step == 4:
        if len(step.parts) == 1:
            facts = (
                "Point differential against the highest-placed region teams outside the tie, capped at 12 a game: "
                "the same for each."
            )
        else:
            facts = (
                "Point differential against the highest-placed region teams outside the tie, capped at 12 a game, "
                f"working down: {_against(step, region, _pd_vs(step))}."
            )
    elif step.step == 5:
        values = ", ".join(f"{t} {step.values[t]}" for t in sorted(step.group, key=lambda t: step.values[t]))
        facts = f"Fewest points allowed in all region games: {values}."
    else:
        places = _join(_ordinal(p) for p in sorted(region.place[t] for t in step.group))
        return f"{lead}{names} are level on every tiebreaker, so a coin flip decides their order for {places}."
    return f"{lead}{facts} {_outcome(step, region)}"


def _unsettled_outside(step: TiebreakStep, unsettled: dict[str, str]) -> str | None:
    """Why steps 2 and 4 can't be stated here, if they can't: the teams above the tie, whose order they
    go down, include some whose order isn't settled (*unsettled*: team -> what settles it)."""
    for og in step.outside:
        if len(og) == 1 and og[0] in unsettled:
            return unsettled[og[0]]
    return None


def _stop(step: TiebreakStep, region: _Region, unsettled: dict[str, str], to_play: set, in_play: set) -> str | None:
    """The sentence ending a tie at *step*, when that step turns on something not known yet; else None.

    Step 3 counts a game among the tied teams, step 4 one against the teams outside the tie, and step 5
    every region game: a game still to play makes them turn on its margin or score. Steps 2 and 4 go
    down the teams above the tie in order, which a margin, a score or a coin flip may still settle.
    """
    names = _join(step.group)
    group = set(step.group)
    if step.step in (2, 4):
        why = _unsettled_outside(step, unsettled)
        if why:
            what = "results" if step.step == 2 else "point differential"
            return (
                f"{names} are still level, so it goes to their {what} against the region teams above them, "
                f"in order, and {why}."
            )
    left = sum(frozenset((x, y)) in to_play for x in group for y in group if x < y)
    if step.step == 3 and left:
        which = "a game still to play: its margin decides" if left == 1 else "games still to play: their margins decide"
        return (
            f"{names} are still level, so it goes to point differential in their games against each other "
            f"(capped at 12 a game), which counts {which} it from here."
        )
    if step.step == 4:
        outside = {t for og in step.outside for t in og}
        if any(frozenset((x, y)) in to_play for x in group for y in outside):
            return (
                f"{names} are still level, so it goes to point differential against the region teams outside the "
                "tie (capped at 12 a game), which counts a game still to play: the margins decide it from here."
            )
    if step.step == 5 and group & in_play:
        return (
            f"{names} are still level, so it goes to fewest points allowed in all region games, which turns on "
            "the scores of games still to play."
        )
    return None


def _explain(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    mask: int,
    margins: dict,
    scenario: bool,
    base_margin_default: int = 7,
    pa_win: int = 14,
) -> tuple[list[str], list[tuple[list[str], TieExplanation]]]:
    """The tiebreaker's order for one result, and each tie (by its teams, best first) explained."""
    trace: list[TiebreakStep] = []
    order = resolve_standings_for_mask(
        teams, completed, remaining, mask, margins, base_margin_default, pa_win, trace_collector=trace
    )
    wl = standings_from_mask(teams, completed, remaining, mask, pa_win, margins, base_margin_default)
    place = {t: i + 1 for i, t in enumerate(order)}
    region = _Region(completed, wl, place, remaining, mask, scenario)
    to_play = {frozenset((g.a, g.b)) for g in remaining}
    in_play = {t for g in remaining for t in (g.a, g.b)}
    # Teams placed in an order not settled yet (team -> what settles it), as ties are broken best first.
    unsettled: dict[str, str] = {}

    ties = []
    for bucket in tie_bucket_groups(teams, wl):
        if len(bucket) < 2:
            continue
        members = set(bucket)
        sentences, ended = [], []
        for k, s in enumerate(t for t in trace if set(t.group) <= members):
            if any(set(s.group) <= e for e in ended):
                continue
            stop = _stop(s, region, unsettled, to_play, in_play)
            if stop:
                sentences.append(stop)
                ended.append(set(s.group))
                settles = "their order turns on the margins of games still to play"
                if s.step == 5:
                    settles = "their order turns on the scores of games still to play"
                unsettled.update(dict.fromkeys(s.group, settles))
                continue
            # A step 1 on fewer teams than the whole tie is a restart among the teams still level.
            restart = s.step == 1 and k > 0 and set(s.group) < members
            sentences.append(_sentence(s, region, restart))
            if s.step == 6:
                unsettled.update(dict.fromkeys(s.group, "a coin flip decides their order"))
        finished = tuple(sorted(bucket, key=place.get))
        ties.append(
            (
                bucket,
                TieExplanation(
                    teams=finished,
                    records=() if scenario else tuple(_record(wl[t]) for t in finished),
                    places=tuple(place[t] for t in finished),
                    steps=tuple(sentences),
                    coin_flip=tuple(
                        t.group
                        for t in trace
                        if t.step == 6 and set(t.group) <= members and not any(set(t.group) <= e for e in ended)
                    ),
                    undecided=tuple(tuple(sorted(e)) for e in ended),
                ),
            )
        )
    return order, ties


def explain_tiebreaks(teams: list[str], completed: list[CompletedGame]) -> tuple[list[str], list[TieExplanation]]:
    """Every tie in a finished region's standings, and how the tiebreaker broke it.

    Args:
        teams: The region's teams.
        completed: Every region game, played (``CompletedGame``s, one per pair).

    Returns:
        ``(order, ties)``: the standings order the tiebreaker gives (a coin-flip group in
        alphabetical order, standing in for the flip), and one ``TieExplanation`` per group of
        teams level on region record, best first. No ties, no explanations.
    """
    order, ties = _explain(teams, completed, [], 0, {}, scenario=False)
    return order, [t for _, t in ties]


def explain_scenario_ties(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    mask: int,
    margins: dict,
    playoff_seeds: int = 4,
    base_margin_default: int = 7,
    pa_win: int = 14,
) -> list[TieExplanation]:
    """How each tie reaching the playoff places breaks for one result of the games still to play.

    *mask* gives the winners (bit i set: ``remaining[i].a`` wins) and *margins* their margins; the
    explanation depends only on the winners (see the module docstring), so any margins give the
    same words. Ties wholly below the playoff places aren't explained.
    """
    _, ties = _explain(teams, completed, remaining, mask, margins, True, base_margin_default, pa_win)
    return [t for _, t in ties if t.places[0] <= playoff_seeds]
