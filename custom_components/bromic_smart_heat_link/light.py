"""Light platform for Bromic Smart Heat Link integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BRIGHTNESS_LEVELS,
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
    """Set up Bromic light entities from a config entry."""
    hub_data = hass.data[DOMAIN][config_entry.entry_id]
    hub: BromicHub = hub_data["hub"]
    
    entities = []
    controllers = config_entry.options.get(CONF_CONTROLLERS, {})
    
    for id_str, controller_info in controllers.items():
        id_location = int(id_str)
        controller_type = controller_info[CONF_CONTROLLER_TYPE]
        learned_buttons = controller_info.get(CONF_LEARNED_BUTTONS, {})
        
        # Only create light entities for dimmer controllers
        if controller_type == CONTROLLER_TYPE_DIMMER:
            # Create light entities for each channel
            for channel in [1, 2]:
                # Check if essential buttons are learned (at least OFF and one brightness level)
                required_buttons = [7]  # Off button is essential
                brightness_buttons = [1, 2, 3, 4]  # 100%, 75%, 50%, 25%
                
                has_off = learned_buttons.get(7, False)
                has_brightness = any(learned_buttons.get(btn, False) for btn in brightness_buttons)
                
                if has_off and has_brightness:
                    entities.append(
                        BromicLight(
                            hub=hub,
                            id_location=id_location,
                            channel=channel,
                            controller_type=controller_type,
                            learned_buttons=learned_buttons,
                        )
                    )
                else:
                    _LOGGER.warning(
                        "Skipping light ID%d Ch%d - essential buttons not learned (OFF=%s, Brightness=%s)",
                        id_location, channel, has_off, has_brightness
                    )
    
    if entities:
        async_add_entities(entities)


class BromicLight(BromicEntity, LightEntity):
    """Representation of a Bromic dimmer controller light."""

    def __init__(
        self,
        hub: BromicHub,
        id_location: int,
        channel: int,
        controller_type: str,
        learned_buttons: dict[int, bool],
    ) -> None:
        """Initialize the light.
        
        Args:
            hub: The Bromic hub
            id_location: ID location (1-50)
            channel: Channel number (1-2)
            controller_type: Controller type
            learned_buttons: Dictionary of learned buttons
        """
        super().__init__(hub, id_location, channel, controller_type, "light")
        
        self._learned_buttons = learned_buttons
        
        # Light-specific attributes
        self._attr_is_on = False
        self._attr_brightness = 0
        self._attr_assumed_state = True  # We don't get feedback from the device
        self._attr_color_mode = ColorMode.BRIGHTNESS
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        
        # Update name with channel info
        self._attr_name = f"Bromic ID{id_location} Channel {channel}"
        
        # Determine available brightness levels based on learned buttons
        self._available_levels = {}
        for brightness, level_info in BRIGHTNESS_LEVELS.items():
            button = level_info["button"]
            if self._learned_buttons.get(button, False):
                self._available_levels[brightness] = level_info

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return light specific state attributes."""
        attrs = super().extra_state_attributes
        attrs.update({
            "channel": self._channel,
            "available_levels": {
                str(brightness): info["name"] 
                for brightness, info in self._available_levels.items()
            },
            "learned_buttons": {
                str(button): DIMMER_BUTTONS[button]["name"]
                for button, learned in self._learned_buttons.items()
                if learned
            }
        })
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        
        # Map HA brightness (0-255) to available Bromic levels
        target_brightness = self._map_brightness_to_available(brightness)
        button = self._available_levels[target_brightness]["button"]
        
        _LOGGER.debug(
            "Turning ON: %s (Brightness %d -> %d, Button %d)",
            self.entity_id, brightness, target_brightness, button
        )
        
        success = await self.async_send_command(button)
        if success:
            self._attr_is_on = True
            self._attr_brightness = target_brightness
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
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
            _LOGGER.warning("Cannot turn off %s - OFF button not learned", self.entity_id)

    def _map_brightness_to_available(self, brightness: int) -> int:
        """Map HA brightness to closest available Bromic level.
        
        Args:
            brightness: HA brightness (0-255)
            
        Returns:
            Closest available brightness level
        """
        if brightness == 0:
            return 0
            
        # Find closest available level
        available_brightnesses = [b for b in self._available_levels.keys() if b > 0]
        if not available_brightnesses:
            return 255  # Fallback to max if no levels available
            
        # Find closest match
        closest = min(available_brightnesses, key=lambda x: abs(x - brightness))
        return closest

    async def async_dim_up(self) -> None:
        """Increase brightness using dim up button."""
        if self._learned_buttons.get(5, False):  # Dim Up button
            _LOGGER.debug("Dim UP: %s (Button 5)", self.entity_id)
            
            success = await self.async_send_command(5)
            if success:
                # Estimate new brightness (move to next higher level)
                current = self._attr_brightness
                available_higher = [b for b in self._available_levels.keys() if b > current]
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
                available_lower = [b for b in self._available_levels.keys() if b < current]
                if available_lower:
                    new_brightness = max(available_lower)
                    self._attr_brightness = new_brightness
                    self._attr_is_on = new_brightness > 0
                    self.async_write_ha_state()
