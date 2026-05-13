"""Tests for `BromicSwitch` — the ON/OFF controller entity.

Covers turn_on / turn_off dispatch to the right button code, the
extra_state_attributes augmentation (on_button / off_button / names),
and the "no state change on failed command" behavior.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.bromic_smart_heat_link.protocol import BromicResponse
from custom_components.bromic_smart_heat_link.switch import BromicSwitch


def _make_switch(
    *,
    on_button: int = 1,
    off_button: int = 2,
    send_result: BromicResponse | None = None,
) -> tuple[BromicSwitch, MagicMock]:
    hub = MagicMock(name="hub")
    hub.port = "/dev/ttyUSB0"
    hub.stats = {"last_success": 0.0}
    if send_result is None:
        send_result = BromicResponse(
            success=True, error_code=None, message="ok", raw_bytes=b""
        )
    hub.async_send_command = AsyncMock(return_value=send_result)

    switch = BromicSwitch(
        hub=hub,
        id_location=5,
        controller_type="onoff",
        on_button=on_button,
        off_button=off_button,
    )
    # Disable `async_write_ha_state` so we don't need an attached hass.
    switch.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
    return switch, hub


class TestInitialState:
    """A freshly-constructed switch is off, assumes its state, and reports button mappings."""

    def test_starts_off(self) -> None:
        switch, _ = _make_switch()
        assert switch.is_on is False

    def test_assumed_state_is_true(self) -> None:
        # The bridge sends no telemetry; switch state is assumed.
        switch, _ = _make_switch()
        assert switch.assumed_state is True

    def test_extra_state_attributes_includes_button_assignments(self) -> None:
        switch, _ = _make_switch(on_button=1, off_button=2)
        attrs = switch.extra_state_attributes
        assert attrs["on_button"] == 1
        assert attrs["off_button"] == 2
        assert attrs["button_names"][1] == "ON"
        assert attrs["button_names"][2] == "OFF"


class TestAsyncTurnOn:
    async def test_dispatches_on_button(self) -> None:
        switch, hub = _make_switch(on_button=1)
        await switch.async_turn_on()
        hub.async_send_command.assert_awaited_once_with(5, 1)
        assert switch.is_on is True

    async def test_does_not_flip_state_on_failed_response(self) -> None:
        bad = BromicResponse(
            success=False, error_code=0x02, message="Wrong command", raw_bytes=b""
        )
        switch, _ = _make_switch(send_result=bad)
        assert switch.is_on is False
        await switch.async_turn_on()
        # State NOT flipped — the device didn't confirm.
        assert switch.is_on is False

    async def test_kwargs_ignored(self) -> None:
        # HA may pass arbitrary kwargs (transition, etc.) — the switch should ignore them.
        switch, hub = _make_switch()
        await switch.async_turn_on(transition=1.5, extra="ignored")
        hub.async_send_command.assert_awaited_once()


class TestAsyncTurnOff:
    async def test_dispatches_off_button(self) -> None:
        switch, hub = _make_switch(on_button=1, off_button=2)
        # Pre-set to on so we can observe the flip.
        switch._attr_is_on = True
        await switch.async_turn_off()
        hub.async_send_command.assert_awaited_once_with(5, 2)
        assert switch.is_on is False

    async def test_does_not_flip_state_on_failed_response(self) -> None:
        bad = BromicResponse(
            success=False, error_code=0x02, message="Wrong command", raw_bytes=b""
        )
        switch, _ = _make_switch(send_result=bad)
        switch._attr_is_on = True
        await switch.async_turn_off()
        # Still "on" because the off command didn't take.
        assert switch.is_on is True
