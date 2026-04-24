"""CLI tool to seed playoff_formats and playoff_format_slots for a new season.

Usage:
    uv run python backend/scripts/add_playoff_season.py --config sql/seeds/playoff_formats_2025.yaml

The YAML config describes the bracket structure for one season.  See
sql/seeds/playoff_format_template.yaml for the format.  The script generates
idempotent SQL (ON CONFLICT DO NOTHING) and executes it against the database
configured via DATABASE_URL or the standard Postgres env vars.

Re-running for the same season is safe — rows already present are skipped.
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
    """Raise ValueError if the config is missing required keys."""
    required_top = {"season", "classes"}
    missing = required_top - cfg.keys()
    if missing:
        raise ValueError(f"Config missing required keys: {missing}")
    for cls_cfg in cfg["classes"]:
        for key in ("class", "num_regions", "seeds_per_region", "num_rounds", "slots"):
            if key not in cls_cfg:
                raise ValueError(f"Class config missing key '{key}': {cls_cfg}")
        for slot in cls_cfg["slots"]:
            for k in ("slot", "home_region", "home_seed", "away_region", "away_seed", "north_south"):
                if k not in slot:
                    raise ValueError(f"Slot missing key '{k}': {slot}")
            if slot["north_south"] not in ("N", "S"):
                raise ValueError(f"north_south must be 'N' or 'S', got: {slot['north_south']!r}")


def _seed(cfg: dict, dry_run: bool) -> None:
    """Insert playoff_formats and playoff_format_slots rows from config."""
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

    if dry_run:
        print(f"[dry-run] Would insert {len(format_rows)} playoff_formats rows for season {season}:")
        for r in format_rows:
            print(f"  class={r[1]}, num_regions={r[2]}, num_rounds={r[4]}")
        total_slots = sum(len(c["slots"]) for c in classes)
        print(f"[dry-run] Would insert {total_slots} playoff_format_slots rows.")
        return

    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(format_sql, format_rows)
            for cls_cfg in classes:
                clazz = cls_cfg["class"]
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
                            clazz,
                        ),
                    )
        conn.commit()

    total_slots = sum(len(c["slots"]) for c in classes)
    print(f"Seeded playoff format for season {season}: {len(format_rows)} classes, {total_slots} slots.")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Seed playoff bracket format for a new season.")
    parser.add_argument("--config", required=True, type=Path, help="Path to YAML config file")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be inserted without writing")
    args = parser.parse_args()

    if not args.config.exists():
        print(f"Error: config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    cfg = _load_config(args.config)
    _validate(cfg)
    _seed(cfg, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
