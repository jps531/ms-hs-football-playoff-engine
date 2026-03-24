"""Scenario output tests for Region 1-3A (2025 season, pre-final-week).

Region 1-3A has two pre-determined seeds (Kossuth clinched #1, Booneville
clinched #2) and a three-way tie scenario for seeds 3–5 among Belmont,
Mantachie, and Alcorn Central.

Teams (alphabetical): Alcorn Central, Belmont, Booneville, Kossuth, Mantachie
Remaining games (cutoff 2025-10-24):
  Belmont vs Mantachie         — Belmont won 36–13, margin 23 (actual, scenario 2)
  Alcorn Central vs Kossuth    — Kossuth won 49–15, margin 34 (actual, scenario 2)

Known 2025 seeds: Kossuth / Booneville / Belmont / Alcorn Central
Eliminated: Mantachie

Code paths exercised:
  - build_scenario_atoms       — Kossuth/Booneville unconditional; Belmont seed-3 first atom
                                  is standalone [Belmont wins any] (consolidates both AC/KOS
                                  game outcomes); three-way H2H cycle (BEL>AC>MAN>BEL) resolved
                                  by H2H PD at threshold 9 on the BEL/MAN margin
  - enumerate_division_scenarios — 4 scenarios: 1a/1b (MAN upsets BEL + KOS wins, threshold 9);
                                    2 (BEL wins, non-MS, consolidates both KOS/AC outcomes);
                                    3 (MAN wins + AC upsets KOS, non-MS)
  - Three-way tie (BEL/MAN/AC at 1-3 when MAN beats BEL + KOS beats AC): perfect H2H cycle;
    H2H PDs: BEL = 12−M (capped), MAN = min(M,12)−6, AC = −6 always.
    AC always eliminated; BEL wins PD when M < 9; MAN wins PD when M ≥ 9.
  - Scenario 2 consolidation: BEL winning always produces BEL #3 / AC #4 / MAN eliminated
    regardless of the KOS/AC game result
"""

import pytest

from backend.helpers.data_classes import GameResult, RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenario_renderer import (
    division_scenarios_as_dict,
    render_team_scenarios,
    team_scenarios_as_dict,
)
from backend.helpers.scenario_viewer import build_scenario_atoms, enumerate_division_scenarios
from backend.helpers.scenarios import determine_odds, determine_scenarios
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025, expand_results, teams_from_games

# ---------------------------------------------------------------------------
# Shared fixtures (module-level, built once)
# ---------------------------------------------------------------------------

_FIXTURE = REGION_RESULTS_2025[(3, 1)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Alcorn Central, Belmont, Booneville, Kossuth, Mantachie
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining order: Belmont/Mantachie (bit 0), Alcorn Central/Kossuth (bit 1)

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(
    _TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom
)

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)
_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)

# ---------------------------------------------------------------------------
# Expected human-readable strings
# ---------------------------------------------------------------------------

KOSSUTH_EXPECTED = "Kossuth\n\nClinched #1 seed. (100.0%)"
BOONEVILLE_EXPECTED = "Booneville\n\nClinched #2 seed. (100.0%)"

ALCORN_CENTRAL_EXPECTED = """\
Alcorn Central

#3 seed if: (25.0%)
1. Mantachie beats Belmont AND Alcorn Central beats Kossuth

#4 seed if: (50.0%)
1. Belmont beats Mantachie

Eliminated if: (25.0%)
1. Mantachie beats Belmont AND Kossuth beats Alcorn Central"""

BELMONT_EXPECTED = """\
Belmont

#3 seed if: (66.7%)
1. Belmont beats Mantachie
2. Mantachie beats Belmont by 1\u20138 AND Kossuth beats Alcorn Central

#4 seed if: (8.3%)
1. Mantachie beats Belmont by 9 or more AND Kossuth beats Alcorn Central

Eliminated if: (25.0%)
1. Mantachie beats Belmont AND Alcorn Central beats Kossuth"""

