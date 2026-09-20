"""Health tracking for Telegram long polling."""

import asyncio
import logging
import os
import time
from collections.abc import Callable

from telegram.request import HTTPXRequest


logger = logging.getLogger(__name__)


class TrackedHTTPXRequest(HTTPXRequest):
    """HTTPX request that records progress of the dedicated polling request."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._poll_started_at: float | None = None

    async def do_request(self, *args, **kwargs):
        self._poll_started_at = time.monotonic()
        try:
            return await super().do_request(*args, **kwargs)
        finally:
            self._poll_started_at = None

    def current_request_age(self) -> float | None:
        """Return the current request age, or ``None`` between retries."""
        if self._poll_started_at is None:
            return None
        return time.monotonic() - self._poll_started_at


async def polling_watchdog(
    request: TrackedHTTPXRequest,
    *,
    stall_timeout: float = 120.0,
    check_interval: float = 15.0,
    terminate: Callable[[int], None] = os._exit,
) -> None:
    """Terminate a process whose ``getUpdates`` transport stopped making progress.

    Normal Telegram and proxy errors complete the request and are retried by
    python-telegram-bot. The watchdog only fires while a single request itself
    remains stuck, and deliberately ignores time spent in a legitimate retry
    delay (for example after a Telegram rate limit).
    """
    logger.info(
        "Telegram polling watchdog started: timeout=%.0fs check_interval=%.0fs",
        stall_timeout,
        check_interval,
    )
    while True:
        await asyncio.sleep(check_interval)
        stalled_for = request.current_request_age()
        if stalled_for is None or stalled_for < stall_timeout:
            continue
        logger.critical(
            "Telegram polling made no progress for %.1fs; terminating for restart",
            stalled_for,
        )
        terminate(1)
        return
