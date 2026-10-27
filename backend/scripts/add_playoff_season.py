"""Seed playoff_formats and playoff_format_slots for a new season.

The season's bracket structure lives in a YAML config next to the other seeds:
copy sql/seeds/playoff_format_template.yaml to sql/seeds/playoff_formats_YYYY.yaml
and fill it in. (2025 and 2026 are seeded at database creation by
sql/seeds/playoff_formats_2025.sql and _2026.sql instead.)

On the server, run it in the worker container, which has the code, sql/seeds/
and the database settings (rebuild the worker first if the config is new):

    docker compose --env-file .env.local --profile local-db exec prefect-worker \\
        python backend/scripts/add_playoff_season.py --config sql/seeds/playoff_formats_2027.yaml --dry-run

Drop --dry-run to write. Locally, the same works with the local overlay's
compose files. The database connection comes from the POSTGRES_* environment
variables (backend.helpers.database_helpers.get_database_connection).

Re-running for the same season is safe: rows already there are skipped
(ON CONFLICT DO NOTHING), and the counts printed are the rows actually added.
"""

import argparse
import sys
from pathlib import Path

import yaml

from backend.helpers.database_helpers import get_database_connection


def _load_config(path: Path) -> dict:
    """Load and parse a YAML playoff format config file."""
    with path.open() as f:
        return yaml.safe_load(f)


def _validate(cfg: dict) -> None:
    """Raise ValueError if the config is missing a key or has an impossible value."""
    missing = {"season", "classes"} - cfg.keys()
    if missing:
        raise ValueError(f"Config missing required keys: {missing}")
    if not cfg["classes"]:
        raise ValueError("Config lists no classes")
    for cls_cfg in cfg["classes"]:
        for key in ("class", "num_regions", "num_rounds", "slots"):
            if key not in cls_cfg:
                raise ValueError(f"Class config missing key '{key}': {cls_cfg}")
        if cls_cfg["class"] not in range(1, 8):
            raise ValueError(f"Class must be 1-7, got {cls_cfg['class']!r}")
        if not cls_cfg["slots"]:
            raise ValueError(f"Class {cls_cfg['class']} lists no slots")
        for slot in cls_cfg["slots"]:
            for key in ("slot", "home_region", "home_seed", "away_region", "away_seed", "north_south"):
                if key not in slot:
                    raise ValueError(f"Class {cls_cfg['class']} slot missing key '{key}': {slot}")
            if slot["north_south"] not in ("N", "S"):
                raise ValueError(f"Class {cls_cfg['class']} slot {slot['slot']}: north_south must be N or S")


def _seed(cfg: dict, dry_run: bool) -> tuple[int, int]:
    """Insert playoff_formats and playoff_format_slots rows from config.

    Returns the number of format and slot rows added (0 for rows already there).
    """
    season = cfg["season"]
    classes = cfg["classes"]

    format_rows = [
        (
            season,
            c["class"],
            c["num_regions"],
            c.get("seeds_per_region", 4),
            c["num_rounds"],
            c.get("notes", f"{c['class']}A — {c['num_regions'] * c.get('seeds_per_region', 4)}-team bracket"),
        )
        for c in classes
    ]
    total_slots = sum(len(c["slots"]) for c in classes)

    if dry_run:
        print(f"[dry-run] The config has {len(format_rows)} classes and {total_slots} slots for season {season}:")
        for r in format_rows:
            print(f"  class={r[1]}, num_regions={r[2]}, num_rounds={r[4]}")
        print("[dry-run] Nothing written; rows already in the database would be skipped.")
        return 0, 0

    format_sql = """
        INSERT INTO playoff_formats (season, class, num_regions, seeds_per_region, num_rounds, notes)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (season, class) DO NOTHING
    """
    slot_sql = """
        INSERT INTO playoff_format_slots (format_id, slot, home_region, home_seed, away_region, away_seed, north_south)
        SELECT f.id, %s, %s, %s, %s, %s, %s
        FROM playoff_formats f
        WHERE f.season = %s AND f.class = %s
        ON CONFLICT DO NOTHING
    """
    formats_added = slots_added = 0
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            for row in format_rows:
                cur.execute(format_sql, row)
                formats_added += cur.rowcount
            for cls_cfg in classes:
                for slot in cls_cfg["slots"]:
                    cur.execute(
                        slot_sql,
                        (
                            slot["slot"],
                            slot["home_region"],
                            slot["home_seed"],
                            slot["away_region"],
                            slot["away_seed"],
                            slot["north_south"],
                            season,
                            cls_cfg["class"],
                        ),
                    )
                    slots_added += cur.rowcount
        conn.commit()

    skipped = formats_added < len(format_rows) or slots_added < total_slots
    print(
        f"Season {season}: added {formats_added} of {len(format_rows)} classes and "
        f"{slots_added} of {total_slots} slots" + (" (the rest were already there)." if skipped else ".")
    )
    return formats_added, slots_added


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Seed playoff bracket format for a new season.")
    parser.add_argument("--config", required=True, type=Path, help="Path to YAML config file")
    parser.add_argument("--dry-run", action="store_true", help="Check the config and print it without writing")
    args = parser.parse_args()

    if not args.config.exists():
        print(f"Error: config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    cfg = _load_config(args.config)
    _validate(cfg)
    _seed(cfg, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
