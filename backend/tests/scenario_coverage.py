"""Checks a region's complete scenarios against the tiebreaker itself.

The scenarios a region page lists (``enumerate_division_scenarios``) are meant
to cover every way the remaining games can go, each exactly once: for any set
of winners and margins, the scenarios whose conditions hold should all give the
seeding ``resolve_standings_for_mask`` gives. ``coverage_problems`` walks the
same outcome space the enumeration does (every winner mask, each margin 1-12,
12 standing for "12 or more") and reports where that fails: results no scenario
covers, and results whose scenarios give a different seeding.

A scenario's ``TiebreakDecision`` conditions match a result when the
tiebreaker makes those decisions for it; its ``open_groups`` (groups whose
order it leaves to the tiebreaker from a step on) must be groups the
tiebreaker really does take to that step (from step 3, part of one), and
their places are compared without an order; a team its ``open_places`` limits
to some seeds must be at one of them.

``team_path_problems`` and ``insight_problems`` check the per-team paths and
the key insights the same way, a team's place in a tie that fewest points
allowed or a coin flip decides counting as any of the tie's places.
"""

import random
from dataclasses import dataclass, field
from itertools import product

from backend.helpers.data_classes import TiebreakDecision
from backend.helpers.tiebreakers import resolve_standings_for_mask

MARGINS = range(1, 13)  # the enumeration's margin domain; 12 means 12+
PLAYOFF_SEEDS = 4  # seeds 1-4 are shown in order; the rest only as out


@dataclass
class CoverageReport:
    """Where a scenario list and the tiebreaker disagree, over the outcomes checked."""

    checked: int = 0
    uncovered: list = field(default_factory=list)  # (mask, margins, seeding): no scenario matches
    wrong: list = field(default_factory=list)  # (mask, margins, seeding, [labels], [their seedings])

    @property
    def ok(self) -> bool:
        """True when every outcome checked has a scenario, and every matching scenario agrees."""
        return not self.uncovered and not self.wrong

    def summary(self, remaining) -> str:
        """A few examples of each problem, readable in a test failure."""
        pairs = [(g.a, g.b) for g in remaining]

        def result(mask, margins):
            """One checked outcome in words: each remaining game's winner, loser and margin."""
            parts = []
            for i, (a, b) in enumerate(pairs):
                w, l = (a, b) if mask >> i & 1 else (b, a)
                parts.append(f"{w} over {l} by {margins[(a, b)]}")
            return "; ".join(parts)

        lines = [f"{self.checked} outcomes checked: {len(self.uncovered)} uncovered, {len(self.wrong)} wrong"]
        for mask, margins, seeding in self.uncovered[:3]:
            lines.append(f"  uncovered: {result(mask, margins)} -> {list(seeding)}")
        for mask, margins, seeding, labels, theirs in self.wrong[:3]:
            lines.append(f"  wrong: {result(mask, margins)} -> {list(seeding)}, but {labels} say {theirs}")
        return "\n".join(lines)


def _label(scenario: dict) -> str:
    """A scenario's label as the site shows it: its number and sub-label ("3b")."""
    return f"{scenario['scenario_num']}{scenario.get('sub_label') or ''}"


def _matches(scenario: dict, mask: int, margins: dict, remaining, decisions: set) -> bool:
    """True when the scenario's winners and conditions all hold for this outcome (*decisions*: the
    tiebreaker's, as ``TiebreakDecision``)."""
    index = {(g.a, g.b): i for i, g in enumerate(remaining)}
    for winner, loser in scenario.get("game_winners") or []:
        pair = (winner, loser) if (winner, loser) in index else (loser, winner)
        a_wins = bool(mask >> index[pair] & 1)
        if (pair[0] if a_wins else pair[1]) != winner:
            return False
    return any(
        all(
            c in decisions if isinstance(c, TiebreakDecision) else c.satisfied_by(mask, margins, remaining)
            for c in atom
        )
        for atom in scenario.get("alternatives") or [scenario.get("conditions_atom") or []]
    )


def _settled(seeding, flip_groups) -> tuple:
    """The seeding with each coin-flip group's places sorted, so any flip result compares equal."""
    out = list(seeding)
    for group in flip_groups:
        spots = sorted(i for i, t in enumerate(out) if t in group)
        for i, team in zip(spots, sorted(out[i] for i in spots), strict=True):
            out[i] = team
    return tuple(out)


