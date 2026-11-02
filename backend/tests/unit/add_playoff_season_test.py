"""backend/scripts/add_playoff_season.py: the template is a valid config, bad ones are refused, and the
counts it prints are the rows actually added."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("add_playoff_season", ROOT / "backend" / "scripts" / "add_playoff_season.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)

TEMPLATE = ROOT / "sql" / "seeds" / "playoff_format_template.yaml"


def _one_class(**slot_changes) -> dict:
    """A one-class, one-slot config for 2099, with *slot_changes* applied to its slot."""
    slot = {"slot": 1, "home_region": 1, "home_seed": 1, "away_region": 2, "away_seed": 4, "north_south": "N"}
    return {"season": 2099, "classes": [{"class": 5, "num_regions": 4, "num_rounds": 4, "slots": [{**slot, **slot_changes}]}]}


def test_the_template_is_a_valid_config():
    """The YAML template shipped with the script passes validation and covers both bracket shapes."""
    cfg = script._load_config(TEMPLATE)
    script._validate(cfg)
    assert {c["class"] for c in cfg["classes"]} == {1, 5, 6, 7}


@pytest.mark.parametrize(
    ("cfg", "message"),
    [
        ({"classes": []}, "missing required keys"),
        ({"season": 2099, "classes": []}, "no classes"),
        ({"season": 2099, "classes": [{**_one_class()["classes"][0], "class": 9}]}, "Class must be 1-7"),
        ({"season": 2099, "classes": [{**_one_class()["classes"][0], "slots": []}]}, "lists no slots"),
        (_one_class(north_south="X"), "north_south must be N or S"),
    ],
)
def test_bad_configs_are_refused(cfg, message):
    """Each malformed config is refused with a message naming what's wrong."""
    with pytest.raises(ValueError, match=message):
        script._validate(cfg)


class _Cursor:
    """Counts as added only rows not seen before, like ON CONFLICT DO NOTHING."""

    def __init__(self, seen: set):
        self.seen, self.rowcount = seen, 0

    def execute(self, sql, params):
        """Note the row (table and values); it counts as added only the first time it's seen."""
        key = (sql.split()[2], params)
        self.rowcount = 0 if key in self.seen else 1
        self.seen.add(key)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Connection:
    """Stands in for a database connection, sharing one record of rows seen across its cursors."""
    def __init__(self, seen: set):
        self.seen = seen

    def cursor(self):
        """A cursor that shares this connection's record of rows seen."""
        return _Cursor(self.seen)

    def commit(self):
        """Nothing to commit: the record of rows is kept as they're executed."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_counts_are_the_rows_actually_added(monkeypatch, capsys):
    """The script reports only rows it added: a second run adds nothing and says so, and a dry run writes nothing."""
    seen: set = set()
    monkeypatch.setattr(script, "get_database_connection", lambda: _Connection(seen))
    cfg = script._load_config(TEMPLATE)
    slots = sum(len(c["slots"]) for c in cfg["classes"])
    assert script._seed(cfg, dry_run=False) == (len(cfg["classes"]), slots)
    assert "already there" not in capsys.readouterr().out
    assert script._seed(cfg, dry_run=False) == (0, 0)  # a second run adds nothing
    assert "(the rest were already there)" in capsys.readouterr().out
    assert script._seed(cfg, dry_run=True) == (0, 0)
