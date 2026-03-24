"""Static test fixtures for Region 3-7A (2025 season) standings and scenario tests."""

from backend.helpers.data_classes import (
    CompletedGame,
    GameResult,
    MarginCondition,
    RawCompletedGame,
    RemainingGame,
    StandingsOdds,
)

# ---------------------------------------------------------------------------
# Scenario atoms using the new GameResult / MarginCondition schema
# ---------------------------------------------------------------------------
# Shorthand helpers for repeated pairs used in MarginCondition
_NWR_PET = ("Northwest Rankin", "Petal")  # game pair: NWR always wins in mask=5
_OG_PRL = ("Oak Grove", "Pearl")  # game pair: Pearl always wins in mask=5

# Mask=5 conditions: Brandon wins, Pearl wins (OG loses), NWR wins
# Every mask=5 atom starts with these three GameResults.
_M5_BASE = [
    GameResult("Brandon", "Meridian"),
    GameResult("Pearl", "Oak Grove"),
    GameResult("Northwest Rankin", "Petal"),
]


# Helper: cross-game MarginCondition shortcuts
def _sum_le(v):  # n + p <= v
    """Return MarginCondition: NWR_margin + Pearl_margin <= v."""
    return MarginCondition(add=(_NWR_PET, _OG_PRL), sub=(), op="<=", threshold=v)


def _sum_ge(v):  # n + p >= v
    """Return MarginCondition: NWR_margin + Pearl_margin >= v."""
    return MarginCondition(add=(_NWR_PET, _OG_PRL), sub=(), op=">=", threshold=v)


def _diff_le(v):  # n - p <= v
    """Return MarginCondition: NWR_margin - Pearl_margin <= v."""
    return MarginCondition(add=(_NWR_PET,), sub=(_OG_PRL,), op="<=", threshold=v)


def _diff_ge(v):  # n - p >= v
    """Return MarginCondition: NWR_margin - Pearl_margin >= v."""
    return MarginCondition(add=(_NWR_PET,), sub=(_OG_PRL,), op=">=", threshold=v)


# ---------------------------------------------------------------------------
# expected_3_7a_scenarios
#
# Correct representation of all pre-final-week scenarios for Region 3-7A
# (2025 season) using the GameResult / MarginCondition schema.
#
# Each atom is a list of conditions (all must hold = AND).
# Each team/seed entry is a list of atoms (any atom holding = OR).
#
# Non-mask-5 atoms are translated directly from the GE-key format.
# Mask-5 atoms (5-way tie) are derived analytically from the H2H PD formulas.
#   n = NWR winning margin, p = Pearl winning margin (both in [1,12])
#   H2H PDs: OG=8-p, Petal=6-n, Pearl=p-4, NWR=n-2, Brandon=-8 (always 5th)
#   Key boundaries:
#     n-p = -2: OG=Petal in PD AND NWR=Pearl in PD; Petal wins OG/Petal tb; NWR wins NWR/Pearl tb
#     n+p = 10: OG=NWR in PD AND Pearl=Petal in PD; OG wins OG/NWR tb; Pearl wins Pearl/Petal tb
#     p = 6:    OG=Pearl in PD; Pearl wins tb
#     n = 4:    NWR=Petal in PD; NWR wins tb
# ---------------------------------------------------------------------------


# GameResult shorthands for mask=5 n/p conditions (NWR and Pearl always win in mask=5)
def _nwr(n_min, n_max=None):
    """NWR beats Petal by n_min to n_max-1 (or n_min+ if n_max=None)."""
    return GameResult("Northwest Rankin", "Petal", n_min, n_max)


def _prl(p_min, p_max=None):
    """Pearl beats Oak Grove by p_min to p_max-1 (or p_min+ if p_max=None)."""
    return GameResult("Pearl", "Oak Grove", p_min, p_max)