MANTACHIE_EXPECTED = """\
Mantachie

#3 seed if: (8.3%)
1. Mantachie beats Belmont by 9 or more AND Kossuth beats Alcorn Central

#4 seed if: (41.7%)
1. Mantachie beats Belmont AND Alcorn Central beats Kossuth
2. Mantachie beats Belmont by 1\u20138 AND Kossuth beats Alcorn Central

Eliminated if: (50.0%)
1. Belmont beats Mantachie"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_kossuth_seed_keys():
    """Kossuth is clinched #1 unconditionally."""
    assert set(_ATOMS["Kossuth"].keys()) == {1}


def test_atoms_booneville_seed_keys():
    """Booneville is clinched #2 unconditionally."""
    assert set(_ATOMS["Booneville"].keys()) == {2}


def test_atoms_alcorn_central_seed_keys():
    """Alcorn Central can finish 3rd, 4th, or be eliminated."""
    assert set(_ATOMS["Alcorn Central"].keys()) == {3, 4, 5}


def test_atoms_belmont_seed_keys():
    """Belmont can finish 3rd, 4th, or be eliminated."""
    assert set(_ATOMS["Belmont"].keys()) == {3, 4, 5}


def test_atoms_mantachie_seed_keys():
    """Mantachie can finish 3rd, 4th, or be eliminated."""
    assert set(_ATOMS["Mantachie"].keys()) == {3, 4, 5}


def test_atoms_kossuth_unconditional():
    """Kossuth clinched #1 unconditionally — atom is [[]]."""
    assert _ATOMS["Kossuth"][1] == [[]]


def test_atoms_booneville_unconditional():
    """Booneville clinched #2 unconditionally — atom is [[]]."""
    assert _ATOMS["Booneville"][2] == [[]]


# ---------------------------------------------------------------------------
# Alcorn Central atoms
# ---------------------------------------------------------------------------


def test_atoms_ac_seed3_count():
    """AC seed-3 has exactly one atom."""
    assert len(_ATOMS["Alcorn Central"][3]) == 1


def test_atoms_ac_seed3_atom():
    """AC seed-3: MAN beats BEL (any) AND AC beats KOS (any)."""
    atom = _ATOMS["Alcorn Central"][3][0]
    assert len(atom) == 2
    gr_man = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Mantachie")
    gr_ac = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Alcorn Central")
    assert gr_man.loser == "Belmont"
    assert gr_man.min_margin == 1
    assert gr_man.max_margin is None
    assert gr_ac.loser == "Kossuth"
    assert gr_ac.min_margin == 1
    assert gr_ac.max_margin is None


def test_atoms_ac_seed4_count():
    """AC seed-4 has exactly one atom."""
    assert len(_ATOMS["Alcorn Central"][4]) == 1


