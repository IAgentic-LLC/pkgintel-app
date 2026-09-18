"""Chapter 15's own real finding: `api.py`'s module-level event loop
policy fix (chapter 7's own first attempt for reorder-app) is not
enough on its own, confirmed live: launching via the bare `uvicorn
pkgintel_app.api:app` CLI still hit `psycopg.InterfaceError`, because
`uvicorn.run()` wraps its own `asyncio.run()` call, whose own loop
setup resets the policy back to Windows' default ProactorEventLoop
regardless of what was set beforehand. reorder-app's own chapter 7
already found the fix that actually works: build the event loop
directly, right after setting the policy, and hand
`uvicorn.Server.serve()` to that loop ourselves, bypassing
`uvicorn.run()`'s own loop management entirely.
"""

import asyncio
import sys

import uvicorn

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    config = uvicorn.Config("pkgintel_app.api:app", host="127.0.0.1", port=8010)
    server = uvicorn.Server(config)
    loop.run_until_complete(server.serve())
