from __future__ import annotations

import os

from data_helpers import get_conn

# --- DATABASE CONFIG ---
DB_HOST = os.getenv("POSTGRES_HOST", "db")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "mshsfootball")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

def get_database_connection():
    """
    Get a connection to the PostgreSQL database.
    """
    conn = get_conn(
        DB_HOST,
        DB_PORT,
        DB_NAME,
        DB_USER,
        DB_PASSWORD
    )
    return conn