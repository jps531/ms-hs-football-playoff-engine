"""How a finished region's ties were broken, step by step, in words.

Once every region game is played, the standings are one outcome with real scores, so every
tiebreaker step can be stated with its actual numbers. ``explain_tiebreaks`` runs the tiebreaker
(``resolve_standings_for_mask``) with a ``trace_collector`` and writes each step it applied, in the
order it applied them, from what that step compared: head-to-head results among the tied teams,
results against the highest-placed teams outside the tie, the capped point differentials, points
allowed, and a coin flip when all of those leave teams level. Nothing is reconstructed: a step that
didn't decide anything is stated as not separating the teams, and a tie partly broken starts over at
head-to-head among the teams still level, as the rules require.

Only for finished standings: with games left to play, the margins and points allowed aren't known.
"""

from dataclasses import dataclass

from backend.helpers.data_classes import CompletedGame
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
    with a game unplayed can be level at 1-0 with one at 2-0); ``places`` the places they took; ``steps`` one sentence per tiebreaker step
    applied, in order; ``coin_flip`` the groups still level after every step, whose order a coin
    flip decides (their places in ``places`` are the places between them, not a decided order).
    """

    teams: tuple[str, ...]
    records: tuple[str, ...]
    places: tuple[int, ...]
    steps: tuple[str, ...]
    coin_flip: tuple[tuple[str, ...], ...] = ()


class _Region:
    """The finished region's results, for wording the steps."""

    def __init__(self, completed: list[CompletedGame], wl: dict, place: dict[str, int]):
        self.games = {(g.a, g.b): g for g in completed}
        self.wl = wl
        self.place = place

    def game(self, team: str, opp: str) -> tuple[int, int, int] | None:
        """(result, points for, points against) of *team*'s game against *opp*, result 1/0/-1; None if unplayed."""
        a, b, _ = normalize_pair(team, opp)
        g = self.games.get((a, b))
        if g is None:
            return None
        if team == a:
            return g.res_a, g.pa_b, g.pa_a
        return -g.res_a, g.pa_a, g.pa_b

    def score(self, team: str, opp: str) -> str:
        """' 21-14' from *team*'s side, or '' when the score isn't recorded."""
        r = self.game(team, opp)
        if r is None or (r[1] == 0 and r[2] == 0):
            return ""
        return f" {r[1]}-{r[2]}"

    def record_vs(self, team: str, opps) -> str:
        """*team*'s record against *opps* (games played only)."""
        w = l = t = 0
        for o in opps:
            r = self.game(team, o)
            if r is None:
                continue
            w, l, t = w + (r[0] == 1), l + (r[0] == -1), t + (r[0] == 0)
        return f"{w}-{l}-{t}" if t else f"{w}-{l}"

    def outside_label(self, group) -> str:
        """'Madison Central (1st)', or 'Florence and Lanier (both 3-2, counted together)'."""
        if len(group) == 1:
            return f"{group[0]} ({_ordinal(self.place[group[0]])})"
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
    for i, og in enumerate(step.outside):
        clauses.append(f"against {region.outside_label(og)}: {describe(list(step.group), og, i)}")
        if len({_key(step.values[t][i]) for t in step.group}) > 1:
            break
    return "; ".join(clauses)


def _results_vs(step: TiebreakStep, region: _Region):
    """Step 2's wording for one outside group: who won, lost, tied or didn't play."""

    def describe(shown, og, i):
        if len(og) == 1:
            words = {2: "won", 1: "tied", 0: "lost", None: "didn't play them"}
            by: dict = {}
            for t in shown:
                by.setdefault(step.values[t][i], []).append(t)
            order = sorted(by, key=_key, reverse=True)
            return ", ".join(f"{_join(by[v])} {words[v]}" for v in order)
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
        r = region.game(a, b)
        if r is None:
            return "they didn't play each other"
        if r[0] == 0:
            return f"{a} and {b} tied{region.score(a, b)}"
        winner, loser = (a, b) if r[0] == 1 else (b, a)
        return f"{winner} beat {loser}{region.score(winner, loser)}"
    ranked = sorted(g, key=lambda t: -step.values[t])
    records = ", ".join(f"{t} {region.record_vs(t, [o for o in g if o != t])}" for t in ranked)
    pairs = [(x, y) for i, x in enumerate(g) for y in g[i + 1 :]]
    if len(pairs) > 3:
        return records
    games = []
    for x, y in pairs:
        r = region.game(x, y)
        if r is None:
            games.append(f"{x} and {y} didn't play")
        elif r[0] == 0:
            games.append(f"{x} and {y} tied{region.score(x, y)}")
        else:
            w, lo = (x, y) if r[0] == 1 else (y, x)
            games.append(f"{w} beat {lo}{region.score(w, lo)}")
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
    trace: list[TiebreakStep] = []
    order = resolve_standings_for_mask(teams, completed, [], 0, {}, trace_collector=trace)
    wl = standings_from_mask(teams, completed, [], 0, 0, {})
    place = {t: i + 1 for i, t in enumerate(order)}
    region = _Region(completed, wl, place)

    ties = []
    for bucket in tie_bucket_groups(teams, wl):
        if len(bucket) < 2:
            continue
        members = set(bucket)
        steps = [s for s in trace if set(s.group) <= members]
        sentences = []
        for k, s in enumerate(steps):
            # A step 1 on fewer teams than the whole tie is a restart among the teams still level.
            restart = s.step == 1 and k > 0 and set(s.group) < members
            sentences.append(_sentence(s, region, restart))
        finished = tuple(sorted(bucket, key=place.get))
        ties.append(
            TieExplanation(
                teams=finished,
                records=tuple(_record(wl[t]) for t in finished),
                places=tuple(place[t] for t in finished),
                steps=tuple(sentences),
                coin_flip=tuple(s.group for s in steps if s.step == 6),
            )
        )
    return order, ties
