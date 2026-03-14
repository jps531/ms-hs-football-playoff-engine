from __future__ import annotations

import os

import psycopg2

# --- DATABASE CONFIG ---
DB_HOST = os.getenv("POSTGRES_HOST", "db")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "mshsfootball")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")


def get_conn(db_host: str, db_port: int, db_name: str, db_user: str, db_password: str):
    """
    Get a connection to the PostgreSQL database.
    """
    return psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
    )


def get_database_connection():
    """
    Get a connection to the PostgreSQL database specified in the environment variables.
    """
    conn = get_conn(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
    return conn