expected_3_7a_scenarios: dict[str, dict[int, list[list]]] = {
    # -----------------------------------------------------------------------
    # Petal
    # -----------------------------------------------------------------------
    "Petal": {
        1: [
            # Non-mask-5: Petal beats NWR (NWR loses → masks 0,1,2,3)
            [GameResult("Petal", "Northwest Rankin")],
            # Mask-5 (5-way tie): Petal=1 when n+p≤9 AND n-p≤-2
            # i.e. NWR wins by 1-3 AND Pearl wins by n+2 to 9-n
            [*_M5_BASE, _sum_le(9), _diff_le(-2)],
        ],
        2: [
            # Non-mask-5: Brandon wins, OG wins, NWR wins (mask=3)
            [
                GameResult("Brandon", "Meridian"),
                GameResult("Oak Grove", "Pearl"),
                GameResult("Northwest Rankin", "Petal"),
            ],
            # Mask-5: Petal=2 has two sub-regions:
            # (a) n≤3, p≤5, n-p≥-1  (OG>Pearl, Petal>NWR, OG>Petal)
            [GameResult("Brandon", "Meridian"), _prl(1, 6), _nwr(1, 4), _diff_ge(-1)],
            # (b) n≤3, p≥6, n+p≥10  (Pearl wins tiebreaker over Petal, Petal still 2nd)
            [GameResult("Brandon", "Meridian"), _prl(6), _nwr(1, 4), _sum_ge(10)],
        ],
        3: [
            # Non-mask-5: Brandon loses, NWR wins (masks 4,6)
            [GameResult("Meridian", "Brandon"), GameResult("Northwest Rankin", "Petal")],
            # Mask-5: Petal=3 has three sub-regions:
            # (a) n=4 exactly (NWR=Petal in PD, NWR wins → NWR=1 or 2; Petal=3 or 4 dep. on p)
            #     But n=4, any p: Petal=3. Verified from grid.
            [GameResult("Brandon", "Meridian"), GameResult("Pearl", "Oak Grove"), _nwr(4, 5)],
            # (b) n≥5, p≤5, n+p≤9  (NWR>OG, OG>Pearl, OG gets seed 1)
            [GameResult("Brandon", "Meridian"), _prl(1, 6), _nwr(5), _sum_le(9)],
            # (c) n≥5, p≥6, n-p≤-2  (Pearl wins, NWR ties Pearl; NWR wins tiebreak → NWR=1)
            [GameResult("Brandon", "Meridian"), _prl(6), _nwr(5), _diff_le(-2)],
        ],
        4: [
            # Mask-5 only: n+p≥10, n-p≥-1  (NWR clearly dominates)
            [*_M5_BASE, _sum_ge(10), _diff_ge(-1)],
        ],
    },
    # -----------------------------------------------------------------------
    # Pearl
    # -----------------------------------------------------------------------
    "Pearl": {
        1: [
            # Non-mask-5: Brandon wins, NWR wins, Pearl wins (mask=5) — NEW mask-5 atom
            # Mask-5: Pearl=1 when n+p≥10 AND n-p≤-3  (Pearl has highest PD)
            [*_M5_BASE, _sum_ge(10), _diff_le(-3)],
        ],
        2: [
            # Non-mask-5 atom a: NWR loses AND Pearl wins (masks 0,1)
            [GameResult("Petal", "Northwest Rankin"), GameResult("Pearl", "Oak Grove")],
            # Non-mask-5 atom b: Brandon loses, NWR wins, Pearl wins (mask=4)
            [
                GameResult("Meridian", "Brandon"),
                GameResult("Northwest Rankin", "Petal"),
                GameResult("Pearl", "Oak Grove"),
            ],
            # Mask-5 sub-regions (three atoms):
            # (a) n≤3, p≥6, n+p≤9  (Petal=1, Pearl beats OG in PD, Pearl=2)
            [GameResult("Brandon", "Meridian"), _prl(6), _nwr(1, 4), _sum_le(9)],
            # (b) n=4, p=6 exactly  (4-way PD tie; NWR=1, Pearl=2 after further tiebreak)
            [GameResult("Brandon", "Meridian"), _prl(6, 7), _nwr(4, 5)],
            # (c) n≥5, p≥6, n-p≥-2  (NWR=1 since NWR≥Pearl; Pearl=2 since Pearl>OG)
            [GameResult("Brandon", "Meridian"), _prl(6), _nwr(5), _diff_ge(-2)],
        ],
        3: [
            # Mask-5 sub-regions (two atoms):
            # (a) n≤3, p≤5, n+p≤7, n-p∈[-4,-3]
            #   (OG=NWR in-region, Pearl tied with NWR; OG wins among top; Pearl=3rd)
            [GameResult("Brandon", "Meridian"), _prl(4, 6), _nwr(1, 4), _sum_le(7), _diff_ge(-4), _diff_le(-3)],
            # (b) n≥5, p≤5, n+p≥10  (NWR=1, OG=2, Pearl=3)
            [GameResult("Brandon", "Meridian"), _prl(1, 6), _nwr(5), _sum_ge(10)],
        ],
        4: [
            # Mask-5: Pearl=4 when n+p≤9, n-p≥-2
            # (Petal=1, OG=2 or OG=1, Pearl=4)
            [*_M5_BASE, _sum_le(9), _diff_ge(-2)],
        ],
        5: [
            # Non-mask-5: OG wins (Pearl eliminated) — masks 2,3,6,7
            [GameResult("Oak Grove", "Pearl")],
        ],
    },
    # -----------------------------------------------------------------------
    # Oak Grove
    # -----------------------------------------------------------------------
    "Oak Grove": {
        1: [
            # Non-mask-5: NWR wins AND OG wins (masks 3,7)
            [GameResult("Northwest Rankin", "Petal"), GameResult("Oak Grove", "Pearl")],
            # Mask-5: OG=1 when n+p≤10 AND n-p≥-1
            [*_M5_BASE, _sum_le(10), _diff_ge(-1)],
        ],
        2: [
            # Non-mask-5: NWR loses AND OG wins (mask=2)
            [GameResult("Petal", "Northwest Rankin"), GameResult("Oak Grove", "Pearl")],
            # Mask-5 sub-regions:
            # (a) n≤3, p≤5, n-p≤-2  (Petal=1, OG=2)
            [GameResult("Brandon", "Meridian"), _prl(1, 6), _nwr(1, 4), _diff_le(-2)],
            # (b) n≥5, p≤5, n+p≥11  (NWR=1, OG=2)
            [GameResult("Brandon", "Meridian"), _prl(1, 6), _nwr(5), _sum_ge(11)],
        ],
        3: [
            # Non-mask-5: NWR loses AND Pearl wins (masks 0,1)
            [GameResult("Petal", "Northwest Rankin"), GameResult("Pearl", "Oak Grove")],
            # Mask-5 sub-regions:
            # (a) n≤3, p≥6, n+p≤10  (Petal=1, Pearl=2, OG=3)
            [GameResult("Brandon", "Meridian"), _prl(6), _nwr(1, 4), _sum_le(10)],
            # (b) n≥5, p≥6, n-p≥-1  (NWR=1, Pearl=2, OG=3)
            [GameResult("Brandon", "Meridian"), _prl(6), _nwr(5), _diff_ge(-1)],
        ],
        4: [
            # Non-mask-5: Brandon loses, NWR wins, Pearl wins (mask=4)
            [
                GameResult("Meridian", "Brandon"),
                GameResult("Northwest Rankin", "Petal"),
                GameResult("Pearl", "Oak Grove"),
            ],
            # Mask-5 sub-regions:
            # (a) n≤3, n+p≥11  (Pearl>Petal in PD → Pearl=1, OG=4)
            [GameResult("Brandon", "Meridian"), GameResult("Pearl", "Oak Grove"), _nwr(1, 4), _sum_ge(11)],
            # (b) n=4, p≥6  (NWR=1, NWR tied with Petal; Petal=3; OG=4)
            [GameResult("Brandon", "Meridian"), _prl(6), _nwr(4, 5)],
            # (c) n≥5, n-p≤-2  (NWR=1, Pearl=2; OG=4 since Pearl>OG)
            [GameResult("Brandon", "Meridian"), GameResult("Pearl", "Oak Grove"), _nwr(5), _diff_le(-2)],
        ],
    },
    # -----------------------------------------------------------------------
    # Northwest Rankin
    # -----------------------------------------------------------------------
    "Northwest Rankin": {
        1: [
            # Non-mask-5: Brandon loses, NWR wins, Pearl wins (mask=4)
            [
                GameResult("Meridian", "Brandon"),
                GameResult("Northwest Rankin", "Petal"),
                GameResult("Pearl", "Oak Grove"),
            ],
            # Mask-5 sub-regions:
            # (a) n=4, p=6 exactly  (4-way PD tie, NWR wins further tiebreak → NWR=1)
            [GameResult("Brandon", "Meridian"), _prl(6, 7), _nwr(4, 5)],
            # (b) n≥5, n+p≥11, n-p≥-2  (NWR strictly highest or ties Pearl and wins)
            [GameResult("Brandon", "Meridian"), GameResult("Pearl", "Oak Grove"), _nwr(5), _sum_ge(11), _diff_ge(-2)],
        ],
        2: [
            # Non-mask-5: Brandon loses, NWR wins, OG wins (mask=6)
            [
                GameResult("Meridian", "Brandon"),
                GameResult("Northwest Rankin", "Petal"),
                GameResult("Oak Grove", "Pearl"),
            ],
            # Mask-5 sub-regions (four atoms):
            # (a) n=4, p≤5  (NWR>OG since n+p≤9; NWR=2 behind OG=1)
            [GameResult("Brandon", "Meridian"), _prl(1, 6), _nwr(4, 5)],
            # (b) n=4, p≥7  (Pearl>OG, NWR=Petal in PD; NWR=2, Pearl=1 not possible since NWR>Pearl needs n>p-2=5, n=4<5; Pearl>NWR so Pearl=1? Wait let me verify)
            #   At n=4,p=7: "31425" → NWR=2, Pearl=1. But Pearl seed 1 condition is n+p>=10 AND n-p<=-3.
            #   n=4,p=7: n+p=11>=10 ✓, n-p=-3<=-3 ✓. So Pearl=1. And NWR=2. ✓
            [GameResult("Brandon", "Meridian"), _prl(7), _nwr(4, 5)],
            # (c) n≥5, p≤5, n+p≤10  (OG=1 or NWR=OG tie → NWR=2)
            [GameResult("Brandon", "Meridian"), _prl(1, 6), _nwr(5), _sum_le(10)],
            # (d) n≥5, p≥6, n-p≤-3  (Pearl>NWR; Pearl=1 → NWR=2)
            [GameResult("Brandon", "Meridian"), _prl(6), _nwr(5), _diff_le(-3)],
        ],
        3: [
            # Mask-5 sub-regions:
            # (a) n≤3, p≤5, n-p≥-2  (Petal>NWR in PD; NWR=3 since OG>Pearl and Petal=1)
            #   Wait: at n≤3, p≤5: OG>Pearl (p<6), Petal>NWR (n<4).
            #   And n-p≥-2 means OG≥Petal (OG wins when tied). So seed order: Petal=?,OG=?,NWR=3,Pearl=4
            #   Actually: n-p≥-2 AND n≤3 AND p≤5. Let me verify from grid.
            #   n=1,p=2: n-p=-1≥-2. "24135" → NWR=3 ✓.
            #   n=2,p=4: n-p=-2≥-2. "14235" → NWR=3 ✓.
            [GameResult("Brandon", "Meridian"), _prl(1, 6), _nwr(1, 4), _diff_ge(-2)],
            # (b) n≤3, p≥6, n+p≥11  (Pearl>Petal AND Pearl>OG; Pearl=1; NWR=3)
            #   At n=1,p=10: Pearl=1, NWR=3. "21435" ✓.
            [GameResult("Brandon", "Meridian"), _prl(6), _nwr(1, 4), _sum_ge(11)],
        ],
        4: [
            # Non-mask-5: NWR loses, OG wins (mask=2)
            [GameResult("Petal", "Northwest Rankin"), GameResult("Oak Grove", "Pearl")],
            # Non-mask-5: Brandon wins, NWR wins, OG wins (mask=3)
            [
                GameResult("Brandon", "Meridian"),
                GameResult("Northwest Rankin", "Petal"),
                GameResult("Oak Grove", "Pearl"),
            ],
            # Mask-5: NWR=4 when n+p≤10 AND n-p≤-3  (Petal=1, Pearl=2 or 3, NWR=4)
            [*_M5_BASE, _sum_le(10), _diff_le(-3)],
        ],
        5: [
            # Non-mask-5: NWR loses, Pearl wins (masks 0,1)
            [GameResult("Petal", "Northwest Rankin"), GameResult("Pearl", "Oak Grove")],
        ],
    },
    # -----------------------------------------------------------------------
    # Brandon  (always seed 5 in mask=5; competitive in other masks)
    # -----------------------------------------------------------------------
    "Brandon": {
        3: [
            # NWR loses, OG wins (mask=2)
            [GameResult("Petal", "Northwest Rankin"), GameResult("Oak Grove", "Pearl")],
            # Brandon wins, NWR wins, OG wins (mask=3)
            [
                GameResult("Brandon", "Meridian"),
                GameResult("Northwest Rankin", "Petal"),
                GameResult("Oak Grove", "Pearl"),
            ],
        ],
        4: [
            # NWR loses, Pearl wins (masks 0,1)
            [GameResult("Petal", "Northwest Rankin"), GameResult("Pearl", "Oak Grove")],
            # Brandon loses, NWR wins, OG wins (mask=6)
            [
                GameResult("Meridian", "Brandon"),
                GameResult("Northwest Rankin", "Petal"),
                GameResult("Oak Grove", "Pearl"),
            ],
        ],
        5: [
            # Brandon loses, NWR wins, Pearl wins (mask=4)
            [
                GameResult("Meridian", "Brandon"),
                GameResult("Northwest Rankin", "Petal"),
                GameResult("Pearl", "Oak Grove"),
            ],
            # Mask-5: Brandon always 5th (all 144 cells)
            [*_M5_BASE],
        ],
    },
    # -----------------------------------------------------------------------
    # Meridian  (always last — 0-5 region record after week 5)
    # -----------------------------------------------------------------------
    "Meridian": {
        6: [
            # NWR loses (masks 0,1,2,3)
            [GameResult("Petal", "Northwest Rankin")],
            # Brandon loses, NWR wins (masks 4,6)
            [GameResult("Meridian", "Brandon"), GameResult("Northwest Rankin", "Petal")],
            # Brandon wins, NWR wins, OG wins (mask=3)
            [
                GameResult("Brandon", "Meridian"),
                GameResult("Northwest Rankin", "Petal"),
                GameResult("Oak Grove", "Pearl"),
            ],
            # Mask-5: Meridian always last (all cells)
            [*_M5_BASE],
        ],
    },
}

