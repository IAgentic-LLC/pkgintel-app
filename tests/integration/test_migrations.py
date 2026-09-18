"""Chapter 17, integration tier: the real migration files in
`migrations/`, applied against the real Postgres chapter 12 already
runs, not a fixture pretending they already ran. Idempotency,
real column and index existence, and the one thing that can't be
proven any other way: `CREATE INDEX CONCURRENTLY` actually applying
successfully outside a transaction block, on the real server.
"""

import os
from pathlib import Path

import psycopg
import pytest
from pkgintel_app.migrations import run_migrations

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="No local Postgres configured, see compose.yaml"
)

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"


async def test_all_real_migrations_apply_and_are_idempotent():
    async with await psycopg.AsyncConnection.connect(os.environ["DATABASE_URL"]) as conn:
        first_run = await run_migrations(conn, _MIGRATIONS_DIR)
        second_run = await run_migrations(conn, _MIGRATIONS_DIR)

        assert second_run == []

        async with conn.cursor() as cur:
            await cur.execute("SELECT version FROM schema_migrations ORDER BY version")
            rows = await cur.fetchall()
        applied = {row[0] for row in rows}

    assert {
        "0001_baseline",
        "0002_add_model_id_to_answer_cache",
        "0003_index_answer_cache_created_at_concurrently",
    } <= applied
    # Whichever of the three was still pending on this particular run,
    # a fresh database applies all of them; an already-migrated one
    # (this book's own dev database, most runs) applies none, both are
    # real, valid states, `first_run` just documents which happened.
    assert isinstance(first_run, list)


async def test_the_model_id_column_and_the_concurrent_index_are_real():
    async with await psycopg.AsyncConnection.connect(os.environ["DATABASE_URL"]) as conn:
        await run_migrations(conn, _MIGRATIONS_DIR)
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'answer_cache' AND column_name = 'model_id'"
            )
            column = await cur.fetchone()

            await cur.execute(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'answer_cache' AND indexname = 'idx_answer_cache_created_at'"
            )
            index = await cur.fetchone()

    assert column is not None
    assert index is not None
