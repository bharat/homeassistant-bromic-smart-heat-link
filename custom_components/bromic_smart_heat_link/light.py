"""Light platform for Bromic Smart Heat Link integration."""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity

from .const import (
    BRIGHTNESS_LEVELS,
    CONF_CONTROLLER_TYPE,
    CONF_CONTROLLERS,
    CONF_LEARNED_BUTTONS,
    CONTROLLER_TYPE_DIMMER,
    DIMMER_BUTTONS,
    DOMAIN,
    OFF_BUTTON_CODE,
)
from .entity import BromicEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .hub import BromicHub


_LOGGER = logging.getLogger(__name__)

# Discrete brightness levels for the dimmer (0-255 mapped to power levels)
DISCRETE_BRIGHTNESS_LEVELS = {
    0: "Off",  # Off
    64: "25",  # 25%
    128: "50",  # 50%
    191: "75",  # 75%
    255: "100",  # 100%
}

# Reverse mapping for power level names to brightness
POWER_LEVEL_TO_BRIGHTNESS = {v: k for k, v in DISCRETE_BRIGHTNESS_LEVELS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bromic light entities from a config entry."""
    hub_data = hass.data[DOMAIN][config_entry.entry_id]
    hub: BromicHub = hub_data["hub"]

    entities = []
    controllers = config_entry.options.get(CONF_CONTROLLERS, {})

    for id_str, controller_info in controllers.items():
        id_location = int(id_str)
        controller_type = controller_info[CONF_CONTROLLER_TYPE]
        learned_buttons = controller_info.get(CONF_LEARNED_BUTTONS, {})
        # Normalize keys from storage (JSON) which may be strings
        with suppress(Exception):
            learned_buttons = {int(k): v for k, v in learned_buttons.items()}

        # Only create a single light for dimmer controllers
        if controller_type == CONTROLLER_TYPE_DIMMER:
            # Check if we have the required buttons learned
            required_buttons = [1, 2, 3, 4, OFF_BUTTON_CODE]  # 100%, 75%, 50%, 25%, Off
            has_required_buttons = all(
                learned_buttons.get(btn, False) for btn in required_buttons
            )

            if has_required_buttons:
                entities.append(
                    BromicLight(
                        hub=hub,
                        id_location=id_location,
                        controller_type=controller_type,
                        learned_buttons=learned_buttons,
                    )
                )
            else:
                _LOGGER.warning(
                    "Skipping light ID%d - not all required buttons learned "
                    "(100%%, 75%%, 50%%, 25%%, Off)",
                    id_location,
                )

    if entities:
        async_add_entities(entities)


class BromicLight(BromicEntity, LightEntity):
    """Representation of a Bromic dimmer controller light with discrete power levels."""

    def __init__(
        self,
        hub: BromicHub,
        id_location: int,
        controller_type: str,
        learned_buttons: dict[int, bool],
    ) -> None:
        """
        Initialize the light.

        Args:
            hub: The Bromic hub
            id_location: ID location (1-50)
            controller_type: Controller type
            learned_buttons: Dictionary of learned buttons

        """
        super().__init__(hub, id_location, controller_type, "light")

        self._learned_buttons = learned_buttons

        # Light-specific attributes
        self._attr_is_on = False
        self._attr_brightness = 0
        self._attr_assumed_state = True  # We don't get feedback from the device
        self._attr_color_mode = ColorMode.BRIGHTNESS
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

        # Name already set by base class (no channel nomenclature)
        # Keep entity name None so object_id derives from device name
        self._attr_name = None

        # Create mapping of brightness levels to button codes
        self._brightness_to_button = {}
        for brightness in DISCRETE_BRIGHTNESS_LEVELS:
            if brightness == 0:
                button = OFF_BUTTON_CODE
            else:
                # Map brightness to button (255->1, 191->2, 128->3, 64->4)
                button = BRIGHTNESS_LEVELS[brightness]["button"]

            if self._learned_buttons.get(button, False):
                self._brightness_to_button[brightness] = button

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return light specific state attributes."""
        attrs = super().extra_state_attributes
        attrs.update(
            {
                "available_power_levels": {
                    str(brightness): level_name
                    for brightness, level_name in DISCRETE_BRIGHTNESS_LEVELS.items()
                    if brightness in self._brightness_to_button
                },
                "learned_buttons": {
                    str(button): DIMMER_BUTTONS[button]["name"]
                    for button, learned in self._learned_buttons.items()
                    if learned
                },
            }
        )
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, 255)

        # Map HA brightness to closest available discrete level
        target_brightness = self._map_brightness_to_discrete(brightness)

        if target_brightness not in self._brightness_to_button:
            _LOGGER.warning(
                "Cannot set brightness %d - button not learned for %s",
                target_brightness,
                DISCRETE_BRIGHTNESS_LEVELS[target_brightness],
            )
            return

        button = self._brightness_to_button[target_brightness]

        _LOGGER.debug(
            "Turning ON: %s (Brightness %d -> %s, Button %d)",
            self.entity_id,
            brightness,
            DISCRETE_BRIGHTNESS_LEVELS[target_brightness],
            button,
        )

        success = await self.async_send_command(button)
        if success:
            self._attr_is_on = target_brightness > 0
            self._attr_brightness = target_brightness
            self.async_write_ha_state()

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn the light off."""
        if 0 in self._brightness_to_button:
            button = self._brightness_to_button[0]  # Off button

            _LOGGER.debug("Turning OFF: %s (Button %d)", self.entity_id, button)

            success = await self.async_send_command(button)
            if success:
                self._attr_is_on = False
                self._attr_brightness = 0
                self.async_write_ha_state()
        else:
            _LOGGER.warning(
                "Cannot turn off %s - OFF button not learned", self.entity_id
            )

    def _map_brightness_to_discrete(self, brightness: int) -> int:
        """
        Map HA brightness to closest available discrete level.

        Args:
            brightness: HA brightness (0-255)

        Returns:
            Closest available discrete brightness level

        """
        if brightness == 0:
            return 0

        # Find closest available discrete level
        available_brightnesses = [b for b in self._brightness_to_button if b > 0]
        if not available_brightnesses:
            return 255  # Fallback to max if no levels available

        # Find closest match
        return min(available_brightnesses, key=lambda x: abs(x - brightness))