# ----------- Test Data for Class 7A Region 3 (2025 season) ----------

# Teams in Class 7A Region 3 for the 2025 season
teams_3_7a: list[str] = ["Meridian", "Oak Grove", "Pearl", "Petal", "Brandon", "Northwest Rankin"]

# ---------------------------------------------------------------------------
# PRE-FINAL-WEEK state (games played through 2025-11-02, 3 games remaining)
# ---------------------------------------------------------------------------

# Raw completed game results — both perspectives for each game
raw_3_7a_region_results: list[RawCompletedGame] = [
    {
        "school": "Meridian",
        "opponent": "Pearl",
        "date": "2025-10-10",
        "result": "L",
        "points_for": 17,
        "points_against": 38,
    },
    {
        "school": "Meridian",
        "opponent": "Oak Grove",
        "date": "2025-10-17",
        "result": "L",
        "points_for": 21,
        "points_against": 42,
    },
    {
        "school": "Meridian",
        "opponent": "Northwest Rankin",
        "date": "2025-10-24",
        "result": "L",
        "points_for": 12,
        "points_against": 31,
    },
    {
        "school": "Meridian",
        "opponent": "Petal",
        "date": "2025-10-31",
        "result": "L",
        "points_for": 14,
        "points_against": 42,
    },
    {
        "school": "Petal",
        "opponent": "Oak Grove",
        "date": "2025-10-10",
        "result": "W",
        "points_for": 28,
        "points_against": 21,
    },
    {
        "school": "Petal",
        "opponent": "Brandon",
        "date": "2025-10-17",
        "result": "W",
        "points_for": 27,
        "points_against": 21,
    },
    {
        "school": "Petal",
        "opponent": "Pearl",
        "date": "2025-10-24",
        "result": "L",
        "points_for": 14,
        "points_against": 21,
    },
    {
        "school": "Petal",
        "opponent": "Meridian",
        "date": "2025-10-31",
        "result": "W",
        "points_for": 42,
        "points_against": 14,
    },
    {
        "school": "Northwest Rankin",
        "opponent": "Brandon",
        "date": "2025-10-03",
        "result": "L",
        "points_for": 0,
        "points_against": 3,
    },
    {
        "school": "Northwest Rankin",
        "opponent": "Pearl",
        "date": "2025-10-17",
        "result": "W",
        "points_for": 33,
        "points_against": 29,
    },
    {
        "school": "Northwest Rankin",
        "opponent": "Meridian",
        "date": "2025-10-24",
        "result": "W",
        "points_for": 31,
        "points_against": 12,
    },
    {
        "school": "Northwest Rankin",
        "opponent": "Oak Grove",
        "date": "2025-10-31",
        "result": "L",
        "points_for": 34,
        "points_against": 37,
    },
    {
        "school": "Brandon",
        "opponent": "Northwest Rankin",
        "date": "2025-10-03",
        "result": "W",
        "points_for": 3,
        "points_against": 0,
    },
    {
        "school": "Brandon",
        "opponent": "Petal",
        "date": "2025-10-17",
        "result": "L",
        "points_for": 21,
        "points_against": 27,
    },
    {
        "school": "Brandon",
        "opponent": "Oak Grove",
        "date": "2025-10-24",
        "result": "L",
        "points_for": 7,
        "points_against": 20,
    },
    {
        "school": "Brandon",
        "opponent": "Pearl",
        "date": "2025-10-31",
        "result": "W",
        "points_for": 17,
        "points_against": 10,
    },
    {
        "school": "Oak Grove",
        "opponent": "Petal",
        "date": "2025-10-10",
        "result": "L",
        "points_for": 21,
        "points_against": 28,
    },
    {
        "school": "Oak Grove",
        "opponent": "Meridian",
        "date": "2025-10-17",
        "result": "W",
        "points_for": 42,
        "points_against": 21,
    },
    {
        "school": "Oak Grove",
        "opponent": "Brandon",
        "date": "2025-10-24",
        "result": "W",
        "points_for": 20,
        "points_against": 7,
    },
    {
        "school": "Oak Grove",
        "opponent": "Northwest Rankin",
        "date": "2025-10-31",
        "result": "W",
        "points_for": 37,
        "points_against": 34,
    },
]

