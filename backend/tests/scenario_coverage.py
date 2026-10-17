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
tiebreaker really does take to that step, and their places are compared
without an order.
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
    return all(
        c in decisions if isinstance(c, TiebreakDecision) else c.satisfied_by(mask, margins, remaining)
        for c in scenario.get("conditions_atom") or []
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
                if any((step, tuple(g)) not in reached for step, g in sc.get("open_groups") or []):
                    return False
                ours, real = (_settled(x, [*flips, *open_groups]) for x in (sc["seeding"], truth))
                return ours[:PLAYOFF_SEEDS] == real[:PLAYOFF_SEEDS] and set(ours) == set(real)

            disagree = [s for s in hits if not agrees(s)]
            if disagree:
                report.wrong.append(
                    (mask, margins, truth, [_label(s) for s in disagree], [list(s["seeding"]) for s in disagree])
                )
    return report