def test_atoms_ac_seed4_atom():
    """AC seed-4: BEL beats MAN (any margin) — unconditional on KOS/AC game."""
    atom = _ATOMS["Alcorn Central"][4][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Belmont"
    assert gr.loser == "Mantachie"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_ac_seed5_count():
    """AC seed-5 (eliminated) has exactly one atom."""
    assert len(_ATOMS["Alcorn Central"][5]) == 1


def test_atoms_ac_seed5_atom():
    """AC eliminated: MAN beats BEL (any) AND KOS beats AC (any)."""
    atom = _ATOMS["Alcorn Central"][5][0]
    assert len(atom) == 2
    gr_man = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Mantachie")
    gr_kos = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Kossuth")
    assert gr_man.loser == "Belmont"
    assert gr_kos.loser == "Alcorn Central"


# ---------------------------------------------------------------------------
# Belmont atoms
# ---------------------------------------------------------------------------


def test_atoms_bel_seed3_count():
    """BEL seed-3 has two alternative atoms."""
    assert len(_ATOMS["Belmont"][3]) == 2


def test_atoms_bel_seed3_first_atom_standalone():
    """First BEL seed-3 atom: standalone BEL beats MAN (any margin, any KOS/AC result)."""
    atom = _ATOMS["Belmont"][3][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Belmont"
    assert gr.loser == "Mantachie"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_bel_seed3_second_atom():
    """Second BEL seed-3 atom: MAN beats BEL by 1–8 AND KOS beats AC (three-way PD)."""
    atom = _ATOMS["Belmont"][3][1]
    assert len(atom) == 2
    gr_man = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Mantachie")
    gr_kos = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Kossuth")
    assert gr_man.loser == "Belmont"
    assert gr_man.min_margin == 1
    assert gr_man.max_margin == 9  # exclusive upper bound: margins 1–8
    assert gr_kos.loser == "Alcorn Central"


def test_atoms_bel_seed4_count():
    """BEL seed-4 has exactly one atom."""
    assert len(_ATOMS["Belmont"][4]) == 1


def test_atoms_bel_seed4_atom():
    """BEL seed-4: MAN beats BEL by 9 or more AND KOS beats AC."""
    atom = _ATOMS["Belmont"][4][0]
    assert len(atom) == 2
    gr_man = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Mantachie")
    gr_kos = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Kossuth")
    assert gr_man.loser == "Belmont"
    assert gr_man.min_margin == 9
    assert gr_man.max_margin is None
    assert gr_kos.loser == "Alcorn Central"


def test_atoms_bel_seed5_count():
    """BEL seed-5 (eliminated) has exactly one atom."""
    assert len(_ATOMS["Belmont"][5]) == 1


def test_atoms_bel_seed5_atom():
    """BEL eliminated: MAN beats BEL (any) AND AC beats KOS (any)."""
    atom = _ATOMS["Belmont"][5][0]
    assert len(atom) == 2
    gr_man = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Mantachie")
    gr_ac = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Alcorn Central")
    assert gr_man.loser == "Belmont"
    assert gr_ac.loser == "Kossuth"


# ---------------------------------------------------------------------------
# Mantachie atoms
# ---------------------------------------------------------------------------


def test_atoms_man_seed3_count():
    """MAN seed-3 has exactly one atom."""
    assert len(_ATOMS["Mantachie"][3]) == 1


def test_atoms_man_seed3_atom():
    """MAN seed-3: MAN beats BEL by 9 or more AND KOS beats AC."""
    atom = _ATOMS["Mantachie"][3][0]
    assert len(atom) == 2
    gr_man = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Mantachie")
    gr_kos = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Kossuth")
    assert gr_man.loser == "Belmont"
    assert gr_man.min_margin == 9
    assert gr_man.max_margin is None
    assert gr_kos.loser == "Alcorn Central"


def test_atoms_man_seed4_count():
    """MAN seed-4 has two alternative atoms."""
    assert len(_ATOMS["Mantachie"][4]) == 2


def test_atoms_man_seed4_first_atom():
    """First MAN seed-4 atom: MAN beats BEL (any) AND AC beats KOS (any)."""
    atom = _ATOMS["Mantachie"][4][0]
    assert len(atom) == 2
    gr_man = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Mantachie")
    gr_ac = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Alcorn Central")
    assert gr_man.loser == "Belmont"
    assert gr_man.min_margin == 1
    assert gr_man.max_margin is None
    assert gr_ac.loser == "Kossuth"


def test_atoms_man_seed4_second_atom():
    """Second MAN seed-4 atom: MAN beats BEL by 1–8 AND KOS beats AC (three-way PD)."""
    atom = _ATOMS["Mantachie"][4][1]
    assert len(atom) == 2
    gr_man = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Mantachie")
    gr_kos = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Kossuth")
    assert gr_man.loser == "Belmont"
    assert gr_man.min_margin == 1
    assert gr_man.max_margin == 9  # exclusive upper bound: margins 1–8
    assert gr_kos.loser == "Alcorn Central"


def test_atoms_man_seed5_count():
    """MAN seed-5 (eliminated) has exactly one atom."""
    assert len(_ATOMS["Mantachie"][5]) == 1


def test_atoms_man_seed5_atom():
    """MAN eliminated: BEL beats MAN (any margin) — unconditional on KOS/AC game."""
    atom = _ATOMS["Mantachie"][5][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Belmont"
    assert gr.loser == "Mantachie"
    assert gr.min_margin == 1
    assert gr.max_margin is None


# ---------------------------------------------------------------------------
# Division scenarios dict
# ---------------------------------------------------------------------------


def test_div_dict_scenario_keys():
    """Division scenarios dict has exactly keys 1a, 1b, 2, 3."""
    assert set(_DIV_DICT.keys()) == {"1a", "1b", "2", "3"}


def test_div_dict_scenario1a_title():
    """Scenario 1a: MAN beats BEL by 1–8 AND KOS beats AC."""
    assert _DIV_DICT["1a"]["title"] == "Mantachie beats Belmont by 1\u20138 AND Kossuth beats Alcorn Central"


def test_div_dict_scenario1b_title():
    """Scenario 1b: MAN beats BEL by 9 or more AND KOS beats AC."""
    assert _DIV_DICT["1b"]["title"] == "Mantachie beats Belmont by 9 or more AND Kossuth beats Alcorn Central"


def test_div_dict_scenario2_title():
    """Scenario 2: BEL beats MAN (no KOS/AC mention — consolidated)."""
    assert _DIV_DICT["2"]["title"] == "Belmont beats Mantachie"


def test_div_dict_scenario3_title():
    """Scenario 3: MAN beats BEL AND AC beats KOS (non-MS)."""
    assert _DIV_DICT["3"]["title"] == "Mantachie beats Belmont AND Alcorn Central beats Kossuth"


def test_div_dict_scenario1a_seeds():
    """Scenario 1a: KOS #1, BOO #2, BEL #3, MAN #4, AC eliminated.

    In the 3-way tie (BEL/MAN/AC all 1-3), AC has the worst H2H PD (−6 always)
    and is eliminated. BEL's PD (12−M) beats MAN's PD (M−6) when M < 9, so BEL #3.
    """
    s = _DIV_DICT["1a"]
    assert s["one_seed"] == "Kossuth"
    assert s["two_seed"] == "Booneville"
    assert s["three_seed"] == "Belmont"
    assert s["four_seed"] == "Mantachie"
    assert "Alcorn Central" in s["eliminated"]


def test_div_dict_scenario1b_seeds():
    """Scenario 1b: KOS #1, BOO #2, MAN #3, BEL #4, AC eliminated.

    Same 3-way tie as 1a. MAN's H2H PD (M−6) beats BEL's (12−M) when M ≥ 9.
    AC is always eliminated (H2H PD = −6 regardless of margin).
    """
    s = _DIV_DICT["1b"]
    assert s["one_seed"] == "Kossuth"
    assert s["two_seed"] == "Booneville"
    assert s["three_seed"] == "Mantachie"
    assert s["four_seed"] == "Belmont"
    assert "Alcorn Central" in s["eliminated"]


def test_div_dict_scenario2_seeds():
    """Scenario 2: KOS #1, BOO #2, BEL #3, AC #4, MAN eliminated (actual result)."""
    s = _DIV_DICT["2"]
    assert s["one_seed"] == "Kossuth"
    assert s["two_seed"] == "Booneville"
    assert s["three_seed"] == "Belmont"
    assert s["four_seed"] == "Alcorn Central"
    assert "Mantachie" in s["eliminated"]


def test_div_dict_scenario3_seeds():
    """Scenario 3: KOS #1, BOO #2, AC #3, MAN #4, BEL eliminated."""
    s = _DIV_DICT["3"]
    assert s["one_seed"] == "Kossuth"
    assert s["two_seed"] == "Booneville"
    assert s["three_seed"] == "Alcorn Central"
    assert s["four_seed"] == "Mantachie"
    assert "Belmont" in s["eliminated"]


def test_div_dict_kossuth_always_one():
    """Kossuth is #1 seed in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert scenario["one_seed"] == "Kossuth", f"Scenario {key}: expected Kossuth #1"


def test_div_dict_booneville_always_two():
    """Booneville is #2 seed in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert scenario["two_seed"] == "Booneville", f"Scenario {key}: expected Booneville #2"


# ---------------------------------------------------------------------------
# team_scenarios_as_dict structure
# ---------------------------------------------------------------------------


def test_team_dict_kossuth_key():
    """Kossuth team dict uses numeric key 1 only."""
    assert list(_TEAM_DICT["Kossuth"].keys()) == [1]


def test_team_dict_booneville_key():
    """Booneville team dict uses numeric key 2 only."""
    assert list(_TEAM_DICT["Booneville"].keys()) == [2]


def test_team_dict_alcorn_central_keys():
    """AC team dict has keys 3, 4, and 'eliminated'."""
    assert set(_TEAM_DICT["Alcorn Central"].keys()) == {3, 4, "eliminated"}


def test_team_dict_belmont_keys():
    """BEL team dict has keys 3, 4, and 'eliminated'."""
    assert set(_TEAM_DICT["Belmont"].keys()) == {3, 4, "eliminated"}


def test_team_dict_mantachie_keys():
    """MAN team dict has keys 3, 4, and 'eliminated'."""
    assert set(_TEAM_DICT["Mantachie"].keys()) == {3, 4, "eliminated"}


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------


def test_odds_kossuth_clinched():
    """Kossuth is clinched #1 with p1=1.0."""
    o = _ODDS["Kossuth"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(1.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_booneville_clinched():
    """Booneville is clinched #2 with p2=1.0."""
    o = _ODDS["Booneville"]
    assert o.clinched is True
    assert o.p2 == pytest.approx(1.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_alcorn_central():
    """AC odds: p3=25%, p4=50%, eliminated=25%."""
    o = _ODDS["Alcorn Central"]
    assert o.clinched is False
    assert o.eliminated is False
    assert o.p3 == pytest.approx(0.25)
    assert o.p4 == pytest.approx(0.5)
    assert o.p_playoffs == pytest.approx(0.75)


def test_odds_belmont():
    """BEL odds: p3≈66.7%, p4≈8.3%, eliminated=25%."""
    o = _ODDS["Belmont"]
    assert o.clinched is False
    assert o.eliminated is False
    assert o.p3 == pytest.approx(2 / 3)
    assert o.p4 == pytest.approx(1 / 12)
    assert o.p_playoffs == pytest.approx(3 / 4)


def test_odds_mantachie():
    """MAN odds: p3≈8.3%, p4≈41.7%, eliminated=50%."""
    o = _ODDS["Mantachie"]
    assert o.clinched is False
    assert o.eliminated is False
    assert o.p3 == pytest.approx(1 / 12)
    assert o.p4 == pytest.approx(5 / 12)
    assert o.p_playoffs == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


def test_render_kossuth():
    """Kossuth renders as clinched #1 string."""
    assert render_team_scenarios("Kossuth", _ATOMS, odds=_ODDS) == KOSSUTH_EXPECTED


def test_render_booneville():
    """Booneville renders as clinched #2 string."""
    assert render_team_scenarios("Booneville", _ATOMS, odds=_ODDS) == BOONEVILLE_EXPECTED


def test_render_alcorn_central():
    """Alcorn Central renders correctly across three possible outcomes."""
    assert render_team_scenarios("Alcorn Central", _ATOMS, odds=_ODDS) == ALCORN_CENTRAL_EXPECTED


def test_render_belmont():
    """Belmont renders correctly with standalone first atom and margin-sensitive second atom."""
    assert render_team_scenarios("Belmont", _ATOMS, odds=_ODDS) == BELMONT_EXPECTED


def test_render_mantachie():
    """Mantachie renders correctly with margin-sensitive seed-3 atom."""
    assert render_team_scenarios("Mantachie", _ATOMS, odds=_ODDS) == MANTACHIE_EXPECTED
