"""Light platform for Bromic Smart Heat Link integration."""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    BRIGHTNESS_LEVELS,
    CONF_CONTROLLER_TYPE,
    CONF_CONTROLLERS,
    CONF_LEARNED_BUTTONS,
    CONTROLLER_TYPE_DIMMER,
    DIMMER_BUTTONS,
    DOMAIN,
    OFF_BUTTON_CODE,
    SIGNAL_LEVEL_FMT,
)
from .entity import BromicEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .hub import BromicHub


_LOGGER = logging.getLogger(__name__)


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

        # Only create a single aggregate light for dimmer controllers
        # (abstract channels)
        if controller_type == CONTROLLER_TYPE_DIMMER:
            brightness_buttons = [1, 2, 3, 4]
            # Require explicitly learned Off button per configuration
            has_off = learned_buttons.get(OFF_BUTTON_CODE, False)
            has_brightness = any(
                learned_buttons.get(btn, False) for btn in brightness_buttons
            )

            if has_off and has_brightness:
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
                    (
                        "Skipping light ID%d - off/brightness not learned "
                        "(OFF=%s, Brightness=%s)"
                    ),
                    id_location,
                    has_off,
                    has_brightness,
                )

    if entities:
        async_add_entities(entities)


class BromicLight(BromicEntity, LightEntity):
    """Representation of a Bromic dimmer controller light."""

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

        # Determine available brightness levels based on learned buttons
        self._available_levels = {}
        for brightness, level_info in BRIGHTNESS_LEVELS.items():
            button = level_info["button"]
            if self._learned_buttons.get(button, False):
                self._available_levels[brightness] = level_info

        # Prepare dispatcher signal for syncing with power level select
        self._level_signal = SIGNAL_LEVEL_FMT.format(
            port_id=self._hub.port.replace("/", "_").replace(":", "_"),
            id_location=id_location,
        )
        self._level_unsub = None

    def _on_level_change(self, option: str) -> None:
        """Handle power level select changes to sync on/off state."""
        if option == "Off":
            self._attr_is_on = False
            self._attr_brightness = 0
        else:
            # Set a representative brightness when level selected
            name_to_brightness = {
                info["name"]: b for b, info in BRIGHTNESS_LEVELS.items()
            }
            self._attr_brightness = name_to_brightness.get(option, 255)
            self._attr_is_on = self._attr_brightness > 0
        # Thread-safe state update (dispatcher may call from executor thread)
        self.schedule_update_ha_state()

    async def async_added_to_hass(self) -> None:
        """Connect dispatcher once hass is available."""
        await super().async_added_to_hass()
        if self.hass and self._level_unsub is None:
            self._level_unsub = async_dispatcher_connect(
                self.hass, self._level_signal, self._on_level_change
            )

    async def async_will_remove_from_hass(self) -> None:
        """Disconnect dispatcher on removal."""
        await super().async_will_remove_from_hass()
        if self._level_unsub is not None:
            try:
                self._level_unsub()
            finally:
                self._level_unsub = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return light specific state attributes."""
        attrs = super().extra_state_attributes
        attrs.update(
            {
                "available_levels": {
                    str(brightness): info["name"]
                    for brightness, info in self._available_levels.items()
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

        # Map HA brightness (0-255) to available Bromic levels
        target_brightness = self._map_brightness_to_available(brightness)
        button = self._available_levels[target_brightness]["button"]

        _LOGGER.debug(
            "Turning ON: %s (Brightness %d -> %d, Button %d)",
            self.entity_id,
            brightness,
            target_brightness,
            button,
        )

        success = await self.async_send_command(button)
        if success:
            self._attr_is_on = True
            self._attr_brightness = target_brightness
            self.async_write_ha_state()

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn the light off."""
        if 0 in self._available_levels:
            button = self._available_levels[0]["button"]  # Off button

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

    def _map_brightness_to_available(self, brightness: int) -> int:
        """
        Map HA brightness to closest available Bromic level.

        Args:
            brightness: HA brightness (0-255)

        Returns:
            Closest available brightness level

        """
        if brightness == 0:
            return 0

        # Find closest available level
        available_brightnesses = [b for b in self._available_levels if b > 0]
        if not available_brightnesses:
            return 255  # Fallback to max if no levels available

        # Find closest match
        return min(available_brightnesses, key=lambda x: abs(x - brightness))

    async def async_dim_up(self) -> None:
        """Increase brightness using dim up button."""
        if self._learned_buttons.get(5, False):  # Dim Up button
            _LOGGER.debug("Dim UP: %s (Button 5)", self.entity_id)

            success = await self.async_send_command(5)
            if success:
                # Estimate new brightness (move to next higher level)
                current = self._attr_brightness
                available_higher = [b for b in self._available_levels if b > current]
                if available_higher:
                    self._attr_brightness = min(available_higher)
                    self._attr_is_on = True
                    self.async_write_ha_state()

    async def async_dim_down(self) -> None:
        """Decrease brightness using dim down button."""
        if self._learned_buttons.get(6, False):  # Dim Down button
            _LOGGER.debug("Dim DOWN: %s (Button 6)", self.entity_id)

            success = await self.async_send_command(6)
            if success:
                # Estimate new brightness (move to next lower level)
                current = self._attr_brightness
                available_lower = [b for b in self._available_levels if b < current]
                if available_lower:
                    new_brightness = max(available_lower)
                    self._attr_brightness = new_brightness
                    self._attr_is_on = new_brightness > 0
                    self.async_write_ha_state()
