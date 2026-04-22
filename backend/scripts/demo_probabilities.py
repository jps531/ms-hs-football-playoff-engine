"""Demo script showing probability outputs across all engine components."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers.data_classes import FormatSlot, StandingsOdds
from helpers.win_probability import (
    EloConfig,
    compute_in_game_win_prob,
    compute_ot_win_prob,
    make_matchup_prob_fn,
)
from helpers.bracket_home_odds import compute_bracket_advancement_odds

BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"

def header(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}\n")

def pct(p: float) -> str:
    return f"{p*100:6.1f}%"


# ---------------------------------------------------------------------------
# 1. REGION SEEDING ODDS
# ---------------------------------------------------------------------------
header("1. REGION SEEDING ODDS — 5A Region 3 (final week, 4 teams)")

# Synthetic final-week standings: 3 games left, 4 teams in a tight race
region_odds: dict[str, StandingsOdds] = {
    "Hattiesburg": StandingsOdds(
        school="Hattiesburg", p1=0.62, p2=0.28, p3=0.08, p4=0.02,
        p_playoffs=1.0, final_playoffs=1.0, clinched=True, eliminated=False,
    ),
    "Wayne County": StandingsOdds(
        school="Wayne County", p1=0.25, p2=0.45, p3=0.22, p4=0.08,
        p_playoffs=1.0, final_playoffs=1.0, clinched=True, eliminated=False,
    ),
    "West Jones": StandingsOdds(
        school="West Jones", p1=0.10, p2=0.18, p3=0.42, p4=0.22,
        p_playoffs=0.92, final_playoffs=0.92, clinched=False, eliminated=False,
    ),
    "Laurel": StandingsOdds(
        school="Laurel", p1=0.03, p2=0.09, p3=0.28, p4=0.68,
        p_playoffs=1.0, final_playoffs=1.0, clinched=True, eliminated=False,
    ),
}

print(f"  {'Team':<18} {'1st':>7} {'2nd':>7} {'3rd':>7} {'4th':>7}  {'Playoffs':>9}  Status")
print(f"  {'-'*18} {'-'*7} {'-'*7} {'-'*7} {'-'*7}  {'-'*9}  {'-'*12}")
for school, o in region_odds.items():
    status = "CLINCHED" if o.clinched else ("ELIM" if o.eliminated else f"{pct(o.final_playoffs).strip()}")
    print(f"  {school:<18} {pct(o.p1):>7} {pct(o.p2):>7} {pct(o.p3):>7} {pct(o.p4):>7}  {pct(o.p_playoffs):>9}  {status}")


# ---------------------------------------------------------------------------
# 2. ELO-BASED PRE-GAME WIN PROBABILITIES
# ---------------------------------------------------------------------------
header("2. PRE-GAME WIN PROBABILITIES (Elo)")

# 5A-calibrated Elo ratings
elo_ratings = {
    "Hattiesburg":   1580.0,   # multi-year playoff contender
    "Wayne County":  1510.0,   # solid but rebuilding
    "West Jones":    1455.0,   # middle of the pack
    "Laurel":        1390.0,   # down year
    "Oak Grove":     1620.0,   # region favorite
    "Petal":         1490.0,
}
cfg = EloConfig()

def elo_wp(team_a: str, team_b: str, hfa: bool = False) -> float:
    r_a = elo_ratings[team_a] + (cfg.hfa_points if hfa else 0)
    r_b = elo_ratings[team_b]
    return 1.0 / (1.0 + 10.0 ** ((r_b - r_a) / cfg.scale))

matchups = [
    ("Oak Grove",   "Hattiesburg",  False, "neutral site"),
    ("Oak Grove",   "Hattiesburg",  True,  "Oak Grove hosting"),
    ("Hattiesburg", "Wayne County", False, "neutral site"),
    ("Hattiesburg", "Wayne County", True,  "Hattiesburg hosting"),
    ("Wayne County","Laurel",       False, "neutral site"),
    ("Hattiesburg", "Laurel",       False, "neutral site (big mismatch)"),
]

print(f"  {'Matchup':<38} {'Elo A':>6} {'Elo B':>6} {'P(A wins)':>10}  Note")
print(f"  {'-'*38} {'-'*6} {'-'*6} {'-'*10}  {'-'*22}")
for a, b, hfa, note in matchups:
    p = elo_wp(a, b, hfa)
    print(f"  {a+' vs '+b:<38} {elo_ratings[a]:>6.0f} {elo_ratings[b]:>6.0f} {pct(p):>10}  {note}")


# ---------------------------------------------------------------------------
# 3. PLAYOFF BRACKET ADVANCEMENT ODDS
# ---------------------------------------------------------------------------
header("3. PLAYOFF BRACKET ADVANCEMENT ODDS — 5A North bracket")

# 5A format: regions 1-4 north half, each with seed 1-4
# First-round slots: home=1-seed hosts 4-seed, 2-seed hosts 3-seed (within region)
slots_5a_north = [
    # Region 1
    FormatSlot(slot=1, home_region=1, home_seed=1, away_region=1, away_seed=4, north_south="N"),
    FormatSlot(slot=2, home_region=1, home_seed=2, away_region=1, away_seed=3, north_south="N"),
    # Region 2
    FormatSlot(slot=3, home_region=2, home_seed=1, away_region=2, away_seed=4, north_south="N"),
    FormatSlot(slot=4, home_region=2, home_seed=2, away_region=2, away_seed=3, north_south="N"),
    # Region 3
    FormatSlot(slot=5, home_region=3, home_seed=1, away_region=3, away_seed=4, north_south="N"),
    FormatSlot(slot=6, home_region=3, home_seed=2, away_region=3, away_seed=3, north_south="N"),
    # Region 4
    FormatSlot(slot=7, home_region=4, home_seed=1, away_region=4, away_seed=4, north_south="N"),
    FormatSlot(slot=8, home_region=4, home_seed=2, away_region=4, away_seed=3, north_south="N"),
]

# Build matchup prob fn using our Region 3 odds + Elo ratings
seeding_odds_by_region = {3: region_odds}
# Also need placeholder odds for regions 1, 2, 4 so expected Elo is defined
for r in [1, 2, 4]:
    seeding_odds_by_region[r] = {
        f"R{r}Seed1": StandingsOdds(school=f"R{r}Seed1", p1=1.0, p2=0.0, p3=0.0, p4=0.0, p_playoffs=1.0, final_playoffs=1.0, clinched=True, eliminated=False),
        f"R{r}Seed2": StandingsOdds(school=f"R{r}Seed2", p1=0.0, p2=1.0, p3=0.0, p4=0.0, p_playoffs=1.0, final_playoffs=1.0, clinched=True, eliminated=False),
        f"R{r}Seed3": StandingsOdds(school=f"R{r}Seed3", p1=0.0, p2=0.0, p3=1.0, p4=0.0, p_playoffs=1.0, final_playoffs=1.0, clinched=True, eliminated=False),
        f"R{r}Seed4": StandingsOdds(school=f"R{r}Seed4", p1=0.0, p2=0.0, p3=0.0, p4=1.0, p_playoffs=1.0, final_playoffs=1.0, clinched=True, eliminated=False),
    }
    elo_ratings[f"R{r}Seed1"] = 1500.0 + (4 - r) * 20
    elo_ratings[f"R{r}Seed2"] = 1460.0 + (4 - r) * 20
    elo_ratings[f"R{r}Seed3"] = 1420.0 + (4 - r) * 20
    elo_ratings[f"R{r}Seed4"] = 1380.0 + (4 - r) * 20

matchup_fn = make_matchup_prob_fn(elo_ratings, seeding_odds_by_region, cfg)

bracket_odds_equal = compute_bracket_advancement_odds(3, region_odds, slots_5a_north)
bracket_odds_elo   = compute_bracket_advancement_odds(3, region_odds, slots_5a_north, matchup_fn)

print(f"  {'Team':<18}  {'QF (equal)':>10} {'QF (Elo)':>9}  {'SF (equal)':>10} {'SF (Elo)':>9}  {'Finals':>7} {'Champ':>7}")
print(f"  {'-'*18}  {'-'*10} {'-'*9}  {'-'*10} {'-'*9}  {'-'*7} {'-'*7}")
for school in region_odds:
    be = bracket_odds_equal[school]
    bl = bracket_odds_elo[school]
    print(
        f"  {school:<18}  {pct(be.quarterfinals):>10} {pct(bl.quarterfinals):>9}"
        f"  {pct(be.semifinals):>10} {pct(bl.semifinals):>9}"
        f"  {pct(bl.finals):>7} {pct(bl.champion):>7}"
    )


# ---------------------------------------------------------------------------
# 4. IN-GAME WIN PROBABILITIES (regulation)
# ---------------------------------------------------------------------------
header("4. IN-GAME WIN PROBABILITIES — Regulation (Gaussian model)")

print(f"  {'Scenario':<42} {'P0':>5} {'Margin':>7} {'Time left':>11} {'P(A wins)':>10}")
print(f"  {'-'*42} {'-'*5} {'-'*7} {'-'*11} {'-'*10}")

scenarios = [
    # (description, pregame_prob, margin, seconds_left)
    ("Kickoff, even matchup",              0.50, 0,   2880),
    ("Kickoff, A is a 65% favorite",       0.65, 0,   2880),
    ("Halftime, tied, even matchup",       0.50, 0,   1440),
    ("Halftime, tied, A favored 65%",      0.65, 0,   1440),
    ("Halftime, A up 14, even pregame",    0.50, 14,  1440),
    ("Halftime, underdog (35%) up 14",     0.35, 14,  1440),
    ("Q3 start, A up 7, favored 65%",      0.65, 7,   1440),
    ("Q4 start, A up 7, even matchup",     0.50, 7,    720),
    ("Q4 start, A down 7, favored 65%",    0.65, -7,   720),
    ("5 min left, A up 44 (mercy rule)",   0.50, 44,   300),
    ("5 min left, A up 35 (mercy start)",  0.50, 35,   300),
    ("30 sec left, A up 3",                0.50, 3,     30),
    ("30 sec left, A down 3",              0.50, -3,    30),
    ("Final whistle, A up 7",              0.50, 7,      0),
    ("Final whistle, tied (OT next)",      0.50, 0,      0),
]
for desc, p0, margin, t in scenarios:
    p = compute_in_game_win_prob(p0, margin, t)
    mins = t // 60
    secs = t % 60
    time_str = f"{mins:02d}:{secs:02d} ({t}s)"
    margin_str = f"{margin:+d}"
    print(f"  {desc:<42} {pct(p0):>5} {margin_str:>7} {time_str:>11} {pct(p):>10}")


# ---------------------------------------------------------------------------
# 5. OT WIN PROBABILITIES (after Team A's possession)
# ---------------------------------------------------------------------------
header("5. OT WIN PROBABILITIES — After Team A scores (Team B yet to possess)")

scored_margins = [0, 3, 6, 7, 8]
pregame_probs = [0.35, 0.50, 0.65]

print(f"  Team A scored margin  {'P0=35% (underdog)':>18} {'P0=50% (even)':>14} {'P0=65% (favored)':>17}")
print(f"  {'-'*22}  {'-'*18} {'-'*14} {'-'*17}")

labels = {
    0: "+0  (no score)",
    3: "+3  (field goal)",
    6: "+6  (TD, missed PAT)",
    7: "+7  (TD + 1-pt PAT)",
    8: "+8  (TD + 2-pt PAT)",
}
for margin in scored_margins:
    row = f"  {labels[margin]:<22}  "
    for p0 in pregame_probs:
        p = compute_ot_win_prob(p0, margin)
        row += f"{pct(p):>14}"
        row += "   "
    print(row)

print(f"\n  {DIM}Interpretation: P(Team A wins) after their possession, before Team B responds.{RESET}")
print(f"  {DIM}Elo-adjusted: a weak team's FG helps less than a strong team's FG.{RESET}")
