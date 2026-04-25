"""Assign a venue to all State Championship games for a given season.

Run this after an ahsfhs_schedule_pipeline run that has ingested championship
games.  Championship games arrive with round = 'Championship Game' and
location_id = NULL; this script fills in the location_id and sets location to
'neutral'.

Usage (dry-run, shows what would change):
    uv run python backend/scripts/assign_championship_venue.py \\
        --season 2025 --location "M.M. Roberts Stadium" --dry-run

Apply:
    uv run python backend/scripts/assign_championship_venue.py \\
        --season 2025 --location "M.M. Roberts Stadium"

To restrict to one MHSAA class (1–7), add --class 4:
    uv run python backend/scripts/assign_championship_venue.py \\
        --season 2025 --location "M.M. Roberts Stadium" --class 4

The --location argument is matched against locations.name (case-insensitive
prefix match).  Use --list-locations to see all available venues.
"""

import argparse
import sys

from backend.helpers.database_helpers import get_database_connection


def _list_locations(conn) -> None:
    """Print all locations in the database as a formatted table."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, city, home_team FROM locations ORDER BY name")
        rows = cur.fetchall()
    if not rows:
        print("No locations in database.")
        return
    print(f"{'ID':>4}  {'Name':<45}  {'City':<20}  Home Team")
    print("-" * 90)
    for loc_id, name, city, home_team in rows:
        print(f"{loc_id:>4}  {name:<45}  {(city or ''):< 20}  {home_team or ''}")


def _resolve_location(conn, location_arg: str) -> tuple[int, str]:
    """Return (location_id, name) for a case-insensitive prefix match on name."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name FROM locations WHERE lower(name) LIKE lower(%s) ORDER BY id",
            (location_arg.rstrip("%") + "%",),
        )
        rows = cur.fetchall()
    if not rows:
        print(f"Error: no location found matching {location_arg!r}", file=sys.stderr)
        sys.exit(1)
    if len(rows) > 1:
        names = ", ".join(r[1] for r in rows)
        print(f"Error: ambiguous location {location_arg!r} — matched: {names}", file=sys.stderr)
        sys.exit(1)
    return rows[0]


def _find_championship_games(conn, season: int, clazz: int | None) -> list[tuple]:
    """Return (school, date, opponent, class) rows for unassigned championship games."""
    sql = """
        SELECT g.school, g.date, g.opponent, ss.class
        FROM games g
        JOIN school_seasons ss ON ss.school = g.school AND ss.season = g.season
        WHERE g.season = %s
          AND g.round = 'Championship Game'
          AND (g.location_id IS NULL OR g.overrides ? 'location_id' = FALSE)
    """
    params: list = [season]
    if clazz is not None:
        sql += " AND ss.class = %s"
        params.append(clazz)
    sql += " ORDER BY ss.class, g.date, g.school"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _apply(conn, season: int, location_id: int, clazz: int | None, dry_run: bool) -> None:
    """Set location_id and location='neutral' on all championship games matching the filters."""
    sql_find = """
        SELECT g.school, g.date
        FROM games g
        JOIN school_seasons ss ON ss.school = g.school AND ss.season = g.season
        WHERE g.season = %s
          AND g.round = 'Championship Game'
    """
    params_find: list = [season]
    if clazz is not None:
        sql_find += " AND ss.class = %s"
        params_find.append(clazz)

    sql_update = """
        UPDATE games
        SET location_id = %s, location = 'neutral'
        WHERE school = %s AND date = %s
    """

    with conn.cursor() as cur:
        cur.execute(sql_find, params_find)
        rows = cur.fetchall()

    if not rows:
        print("No championship games found matching the given filters.")
        return

    if dry_run:
        print(f"[dry-run] Would update {len(rows)} game row(s) to location_id={location_id}:")
        for school, date in rows:
            print(f"  {date}  {school}")
        return

    with conn.cursor() as cur:
        for school, date in rows:
            cur.execute(sql_update, (location_id, school, date))
    conn.commit()
    print(f"Updated {len(rows)} game row(s) to location_id={location_id}.")
    for school, date in rows:
        print(f"  {date}  {school}")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Assign a venue to all State Championship games for a season.")
    parser.add_argument("--season", type=int, help="Season year (e.g. 2025)")
    parser.add_argument("--location", help="Venue name (case-insensitive prefix match)")
    parser.add_argument(
        "--class", dest="clazz", type=int, choices=range(1, 8), help="Restrict to one MHSAA class (1–7)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing to the database")
    parser.add_argument("--list-locations", action="store_true", help="Print available locations and exit")
    args = parser.parse_args()

    if args.list_locations:
        with get_database_connection() as conn:
            _list_locations(conn)
        return

    if not args.season:
        parser.error("--season is required")
    if not args.location:
        parser.error("--location is required (or use --list-locations to browse)")

    with get_database_connection() as conn:
        location_id, location_name = _resolve_location(conn, args.location)
        print(f"Resolved location: [{location_id}] {location_name}")

        games = _find_championship_games(conn, args.season, args.clazz)
        if not games:
            print("No unassigned Championship Game rows found for the given filters.")
            return

        class_filter = f" class {args.clazz}A" if args.clazz else " all classes"
        print(f"Found {len(games)} unassigned championship game row(s) for {args.season}{class_filter}:")
        for school, date, opponent, cls in games:
            print(f"  {cls}A  {date}  {school} vs {opponent}")

        _apply(conn, args.season, location_id, args.clazz, args.dry_run)


if __name__ == "__main__":
    main()
