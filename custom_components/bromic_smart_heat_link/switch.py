"""Switch platform for Bromic Smart Heat Link integration."""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity

from .const import (
    CONF_CONTROLLER_TYPE,
    CONF_CONTROLLERS,
    CONF_LEARNED_BUTTONS,
    CONTROLLER_TYPE_ONOFF,
    DOMAIN,
    ONOFF_BUTTONS,
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
    """Set up Bromic switch entities from a config entry."""
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

        # Only create a single aggregate switch for ON/OFF controllers
        if controller_type == CONTROLLER_TYPE_ONOFF:
            on_button, off_button = 1, 2
            if learned_buttons.get(on_button) and learned_buttons.get(off_button):
                entities.append(
                    BromicSwitch(
                        hub=hub,
                        id_location=id_location,
                        controller_type=controller_type,
                        on_button=on_button,
                        off_button=off_button,
                    )
                )
            else:
                _LOGGER.warning(
                    (
                        "Skipping switch ID%d - required buttons not learned "
                        "(ON=%d, OFF=%d)"
                    ),
                    id_location,
                    on_button,
                    off_button,
                )

    if entities:
        async_add_entities(entities)


class BromicSwitch(BromicEntity, SwitchEntity):
    """Representation of a Bromic ON/OFF controller switch."""

    def __init__(
        self,
        hub: BromicHub,
        id_location: int,
        controller_type: str,
        on_button: int,
        off_button: int,
    ) -> None:
        """
        Initialize the switch.

        Args:
            hub: The Bromic hub
            id_location: ID location (1-50)
            controller_type: Controller type
            on_button: Button code for turning ON
            off_button: Button code for turning OFF

        """
        super().__init__(hub, id_location, controller_type, "switch")

        self._on_button = on_button
        self._off_button = off_button

        # Switch-specific attributes
        self._attr_is_on = False
        self._attr_assumed_state = True  # We don't get feedback from the device

        # Name already set by base class (no channel)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return switch specific state attributes."""
        attrs = super().extra_state_attributes
        attrs.update(
            {
                "on_button": self._on_button,
                "off_button": self._off_button,
                "button_names": {
                    self._on_button: ONOFF_BUTTONS[self._on_button]["name"],
                    self._off_button: ONOFF_BUTTONS[self._off_button]["name"],
                },
            }
        )
        return attrs

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn the switch on."""
        _LOGGER.debug("Turning ON: %s (Button %d)", self.entity_id, self._on_button)

        success = await self.async_send_command(self._on_button)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.debug("Turning OFF: %s (Button %d)", self.entity_id, self._off_button)

        success = await self.async_send_command(self._off_button)
        if success:
            self._attr_is_on = False
            self.async_write_ha_state()
