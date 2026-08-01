"""
backend/utils/background_tasks.py
====================================
Safe "fire-and-forget" scheduling for asyncio coroutines.

Root-cause fix for the password-reset / verification / signup / alert
emails silently never arriving: raw `asyncio.create_task(coro)` calls
whose returned Task object isn't kept anywhere are only referenced by a
*weak* reference from the event loop. Per the official asyncio docs:

    "Important: Save a reference to the result of this function, to avoid
    a task disappearing mid-execution. The event loop only keeps weak
    references to tasks. A task that isn't referenced elsewhere may get
    garbage collected at any time, even before it's done."

In production this meant background email/alert coroutines were being
garbage-collected before they ever ran — no exception, no log, nothing
sent — because nothing in the request handler kept the Task alive after
the request context went out of scope.

`fire_and_forget()` keeps a strong reference in a module-level set until
the task completes, and logs any exception that the task raises (which
would otherwise be silently swallowed).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Coroutine

logger = logging.getLogger(__name__)

# Strong references to in-flight background tasks so they are never
# garbage-collected mid-execution.
_background_tasks: set[asyncio.Task] = set()


def fire_and_forget(coro: Coroutine, *, name: str | None = None) -> asyncio.Task:
    """
    Schedule `coro` to run in the background without blocking the caller,
    while guaranteeing it actually runs to completion (or logs its error).

    Use this instead of bare `asyncio.create_task(...)` for any
    notification / email / webhook dispatch that must not block the HTTP
    response but must still reliably execute.
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)

    def _on_done(t: asyncio.Task) -> None:
        _background_tasks.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error("Background task %s failed: %s", name or t.get_name(), exc, exc_info=exc)

    task.add_done_callback(_on_done)
    return task
