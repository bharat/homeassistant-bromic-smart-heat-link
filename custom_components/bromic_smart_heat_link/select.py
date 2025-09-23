"""Select platform for Bromic Smart Heat Link integration."""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from .const import (
    BRIGHTNESS_LEVELS,
    CONF_CONTROLLER_TYPE,
    CONF_CONTROLLERS,
    CONF_LEARNED_BUTTONS,
    CONTROLLER_TYPE_DIMMER,
    DIMMER_BUTTONS,
    DOMAIN,
    SIGNAL_LEVEL_FMT,
    SIGNAL_LIGHT_FMT,
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
    """Set up power-level select entities for dimmer controllers."""
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

        # Only create select entities for dimmer controllers
        if controller_type == CONTROLLER_TYPE_DIMMER:
            # Create select entity for power level presets
            available_levels = []
            button_mapping = {}

            for level_info in BRIGHTNESS_LEVELS.values():
                button = level_info["button"]
                if learned_buttons.get(button, False):
                    level_name = level_info["name"]
                    available_levels.append(level_name)
                    button_mapping[level_name] = button

            if len(available_levels) > 1:  # Only create if multiple levels available
                entities.append(
                    BromicPowerLevelSelect(
                        hub=hub,
                        id_location=id_location,
                        controller_type=controller_type,
                        available_levels=available_levels,
                        button_mapping=button_mapping,
                    )
                )

    if entities:
        async_add_entities(entities)


class BromicPowerLevelSelect(BromicEntity, SelectEntity):
    """Representation of a Bromic power level select entity."""

    def __init__(
        self,
        hub: BromicHub,
        id_location: int,
        controller_type: str,
        available_levels: list[str],
        button_mapping: dict[str, int],
    ) -> None:
        """
        Initialize the select entity.

        Args:
            hub: The Bromic hub
            id_location: ID location (1-50)
            controller_type: Controller type
            available_levels: List of available power levels
            button_mapping: Mapping of level names to button codes

        """
        super().__init__(hub, id_location, controller_type, "select")

        self._available_levels = available_levels
        self._button_mapping = button_mapping

        # Select-specific attributes
        self._attr_name = "Power Level"
        self._attr_options = available_levels
        self._attr_current_option = available_levels[0] if available_levels else None

        # Update unique ID
        port_id = self._hub.port.replace("/", "_").replace(":", "_")
        self._attr_unique_id = f"{DOMAIN}_{port_id}_{id_location}_power_level"

        # Prepare dispatcher signal for syncing with light entity
        self._light_signal = SIGNAL_LEVEL_FMT.format(
            port_id=port_id, id_location=id_location
        )
        self._light_unsub = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return select specific state attributes."""
        attrs = super().extra_state_attributes
        attrs.update(
            {
                "available_levels": self._available_levels,
                "button_mapping": {
                    level: {
                        "button": button,
                        "function": DIMMER_BUTTONS[button]["name"],
                    }
                    for level, button in self._button_mapping.items()
                },
            }
        )
        return attrs

    def _on_light_state_change(self, level_name: str) -> None:
        """Handle light state changes to sync power level."""
        if level_name in self._available_levels:
            self._attr_current_option = level_name
            # Thread-safe state update (dispatcher may call from executor thread)
            self.schedule_update_ha_state()

    async def async_added_to_hass(self) -> None:
        """Connect dispatcher once hass is available."""
        await super().async_added_to_hass()
        if self.hass and self._light_unsub is None:
            self._light_unsub = async_dispatcher_connect(
                self.hass, self._light_signal, self._on_light_state_change
            )

    async def async_will_remove_from_hass(self) -> None:
        """Disconnect dispatcher on removal."""
        await super().async_will_remove_from_hass()
        if self._light_unsub is not None:
            try:
                self._light_unsub()
            finally:
                self._light_unsub = None

    async def async_select_option(self, option: str) -> None:
        """Select a power level option."""
        if option not in self._button_mapping:
            _LOGGER.error("Invalid power level option: %s", option)
            return

        button_code = self._button_mapping[option]

        _LOGGER.debug(
            "Selecting power level: %s (ID=%d, Level=%s, Button=%d)",
            self.entity_id,
            self._id_location,
            option,
            button_code,
        )

        success = await self.async_send_command(button_code)
        if success:
            self._attr_current_option = option
            # Broadcast new level to peer entities for state sync
            port_id = self._hub.port.replace("/", "_").replace(":", "_")
            level_signal = SIGNAL_LEVEL_FMT.format(
                port_id=port_id, id_location=self._id_location
            )
            light_signal = SIGNAL_LIGHT_FMT.format(
                port_id=port_id, id_location=self._id_location
            )
            async_dispatcher_send(self.hass, level_signal, option)
            async_dispatcher_send(self.hass, light_signal, option)
            self.async_write_ha_state()
