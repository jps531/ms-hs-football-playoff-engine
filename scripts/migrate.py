#!/usr/bin/env python3
"""Apply the database migrations (sql/migrations/) that haven't been applied, in order, and record each.

    scripts/migrate.py            # apply what's pending
    scripts/migrate.py --dry-run  # list what's pending, apply nothing

Run on the server from the repository's root, as part of a deploy (scripts/deploy.sh) or by hand. It runs
psql in the ``db`` container as the database owner (that container's POSTGRES_USER and POSTGRES_DB), the
way the migrations were applied by hand before.

``schema_migrations`` records what's been applied. The migrations written before it existed (BASELINE)
were applied by hand on the server, and ``sql/init.sql`` already includes them on a new database, so the
first run records them as applied without running them. Every later migration is named
``NNNN_name.sql`` (0001, 0002, ...), applied in that order, each once, and the run stops at the first
that fails. A migration must still be safe to run more than once: a new database gets its effect from
``init.sql`` and then runs it here too.

Standard library only, so it runs with the server's own Python 3.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "sql" / "migrations"
COMPOSE = ["docker", "compose", "--env-file", ".env.local", "--profile", "local-db"]
NUMBERED = re.compile(r"^(\d{4})_[a-z][a-z0-9_]*\.sql$")  # 0001_add_thing.sql: a name, not a date, after the number

# Written before schema_migrations existed: applied on the server by hand, and included in init.sql.
BASELINE = (
    "2026_10_attended_games_follow_moves.sql",
    "2026_10_date_reports.sql",
    "2026_10_final_override.sql",
    "2026_10_game_date.sql",
    "2026_10_game_id.sql",
    "2026_10_leake_central_to_leake.sql",
    "2026_10_odds_double_precision.sql",
    "2026_10_recompute_requests.sql",
    "2026_10_region_games_from_alignment.sql",
    "2026_10_region_seed_pairs.sql",
    "2026_10_region_standings_archive.sql",
    "2026_10_schema_comments.sql",
    "2026_11_one_score_per_game.sql",
    "2026_11_opponent_corrections.sql",
)

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  name        TEXT PRIMARY KEY,
  applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  baseline    BOOLEAN NOT NULL DEFAULT FALSE
);
COMMENT ON TABLE schema_migrations IS
  'Which sql/migrations files have been applied (scripts/migrate.py). baseline: recorded, not run, '
  'as one of those applied by hand before this table existed.';
"""

Psql = Callable[[str], str]


def docker_psql(sql: str) -> str:
    """Run *sql* with psql in the db container, as the database owner; return its unaligned output."""
    command = [
        *COMPOSE,
        "exec",
        "-T",
        "db",
        "sh",
        "-c",
        'psql -X -q -A -t -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
    ]
    done = subprocess.run(command, cwd=ROOT, input=sql, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise MigrationError(done.stderr.strip() or f"psql exited {done.returncode}")
    return done.stdout


class MigrationError(RuntimeError):
    """A migration (or the bookkeeping around it) failed."""


def numbered(names: list[str]) -> list[str]:
    """The migrations after BASELINE, in the order they're applied (by number). Raises on a file that
    isn't in BASELINE and isn't numbered, or on two files sharing a number."""
    later = [n for n in names if n not in BASELINE]
    wrong = [n for n in later if not NUMBERED.match(n)]
    if wrong:
        raise MigrationError(f"Name new migrations NNNN_name.sql (0001, 0002, ...): {', '.join(wrong)}")
    numbers = [NUMBERED.match(n).group(1) for n in later]
    shared = sorted({n for n in numbers if numbers.count(n) > 1})
    if shared:
        raise MigrationError(f"Two migrations share a number: {', '.join(shared)}")
    return sorted(later)


def pending(psql: Psql, files: list[str]) -> list[str]:
    """Make sure schema_migrations exists (recording BASELINE the first time) and return the numbered
    migrations not yet applied, in order."""
    order = numbered(files)
    psql(TABLE_SQL)
    applied = set(psql("SELECT name FROM schema_migrations;").split())
    if not applied:
        values = ", ".join(f"('{name}', TRUE)" for name in BASELINE)
        psql(f"INSERT INTO schema_migrations (name, baseline) VALUES {values} ON CONFLICT DO NOTHING;")
        applied = set(BASELINE)
    return [name for name in order if name not in applied]


def apply(psql: Psql, name: str, sql: str) -> None:
    """Run one migration, then record it. psql runs the file as it is (no wrapping transaction), as when
    applied by hand: some statements, like ALTER TYPE ... ADD VALUE, can't run inside one."""
    psql(sql)
    psql(f"INSERT INTO schema_migrations (name) VALUES ('{name}');")


def main(argv: list[str] | None = None, psql: Psql = docker_psql, folder: Path = MIGRATIONS) -> int:
    """Apply (or with --dry-run, list) the pending migrations; returns the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="list what's pending; apply nothing")
    args = parser.parse_args(argv)
    try:
        todo = pending(psql, sorted(p.name for p in folder.glob("*.sql")))
        if not todo:
            print("No migrations pending.")
            return 0
        for name in todo:
            if args.dry_run:
                print(f"Pending: {name}")
                continue
            print(f"Applying {name} ...", flush=True)
            apply(psql, name, (folder / name).read_text())
            print(f"Applied {name}")
    except MigrationError as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
