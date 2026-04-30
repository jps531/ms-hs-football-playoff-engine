"""One-off script to upload school logos to Cloudinary and write logo_primary to DB.

Usage:
    source .venv/bin/activate
    set -a && source .env.local && set +a
    python -m backend.scripts.seed_logos
"""

import os

import psycopg2

from backend.helpers.image_helpers import upload_logo

LOGO_DIR = "/Users/paulsullivan/Library/Mobile Documents/com~apple~CloudDocs/HailStateUnis/Sports Logos/HS"

LOGOS = {
    "Magee": f"{LOGO_DIR}/Magee.png",
    "North Forrest": f"{LOGO_DIR}/North Forrest.png",
    "Bay Springs": f"{LOGO_DIR}/Bay Springs.png",
}

conn = psycopg2.connect(
    host=os.getenv("POSTGRES_HOST", "db"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    dbname=os.getenv("POSTGRES_DB", "mshsfootball"),
    user=os.getenv("POSTGRES_USER", "postgres"),
    password=os.getenv("POSTGRES_PASSWORD", "postgres"),
)
cur = conn.cursor()

for school, path in LOGOS.items():
    public_id = upload_logo(path, school, logo_type="primary")
    print(f"{school} → uploaded as '{public_id}'")
    cur.execute("UPDATE schools SET logo_primary = %s WHERE school = %s", (public_id, school))
    print(f"  DB updated: logo_primary = '{public_id}'")

conn.commit()
cur.close()
conn.close()
print("\nDone.")
