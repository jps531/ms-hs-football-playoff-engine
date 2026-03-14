#!/usr/bin/env python3
"""
Generate a single all_scenarios.txt for all regions across classes.

Requirements:
- psycopg (pip install 'psycopg[binary]')
- The module simulate_region_finish_odds_enum_with_scenarios.py must be importable
  (in the same directory or on PYTHONPATH). It should expose enumerate_region().

Usage:
  python enumerate_all_regions_scenarios.py \
    --season 2025 \
    --dsn "postgresql://USER:PASS@HOST:PORT/DB" \
    --outfile all_scenarios.txt
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

try:
    import psycopg
except Exception:
    print("Please install psycopg: pip install 'psycopg[binary]'")
    raise

try:
    # Import the enumeration function from your main simulator module
    from simulate_region_finish import enumerate_region
except Exception:
    print("ERROR: Could not import enumerate_region from simulate_region_finish.py")
    print("Make sure that file is in the same directory or on your PYTHONPATH.")
    raise


def main():
    """Parse CLI arguments and run enumerate_region() for every (class, region) combination.

    Reads class and region ranges from ``--classes`` and ``--regions`` flags, connects to
    PostgreSQL, and writes a single combined scenarios file with all regions appended in
    order.  A temporary file is used per region so that partial failures do not corrupt the
    combined output.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--dsn", type=str, default=os.getenv("PG_DSN", ""))
    ap.add_argument("--classes", type=str, default="5-7", help="Class range, e.g. '1-4' or '2-3' (inclusive).")
    ap.add_argument("--regions", type=str, default="1-4", help="Region range, e.g. '1-8' or '3-6' (inclusive).")
    ap.add_argument("--outfile", type=str, default="all_scenarios.txt")
    args = ap.parse_args()

    if not args.dsn:
        print("Provide --dsn or set PG_DSN env var")
        sys.exit(1)

    # Parse ranges
    def parse_range(s):
        """Convert a dash-separated inclusive range string (e.g. ``'1-4'``) to a ``range``.

        A bare integer (e.g. ``'3'``) is treated as a single-element range.

        Args:
            s: Range string in the form ``'lo-hi'`` or a single integer string.

        Returns:
            A ``range`` object covering ``[lo, hi]`` inclusive.
        """
        if "-" in s:
            lo, hi = s.split("-", 1)
            return range(int(lo), int(hi) + 1)
        else:
            v = int(s)
            return range(v, v + 1)

    class_range = parse_range(args.classes)
    region_range = parse_range(args.regions)

    out_path = Path(args.outfile)
    # Clear file first
    out_path.write_text("")

    with psycopg.connect(args.dsn) as conn:
        for clazz in class_range:
            for region in region_range:
                # Create a temp scenarios file per (class,region)
                with tempfile.NamedTemporaryFile("w+", delete=False, suffix=f".sc_{clazz}_{region}.txt") as tf:
                    temp_name = tf.name
                try:
                    print(f"Processing Class {clazz}, Region {region} ...")
                    # Run enumeration; we only need scenarios
                    enumerate_region(
                        conn,
                        clazz,
                        region,
                        args.season,
                        out_seeding=None,
                        out_scenarios=temp_name,
                    )
                    # Append to combined file with a separating newline
                    with open(temp_name) as f_in, open(out_path, "a") as f_out:
                        content = f_in.read().rstrip()
                        if content:
                            # Ensure clear section separation
                            if out_path.stat().st_size > 0:
                                f_out.write("\n")
                            f_out.write(content)
                            f_out.write("\n")
                finally:
                    try:
                        os.remove(temp_name)
                    except Exception:
                        pass

    print(f"Wrote combined scenarios to: {out_path}")


if __name__ == "__main__":
    main()
