"""Database connection helpers.

Provides a psycopg2 connection factory used by scripts and pipelines.
Connection parameters are read from environment variables with sensible
Docker-compose defaults.
"""

import os

import psycopg2

# --- DATABASE CONFIG ---
DB_HOST = os.getenv("POSTGRES_HOST", "db")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "mshsfootball")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")


def get_conn(db_host: str, db_port: int, db_name: str, db_user: str, db_password: str):
    """Open and return a psycopg2 connection to the specified PostgreSQL database.

    Args:
        db_host: Hostname or IP of the PostgreSQL server.
        db_port: Port number the server is listening on.
        db_name: Name of the database to connect to.
        db_user: Database user name.
        db_password: Database user password.

    Returns:
        An open psycopg2 connection object.
    """
    return psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
    )


def get_database_connection():
    """Open a psycopg2 connection using environment-variable configuration.

    Reads ``POSTGRES_HOST``, ``POSTGRES_PORT``, ``POSTGRES_DB``,
    ``POSTGRES_USER``, and ``POSTGRES_PASSWORD`` from the environment,
    falling back to Docker-compose defaults.

    Returns:
        An open psycopg2 connection object.
    """
    conn = get_conn(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
    return conn
