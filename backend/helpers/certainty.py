"""When a probability may read as certain: 0% and 100% are kept for outcomes that are.

The site promises that 0% and 100%, and "clinched" and "eliminated", mean certain. A float can't
carry that on its own: an Elo-weighted chance can be smaller than any rounding keeps, and a
simulation can miss a possible ending or hit a likely one every time. So the seed odds take their
certainty from the endings themselves (``scenarios.determine_odds``: a place no ending gives is 0,
the only place a team can take is 1, and none of it when the odds are simulated), and every chance
that isn't certain is kept at least ``UNCERTAIN_FLOOR`` away from 0 and 1, far enough for every
reader to see it isn't. ``CERTAIN_EPS`` is the one cutoff every reader uses, here and in the
site's ``format.js``.

The advancement and hosting odds are built from the seed odds by arithmetic, which leaves float
noise, so ``settle`` snaps anything within ``NOISE`` of 0 or 1 to it: a derived chance smaller than
one in a trillion would read as 0%. Its Projected twin follows the Toss-up one (``settle_pair``),
since the two weigh the same endings.
"""

CERTAIN_EPS = 1e-9
"""The one cutoff for reading a stored or served chance as certain: at or below it is 0, at or above
``1 - CERTAIN_EPS`` is 1. Stored chances that aren't certain sit at least ``UNCERTAIN_FLOOR`` away."""

UNCERTAIN_FLOOR = 1e-6
"""How close a chance that isn't certain may come to 0 or 1: a smaller real chance is stored as one
in a million, which every reader shows as "<1%" (or ">99%")."""

NOISE = 1e-12
"""Float noise from summing many exact shares; an exact count within this of 0 or 1 is 0 or 1."""


def is_certain(p: float | None) -> bool:
    """True when *p* reads as 100%."""
    return p is not None and p >= 1 - CERTAIN_EPS


def is_impossible(p: float | None) -> bool:
    """True when *p* reads as 0%."""
    return p is not None and p <= CERTAIN_EPS


def keep_uncertain(p: float) -> float:
    """*p*, moved at least ``UNCERTAIN_FLOOR`` away from 0 and 1: for a chance known not to be certain."""
    return min(max(p, UNCERTAIN_FLOOR), 1 - UNCERTAIN_FLOOR)


def settle(p: float) -> float:
    """An exact count's chance: 0 or 1 within ``NOISE``, otherwise kept uncertain."""
    if p <= NOISE:
        return 0.0
    if p >= 1 - NOISE:
        return 1.0
    return keep_uncertain(p)


def settle_pair(tossup: float, projected: float | None) -> tuple[float, float | None]:
    """A Toss-up chance from exact counts and its Projected twin, settled together.

    Both are 0 or 1 when the Toss-up one is (the two weigh the same endings, so they are certain
    together); otherwise both are kept uncertain.
    """
    t = settle(tossup)
    if projected is None:
        return t, None
    if t in (0.0, 1.0):
        return t, t
    return t, keep_uncertain(projected)
