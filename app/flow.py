from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from typing import Iterable, List

import pandas as pd
import psycopg2
import requests
from prefect import flow, task, get_run_logger
from prefect.deployments import Deployment
from prefect.server.schemas.schedules import CronSchedule

# -------------------------
# Config
# -------------------------

DEFAULT_URL = "https://www.misshsaa.com/2024/11/19/2025-27-football-regions/"
SOURCE_URL = os.getenv("MHSAA_SOURCE_URL", DEFAULT_URL)

DB_HOST = os.getenv("POSTGRES_HOST", "db")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "mhsaa")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

CLEAN_PHRASES = [
    r"\bHigh School\b",
    r"\bAttendance Center\b",
]
CLEAN_RE = re.compile("|".join(CLEAN_PHRASES), flags=re.IGNORECASE)
SPACE_RE = re.compile(r"\s+")


@dataclass
class RegionRow:
    school: str
    class_: int
    region: int

    def as_db_tuple(self):
        return (self.school, self.class_, self.region)


# -------------------------
# Helpers
# -------------------------

def to_normal_case(s: str) -> str:
    if not s:
        return s
    t = s.title()
    t = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), t)
    return t


def clean_school_name(raw: str) -> str:
    tmp = CLEAN_RE.sub("", raw)
    tmp = SPACE_RE.sub(" ", tmp).strip(" ,.-\u2013\u2014\t\r\n")
    return to_normal_case(tmp)


def fetch_tables(url: str) -> List[pd.DataFrame]:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return pd.read_html(resp.text)


def normalize_tables(tables: List[pd.DataFrame]) -> List[RegionRow]:
    rows: List[RegionRow] = []
    COL_ALIASES = {
        "School Name": {"School", "School Name"},
        "Class": {"Class"},
        "Region": {"Region"},
    }

    def find_col(df: pd.DataFrame, wanted: str) -> str | None:
        aliases = COL_ALIASES[wanted]
        for col in df.columns:
            if str(col).strip() in aliases:
                return col
        return None

    for df in tables:
        df.columns = [str(c).strip() for c in df.columns]

        school_col = find_col(df, "School Name")
        class_col = find_col(df, "Class")
        region_col = find_col(df, "Region")

        if not (school_col and class_col and region_col):
            continue

        for _, r in df.iterrows():
            school_raw = str(r[school_col]).strip()
            if not school_raw or school_raw.lower() in {"school name", "nan"}:
                continue
            try:
                class_ = int(str(r[class_col]).strip())
                region = int(str(r[region_col]).strip())
            except (ValueError, TypeError):
                continue

            school = clean_school_name(school_raw)
            rows.append(RegionRow(school=school, class_=class_, region=region))

    return rows


def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def insert_rows(rows: Iterable[RegionRow]) -> int:
    if not rows:
        return 0
    q = """
        INSERT INTO football_regions (school, class, region)
        VALUES (%s, %s, %s)
        ON CONFLICT (school, class, region) DO NOTHING
    """
    count = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(q, row.as_db_tuple())
                # rowcount is 1 for inserted, 0 for no-op on conflict
                count += cur.rowcount
    return count


# -------------------------
# Prefect tasks & flow
# -------------------------

@task(retries=2, retry_delay_seconds=10)
def scrape_task(url: str) -> List[RegionRow]:
    logger = get_run_logger()
    logger.info("Fetching tables from %s", url)
    tables = fetch_tables(url)
    rows = normalize_tables(tables)
    logger.info("Scraped %d rows", len(rows))
    return rows


@task
def load_task(rows: List[RegionRow]) -> int:
    logger = get_run_logger()
    inserted = insert_rows(rows)
    logger.info("Inserted %d new rows into football_regions", inserted)
    return inserted


@flow(name="mhsaa-football-regions-pipeline")
def ingest_flow(url: str = SOURCE_URL) -> int:
    rows = scrape_task(url)
    inserted = load_task(rows)
    return inserted


# -------------------------
# CLI helpers
# -------------------------

def register_deployment():
    """
    Registers a deployment on the connected Prefect server with:
      - name: daily-0700
      - queue: default
      - schedule: every day at 07:00 America/Chicago
      - infrastructure: process (runs in the worker)
    """
    deployment = Deployment.build_from_flow(
        flow=ingest_flow,
        name="daily-0700",
        parameters={"url": SOURCE_URL},
        work_queue_name="default",
        schedule=(CronSchedule(cron="0 7 * * *", timezone="America/Chicago")),
        # process infra means the worker executes this in its own environment
        # (no extra image needed). For containerized execution, you'd switch
        # to Kubernetes or Docker infra.
        tags=["mhsaa", "regions"],
    )
    deployment.apply()
    print("✅ Deployment registered: ingest_flow -> daily-0700")


def run_once():
    inserted = ingest_flow()
    print(f"✅ Flow run complete. Inserted {inserted} rows.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--register-deployment", action="store_true")
    parser.add_argument("--run-once", action="store_true")
    args = parser.parse_args()

    if args.register_deployment:
        register_deployment()
    elif args.run-once:
        run_once()
    else:
        parser.print_help()