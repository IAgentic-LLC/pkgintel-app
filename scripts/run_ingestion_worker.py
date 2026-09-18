"""Chapter 12's worker process: SAQ's cron, not a human, calling
`sync_all_tenants` on a real schedule. `load_dotenv()` before importing
anything that reads `DATABASE_URL` (chapter 6's lesson), and the
Windows event-loop policy set before SAQ's own runner builds its loop
(chapter 7/9's fix, the same shape, applied here on purpose, not
rediscovered).
"""

import asyncio
import sys

from dotenv import load_dotenv
from saq.runner import start

load_dotenv()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    start("pkgintel_app.ingestion_schedule.settings")