def coverage_problems(
    teams, completed, remaining, scenarios, *, samples_per_mask: int | None = None, seed: int = 0
) -> CoverageReport:
    """Check *scenarios* against the tiebreaker over every winner mask and margin combination.

    With *samples_per_mask*, each mask checks that many random margin combinations instead of
    all 12**R (for regions with more games left than an exhaustive check can afford).
    """
    pairs = [(g.a, g.b) for g in remaining]
    rng = random.Random(seed)
    report = CoverageReport()
    for mask in range(1 << len(pairs)):
        if samples_per_mask is None:
            combos = product(MARGINS, repeat=len(pairs))
        else:
            combos = (tuple(rng.choice(MARGINS) for _ in pairs) for _ in range(samples_per_mask))
        for combo in combos:
            margins = dict(zip(pairs, combo, strict=True))
            flips: list = []
            raw: list = []
            truth = tuple(
                resolve_standings_for_mask(
                    teams, completed, remaining, mask, margins, coin_flip_collector=flips, decision_collector=raw
                )
            )
            decisions = {TiebreakDecision(step, group, parts) for step, group, parts in raw}
            reached = {(step, group) for step, group, _ in raw}
            reached |= {(6, group) for step, group, parts in raw if step == 5 and len(parts) == 1}
            report.checked += 1
            hits = [s for s in scenarios if _matches(s, mask, margins, remaining, decisions)]
            if not hits:
                report.uncovered.append((mask, margins, truth))
                continue

            def agrees(sc: dict) -> bool:
                """Its seeding is the tiebreaker's, and every group it leaves open really is open."""
                open_groups = [tuple(g) for _, g in sc.get("open_groups") or []]
                # A tie left from step 3 can be narrowed to the teams whose places vary (part of one
                # that reaches it); one left from step 5 or 6 is exactly a group still level there.
                for step, g in sc.get("open_groups") or []:
                    if (step, tuple(g)) not in reached and not (
                        step == 3 and any(s == 3 and set(g) <= set(r) for s, r in reached)
                    ):
                        return False
                ours, real = (_settled(x, [*flips, *open_groups]) for x in (sc["seeding"], truth))
                # A tied team it says can reach only some seeds must be at one of them (out is one past the seeds).
                for team, seeds in (sc.get("open_places") or {}).items():
                    if min(truth.index(team) + 1, PLAYOFF_SEEDS + 1) not in seeds:
                        return False
                return ours[:PLAYOFF_SEEDS] == real[:PLAYOFF_SEEDS] and set(ours) == set(real)

            disagree = [s for s in hits if not agrees(s)]
            if disagree:
                report.wrong.append(
                    (mask, margins, truth, [_label(s) for s in disagree], [list(s["seeding"]) for s in disagree])
                )
    return report


def possible_places(teams, completed, remaining, mask, margins):
    """The tiebreaker's order for one result, its decisions, and each team's possible places.

    A team's possible places are its place (past the playoff seeds, all one "out" place), or, in a
    group the tiebreaker takes to fewest points allowed with a team still to play, or to a coin
    flip, any of that group's places: points allowed turn on scores, which margins don't fix.
    """
    out = PLAYOFF_SEEDS + 1
    in_play = {t for g in remaining for t in (g.a, g.b)}
    flips: list = []
    raw: list = []
    order = resolve_standings_for_mask(
        teams, completed, remaining, mask, margins, coin_flip_collector=flips, decision_collector=raw
    )
    decisions = {TiebreakDecision(step, group, parts) for step, group, parts in raw}
    places = {t: {min(i + 1, out)} for i, t in enumerate(order)}
    for g in [g for step, g, _ in raw if step == 5 and set(g) & in_play] + [tuple(f) for f in flips]:
        span = {min(order.index(t) + 1, out) for t in g}
        for t in g:
            places[t] = places[t] | span
    return order, decisions, places


