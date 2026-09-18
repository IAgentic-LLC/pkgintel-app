"""Chapter 17: chapter 15's own `ensure_tables`, a bare `CREATE TABLE
IF NOT EXISTS` run implicitly inside this app's own API process on
every single startup, was convenient bootstrapping, not a real
migration system. It has no ordering, no record of what has already
run, and no way to express the one thing a real schema change over an
existing table under real traffic actually needs answered: does this
lock it, and for how long.

Numbered, idempotent `.sql` files under `migrations/`, applied once
each, tracked in a real `schema_migrations` table, run as their own
explicit step (`scripts/migrate.py`), not smuggled into the request
path or a lifespan handler where multiple replicas starting at once
would race to run the identical DDL concurrently.

A migration file whose first line is `-- concurrent` is applied
outside a transaction block, on purpose: `CREATE INDEX CONCURRENTLY`
refuses to run inside one at all, confirmed against Postgres's own
current documentation, not assumed. Every other migration runs inside
a normal transaction, same reasoning as chapter 7's own `ensure_table`.
"""

from pathlib import Path

import psycopg

CREATE_MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


async def ensure_migrations_table(conn: psycopg.AsyncConnection) -> None:
    await conn.execute(CREATE_MIGRATIONS_TABLE_SQL)
    await conn.commit()


async def applied_versions(conn: psycopg.AsyncConnection) -> set[str]:
    async with conn.cursor() as cur:
        await cur.execute("SELECT version FROM schema_migrations")
        rows = await cur.fetchall()
    return {row[0] for row in rows}


def pending_migrations(migrations_dir: Path, applied: set[str]) -> list[Path]:
    files = sorted(migrations_dir.glob("*.sql"))
    return [f for f in files if f.stem not in applied]


async def apply_migration(conn: psycopg.AsyncConnection, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    concurrent = sql.lstrip().startswith("-- concurrent")

    if concurrent:
        await conn.set_autocommit(True)
        try:
            await conn.execute(sql)
        finally:
            await conn.set_autocommit(False)
    else:
        await conn.execute(sql)
        await conn.commit()

    async with conn.cursor() as cur:
        await cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
    await conn.commit()


async def run_migrations(conn: psycopg.AsyncConnection, migrations_dir: Path) -> list[str]:
    await ensure_migrations_table(conn)
    applied = await applied_versions(conn)
    pending = pending_migrations(migrations_dir, applied)
    for path in pending:
        await apply_migration(conn, path)
    return [p.stem for p in pending]