# Expected CompletedGame objects — 12 completed games, sorted by (a, b)
expected_3_7a_completed_games: list[CompletedGame] = [
    CompletedGame("Brandon", "Northwest Rankin", 1, 3, 0, 3),
    CompletedGame("Brandon", "Oak Grove", -1, -13, 20, 7),
    CompletedGame("Brandon", "Pearl", 1, 7, 10, 17),
    CompletedGame("Brandon", "Petal", -1, -6, 27, 21),
    CompletedGame("Meridian", "Northwest Rankin", -1, -19, 31, 12),
    CompletedGame("Meridian", "Oak Grove", -1, -21, 42, 21),
    CompletedGame("Meridian", "Pearl", -1, -21, 38, 17),
    CompletedGame("Meridian", "Petal", -1, -28, 42, 14),
    CompletedGame("Northwest Rankin", "Oak Grove", -1, -3, 37, 34),
    CompletedGame("Northwest Rankin", "Pearl", 1, 4, 29, 33),
    CompletedGame("Oak Grove", "Petal", -1, -7, 28, 21),
    CompletedGame("Pearl", "Petal", 1, 7, 14, 21),
]

# Remaining games heading into final week
expected_3_7a_remaining_games: list[RemainingGame] = [
    RemainingGame("Brandon", "Meridian"),
    RemainingGame("Oak Grove", "Pearl"),
    RemainingGame("Northwest Rankin", "Petal"),
]

