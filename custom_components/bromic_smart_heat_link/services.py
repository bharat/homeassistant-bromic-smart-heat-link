"""Services for Bromic Smart Heat Link integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_BUTTON_NUMBER,
    ATTR_ID_LOCATION,
    ATTR_RAW_COMMAND,
    DOMAIN,
    MAX_ID_LOCATION,
    MIN_ID_LOCATION,
    SERVICE_CLEAR_CONTROLLER,
    SERVICE_LEARN_BUTTON,
    SERVICE_SEND_RAW_COMMAND,
)
from .hub import BromicHub
from .protocol import BromicProtocol

_LOGGER = logging.getLogger(__name__)

# Service schemas
LEARN_BUTTON_SCHEMA = vol.Schema({
    vol.Required(ATTR_ID_LOCATION): vol.All(
        cv.positive_int, vol.Range(min=MIN_ID_LOCATION, max=MAX_ID_LOCATION)
    ),
    vol.Required(ATTR_BUTTON_NUMBER): vol.All(
        cv.positive_int, vol.Range(min=1, max=7)
    ),
})

CLEAR_CONTROLLER_SCHEMA = vol.Schema({
    vol.Required(ATTR_ID_LOCATION): vol.All(
        cv.positive_int, vol.Range(min=MIN_ID_LOCATION, max=MAX_ID_LOCATION)
    ),
})

SEND_RAW_COMMAND_SCHEMA = vol.Schema({
    vol.Required(ATTR_RAW_COMMAND): cv.string,
})


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for the Bromic integration."""
    
    async def learn_button_service(call: ServiceCall) -> None:
        """Handle learn button service call."""
        id_location = call.data[ATTR_ID_LOCATION]
        button_number = call.data[ATTR_BUTTON_NUMBER]
        
        # Find a hub to use (use the first available)
        hub = _get_hub(hass)
        if not hub:
            raise ServiceValidationError("No Bromic device connected")
        
        try:
            response = await hub.async_send_command(id_location, button_number)
            if response.success:
                _LOGGER.info(
                    "Button learning successful: ID=%d, Button=%d",
                    id_location, button_number
                )
            else:
                _LOGGER.error(
                    "Button learning failed: ID=%d, Button=%d, Error=%s",
                    id_location, button_number, response.message
                )
                raise ServiceValidationError(
                    f"Learning failed: {response.message}"
                )
        except Exception as err:
            _LOGGER.error(
                "Button learning exception: ID=%d, Button=%d, Error=%s",
                id_location, button_number, err
            )
            raise ServiceValidationError(f"Learning failed: {err}") from err

    async def clear_controller_service(call: ServiceCall) -> None:
        """Handle clear controller service call."""
        id_location = call.data[ATTR_ID_LOCATION]
        
        hub = _get_hub(hass)
        if not hub:
            raise ServiceValidationError("No Bromic device connected")
        
        # Note: The Bromic protocol doesn't seem to have a specific "clear" command
        # This service could be enhanced if such functionality exists
        _LOGGER.warning(
            "Clear controller service called for ID=%d (not implemented in protocol)",
            id_location
        )
        raise ServiceValidationError(
            "Clear controller functionality not available in Bromic protocol"
        )

    async def send_raw_command_service(call: ServiceCall) -> None:
        """Handle send raw command service call."""
        raw_command = call.data[ATTR_RAW_COMMAND]
        
        hub = _get_hub(hass)
        if not hub:
            raise ServiceValidationError("No Bromic device connected")
        
        # Parse the raw command
        command = BromicProtocol.parse_hex_command(raw_command)
        if not command:
            raise ServiceValidationError(f"Invalid raw command format: {raw_command}")
        
        try:
            response = await hub.async_send_command(command.id_location, command.button_code)
            _LOGGER.info(
                "Raw command sent: %s -> ID=%d, Button=%d, Success=%s, Response=%s",
                raw_command, command.id_location, command.button_code,
                response.success, response.message
            )
            
            if not response.success:
                raise ServiceValidationError(f"Command failed: {response.message}")
                
        except Exception as err:
            _LOGGER.error("Raw command exception: %s -> %s", raw_command, err)
            raise ServiceValidationError(f"Command failed: {err}") from err

    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_LEARN_BUTTON,
        learn_button_service,
        schema=LEARN_BUTTON_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_CONTROLLER,
        clear_controller_service,
        schema=CLEAR_CONTROLLER_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_RAW_COMMAND,
        send_raw_command_service,
        schema=SEND_RAW_COMMAND_SCHEMA,
    )
    
    _LOGGER.debug("Bromic services registered")


async def async_remove_services(hass: HomeAssistant) -> None:
    """Remove services for the Bromic integration."""
    services = [
        SERVICE_LEARN_BUTTON,
        SERVICE_CLEAR_CONTROLLER,
        SERVICE_SEND_RAW_COMMAND,
    ]
    
    for service in services:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
    
    _LOGGER.debug("Bromic services removed")


def _get_hub(hass: HomeAssistant) -> BromicHub | None:
    """Get the first available Bromic hub."""
    domain_data = hass.data.get(DOMAIN, {})
    
    for entry_data in domain_data.values():
        if isinstance(entry_data, dict) and "hub" in entry_data:
            hub: BromicHub = entry_data["hub"]
            if hub.connected:
                return hub
    
    return None
