"""2025 MHSAA playoff bracket matchup data for all 7 classes.

Used by bracket_home_odds_2025_test.py to verify that
``compute_second_round_home_odds``, ``compute_quarterfinal_home_odds``, and
``compute_semifinal_home_odds`` correctly predict the actual home team for
each 2025 playoff game.

Each game tuple is ``(home_region, home_seed, away_region, away_seed)`` —
the *home* team is always listed first.  Leave a round's list empty if the
data is not yet available; tests for that round are automatically skipped.

Bracket slots
-------------
The same first-round slot structure applies to all classes within each group:

* ``SLOTS_5A_7A_2025`` — classes 5, 6, 7  (4 regions, 4-round bracket)
* ``SLOTS_1A_4A_2025`` — classes 1, 2, 3, 4  (8 regions, 5-round bracket)
"""

from backend.helpers.data_classes import FormatSlot

# ---------------------------------------------------------------------------
# Format slot lists (hardcoded from init.sql)
# ---------------------------------------------------------------------------

# 5A–7A: 4 regions, 2 bracket halves (N = regions 1-2, S = regions 3-4).
# QF is round 2 (one prior game), SF is round 3 (two prior games).
SLOTS_5A_7A_2025: list[FormatSlot] = [
    FormatSlot(slot=1, home_region=1, home_seed=1, away_region=2, away_seed=4, north_south="N"),
    FormatSlot(slot=2, home_region=2, home_seed=2, away_region=1, away_seed=3, north_south="N"),
    FormatSlot(slot=3, home_region=2, home_seed=1, away_region=1, away_seed=4, north_south="N"),
    FormatSlot(slot=4, home_region=1, home_seed=2, away_region=2, away_seed=3, north_south="N"),
    FormatSlot(slot=5, home_region=3, home_seed=1, away_region=4, away_seed=4, north_south="S"),
    FormatSlot(slot=6, home_region=4, home_seed=2, away_region=3, away_seed=3, north_south="S"),
    FormatSlot(slot=7, home_region=4, home_seed=1, away_region=3, away_seed=4, north_south="S"),
    FormatSlot(slot=8, home_region=3, home_seed=2, away_region=4, away_seed=3, north_south="S"),
]

# 1A–4A: 8 regions, 2 bracket halves (N = regions 1-4, S = regions 5-8).
# R2 is round 2 (one prior game), QF is round 3 (two), SF is round 4 (three).
SLOTS_1A_4A_2025: list[FormatSlot] = [
    FormatSlot(slot=1, home_region=1, home_seed=1, away_region=2, away_seed=4, north_south="N"),
    FormatSlot(slot=2, home_region=3, home_seed=2, away_region=4, away_seed=3, north_south="N"),
    FormatSlot(slot=3, home_region=2, home_seed=1, away_region=1, away_seed=4, north_south="N"),
    FormatSlot(slot=4, home_region=4, home_seed=2, away_region=3, away_seed=3, north_south="N"),
    FormatSlot(slot=5, home_region=3, home_seed=1, away_region=4, away_seed=4, north_south="N"),
    FormatSlot(slot=6, home_region=1, home_seed=2, away_region=2, away_seed=3, north_south="N"),
    FormatSlot(slot=7, home_region=4, home_seed=1, away_region=3, away_seed=4, north_south="N"),
    FormatSlot(slot=8, home_region=2, home_seed=2, away_region=1, away_seed=3, north_south="N"),
    FormatSlot(slot=9, home_region=5, home_seed=1, away_region=6, away_seed=4, north_south="S"),
    FormatSlot(slot=10, home_region=7, home_seed=2, away_region=8, away_seed=3, north_south="S"),
    FormatSlot(slot=11, home_region=6, home_seed=1, away_region=5, away_seed=4, north_south="S"),
    FormatSlot(slot=12, home_region=8, home_seed=2, away_region=7, away_seed=3, north_south="S"),
    FormatSlot(slot=13, home_region=7, home_seed=1, away_region=8, away_seed=4, north_south="S"),
    FormatSlot(slot=14, home_region=5, home_seed=2, away_region=6, away_seed=3, north_south="S"),
    FormatSlot(slot=15, home_region=8, home_seed=1, away_region=7, away_seed=4, north_south="S"),
    FormatSlot(slot=16, home_region=6, home_seed=2, away_region=5, away_seed=3, north_south="S"),
]

# ---------------------------------------------------------------------------
# 2025 playoff bracket results
# ---------------------------------------------------------------------------
# Each game tuple: (home_region, home_seed, away_region, away_seed)
# The home team is always listed first.
# Leave a list empty if data is not yet available — tests are skipped.
# fmt: off

