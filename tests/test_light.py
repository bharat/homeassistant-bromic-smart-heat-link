"""Tests for `BromicLight` — the dimmer controller entity with discrete brightness levels.

Covers: brightness-to-button mapping (HA's 0-255 → 5 discrete levels),
the `_map_brightness_to_discrete` closest-match logic, turn_on / turn_off
with state updates, and the case where the off button isn't learned.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode

from custom_components.bromic_smart_heat_link.const import OFF_BUTTON_CODE
from custom_components.bromic_smart_heat_link.light import (
    DISCRETE_BRIGHTNESS_LEVELS,
    BromicLight,
)
from custom_components.bromic_smart_heat_link.protocol import BromicResponse

ALL_LEARNED = {1: True, 2: True, 3: True, 4: True, OFF_BUTTON_CODE: True}


def _make_light(
    *,
    learned: dict[int, bool] | None = None,
    send_result: BromicResponse | None = None,
) -> tuple[BromicLight, MagicMock]:
    hub = MagicMock(name="hub")
    hub.port = "/dev/ttyUSB0"
    hub.stats = {"last_success": 0.0}
    if send_result is None:
        send_result = BromicResponse(
            success=True, error_code=None, message="ok", raw_bytes=b""
        )
    hub.async_send_command = AsyncMock(return_value=send_result)

    light = BromicLight(
        hub=hub,
        id_location=7,
        controller_type="dimmer",
        learned_buttons=learned if learned is not None else ALL_LEARNED,
    )
    light.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
    return light, hub


class TestInitialState:
    def test_starts_off_with_zero_brightness(self) -> None:
        light, _ = _make_light()
        assert light.is_on is False
        assert light.brightness == 0

    def test_color_mode_is_brightness_only(self) -> None:
        light, _ = _make_light()
        assert light.color_mode == ColorMode.BRIGHTNESS
        assert light.supported_color_modes == {ColorMode.BRIGHTNESS}

    def test_assumed_state(self) -> None:
        light, _ = _make_light()
        assert light.assumed_state is True

    def test_available_brightness_levels_reflect_learned_buttons(self) -> None:
        # If only 100% and Off are learned, only those should appear.
        partial = {1: True, OFF_BUTTON_CODE: True, 2: False, 3: False, 4: False}
        light, _ = _make_light(learned=partial)
        attrs = light.extra_state_attributes
        # The key strings are stringified brightness values.
        levels = set(attrs["available_power_levels"])
        assert levels == {"0", "255"}  # Off + 100%


class TestBrightnessToButtonMapping:
    """Brightness levels map to button codes per the documented LUT."""

    def test_full_lut_when_all_buttons_learned(self) -> None:
        light, _ = _make_light()
        # 0/64/128/191/255 each maps to a button.
        assert light._brightness_to_button == {
            0: OFF_BUTTON_CODE,
            64: 4,  # 25%
            128: 3,  # 50%
            191: 2,  # 75%
            255: 1,  # 100%
        }

    def test_unlearned_buttons_dropped_from_map(self) -> None:
        partial = {1: True, OFF_BUTTON_CODE: True}  # 100% and Off only
        light, _ = _make_light(learned=partial)
        assert set(light._brightness_to_button) == {0, 255}


class TestMapBrightnessToDiscrete:
    """`_map_brightness_to_discrete` picks the closest available level."""

    def test_zero_maps_to_zero(self) -> None:
        light, _ = _make_light()
        assert light._map_brightness_to_discrete(0) == 0

    def test_exact_levels_pass_through(self) -> None:
        light, _ = _make_light()
        for level in (64, 128, 191, 255):
            assert light._map_brightness_to_discrete(level) == level

    def test_in_between_picks_closest(self) -> None:
        # 100 is between 64 and 128. Closest: 128 (distance 28 < 36).
        light, _ = _make_light()
        assert light._map_brightness_to_discrete(100) == 128
        # 90 is closer to 64 (distance 26) than to 128 (distance 38).
        assert light._map_brightness_to_discrete(90) == 64

    def test_no_levels_available_returns_max(self) -> None:
        # If nothing > 0 is learned, fallback is 255.
        only_off = {OFF_BUTTON_CODE: True, 1: False, 2: False, 3: False, 4: False}
        light, _ = _make_light(learned=only_off)
        assert light._map_brightness_to_discrete(100) == 255


class TestAsyncTurnOn:
    async def test_default_brightness_full_power(self) -> None:
        # No ATTR_BRIGHTNESS = full power → button 1.
        light, hub = _make_light()
        await light.async_turn_on()
        hub.async_send_command.assert_awaited_once_with(7, 1)
        assert light.is_on is True
        assert light.brightness == 255

    async def test_explicit_brightness_maps_to_correct_button(self) -> None:
        light, hub = _make_light()
        await light.async_turn_on(**{ATTR_BRIGHTNESS: 64})
        # 64 → 25% → button 4.
        hub.async_send_command.assert_awaited_once_with(7, 4)
        assert light.brightness == 64

    async def test_no_state_change_on_failed_response(self) -> None:
        bad = BromicResponse(
            success=False, error_code=0x02, message="Wrong command", raw_bytes=b""
        )
        light, _ = _make_light(send_result=bad)
        await light.async_turn_on()
        assert light.is_on is False
        assert light.brightness == 0

    async def test_unlearned_level_skips_send(self) -> None:
        # Only 100% learned. Request for 64 (25%) should refuse silently.
        partial = {1: True, OFF_BUTTON_CODE: True, 2: False, 3: False, 4: False}
        light, hub = _make_light(learned=partial)
        # Bypass closest-match by patching it to return an unlearned level.
        light._map_brightness_to_discrete = lambda _b: 64  # type: ignore[assignment]
        await light.async_turn_on(**{ATTR_BRIGHTNESS: 64})
        hub.async_send_command.assert_not_called()


class TestAsyncTurnOff:
    async def test_dispatches_off_button(self) -> None:
        light, hub = _make_light()
        light._attr_is_on = True
        light._attr_brightness = 255
        await light.async_turn_off()
        hub.async_send_command.assert_awaited_once_with(7, OFF_BUTTON_CODE)
        assert light.is_on is False
        assert light.brightness == 0

    async def test_no_op_when_off_button_not_learned(self) -> None:
        # 0 is removed from the brightness_to_button map when off button isn't learned.
        partial = {1: True, 2: True, 3: True, 4: True, OFF_BUTTON_CODE: False}
        light, hub = _make_light(learned=partial)
        light._attr_is_on = True
        await light.async_turn_off()
        hub.async_send_command.assert_not_called()
        # State stays on — the off command couldn't be sent.
        assert light.is_on is True


def test_discrete_brightness_levels_constant() -> None:
    # Pin the module-level mapping that documents the discrete LUT.
    assert DISCRETE_BRIGHTNESS_LEVELS == {
        0: "Off",
        64: "25",
        128: "50",
        191: "75",
        255: "100",
    }
