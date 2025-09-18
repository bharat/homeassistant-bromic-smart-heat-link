"""Button platform for Bromic Smart Heat Link integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CONTROLLERS,
    CONF_CONTROLLER_TYPE,
    CONF_LEARNED_BUTTONS,
    CONTROLLER_TYPE_DIMMER,
    DIMMER_BUTTONS,
    DOMAIN,
)
from .entity import BromicEntity
from .hub import BromicHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bromic button entities from a config entry."""
    hub_data = hass.data[DOMAIN][config_entry.entry_id]
    hub: BromicHub = hub_data["hub"]
    
    entities = []
    controllers = config_entry.options.get(CONF_CONTROLLERS, {})
    
    for id_str, controller_info in controllers.items():
        id_location = int(id_str)
        controller_type = controller_info[CONF_CONTROLLER_TYPE]
        learned_buttons = controller_info.get(CONF_LEARNED_BUTTONS, {})
        
        # Only create button entities for dimmer controllers
        if controller_type == CONTROLLER_TYPE_DIMMER:
            # Create button entities for Dim Up/Down if learned
            if learned_buttons.get(5, False):  # Dim Up
                entities.append(
                    BromicButton(
                        hub=hub,
                        id_location=id_location,
                        controller_type=controller_type,
                        button_code=5,
                        button_name="Dim Up",
                    )
                )
            
            if learned_buttons.get(6, False):  # Dim Down
                entities.append(
                    BromicButton(
                        hub=hub,
                        id_location=id_location,
                        controller_type=controller_type,
                        button_code=6,
                        button_name="Dim Down",
                    )
                )
    
    if entities:
        async_add_entities(entities)


class BromicButton(BromicEntity, ButtonEntity):
    """Representation of a Bromic button."""

    def __init__(
        self,
        hub: BromicHub,
        id_location: int,
        controller_type: str,
        button_code: int,
        button_name: str,
    ) -> None:
        """Initialize the button.
        
        Args:
            hub: The Bromic hub
            id_location: ID location (1-50)
            controller_type: Controller type
            button_code: Button code to send
            button_name: Human-readable button name
        """
        super().__init__(hub, id_location, 0, controller_type, "button")
        
        self._button_code = button_code
        self._button_name = button_name
        
        # Button-specific attributes
        self._attr_name = f"Bromic ID{id_location} {button_name}"
        
        # Update unique ID to include button code
        port_id = self._hub.port.replace("/", "_").replace(":", "_")
        self._attr_unique_id = f"{DOMAIN}_{port_id}_{id_location}_btn{button_code}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return button specific state attributes."""
        attrs = super().extra_state_attributes
        attrs.update({
            "button_code": self._button_code,
            "button_name": self._button_name,
            "button_function": DIMMER_BUTTONS[self._button_code]["function"],
        })
        return attrs

    async def async_press(self) -> None:
        """Press the button."""
        _LOGGER.debug(
            "Pressing button: %s (ID=%d, Button=%d)",
            self.entity_id, self._id_location, self._button_code
        )
        
        await self.async_send_command(self._button_code)
