"""Tests for `BromicHub` — the serial I/O layer.

CI has no real serial hardware, so every test here mocks `serial.Serial`.
The goal is to pin down the hub's behavioral contract: connection lifecycle,
retry policy, statistics tracking, the `ConfigEntryNotReady` path used by
`async_setup_entry`, and the connection-state callback fan-out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import serial as pyserial

from custom_components.bromic_smart_heat_link.const import ACK_RESPONSE
from custom_components.bromic_smart_heat_link.exceptions import (
    BromicConnectionError,
    BromicTimeoutError,
)
from custom_components.bromic_smart_heat_link.hub import BromicHub

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def _make_fake_serial(*, response: bytes = ACK_RESPONSE) -> MagicMock:
    """Build a MagicMock that quacks like a `serial.Serial` returning `response`.

    The hub reads `in_waiting` and then calls `read(n)`. We arrange the mock so
    that the first poll returns 0 (no data yet), then enough bytes for the
    response, then 0 again.
    """
    fake = MagicMock(name="fake_serial.Serial")
    fake.is_open = True

    # Track read state across calls to in_waiting and read().
    state = {"sent": False}

    def _in_waiting() -> int:
        if not state["sent"]:
            return 0  # waiting for write to complete
        return len(response)

    type(fake).in_waiting = property(lambda _self: _in_waiting())

    def _read(n: int = 1) -> bytes:
        return response[:n]

    fake.read.side_effect = _read

    def _write(_data: bytes) -> int:
        # Flip state.sent so the next in_waiting poll reports the response
        # is available. The read loop polls in_waiting > 0 and then read()s.
        state["sent"] = True
        return len(_data)

    fake.write.side_effect = _write
    fake.flush.return_value = None
    fake.close.return_value = None
    return fake


class TestInitialization:
    """Hub starts in a clean disconnected state."""

    def test_initial_state(self, hass: HomeAssistant) -> None:
        hub = BromicHub(hass, "/dev/ttyUSB0")
        assert hub.port == "/dev/ttyUSB0"
        assert hub.connected is False

    def test_stats_returns_copy(self, hass: HomeAssistant) -> None:
        # The `stats` property must return a copy — callers shouldn't mutate live state.
        hub = BromicHub(hass, "/dev/ttyUSB0")
        snap = hub.stats
        snap["commands_sent"] = 999
        assert hub.stats["commands_sent"] == 0

    def test_stats_initial_zero(self, hass: HomeAssistant) -> None:
        hub = BromicHub(hass, "/dev/ttyUSB0")
        s = hub.stats
        assert s["commands_sent"] == 0
        assert s["commands_successful"] == 0
        assert s["commands_failed"] == 0
        assert s["connection_errors"] == 0
        assert s["last_error"] is None
        assert s["last_success"] is None


class TestConnectionCallbacks:
    """Callbacks fire on `_notify_connection_state` and survive exceptions."""

    def test_add_then_notify(self, hass: HomeAssistant) -> None:
        hub = BromicHub(hass, "/dev/ttyUSB0")
        seen: list[bool] = []
        hub.add_connection_callback(seen.append)
        hub._notify_connection_state(connected=True)
        hub._notify_connection_state(connected=False)
        assert seen == [True, False]

    def test_remove_stops_notifications(self, hass: HomeAssistant) -> None:
        hub = BromicHub(hass, "/dev/ttyUSB0")
        seen: list[bool] = []
        hub.add_connection_callback(seen.append)
        hub.remove_connection_callback(seen.append)
        hub._notify_connection_state(connected=True)
        assert seen == []

    def test_remove_callback_not_registered_is_noop(self, hass: HomeAssistant) -> None:
        # The implementation guards on `if callback in self._connection_callbacks`,
        # so removing one that was never added must not raise.
        hub = BromicHub(hass, "/dev/ttyUSB0")
        hub.remove_connection_callback(lambda _c: None)

    def test_exception_in_callback_does_not_break_fanout(
        self, hass: HomeAssistant
    ) -> None:
        hub = BromicHub(hass, "/dev/ttyUSB0")
        seen: list[bool] = []

        def bad(_c: bool) -> None:
            msg = "callback boom"
            raise RuntimeError(msg)

        hub.add_connection_callback(bad)
        hub.add_connection_callback(seen.append)
        hub._notify_connection_state(connected=True)
        # The second callback still ran despite the first one raising.
        assert seen == [True]


class TestAsyncConnect:
    """`async_connect` opens the serial port and updates state / stats / callbacks."""

    async def test_success_path(self, hass: HomeAssistant) -> None:
        hub = BromicHub(hass, "/dev/ttyUSB0")
        seen: list[bool] = []
        hub.add_connection_callback(seen.append)

        fake = _make_fake_serial()
        with patch.object(pyserial, "Serial", return_value=fake) as ctor:
            await hub.async_connect()

        assert hub.connected is True
        assert hub.stats["last_success"] is not None
        assert seen == [True]
        ctor.assert_called_once()

    async def test_idempotent_when_already_connected(self, hass: HomeAssistant) -> None:
        hub = BromicHub(hass, "/dev/ttyUSB0")
        with patch.object(pyserial, "Serial", return_value=_make_fake_serial()):
            await hub.async_connect()
            # Second call short-circuits and doesn't even touch serial.Serial.
            with patch.object(pyserial, "Serial") as ctor:
                await hub.async_connect()
                ctor.assert_not_called()
        assert hub.connected is True

    async def test_serial_failure_raises_bromic_connection_error(
        self, hass: HomeAssistant
    ) -> None:
        hub = BromicHub(hass, "/dev/ttyUSB0")
        seen: list[bool] = []
        hub.add_connection_callback(seen.append)

        with (
            patch.object(
                pyserial, "Serial", side_effect=pyserial.SerialException("nope")
            ),
            pytest.raises(BromicConnectionError),
        ):
            await hub.async_connect()

        assert hub.connected is False
        assert hub.stats["connection_errors"] == 1
        assert hub.stats["last_error"] is not None
        # The failure callback fired with connected=False.
        assert seen == [False]


class TestAsyncDisconnect:
    """`async_disconnect` is a no-op when never connected; otherwise closes."""

    async def test_disconnect_when_never_connected_is_noop(
        self, hass: HomeAssistant
    ) -> None:
        hub = BromicHub(hass, "/dev/ttyUSB0")
        # Should not raise.
        await hub.async_disconnect()
        assert hub.connected is False

    async def test_disconnect_after_connect_closes_serial(
        self, hass: HomeAssistant
    ) -> None:
        hub = BromicHub(hass, "/dev/ttyUSB0")
        fake = _make_fake_serial()
        seen: list[bool] = []
        hub.add_connection_callback(seen.append)

        with patch.object(pyserial, "Serial", return_value=fake):
            await hub.async_connect()

        await hub.async_disconnect()
        assert hub.connected is False
        fake.close.assert_called()
        # Both transitions surfaced.
        assert seen == [True, False]


class TestAsyncSendCommand:
    """Sending commands: success counts, failure-response counts, retries, and not-connected gate."""

    async def test_not_connected_raises(self, hass: HomeAssistant) -> None:
        hub = BromicHub(hass, "/dev/ttyUSB0")
        with pytest.raises(BromicConnectionError):
            await hub.async_send_command(1, 1)

    async def test_success_increments_stats(self, hass: HomeAssistant) -> None:
        hub = BromicHub(hass, "/dev/ttyUSB0")
        with patch.object(
            pyserial, "Serial", return_value=_make_fake_serial(response=ACK_RESPONSE)
        ):
            await hub.async_connect()

        response = await hub.async_send_command(1, 1)
        assert response.success is True
        s = hub.stats
        assert s["commands_sent"] == 1
        assert s["commands_successful"] == 1
        assert s["commands_failed"] == 0

    async def test_error_response_increments_failed(self, hass: HomeAssistant) -> None:
        # 'E' 0x02 0x00 = "Wrong command" error response shape.
        from custom_components.bromic_smart_heat_link.const import ERROR_COMMAND

        bad_response = bytes([ERROR_COMMAND, 0x02, 0x00])
        hub = BromicHub(hass, "/dev/ttyUSB0")
        with patch.object(
            pyserial, "Serial", return_value=_make_fake_serial(response=bad_response)
        ):
            await hub.async_connect()

        response = await hub.async_send_command(1, 1)
        assert response.success is False
        assert response.error_code == 0x02
        s = hub.stats
        # commands_sent is still incremented (we did send something).
        assert s["commands_sent"] == 1
        assert s["commands_failed"] == 1
        assert s["commands_successful"] == 0

    async def test_retries_then_raises_after_exhaustion(
        self, hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Speed up: drop the exponential backoff to zero so the test doesn't wait.
        async def _fast_sleep(_delay: float) -> None:
            return None

        monkeypatch.setattr(
            "custom_components.bromic_smart_heat_link.hub.asyncio.sleep", _fast_sleep
        )

        hub = BromicHub(hass, "/dev/ttyUSB0")
        with patch.object(pyserial, "Serial", return_value=_make_fake_serial()):
            await hub.async_connect()

        # Make the sync send path raise every time.
        with (
            patch.object(
                hub, "_send_command_sync", side_effect=BromicTimeoutError("nope")
            ),
            pytest.raises(BromicTimeoutError),
        ):
            await hub.async_send_command(1, 1, retries=2)

        # 3 attempts (initial + 2 retries) all failed.
        assert hub.stats["commands_failed"] == 3

    async def test_retry_succeeds_on_second_attempt(
        self, hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _fast_sleep(_delay: float) -> None:
            return None

        monkeypatch.setattr(
            "custom_components.bromic_smart_heat_link.hub.asyncio.sleep", _fast_sleep
        )

        hub = BromicHub(hass, "/dev/ttyUSB0")
        with patch.object(pyserial, "Serial", return_value=_make_fake_serial()):
            await hub.async_connect()

        from custom_components.bromic_smart_heat_link.protocol import BromicResponse

        ok = BromicResponse(
            success=True, error_code=None, message="ok", raw_bytes=ACK_RESPONSE
        )
        call_count = {"n": 0}

        def fake_sync(_cmd):
            call_count["n"] += 1
            if call_count["n"] == 1:
                msg = "first attempt fails"
                raise BromicTimeoutError(msg)
            return ok

        with patch.object(hub, "_send_command_sync", side_effect=fake_sync):
            resp = await hub.async_send_command(1, 1, retries=2)

        assert resp.success is True
        assert call_count["n"] == 2
        assert hub.stats["commands_failed"] == 1  # the first attempt
        assert hub.stats["commands_successful"] == 1


class TestAsyncTestConnection:
    """`async_test_connection` returns True iff a no-op command succeeds."""

    async def test_returns_false_when_not_connected(self, hass: HomeAssistant) -> None:
        hub = BromicHub(hass, "/dev/ttyUSB0")
        assert await hub.async_test_connection() is False

    async def test_returns_false_when_command_raises(
        self, hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _fast_sleep(_delay: float) -> None:
            return None

        monkeypatch.setattr(
            "custom_components.bromic_smart_heat_link.hub.asyncio.sleep", _fast_sleep
        )
        hub = BromicHub(hass, "/dev/ttyUSB0")
        with patch.object(pyserial, "Serial", return_value=_make_fake_serial()):
            await hub.async_connect()
        async_send = AsyncMock(side_effect=BromicTimeoutError("nope"))
        with patch.object(hub, "async_send_command", async_send):
            assert await hub.async_test_connection() is False
