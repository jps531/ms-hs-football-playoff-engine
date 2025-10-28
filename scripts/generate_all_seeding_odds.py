
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
generate_all_seeding_odds.py

Loops through classes (1–4) and regions (1–8), calls simulate_region_finish_odds_enum.py
for each (class, region) pair, and aggregates the "seeding odds" text output into a single file.

Usage:
  python generate_all_seeding_odds.py \
    --dsn "postgresql://USER:PASS@HOST:PORT/DB" \
    --season 2025 \
    --out all_seeding_odds.txt \
    --script simulate_region_finish_odds_enum.py

Optional filters:
  --classes 2 3
  --regions 5 6 7

Optional:
  --python /usr/bin/python3   # path to Python interpreter if needed
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

DEFAULT_CLASSES = [1, 2, 3, 4]
DEFAULT_REGIONS = [1, 2, 3, 4, 5, 6, 7, 8]

def run_simulate(script_path: Path, py_exe: str, dsn: str, season: int, clazz: int, region: int) -> str:
    """
    Calls simulate_region_finish_odds_enum.py for (class, region) and returns the seeding-odds text.
    Returns an empty string if no output / error.
    """
    with tempfile.TemporaryDirectory() as td:
        out_txt = Path(td) / "seeding_odds.txt"
        cmd = [
            py_exe, str(script_path),
            "--class", str(clazz),
            "--region", str(region),
            "--season", str(season),
            "--dsn", dsn,
            "--out-seeding", str(out_txt),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except Exception as e:
            return f"[ERROR] Failed to execute: {e}"

        # Prefer the produced text file; if missing, fall back to stderr/stdout
        if out_txt.exists():
            try:
                txt = out_txt.read_text(encoding="utf-8").strip()
                return txt
            except Exception as e:
                return f"[ERROR] Could not read output file: {e}"

        # If script printed "No teams found." or other info without creating file
        combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        combined = combined.strip()
        if combined:
            return f"[NOTE] No seeding file was created. Script output:\n{combined}"
        return ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True, help="PostgreSQL DSN for your database")
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--out", default="all_seeding_odds.txt", help="Output text file path")
    ap.add_argument("--script", default="simulate_region_finish_odds_enum.py", help="Path to simulate script")
    ap.add_argument("--python", default=sys.executable, help="Python interpreter to use")
    ap.add_argument("--classes", type=int, nargs="*", default=DEFAULT_CLASSES, help="Subset of classes to process")
    ap.add_argument("--regions", type=int, nargs="*", default=DEFAULT_REGIONS, help="Subset of regions to process")
    args = ap.parse_args()

    script_path = Path(args.script)
    if not script_path.exists():
        sys.exit(f"simulate script not found at: {script_path}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sections: List[str] = []
    for clazz in args.classes:
        for region in args.regions:
            header = f"=== Region {region}-{clazz}A ==="
            body = run_simulate(script_path, args.python, args.dsn, args.season, clazz, region)
            if not body:
                body = "No data available."
            sections.append(header + "\n" + body + "\n")

    out_path.write_text("\n".join(sections), encoding="utf-8")
    print(f"Wrote combined seeding odds: {out_path}")

if __name__ == "__main__":
    main()