# Scenario counts — fractional due to margin-sensitive tiebreaker branches
# denom = 8.0 (2^3 remaining games)
expected_3_7a_first_counts: dict[str, float] = {
    "Petal": 4.083333333333392,
    "Northwest Rankin": 1.4652777777777737,
    "Oak Grove": 2.2013888888888884,
    "Pearl": 0.25000000000000006,
}
expected_3_7a_second_counts: dict[str, float] = {
    "Pearl": 3.3333333333333703,
    "Oak Grove": 2.2152777777777777,
    "Petal": 1.1666666666666667,
    "Northwest Rankin": 1.284722222222222,
}
expected_3_7a_third_counts: dict[str, float] = {
    "Oak Grove": 2.3055555555555634,
    "Brandon": 2.9999999999999956,
    "Petal": 2.2986111111111076,
    "Northwest Rankin": 0.1666666666666667,
    "Pearl": 0.22916666666666674,
}
expected_3_7a_fourth_counts: dict[str, float] = {
    "Brandon": 3.000000000000001,
    "Northwest Rankin": 3.0833333333333313,
    "Oak Grove": 1.2777777777777743,
    "Pearl": 0.18750000000000006,
    "Petal": 0.45138888888888823,
}

# Odds for each team heading into final week
expected_3_7a_odds: dict[str, StandingsOdds] = {
    "Meridian": StandingsOdds("Meridian", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False, True),
    "Oak Grove": StandingsOdds(
        "Oak Grove",
        0.27517361111111105,
        0.2769097222222222,
        0.2881944444444454,
        0.1597222222222218,
        1.0000000000000004,
        1.0,
        True,
        False,
    ),
    "Pearl": StandingsOdds(
        "Pearl",
        0.03125000000000001,
        0.4166666666666713,
        0.028645833333333343,
        0.023437500000000007,
        0.5000000000000047,
        0.5000000000000047,
        False,
        False,
    ),
    "Petal": StandingsOdds(
        "Petal",
        0.510416666666674,
        0.14583333333333334,
        0.28732638888888845,
        0.05642361111111103,
        1.0000000000000067,
        1.0,
        True,
        False,
    ),
    "Brandon": StandingsOdds("Brandon", 0.0, 0.0, 0.37499999999999944, 0.3750000000000001, 0.7499999999999996, 0.7499999999999996, False, False),
    "Northwest Rankin": StandingsOdds(
        "Northwest Rankin",
        0.1831597222222217,
        0.16059027777777776,
        0.02083333333333334,
        0.3854166666666664,
        0.7499999999999991,
        0.7499999999999991,
        False,
        False,
    ),
}

