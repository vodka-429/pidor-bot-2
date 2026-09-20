from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bot.polling_health import polling_watchdog


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
