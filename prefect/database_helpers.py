from __future__ import annotations

import os

import psycopg2

# --- DATABASE CONFIG ---
DB_HOST = os.getenv("POSTGRES_HOST", "db")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "mshsfootball")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")


def get_conn(DB_HOST: str, DB_PORT: int, DB_NAME: str, DB_USER: str, DB_PASSWORD: str):
    """
    Get a connection to the PostgreSQL database.
    """
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def get_database_connection():
    """
    Get a connection to the PostgreSQL database specified in the environment variables.
    """
    conn = get_conn(
        DB_HOST,
        DB_PORT,
        DB_NAME,
        DB_USER,
        DB_PASSWORD
    )
    return conn