# ---------------------------------------------------------------------------
# FULL SEASON state (all 15 games played, 0 remaining)
# Ground truth: seeds 1-4 = Oak Grove, Petal, Brandon, Northwest Rankin
# ---------------------------------------------------------------------------

raw_3_7a_region_results_full: list[RawCompletedGame] = list(raw_3_7a_region_results) + [
    {
        "school": "Brandon",
        "opponent": "Meridian",
        "date": "2025-11-07",
        "result": "W",
        "points_for": 40,
        "points_against": 13,
    },
    {
        "school": "Meridian",
        "opponent": "Brandon",
        "date": "2025-11-07",
        "result": "L",
        "points_for": 13,
        "points_against": 40,
    },
    {
        "school": "Oak Grove",
        "opponent": "Pearl",
        "date": "2025-11-07",
        "result": "W",
        "points_for": 28,
        "points_against": 7,
    },
    {
        "school": "Pearl",
        "opponent": "Oak Grove",
        "date": "2025-11-07",
        "result": "L",
        "points_for": 7,
        "points_against": 28,
    },
    {
        "school": "Northwest Rankin",
        "opponent": "Petal",
        "date": "2025-11-07",
        "result": "W",
        "points_for": 34,
        "points_against": 28,
    },
    {
        "school": "Petal",
        "opponent": "Northwest Rankin",
        "date": "2025-11-07",
        "result": "L",
        "points_for": 28,
        "points_against": 34,
    },
]

