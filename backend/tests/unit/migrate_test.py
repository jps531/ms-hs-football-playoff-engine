"""scripts/migrate.py: applies each pending migration once, in order, records it, and stops at a failure;
the migrations from before schema_migrations existed are recorded, not run."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location("migrate", ROOT / "scripts" / "migrate.py")
migrate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(migrate)


class FakeDb:
    """A stand-in for psql: keeps schema_migrations' names, logs every migration body it runs."""

    def __init__(self, applied=(), fail_on=None):
        self.applied = list(applied)
        self.ran: list[str] = []
        self.fail_on = fail_on

    def __call__(self, sql: str) -> str:
        """Answer the runner's statements; run (log) anything else as a migration."""
        if sql.startswith("\nCREATE TABLE IF NOT EXISTS schema_migrations"):
            return ""
        if sql.startswith("SELECT name FROM schema_migrations"):
            return "\n".join(self.applied)
        if sql.startswith("INSERT INTO schema_migrations (name, baseline)"):
            self.applied += list(migrate.BASELINE)
            return ""
        if sql.startswith("INSERT INTO schema_migrations (name)"):
            self.applied.append(sql.split("'")[1])
            return ""
        if self.fail_on and self.fail_on in sql:
            raise migrate.MigrationError("ERROR: boom")
        self.ran.append(sql)
        return ""


def _folder(tmp_path, *names):
    """A migrations folder with BASELINE's files and *names*, each file's body its own name."""
    for name in (*migrate.BASELINE, *names):
        (tmp_path / name).write_text(f"-- {name}\n")
    return tmp_path


def test_the_baseline_is_every_migration_in_the_repository_today():
    """Every file in sql/migrations is in BASELINE or numbered (a misnamed new one fails here, in CI)."""
    files = sorted(p.name for p in (ROOT / "sql" / "migrations").glob("*.sql"))
    assert set(migrate.BASELINE) <= set(files)
    migrate.numbered(files)  # raises on a misnamed file or a shared number


def test_the_first_run_records_the_baseline_without_running_it_then_runs_the_new_ones_in_order(tmp_path):
    db = FakeDb()
    folder = _folder(tmp_path, "0002_second.sql", "0001_first.sql")
    assert migrate.main([], psql=db, folder=folder) == 0
    assert db.ran == ["-- 0001_first.sql\n", "-- 0002_second.sql\n"]
    assert db.applied[-2:] == ["0001_first.sql", "0002_second.sql"] and set(migrate.BASELINE) <= set(db.applied)


def test_a_later_run_applies_only_whats_new(tmp_path):
    db = FakeDb(applied=[*migrate.BASELINE, "0001_first.sql"])
    folder = _folder(tmp_path, "0001_first.sql", "0002_second.sql")
    assert migrate.main([], psql=db, folder=folder) == 0
    assert db.ran == ["-- 0002_second.sql\n"]
    assert migrate.main([], psql=db, folder=folder) == 0 and len(db.ran) == 1  # nothing left


def test_a_failure_stops_the_run_and_isnt_recorded(tmp_path, capsys):
    db = FakeDb(applied=list(migrate.BASELINE), fail_on="0001_first")
    folder = _folder(tmp_path, "0001_first.sql", "0002_second.sql")
    assert migrate.main([], psql=db, folder=folder) == 1
    assert db.ran == [] and "0001_first.sql" not in db.applied
    assert "Migration failed: ERROR: boom" in capsys.readouterr().err


def test_a_dry_run_lists_and_applies_nothing(tmp_path, capsys):
    db = FakeDb(applied=list(migrate.BASELINE))
    assert migrate.main(["--dry-run"], psql=db, folder=_folder(tmp_path, "0001_first.sql")) == 0
    assert db.ran == [] and "Pending: 0001_first.sql" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("names", "message"),
    [
        (["2026_12_new_thing.sql"], "Name new migrations NNNN_name.sql"),
        (["0003_a.sql", "0003_b.sql"], "Two migrations share a number: 0003"),
    ],
)
def test_misnamed_or_clashing_migrations_stop_before_anything_runs(tmp_path, names, message, capsys):
    db = FakeDb(applied=list(migrate.BASELINE))
    assert migrate.main([], psql=db, folder=_folder(tmp_path, *names)) == 1
    assert db.ran == [] and message in capsys.readouterr().err


def test_it_runs_as_a_program_the_way_the_server_and_deploy_sh_call_it():
    """`scripts/migrate.py` on its own (not `python3 scripts/migrate.py`): it needs its #! line and the
    executable bit, or the shell runs it as a shell script."""
    import os
    import subprocess

    script = ROOT / "scripts" / "migrate.py"
    assert os.access(script, os.X_OK)
    done = subprocess.run([str(script), "--help"], capture_output=True, text=True, check=False)
    assert done.returncode == 0 and "--dry-run" in done.stdout, done.stderr


def test_every_executable_script_names_its_interpreter():
    """A script with the executable bit starts with #!, so running it directly runs the right program."""
    import os

    for script in sorted((ROOT / "scripts").iterdir()):
        if script.is_file() and os.access(script, os.X_OK):
            assert script.read_text().startswith("#!"), script.name
