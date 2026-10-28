"""How a region's ties are broken, step by step, in words.

``explain_tiebreaks`` (finished standings) and ``explain_scenario_ties`` (one result of the games still
to play) run the tiebreaker (``resolve_standings_for_mask``) with a ``trace_collector`` and write
each step it applied, in the order it applied them, from what that step compared: head-to-head
results among the tied teams, results against the highest-placed teams outside the tie, the capped
point differentials, points allowed, and a coin flip when all of those leave teams level. Nothing
is reconstructed: a step that didn't decide anything is stated as not separating the teams, and a
tie partly broken starts over at head-to-head among the teams still level, as the rules require.

Once every region game is played, every step is stated with its actual numbers. With games left,
a game still to play is stated as the result being explained ("Raleigh beats Magee"), and its
margin is known too: one explanation covers a set of results with the same winners in which the
tiebreaker takes the same steps to the same order, and a number that varies with the margins is
stated as the range it takes over them ("Taylorsville +1 to +11"). Point differential counting a
game still to play lists the games it adds up, that one with its margin ("Lumberton beats
Taylorsville by 12+, counted as 12"). Only fewest points allowed, which turns on the scores and not
just the margins, ends a tie with what decides it from there, as does a step going down the teams
above when their order is left to it or to a coin flip, and the first step counting a margin in a
tie the scenario itself leaves open (too many outcomes to list, each team's places given instead).
"""

from dataclasses import dataclass, field

from backend.helpers.data_classes import CompletedGame, RemainingGame
from backend.helpers.data_helpers import normalize_pair
from backend.helpers.engine_settings import PLAYOFF_SEEDS
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


@dataclass(frozen=True)
class _Span:
    """A number that varies over the results one explanation covers: the least and greatest it takes."""

    lo: int
    hi: int


def _signed(n) -> str:
    """'+5', '0', '−3' (a true minus sign); a _Span as '−11 to −1'."""
    if isinstance(n, _Span):
        return _signed(n.lo) if n.lo == n.hi else f"{_signed(n.lo)} to {_signed(n.hi)}"
    return f"+{n}" if n > 0 else ("0" if n == 0 else f"−{-n}")


def _count(n) -> str:
    """A capped margin as counted: '12', or a _Span as '1–11'."""
    if isinstance(n, _Span):
        return str(n.lo) if n.lo == n.hi else f"{n.lo}–{n.hi}"
    return str(n)


def _margin_words(lo: int, hi: int) -> str:
    """A winning margin range of a game still to play, as the scenario cards word it: ' by 12+'
    (12 counts as 12 or more), ' by exactly 5', ' by 1–11', '' for any margin."""
    if lo <= 1 and hi >= _CAP:
        return ""
    if hi >= _CAP:
        return f" by {lo}+"
    if lo == hi:
        return f" by exactly {lo}"
    return f" by {lo}–{hi}"


_CAP = 12  # point differential counts at most 12 a game; a margin of 12 stands for 12 or more


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
        margins: dict | None = None,
    ):
        self.games = {(g.a, g.b): g for g in completed}
        # A game still to play: who wins it in the result being explained (+1 a wins, -1 b).
        self.to_play = {(g.a, g.b): (1 if mask >> i & 1 else -1) for i, g in enumerate(remaining)}
        # Its winning margin over the results explained, (least, greatest), 12 meaning 12 or more.
        self.margins = margins or {}
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

    def counted(self, x: str, y: str) -> str:
        """How the game between *x* and *y* counts in point differential (capped at 12): 'Stringer beat
        Lumberton 46-20, counted as 12', 'Lumberton beats Taylorsville by 12+, counted as 12'."""
        a, b, _ = normalize_pair(x, y)
        g = self.games.get((a, b))
        if g is not None:
            return f"{self.result(x, y)}, counted as {min(abs(g.pd_a), _CAP)}"
        w, lo = (a, b) if self.to_play[(a, b)] == 1 else (b, a)
        least, most = self.margins.get((a, b), (1, _CAP))
        return f"{w} beats {lo}{_margin_words(least, most)}, counted as {_count(_Span(least, most))}"

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


def _ranked(step: TiebreakStep, teams) -> list[str]:
    """*teams* in the order *step* put them (its parts, best first), level teams as listed."""
    part = {t: i for i, p in enumerate(step.parts) for t in p}
    return sorted(teams, key=lambda t: part[t])


def _stop_at(step: TiebreakStep) -> int | None:
    """Steps 2 and 4: the index of the first outside group the tied teams differ against (where the
    step stops going down), None when they never do."""
    if getattr(step, "stop_at", -1) != -1:
        return step.stop_at
    for i in range(len(step.outside)):
        if len({_key(step.values[t][i]) for t in step.group}) > 1:
            return i
    return None


