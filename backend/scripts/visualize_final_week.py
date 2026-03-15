"""
Visualize all final-week seeding outcomes for Region 3-7A (2025 season).

Three games remaining:
  Game 0 (bit 0): Brandon (a) vs Meridian (b)
  Game 1 (bit 1): Oak Grove (a) vs Pearl (b)
  Game 2 (bit 2): Northwest Rankin (a) vs Petal (b)

Each game's signed margin: negative = b-team wins, positive = a-team wins.
Range: -12 .. -1 (b wins) and +1 .. +12 (a wins) — 24 values per game.

Output: scripts/final_week_scenarios.png

Run from project root:
    python scripts/visualize_final_week.py
    # or, if matplotlib is not yet installed:
    uv run --with matplotlib python scripts/visualize_final_week.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap

from backend.helpers.tiebreakers import resolve_standings_for_mask
from backend.tests.data.test_region_standings import (
    expected_3_7a_completed_games as completed,
)
from backend.tests.data.test_region_standings import (
    expected_3_7a_remaining_games as remaining,
)
from backend.tests.data.test_region_standings import (
    teams_3_7a as teams,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BRANDON = "Brandon"
_MERIDIAN = "Meridian"
_OAK_GROVE = "Oak Grove"
_NORTHWEST_RANKIN = "Northwest Rankin"
_PEARL = "Pearl"
_PETAL = "Petal"

ABBREV = {
    _OAK_GROVE: "OG",
    _PETAL: "P",
    _BRANDON: "B",
    _NORTHWEST_RANKIN: "NR",
    _PEARL: "Pr",
    _MERIDIAN: "M",
}

TEAM_DISPLAY = {
    _OAK_GROVE: "Oak Grove (OG)",
    _PETAL: "Petal (P)",
    _BRANDON: "Brandon (B)",
    _NORTHWEST_RANKIN: "NW Rankin (NR)",
    _PEARL: "Pearl (Pr)",
    _MERIDIAN: "Meridian (M)",
}

# Signed margins: -12..−1 (b wins by |m|), +1..+12 (a wins by m)
MARGINS: list[int] = list(range(-12, 0)) + list(range(1, 13))  # 24 values

# Panels: OG vs Pearl margin (negative = Pearl wins)
OG_PANELS: list[tuple[str, int]] = [
    ("Pearl wins by 12", -12),
    ("Pearl wins by 6", -6),
    ("Pearl wins by 1", -1),
    ("OG wins by 1", 1),
    ("OG wins by 6", 6),
    ("OG wins by 12", 12),
]

# ---------------------------------------------------------------------------
# Seeding computation
# ---------------------------------------------------------------------------

# Remaining-game indices:  0 = Brandon vs Meridian, 1 = OG vs Pearl, 2 = NWR vs Petal
_GAME_BM = 0
_GAME_OG = 1
_GAME_NWR = 2


def _seedings_for(bm: int, nm: int, om: int) -> tuple[str, ...]:
    """Return the top-4 seeding tuple for the given signed winning margins.

    Encodes each game's result as a win-mask bit and an absolute margin, then
    delegates to ``resolve_standings_for_mask`` to apply the full tiebreaker chain.
    Positive margin means the first-listed team (a-team) wins; negative means the
    second-listed team (b-team) wins.

    Args:
        bm: Signed margin for Brandon (a) vs Meridian (b).  Positive = Brandon wins.
        nm: Signed margin for Northwest Rankin (a) vs Petal (b).  Positive = NWR wins.
        om: Signed margin for Oak Grove (a) vs Pearl (b).  Positive = Oak Grove wins.

    Returns:
        A tuple of the top-4 school names in seed order (1st through 4th).
    """
    mask = 0
    margs: dict[tuple[str, str], int] = {}

    if bm > 0:
        mask |= 1 << _GAME_BM
    margs[(_BRANDON, _MERIDIAN)] = abs(bm)

    if om > 0:
        mask |= 1 << _GAME_OG
    margs[(_OAK_GROVE, _PEARL)] = abs(om)

    if nm > 0:
        mask |= 1 << _GAME_NWR
    margs[(_NORTHWEST_RANKIN, _PETAL)] = abs(nm)

    order = resolve_standings_for_mask(teams, completed, remaining, mask, margs)
    return tuple(order[:4])


# ---------------------------------------------------------------------------
# Pre-compute all seedings and build the unique-seeding index
# ---------------------------------------------------------------------------

print("Computing seedings for all outcome combinations…")
_all_seedings: set[tuple[str, ...]] = set()
for _bm in MARGINS:
    for _nm in MARGINS:
        for _, _om in OG_PANELS:
            _all_seedings.add(_seedings_for(_bm, _nm, _om))

seeding_list: list[tuple[str, ...]] = sorted(_all_seedings, key=lambda s: tuple(ABBREV[t] for t in s))
seeding_idx: dict[tuple[str, ...], int] = {s: i for i, s in enumerate(seeding_list)}
n_seedings = len(seeding_list)

print(f"\nFound {n_seedings} distinct top-4 seeding orders:")
for i, s in enumerate(seeding_list):
    label = " > ".join(ABBREV[t] for t in s)
    print(f"  [{i:2d}] {label}")

# ---------------------------------------------------------------------------
# Color palette — perceptually distinct
# ---------------------------------------------------------------------------

# Use tab20 for up to 20 distinct orderings; fall back to hsv if more
if n_seedings <= 20:
    palette = [plt.colormaps["tab20"].colors[i] for i in range(n_seedings)]  # type: ignore[index]
else:
    palette = [plt.colormaps["hsv"](x) for x in np.linspace(0, 0.92, n_seedings)]

cmap = ListedColormap(palette)
norm = BoundaryNorm(boundaries=list(range(n_seedings + 1)), ncolors=n_seedings)

# ---------------------------------------------------------------------------
# Build grids for each panel
# ---------------------------------------------------------------------------

n_m = len(MARGINS)
# grids[panel_idx][yi][xi] = seeding index
grids: list[np.ndarray] = []

for _, om in OG_PANELS:
    grid = np.zeros((n_m, n_m), dtype=int)
    for yi, nm in enumerate(MARGINS):
        for xi, bm in enumerate(MARGINS):
            grid[yi, xi] = seeding_idx[_seedings_for(bm, nm, om)]
    grids.append(grid)

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

N_ROWS, N_COLS = 2, 3
fig, axes = plt.subplots(N_ROWS, N_COLS, figsize=(20, 14))
axes = axes.flatten()

# Axis tick positions — label every 2nd margin to avoid crowding
tick_positions = list(range(0, n_m, 2))  # 0,2,4,…,22
tick_labels_x = [str(MARGINS[i]) for i in tick_positions]
tick_labels_y = [str(MARGINS[i]) for i in tick_positions]

# Quadrant divider position (between index 11 and 12, i.e., between −1 and +1)
DIVIDER = 11.5

for panel_idx, ((panel_label, _om), grid) in enumerate(zip(OG_PANELS, grids)):
    ax = axes[panel_idx]

    im = ax.imshow(
        grid,
        cmap=cmap,
        norm=norm,
        origin="lower",
        aspect="auto",
        interpolation="nearest",
    )

    # W/L boundary lines
    ax.axvline(x=DIVIDER, color="white", linewidth=2.5, linestyle="--", alpha=0.85)
    ax.axhline(y=DIVIDER, color="white", linewidth=2.5, linestyle="--", alpha=0.85)

    # Quadrant annotations
    kw = {
        "ha": "center",
        "va": "center",
        "fontsize": 7.5,
        "color": "white",
        "fontweight": "bold",
        "alpha": 0.9,
        "bbox": {"boxstyle": "round,pad=0.2", "fc": "black", "alpha": 0.35},
    }
    ax.text(5.75, 5.75, "Meridian wins\nPetal wins", **kw)
    ax.text(18.25, 5.75, "Brandon wins\nPetal wins", **kw)
    ax.text(5.75, 18.25, "Meridian wins\nNWR wins", **kw)
    ax.text(18.25, 18.25, "Brandon wins\nNWR wins", **kw)

    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels_x, fontsize=7)
    ax.set_yticks(tick_positions)
    ax.set_yticklabels(tick_labels_y, fontsize=7)

    ax.set_xlabel("Brandon (+) / Meridian (−) winning margin", fontsize=8)
    ax.set_ylabel("NWR (+) / Petal (−) winning margin", fontsize=8)
    ax.set_title(f"OG vs Pearl: {panel_label}", fontsize=10, fontweight="bold", pad=6)

# ---------------------------------------------------------------------------
# Shared color legend
# ---------------------------------------------------------------------------

legend_patches = [
    mpatches.Patch(
        color=palette[i],
        label="{} > {} > {} > {}".format(*(ABBREV[t] for t in seeding_list[i])),
    )
    for i in range(n_seedings)
]

fig.legend(
    handles=legend_patches,
    loc="lower center",
    ncol=min(5, n_seedings),
    fontsize=8.5,
    title="Seeds  1 > 2 > 3 > 4   (OG=Oak Grove  P=Petal  B=Brandon  NR=NW Rankin  Pr=Pearl)",
    title_fontsize=9,
    bbox_to_anchor=(0.5, -0.01),
    framealpha=0.9,
)

fig.suptitle(
    "Region 3-7A 2025 — Final-Week Playoff Seeding Outcomes\n"
    "Each cell shows which team earns each seed (1–4) given the winning margin in all three games",
    fontsize=13,
    fontweight="bold",
    y=1.01,
)

plt.tight_layout(rect=(0, 0.07, 1, 1))

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "final_week_scenarios.png")
plt.savefig(output_path, dpi=150, bbox_inches="tight")
print(f"\nSaved → {output_path}")
plt.close()
