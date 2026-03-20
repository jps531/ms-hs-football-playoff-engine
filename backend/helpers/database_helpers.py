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
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")


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


def read_region_scenarios(conn, season: int, clazz: int | str, region: int) -> dict | None:
    """Load and deserialize pre-computed scenario data from ``region_scenarios``.

    Returns a dict with keys:
    - ``remaining_games``    — list of RemainingGame instances
    - ``scenario_atoms``     — deserialized scenario_atoms dict
                               (team → seed (int) → list of atom lists)
    - ``complete_scenarios`` — deserialized list of scenario dicts
                               (output format of enumerate_division_scenarios)

    Returns None if no row exists for the given (season, class, region).

    Example usage::

        with get_database_connection() as conn:
            data = read_region_scenarios(conn, 2025, 7, 3)
            if data:
                text = render_scenarios(data["complete_scenarios"])
    """
    from backend.helpers.scenario_serializers import (
        deserialize_complete_scenarios,
        deserialize_remaining_games,
        deserialize_scenario_atoms,
    )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT remaining_games, scenario_atoms, complete_scenarios
            FROM region_scenarios
            WHERE season = %s AND class = %s AND region = %s
            """,
            (season, str(clazz), region),
        )
        row = cur.fetchone()

    if row is None:
        return None

    remaining_raw, atoms_raw, scenarios_raw = row
    return {
        "remaining_games": deserialize_remaining_games(remaining_raw),
        "scenario_atoms": deserialize_scenario_atoms(atoms_raw),
        "complete_scenarios": deserialize_complete_scenarios(scenarios_raw),
    }
