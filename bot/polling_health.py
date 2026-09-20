"""Health tracking for Telegram long polling."""

import asyncio
import faulthandler
import logging
import os
import sys
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from telegram import Update
from telegram.ext import BaseUpdateProcessor
from telegram.request import HTTPXRequest


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessingUpdate:
    """Sanitized description of the update currently handled by dispatcher."""

    update_id: int | None
    chat_id: int | None
    user_id: int | None
    kind: str
    detail: str | None
    started_at: float


def _describe_update(update: object, started_at: float) -> ProcessingUpdate:
    if not isinstance(update, Update):
        return ProcessingUpdate(None, None, None, type(update).__name__, None, started_at)

    chat_id = update.effective_chat.id if update.effective_chat else None
    user_id = update.effective_user.id if update.effective_user else None
    if update.callback_query:
        kind = "callback_query"
        detail = update.callback_query.data
    elif update.message:
        kind = "message"
        text = update.message.text or ""
        detail = text.split(maxsplit=1)[0] if text.startswith("/") else None
    elif update.inline_query:
        kind = "inline_query"
        detail = None
    elif update.poll:
        kind = "poll"
        detail = None
    elif update.poll_answer:
        kind = "poll_answer"
        detail = None
    else:
        kind = "other"
        detail = None
    return ProcessingUpdate(update.update_id, chat_id, user_id, kind, detail, started_at)


def _dump_all_thread_stacks() -> None:
    faulthandler.dump_traceback(file=sys.stderr, all_threads=True)


class WatchedSequentialUpdateProcessor(BaseUpdateProcessor):
    """Keep update handling sequential and restart on a wedged handler.

    Telegram polling and application update processing are separate pipelines.
    A handler can therefore wait forever while ``getUpdates`` remains healthy
    and keeps filling the queue. This processor watches the dispatcher itself.
    A daemon thread is intentional: it can still fire if synchronous code blocks
    the asyncio event loop.
    """

    __slots__ = (
        "_check_interval",
        "_clock",
        "_current",
        "_dump_threads",
        "_lock",
        "_stall_timeout",
        "_stop_event",
        "_terminate",
        "_thread",
    )

    def __init__(
        self,
        *,
        stall_timeout: float = 120.0,
        check_interval: float = 15.0,
        terminate: Callable[[int], None] = os._exit,
        clock: Callable[[], float] = time.monotonic,
        dump_threads: Callable[[], None] = _dump_all_thread_stacks,
    ) -> None:
        super().__init__(max_concurrent_updates=1)
        self._stall_timeout = stall_timeout
        self._check_interval = check_interval
        self._terminate = terminate
        self._clock = clock
        self._dump_threads = dump_threads
        self._lock = threading.Lock()
        self._current: ProcessingUpdate | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    async def initialize(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._watchdog_loop,
            name="telegram-update-watchdog",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Telegram update watchdog started: timeout=%.0fs check_interval=%.0fs",
            self._stall_timeout,
            self._check_interval,
        )

    async def shutdown(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(1.0, self._check_interval + 1.0))
        self._thread = None

    async def do_process_update(self, update: object, coroutine: Awaitable[Any]) -> None:
        current = _describe_update(update, self._clock())
        with self._lock:
            self._current = current
        try:
            await coroutine
        finally:
            elapsed = self._clock() - current.started_at
            with self._lock:
                if self._current is current:
                    self._current = None
            if elapsed >= self._check_interval:
                logger.info(
                    "UPDATE_PROCESSING_DONE update_id=%s chat_id=%s user_id=%s "
                    "kind=%s detail=%s elapsed=%.1fs",
                    current.update_id,
                    current.chat_id,
                    current.user_id,
                    current.kind,
                    current.detail,
                    elapsed,
                )

    def _check_for_stall(self, now: float | None = None) -> bool:
        with self._lock:
            current = self._current
        if current is None:
            return False
        elapsed = (self._clock() if now is None else now) - current.started_at
        if elapsed < self._stall_timeout:
            return False

        logger.critical(
            "Telegram update processing stalled: update_id=%s chat_id=%s user_id=%s "
            "kind=%s detail=%s elapsed=%.1fs; dumping stacks and terminating",
            current.update_id,
            current.chat_id,
            current.user_id,
            current.kind,
            current.detail,
            elapsed,
        )
        try:
            self._dump_threads()
        except Exception:
            logger.exception("Failed to dump thread stacks for stalled Telegram update")
        finally:
            self._terminate(1)
        return True

    def _watchdog_loop(self) -> None:
        while not self._stop_event.wait(self._check_interval):
            if self._check_for_stall():
                return


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