PLAYOFF_BRACKETS_2025: dict[int, dict[str, list[tuple[int, int, int, int]]]] = {

    # -----------------------------------------------------------------------
    # 7A — quarterfinals and semifinals only (no second round)
    # -----------------------------------------------------------------------
    7: {
        "quarterfinals": [
            # North (2 games)
            (1, 1, 2, 2),
            (2, 1, 1, 2),
            # South (2 games)
            (3, 1, 3, 3),
            (4, 1, 3, 2),
        ],
        "semifinals": [
            # North (1 game)
            (1, 1, 2, 1),
            # South (1 game)
            (4, 1, 3, 3),
        ],
    },

    # -----------------------------------------------------------------------
    # 6A
    # -----------------------------------------------------------------------
    6: {
        "quarterfinals": [
            # North (2 games)
            (2, 2, 2, 4),
            (2, 1, 1, 2),
            # South (2 games)
            (3, 1, 4, 2),
            (4, 1, 4, 3),
        ],
        "semifinals": [
            # North (1 game)
            (2, 1, 2, 2),
            # South (1 game)
            (3, 1, 4, 1),
        ],
    },

    # -----------------------------------------------------------------------
    # 5A
    # -----------------------------------------------------------------------
    5: {
        "quarterfinals": [
            # North (2 games)
            (1, 1, 1, 3),
            (2, 1, 2, 3),
            # South (2 games)
            (3, 1, 4, 2),
            (4, 1, 3, 2),
        ],
        "semifinals": [
            # North (1 game)
            (1, 1, 2, 3),
            # South (1 game)
            (3, 1, 3, 2),
        ],
    },

    # -----------------------------------------------------------------------
    # 4A — second round, quarterfinals, semifinals
    # -----------------------------------------------------------------------
    4: {
        "second_round": [
            # North (4 games)
            (1, 1, 3, 2),
            (2, 1, 4, 2),
            (3, 1, 2, 3),
            (4, 1, 1, 3),
            # South (4 games)
            (5, 1, 7, 2),
            (6, 1, 7, 3),
            (7, 1, 5, 2),
            (8, 1, 6, 2),
        ],
        "quarterfinals": [
            # North (2 games)
            (4, 2, 1, 1),
            (3, 1, 4, 1),
            # South (2 games)
            (7, 2, 7, 3),
            (7, 1, 8, 1),
        ],
        "semifinals": [
            # North (1 game)
            (4, 1, 4, 2),
            # South (1 game)
            (7, 1, 7, 3),
        ],
    },

    # -----------------------------------------------------------------------
    # 3A
    # -----------------------------------------------------------------------
    3: {
        "second_round": [
            # North (4 games)
            (1, 1, 4, 3),
            (2, 1, 4, 2),
            (1, 2, 4, 4),
            (4, 1, 1, 3),
            # South (4 games)
            (5, 1, 7, 2),
            (6, 1, 8, 2),
            (7, 1, 6, 3),
            (8, 1, 6, 2),
        ],
        "quarterfinals": [
            # North (2 games)
            (4, 2, 4, 3),
            (4, 1, 4, 4),
            # South (2 games)
            (5, 1, 6, 1),
            (6, 2, 7, 1),
        ],
        "semifinals": [
            # North (1 game)
            (4, 1, 4, 2),
            # South (1 game)
            (6, 1, 6, 2),
        ],
    },

    # -----------------------------------------------------------------------
    # 2A
    # -----------------------------------------------------------------------
    2: {
        "second_round": [
            # North (4 games)
            (1, 1, 3, 2),
            (2, 1, 4, 2),
            (3, 1, 1, 2),
            (4, 1, 2, 2),
            # South (4 games)
            (7, 2, 6, 4),
            (6, 1, 8, 2),
            (7, 1, 6, 3),
            (8, 1, 6, 2),
        ],
        "quarterfinals": [
            # North (2 games)
            (3, 2, 4, 2),
            (3, 1, 4, 1),
            # South (2 games)
            (6, 1, 6, 4),
            (6, 3, 8, 1),
        ],
        "semifinals": [
            # North (1 game)
            (4, 1, 4, 2),
            # South (1 game)
            (6, 1, 6, 3),
        ],
    },

    # -----------------------------------------------------------------------
    # 1A
    # -----------------------------------------------------------------------
    1: {
        "second_round": [
            # North (4 games)
            (1, 1, 3, 2),
            (2, 1, 3, 3),
            (3, 1, 1, 2),
            (4, 1, 2, 2),
            # South (4 games)
            (5, 1, 8, 3),
            (6, 1, 8, 2),
            (7, 1, 5, 2),
            (8, 1, 6, 2),
        ],
        "quarterfinals": [
            # North (2 games)
            (3, 3, 1, 1),
            (3, 1, 4, 1),
            # South (2 games)
            (5, 1, 6, 1),
            (5, 2, 8, 1),
        ],
        "semifinals": [
            # North (1 game)
            (1, 1, 3, 1),
            # South (1 game)
            (6, 1, 8, 1),
        ],
    },
}
# fmt: on
