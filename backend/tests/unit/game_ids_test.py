"""Unit tests for backend.helpers.game_ids: which rows are one game, and the game_id changes that say so."""

from datetime import date
from itertools import count

from backend.helpers.game_ids import GameIdChange, GameRow, assign_game_ids, pair_rows

D = date(2026, 10, 23)


def _row(school, day, opponent, game_id):
    return GameRow(school, date(2026, 10, day), opponent, game_id)


def _ids(start=100):
    return count(start).__next__


def test_rows_dated_a_day_apart_are_one_game():
    rows = [_row("A", 23, "B", 1), _row("B", 22, "A", 2)]
    assert pair_rows(rows) == {("A", D): ("B", date(2026, 10, 22)), ("B", date(2026, 10, 22)): ("A", D)}


def test_rows_more_than_three_days_apart_are_different_games():
    """A playoff rematch weeks later is its own game."""
    assert pair_rows([_row("A", 2, "B", 1), _row("B", 23, "A", 2)]) == {}


def test_a_row_pairs_only_with_a_row_naming_it_as_the_opponent():
    assert pair_rows([_row("A", 23, "B", 1), _row("B", 23, "C", 2)]) == {}


def test_the_nearest_row_wins_then_the_later_one():
    rows = [_row("A", 23, "B", 1), _row("B", 21, "A", 2), _row("B", 24, "A", 3)]
    assert pair_rows(rows)[("A", D)] == ("B", date(2026, 10, 24))


def test_only_mutual_nearest_rows_pair():
    """B's 10-21 row's nearest A row is 10-20, so A's 10-23 row is left unpaired."""
    rows = [_row("A", 20, "B", 1), _row("A", 23, "B", 2), _row("B", 21, "A", 3)]
    assert pair_rows(rows) == {
        ("A", date(2026, 10, 20)): ("B", date(2026, 10, 21)),
        ("B", date(2026, 10, 21)): ("A", date(2026, 10, 20)),
    }


def test_a_new_row_joins_its_partners_id():
    """The opponent's row arrives later with a fresh id; it takes the older one."""
    rows = [_row("A", 23, "B", 5), _row("B", 23, "A", 9)]
    assert assign_game_ids(rows, _ids()) == [GameIdChange("B", D, 9, 5)]


def test_rows_already_paired_change_nothing():
    rows = [_row("A", 23, "B", 5), _row("B", 22, "A", 5), _row("A", 30, "C", 6)]
    assert assign_game_ids(rows, _ids()) == []


def test_rows_that_stop_being_one_game_split_and_one_keeps_the_id():
    """AHSFHS changed A's opponent: A and B no longer pair, so one of them needs a new id."""
    rows = [_row("A", 23, "C", 5), _row("B", 23, "A", 5)]
    assert assign_game_ids(rows, _ids()) == [GameIdChange("B", D, 5, 100)]


def test_a_game_keeps_the_id_more_of_its_rows_hold():
    """Three rows hold id 5 but only A and B pair: they keep it, and C gets a new one."""
    rows = [_row("A", 23, "B", 5), _row("B", 23, "A", 5), _row("C", 23, "A", 5)]
    changes = assign_game_ids(rows, _ids())
    assert changes == [GameIdChange("C", D, 5, 100)]


def test_every_game_ends_with_its_own_id():
    rows = [
        _row("A", 23, "B", 1),
        _row("B", 22, "A", 2),
        _row("C", 23, "D", 2),
        _row("D", 23, "C", 3),
        _row("E", 23, "Out of State", 3),
    ]
    changes = {(c.school, c.date): c.new for c in assign_game_ids(rows, _ids())}
    final = {r.key: changes.get(r.key, r.game_id) for r in rows}
    games = [{final[("A", D)], final[("B", date(2026, 10, 22))]}, {final[("C", D)], final[("D", D)]}, {final[("E", D)]}]
    assert all(len(g) == 1 for g in games)
    assert len({g.pop() for g in games}) == 3
