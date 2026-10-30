"""Unit tests for backend.helpers.playoff_check: AHSFHS's playoff rows against the bracket's settled games."""

from backend.helpers.data_classes import FormatSlot
from backend.helpers.playoff_check import (
    CHAMPIONSHIP,
    PlayoffRow,
    SettledGame,
    contradictions,
    round_order,
    settled_games,
)

# A 4-team-per-half bracket (5A-7A shape): First Round, Quarterfinals, Semifinals, then the championship.
SLOTS = [
    FormatSlot(1, 1, 1, 2, 4, "N"),
    FormatSlot(2, 2, 2, 1, 3, "N"),
    FormatSlot(3, 2, 1, 1, 4, "N"),
    FormatSlot(4, 1, 2, 2, 3, "N"),
    FormatSlot(5, 3, 1, 4, 4, "S"),
    FormatSlot(6, 4, 2, 3, 3, "S"),
    FormatSlot(7, 4, 1, 3, 4, "S"),
    FormatSlot(8, 3, 2, 4, 3, "S"),
]
SEEDS = {(r, s): f"R{r}S{s}" for r in (1, 2, 3, 4) for s in (1, 2, 3, 4)}
ORDER = ["First Round", "Quarterfinals", "Semifinals", CHAMPIONSHIP]


def test_round_names_follow_the_bracket_size() -> None:
    assert round_order(SLOTS) == ORDER
    eight_per_half = [FormatSlot(i, 1, 1, 2, 2, "N" if i <= 8 else "S") for i in range(1, 17)]
    assert round_order(eight_per_half) == ["First Round", "Second Round", "Quarterfinals", "Semifinals", CHAMPIONSHIP]


def test_first_round_games_are_settled_once_both_seeds_are_known() -> None:
    games = settled_games(SLOTS, {k: v for k, v in SEEDS.items() if k != (2, 4)}, set())
    assert SettledGame("First Round", "R1S1", "R2S4", None) not in games  # 2-4 isn't known yet
    assert SettledGame("First Round", "R2S2", "R1S3", None) in games
    assert len(games) == 7  # no later round has both teams yet


def test_later_games_are_settled_once_both_feeding_games_have_a_winner() -> None:
    wins = {("R1S1", "R2S4"), ("R1S3", "R2S2")}
    games = settled_games(SLOTS, SEEDS, wins)
    assert SettledGame("First Round", "R1S1", "R2S4", "R1S1") in games
    assert SettledGame("Quarterfinals", "R1S1", "R1S3", None) in games
    assert not any(g.round == "Semifinals" for g in games)


def test_a_complete_bracket_reaches_the_championship() -> None:
    wins = set()
    for g in settled_games(SLOTS, SEEDS, set()):  # first round: home team wins
        wins.add((g.team_a, g.team_b))
    for _ in range(3):
        for g in settled_games(SLOTS, SEEDS, wins):
            if g.winner is None:
                wins.add((g.team_a, g.team_b))
    final = [g for g in settled_games(SLOTS, SEEDS, wins) if g.round == CHAMPIONSHIP]
    assert final == [SettledGame(CHAMPIONSHIP, "R1S1", "R3S1", "R1S1")]


def test_rows_that_agree_or_arent_settled_are_fine() -> None:
    wins = {("R1S1", "R2S4")}
    games = settled_games(SLOTS, SEEDS, wins)
    rows = [
        PlayoffRow("R1S1", "R2S4", "First Round", "W"),
        PlayoffRow("R2S4", "R1S1", "First Round", "L"),
        PlayoffRow("R1S1", "R1S3", "Quarterfinals", None),  # not settled yet: R1S3's game is unplayed
    ]
    assert contradictions(rows, games, ORDER) == []


def test_a_different_opponent_in_a_settled_game_is_reported() -> None:
    games = settled_games(SLOTS, SEEDS, set())
    rows = [PlayoffRow("R1S1", "R3S4", "First Round", None)]
    assert contradictions(rows, games, ORDER) == [
        "AHSFHS has R1S1 playing R3S4 in the First Round, but the bracket has R1S1 playing R2S4"
    ]


def test_a_team_playing_after_it_was_knocked_out_is_reported() -> None:
    games = settled_games(SLOTS, SEEDS, {("R2S4", "R1S1")})
    rows = [PlayoffRow("R1S1", "R1S3", "Quarterfinals", None)]
    assert contradictions(rows, games, ORDER) == [
        "AHSFHS has R1S1 playing R1S3 in the Quarterfinals, but R1S1 was knocked out in the First Round"
    ]


def test_an_unknown_round_name_is_reported() -> None:
    rows = [PlayoffRow("R1S1", "R2S4", "Round of 64", None)]
    assert contradictions(rows, [], ORDER) == ["AHSFHS lists R1S1 vs R2S4 as a playoff round named 'Round of 64'"]