expected_3_7a_completed_games_full: list[CompletedGame] = [
    CompletedGame("Brandon", "Meridian", 1, 27, 13, 40),
    CompletedGame("Brandon", "Northwest Rankin", 1, 3, 0, 3),
    CompletedGame("Brandon", "Oak Grove", -1, -13, 20, 7),
    CompletedGame("Brandon", "Pearl", 1, 7, 10, 17),
    CompletedGame("Brandon", "Petal", -1, -6, 27, 21),
    CompletedGame("Meridian", "Northwest Rankin", -1, -19, 31, 12),
    CompletedGame("Meridian", "Oak Grove", -1, -21, 42, 21),
    CompletedGame("Meridian", "Pearl", -1, -21, 38, 17),
    CompletedGame("Meridian", "Petal", -1, -28, 42, 14),
    CompletedGame("Northwest Rankin", "Oak Grove", -1, -3, 37, 34),
    CompletedGame("Northwest Rankin", "Pearl", 1, 4, 29, 33),
    CompletedGame("Northwest Rankin", "Petal", 1, 6, 28, 34),
    CompletedGame("Oak Grove", "Pearl", 1, 21, 7, 28),
    CompletedGame("Oak Grove", "Petal", -1, -7, 28, 21),
    CompletedGame("Pearl", "Petal", 1, 7, 14, 21),
]

# No remaining games after final week
expected_3_7a_remaining_games_full: list[RemainingGame] = []

# Full-season counts: deterministic (denom = 1.0), each team has exactly one seed
expected_3_7a_first_counts_full: dict[str, float] = {"Oak Grove": 1}
expected_3_7a_second_counts_full: dict[str, float] = {"Petal": 1}
expected_3_7a_third_counts_full: dict[str, float] = {"Brandon": 1}
expected_3_7a_fourth_counts_full: dict[str, float] = {"Northwest Rankin": 1}

expected_3_7a_odds_full: dict[str, StandingsOdds] = {
    "Meridian": StandingsOdds("Meridian", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False, True),
    "Oak Grove": StandingsOdds("Oak Grove", 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, True, False),
    "Pearl": StandingsOdds("Pearl", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False, True),
    "Petal": StandingsOdds("Petal", 0.0, 1.0, 0.0, 0.0, 1.0, 1.0, True, False),
    "Brandon": StandingsOdds("Brandon", 0.0, 0.0, 1.0, 0.0, 1.0, 1.0, True, False),
    "Northwest Rankin": StandingsOdds("Northwest Rankin", 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, True, False),
}