def insight_problems(teams, completed, remaining, insights, *, samples_per_mask: int | None = None, seed: int = 0):
    """The key insights that are false for some result meeting their conditions, with an example each."""
    pairs = [(g.a, g.b) for g in remaining]
    rng = random.Random(seed)
    false = []
    for ins in insights:
        if not ins.conditions:
            continue
        example = None
        for mask in range(1 << len(pairs)):
            if samples_per_mask is None:
                combos = product(MARGINS, repeat=len(pairs))
            else:
                combos = (tuple(rng.choice(MARGINS) for _ in pairs) for _ in range(samples_per_mask))
            for combo in combos:
                margins = dict(zip(pairs, combo, strict=True))
                if not all(c.satisfied_by(mask, margins, remaining) for c in ins.conditions):
                    continue
                p = possible_places(teams, completed, remaining, mask, margins)[2][ins.team]
                if ins.insight_type == "clinch_seed":
                    ok = p == {ins.seed}
                elif ins.insight_type == "clinch_playoffs":
                    ok = max(p) <= PLAYOFF_SEEDS
                else:
                    ok = min(p) > PLAYOFF_SEEDS
                if not ok:
                    example = (mask, margins, sorted(p))
                    break
            if example:
                break
        if example:
            false.append((ins.rendered, *example))
    return false


@dataclass
class PathReport:
    """Where a region's team paths (``build_scenario_atoms``) and the tiebreaker disagree."""

    checked: int = 0
    false: list = field(default_factory=list)  # (team, seed, mask, margins, places it can take, atom)
    missing: list = field(default_factory=list)  # (team, seed, mask, margins): a place it can take, no path to it

    @property
    def ok(self) -> bool:
        """True when every path that holds is right, and every place a team can take has a path."""
        return not self.false and not self.missing

    def summary(self) -> str:
        """A few examples of each problem, readable in a test failure."""
        lines = [f"{self.checked} outcomes checked: {len(self.false)} false, {len(self.missing)} missing"]
        for team, seed, mask, margins, places, atom in self.false[:3]:
            lines.append(f"  false: {team} #{seed} by {[str(c) for c in atom]} at {mask} {margins}; can take {places}")
        for team, seed, mask, margins in self.missing[:3]:
            lines.append(f"  missing: {team} #{seed} at {mask} {margins}")
        return "\n".join(lines)


def team_path_problems(
    teams, completed, remaining, atoms, *, samples_per_mask: int | None = None, seed: int = 0
) -> PathReport:
    """Check per-team paths against the tiebreaker over every winner mask and margin combination.

    A team's possible places for a result are its place, or, in a group the tiebreaker takes to
    fewest points allowed with a team still to play (or to a coin flip), any of that group's
    places: points allowed turn on scores, not margins. A path is false when its conditions can
    all hold but the team can't take that place; a place is missing when a team can take it but
    no path's conditions can hold. A ``TiebreakPlace`` condition can hold when the team is at that
    place among the group, or could be there on points allowed or a flip.
    """
    from backend.helpers.data_classes import TiebreakPlace

    out = PLAYOFF_SEEDS + 1
    pairs = [(g.a, g.b) for g in remaining]
    rng = random.Random(seed)
    report = PathReport()
    for mask in range(1 << len(pairs)):
        if samples_per_mask is None:
            combos = product(MARGINS, repeat=len(pairs))
        else:
            combos = (tuple(rng.choice(MARGINS) for _ in pairs) for _ in range(samples_per_mask))
        for combo in combos:
            margins = dict(zip(pairs, combo, strict=True))
            order, decisions, places = possible_places(teams, completed, remaining, mask, margins)
            report.checked += 1

            def can_hold(c) -> bool:
                """True when condition *c* holds for this outcome: a tiebreaker decision the resolver made, a place the team can take within its tie, or a game result met by these winners and margins."""
                if isinstance(c, TiebreakDecision):
                    return c in decisions
                if isinstance(c, TiebreakPlace):
                    spots = sorted(order.index(t) for t in c.group)
                    return min(spots[c.place - 1] + 1, out) in places[c.team]
                return c.satisfied_by(mask, margins, remaining)

            for team in teams:
                held = {s for s, alist in atoms.get(team, {}).items() if any(all(map(can_hold, a)) for a in alist)}
                for s, alist in atoms.get(team, {}).items():
                    for a in alist:
                        if not all(map(can_hold, a)):
                            continue
                        certain = not any(isinstance(c, TiebreakPlace) for c in a)
                        if s not in places[team] or (certain and places[team] != {s}):
                            report.false.append((team, s, mask, margins, sorted(places[team]), a))
                for s in places[team] - held:
                    report.missing.append((team, s, mask, margins))
    return report
