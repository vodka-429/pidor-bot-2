import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bot.polling_health import WatchedSequentialUpdateProcessor, polling_watchdog


@pytest.mark.asyncio
@pytest.mark.unit
async def test_polling_watchdog_terminates_stalled_process(caplog):
    request = SimpleNamespace(current_request_age=lambda: 121.0)
    terminate = Mock()

    await polling_watchdog(
        request,
        stall_timeout=120.0,
        check_interval=0,
        terminate=terminate,
    )

    terminate.assert_called_once_with(1)
    assert "Telegram polling made no progress" in caplog.text


@pytest.mark.asyncio
@pytest.mark.unit
async def test_update_watchdog_terminates_stalled_dispatcher(caplog):
    terminate = Mock()
    dump_threads = Mock()
    processor = WatchedSequentialUpdateProcessor(
        stall_timeout=120.0,
        check_interval=15.0,
        terminate=terminate,
        clock=lambda: 10.0,
        dump_threads=dump_threads,
    )
    release = asyncio.Event()

    async def stuck_handler():
        await release.wait()

    task = asyncio.create_task(processor.do_process_update(object(), stuck_handler()))
    await asyncio.sleep(0)

    assert processor._check_for_stall(now=129.9) is False
    assert processor._check_for_stall(now=130.0) is True
    terminate.assert_called_once_with(1)
    dump_threads.assert_called_once_with()
    assert "Telegram update processing stalled" in caplog.text

    release.set()
    await task


@pytest.mark.asyncio
@pytest.mark.unit
async def test_update_watchdog_clears_completed_update():
    terminate = Mock()
    processor = WatchedSequentialUpdateProcessor(
        terminate=terminate,
        clock=lambda: 10.0,
        dump_threads=Mock(),
    )

    async def completed_handler():
        return None

    await processor.do_process_update(object(), completed_handler())

    assert processor._check_for_stall(now=1000.0) is False
    terminate.assert_not_called()


@pytest.mark.unit
def test_update_watchdog_terminates_even_if_stack_dump_fails():
    terminate = Mock()
    processor = WatchedSequentialUpdateProcessor(
        stall_timeout=1.0,
        terminate=terminate,
        clock=lambda: 0.0,
        dump_threads=Mock(side_effect=RuntimeError("stderr unavailable")),
    )
    processor._current = SimpleNamespace(
        update_id=1,
        chat_id=-1,
        user_id=2,
        kind="callback_query",
        detail="shop_title_input_2",
        started_at=0.0,
    )

    assert processor._check_for_stall(now=1.0) is True
    terminate.assert_called_once_with(1)
