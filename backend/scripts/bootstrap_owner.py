"""One-shot script to seed the owner account.

Run once on first deploy via the ``bootstrap`` Docker Compose profile:

    docker compose --profile bootstrap up bootstrap

Reads OWNER_EMAIL and OWNER_PASSWORD from the environment, hashes the password
with passlib/bcrypt, and inserts a single owner row — but only if no owner exists
yet.  Safe to run on an already-initialized database (no-op if owner is present).
"""

import asyncio
import os

import psycopg

from backend.api.auth import hash_password


async def main() -> None:
    """Insert the owner account if one does not already exist."""
    owner_email = os.environ["OWNER_EMAIL"]
    owner_password = os.environ["OWNER_PASSWORD"]

    conninfo = (
        f"host={os.getenv('POSTGRES_HOST', 'db')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'mshsfootball')} "
        f"user={os.getenv('POSTGRES_USER', 'postgres')} "
        f"password={os.getenv('POSTGRES_PASSWORD', '')}"
    )

    async with await psycopg.AsyncConnection.connect(conninfo) as conn:
        existing = await (
            await conn.execute("SELECT id FROM users WHERE role = 'owner'")
        ).fetchone()

        if existing:
            print(f"Owner already exists (id={existing[0]}). No action taken.")
            return

        pw_hash = hash_password(owner_password)
        row = await (
            await conn.execute(
                """
                INSERT INTO users (email, password_hash, display_name, role, is_active, email_verified)
                VALUES (LOWER(%s), %s, 'Site Owner', 'owner', TRUE, TRUE)
                RETURNING id
                """,
                (owner_email, pw_hash),
            )
        ).fetchone()
        assert row is not None
        print(f"Owner account created: email={owner_email.lower()}, id={row[0]}")


if __name__ == "__main__":
    asyncio.run(main())