def _against(step: TiebreakStep, region: _Region, describe) -> str:
    """Steps 2 and 4: the teams outside the tie, best first, down to the first one that separates them.

    The step goes down the outside teams one at a time and stops at the first where the tied teams
    differ (teams still level there start over at step 1), so that's as far as this goes.
    """
    clauses = []
    best = min(region.place[t] for t in step.group)
    stop = _stop_at(step)
    for i, og in enumerate(step.outside):
        clauses.append(f"against {region.outside_label(og, best)}: {describe(list(step.group), og, i)}")
        if i == stop:
            break
    return "; ".join(clauses)


def _results_vs(step: TiebreakStep, region: _Region):
    """Step 2's wording for one outside group: who won, lost, tied or didn't play."""

    def describe(shown, og, i):
        """How each team in *shown* did against outside group *og* (the step's *i*-th): who won, tied, lost or didn't play them."""
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
        """Each team in *shown*'s capped point differential against the step's *i*-th outside group,
        best first (level until the group the step stops at, where its parts give the order)."""
        order = _ranked(step, shown) if i == _stop_at(step) else shown
        return ", ".join(
            f"{t} {_signed(step.values[t][i])}" if step.values[t][i] is not None else f"{t} didn't play them"
            for t in order
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
        values = ", ".join(f"{t} {_signed(step.values[t])}" for t in _ranked(step, step.group))
        facts = f"Point differential in their games against each other, capped at 12 a game: {values}"
        # Counting a game still to play, say what each game adds, so the numbers can be followed.
        g = list(step.group)
        pairs = [(x, y) for i, x in enumerate(g) for y in g[i + 1 :] if region.game(x, y) is not None]
        if any(not region.played(x, y) for x, y in pairs):
            facts += f" ({'; '.join(region.counted(x, y) for x, y in pairs)})"
        facts += "."
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


def _stop(
    step: TiebreakStep, region: _Region, unsettled: dict[str, str], in_play: set, to_play: set, left_open
) -> str | None:
    """The sentence ending a tie at *step*, when that step turns on something not known yet; else None.

    Margins are known (each explanation covers results with given margins), scores aren't: step 5
    counts points allowed in every region game, so a tied team still to play makes it turn on a score.
    Steps 2 and 4 go down the teams above the tie in order, which that step 5 or a coin flip may
    leave unsettled. A tie the scenario leaves open (*left_open*: it has too many outcomes to list,
    each team's places stated instead; True for every tie) ends at the first step counting a margin
    still to come.
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
    if left_open is True or any(group <= set(g) for g in left_open):
        left = sum(frozenset((x, y)) in to_play for x in group for y in group if x < y)
        if step.step == 3 and left:
            which = (
                "a game still to play: its margin decides" if left == 1 else "games still to play: their margins decide"
            )
            return (
                f"{names} are still level, so it goes to point differential in their games against each other "
                f"(capped at 12 a game), which counts {which} it from here."
            )
        outside = {t for og in step.outside for t in og}
        if step.step == 4 and any(frozenset((x, y)) in to_play for x in group for y in outside):
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
    spans = {pair: (m, m) for pair, m in margins.items()}
    return order, _explain_trace(teams, completed, remaining, mask, order, trace, spans, scenario, pa_win)


def _explain_trace(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    mask: int,
    order: list[str],
    trace: list,
    margins: dict,
    scenario: bool,
    pa_win: int = 14,
    left_open=(),
) -> list[tuple[list[str], TieExplanation]]:
    """Each tie (by its teams, best first) explained from the tiebreaker's *order* and *trace* for one
    set of winners; *margins* the winning margin of each game still to play as (least, greatest);
    *left_open* the ties the scenario leaves open (see ``_stop``)."""
    # Records don't depend on margins (only points allowed does, which isn't used here).
    wl = standings_from_mask(teams, completed, remaining, mask, pa_win, {}, 7)
    place = {t: i + 1 for i, t in enumerate(order)}
    region = _Region(completed, wl, place, remaining, mask, scenario, margins)
    in_play = {t for g in remaining for t in (g.a, g.b)}
    to_play = {frozenset((g.a, g.b)) for g in remaining}
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
            stop = _stop(s, region, unsettled, in_play, to_play, left_open)
            if stop:
                sentences.append(stop)
                ended.append(set(s.group))
                settles = "their order turns on the scores of games still to play"
                if s.step in (3, 4):
                    settles = "their order turns on the margins of games still to play"
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
    return ties


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


@dataclass(frozen=True)
class _MergedStep(TiebreakStep):
    """A step as taken over several results: values that vary as _Spans, and (steps 2 and 4) the
    outside group it stops at, which is the same for all of them."""

    stop_at: int | None = None


def _merge(a, b):
    """Two results' values for one entry, as one: equal stays as is, numbers that differ make a _Span."""
    if isinstance(a, list):
        return [_merge(x, y) for x, y in zip(a, b, strict=True)]
    if a == b and not isinstance(a, _Span) and not isinstance(b, _Span):
        return a
    if a is None or b is None:
        raise ValueError("a game played in one result and not in another")
    lo = min(a.lo if isinstance(a, _Span) else a, b.lo if isinstance(b, _Span) else b)
    hi = max(a.hi if isinstance(a, _Span) else a, b.hi if isinstance(b, _Span) else b)
    return _Span(lo, hi)


@dataclass
class ScenarioTrace:
    """The tiebreaker's run for one result of the games still to play: its order, the steps it took,
    and the margins (one per game still to play, in order). ``key`` is what the words depend on
    besides the numbers: results with the same winners and key are explained together."""

    order: list[str]
    trace: list
    margins: tuple[int, ...]
    key: tuple = field(init=False)

    def __post_init__(self):
        self.key = (
            tuple(self.order),
            tuple((s.step, s.group, s.parts, s.outside, _stop_at(s)) for s in self.trace),
        )


def scenario_trace(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    mask: int,
    margins: dict,
    base_margin_default: int = 7,
    pa_win: int = 14,
) -> ScenarioTrace:
    """The tiebreaker's run for one result: *mask* the winners (bit i set: ``remaining[i].a`` wins),
    *margins* their margins by (a, b)."""
    trace: list[TiebreakStep] = []
    order = resolve_standings_for_mask(
        teams, completed, remaining, mask, margins, base_margin_default, pa_win, trace_collector=trace
    )
    return ScenarioTrace(order, trace, tuple(margins.get((g.a, g.b), base_margin_default) for g in remaining))


def counts_a_margin(run: ScenarioTrace, remaining: list[RemainingGame]) -> bool:
    """True when a step of *run* counts the margin of a game still to play (point differential among
    the tied teams, or against the teams outside the tie), so its numbers depend on margins."""
    to_play = {frozenset((g.a, g.b)) for g in remaining}
    for s in run.trace:
        if s.step == 3 and any(frozenset((x, y)) in to_play for x in s.group for y in s.group if x < y):
            return True
        if s.step == 4 and any(frozenset((x, y)) in to_play for x in s.group for og in s.outside for y in og):
            return True
    return False


class MergedTrace:
    """Results with the same winners and the same ``ScenarioTrace.key``, gathered to be explained
    together: each number they compare as the range it takes over them, each margin likewise."""

    def __init__(self, first: ScenarioTrace):
        self.key = first.key
        self.order = first.order
        self.steps = list(first.trace)
        self.values = [s.values for s in first.trace]
        self.margins = [(m, m) for m in first.margins]
        # Values already taken in (most results repeat a few), so each is merged once.
        self._seen = {repr([s.values for s in first.trace])}

    def add(self, run: ScenarioTrace) -> None:
        """Take in one more result with the same winners and key."""
        if run.key != self.key:
            raise ValueError("results with different steps can't be explained together")
        self.margins = [(min(lo, m), max(hi, m)) for (lo, hi), m in zip(self.margins, run.margins, strict=True)]
        seen = repr([s.values for s in run.trace])
        if seen in self._seen:
            return
        self._seen.add(seen)
        for i, s in enumerate(run.trace):
            mine = self.values[i]
            self.values[i] = {t: _merge(mine[t], s.values[t]) for t in mine}

    def ties(
        self,
        teams: list[str],
        completed: list[CompletedGame],
        remaining: list[RemainingGame],
        mask: int,
        playoff_seeds: int = PLAYOFF_SEEDS,
        pa_win: int = 14,
        left_open=(),
    ) -> list[TieExplanation]:
        """How each tie reaching the playoff places breaks, over every result taken in; *left_open*
        the ties the scenario leaves open, which end at the first step counting a margin."""
        trace = [
            _MergedStep(s.step, s.group, s.parts, v, s.outside, _stop_at(s))
            for s, v in zip(self.steps, self.values, strict=True)
        ]
        margins = {(g.a, g.b): span for g, span in zip(remaining, self.margins, strict=True)}
        ties = _explain_trace(teams, completed, remaining, mask, self.order, trace, margins, True, pa_win, left_open)
        return [t for _, t in ties if t.places[0] <= playoff_seeds]


def explain_scenario_ties(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    mask: int,
    margins: dict,
    playoff_seeds: int = PLAYOFF_SEEDS,
    base_margin_default: int = 7,
    pa_win: int = 14,
) -> list[TieExplanation]:
    """How each tie reaching the playoff places breaks for one result of the games still to play.

    *mask* gives the winners (bit i set: ``remaining[i].a`` wins) and *margins* their margins, which
    the numbers are stated at. Ties wholly below the playoff places aren't explained. To explain
    several results together, gather their ``scenario_trace``s in a ``MergedTrace``.
    """
    run = scenario_trace(teams, completed, remaining, mask, margins, base_margin_default, pa_win)
    return MergedTrace(run).ties(teams, completed, remaining, mask, playoff_seeds, pa_win)
