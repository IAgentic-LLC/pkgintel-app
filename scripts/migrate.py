"""Chapter 17: the real deploy step chapter 15's own `ensure_tables`
call was never supposed to be. Run this once, before a new version of
this app starts taking real traffic, `uv run python scripts/migrate.py`,
not implicitly, every time any one process happens to boot.
"""

import asyncio
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from pkgintel_app.migrations import run_migrations  # noqa: E402

load_dotenv()

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


async def main() -> None:
    async with await psycopg.AsyncConnection.connect(os.environ["DATABASE_URL"]) as conn:
        applied = await run_migrations(conn, MIGRATIONS_DIR)
    if applied:
        print(f"Applied {len(applied)} migration(s): {', '.join(applied)}")
    else:
        print("No pending migrations.")


if __name__ == "__main__":
    asyncio.run(main())
