"""Services for Bromic Smart Heat Link integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import voluptuous as vol
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
from .protocol import BromicProtocol

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from homeassistant.core import HomeAssistant, ServiceCall

    from .hub import BromicHub

_LOGGER = logging.getLogger(__name__)

# Service schemas
LEARN_BUTTON_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ID_LOCATION): vol.All(
            cv.positive_int, vol.Range(min=MIN_ID_LOCATION, max=MAX_ID_LOCATION)
        ),
        vol.Required(ATTR_BUTTON_NUMBER): vol.All(
            cv.positive_int, vol.Range(min=1, max=7)
        ),
    }
)

CLEAR_CONTROLLER_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ID_LOCATION): vol.All(
            cv.positive_int, vol.Range(min=MIN_ID_LOCATION, max=MAX_ID_LOCATION)
        ),
    }
)

SEND_RAW_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_RAW_COMMAND): cv.string,
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:  # noqa: PLR0915
    """Set up services for the Bromic integration."""

    async def learn_button_service(call: ServiceCall) -> None:
        """Handle learn button service call."""
        id_location = call.data[ATTR_ID_LOCATION]
        button_number = call.data[ATTR_BUTTON_NUMBER]

        # Find a hub to use (use the first available)
        hub = _get_hub(hass)
        if not hub:
            message = "No Bromic device connected"
            raise ServiceValidationError(message)

        try:
            response = await hub.async_send_command(id_location, button_number)
        except Exception as err:
            _LOGGER.exception(
                "Button learning exception: ID=%d, Button=%d",
                id_location,
                button_number,
            )
            message = f"Learning failed: {err}"
            raise ServiceValidationError(message) from err
        else:
            if response.success:
                _LOGGER.info(
                    "Button learning successful: ID=%d, Button=%d",
                    id_location,
                    button_number,
                )
            else:
                _LOGGER.error(
                    "Button learning failed: ID=%d, Button=%d, Error=%s",
                    id_location,
                    button_number,
                    response.message,
                )
                message = f"Learning failed: {response.message}"
                raise ServiceValidationError(message)

    async def clear_controller_service(call: ServiceCall) -> None:
        """Handle clear controller service call."""
        id_location = call.data[ATTR_ID_LOCATION]

        hub = _get_hub(hass)
        if not hub:
            message = "No Bromic device connected"
            raise ServiceValidationError(message)

        # Note: The Bromic protocol doesn't seem to have a specific "clear" command
        # This service could be enhanced if such functionality exists
        _LOGGER.warning(
            "Clear controller service called for ID=%d (not implemented in protocol)",
            id_location,
        )
        message = "Clear controller functionality not available in Bromic protocol"
        raise ServiceValidationError(message)

    async def send_raw_command_service(call: ServiceCall) -> None:
        """Handle send raw command service call."""
        raw_command = call.data[ATTR_RAW_COMMAND]

        hub = _get_hub(hass)
        if not hub:
            message = "No Bromic device connected"
            raise ServiceValidationError(message)

        # Parse the raw command
        command = BromicProtocol.parse_hex_command(raw_command)
        if not command:
            message = f"Invalid raw command format: {raw_command}"
            raise ServiceValidationError(message)

        try:
            response = await hub.async_send_command(
                command.id_location, command.button_code
            )
        except Exception as err:
            _LOGGER.exception("Raw command exception: %s", raw_command)
            message = f"Command failed: {err}"
            raise ServiceValidationError(message) from err
        else:
            _LOGGER.info(
                "Raw command sent: %s -> ID=%d, Button=%d, Success=%s, Response=%s",
                raw_command,
                command.id_location,
                command.button_code,
                response.success,
                response.message,
            )

            if not response.success:
                message = f"Command failed: {response.message}"
                raise ServiceValidationError(message)

    # Register services
    _register_service(
        hass,
        SERVICE_LEARN_BUTTON,
        learn_button_service,
        LEARN_BUTTON_SCHEMA,
    )
    _register_service(
        hass,
        SERVICE_CLEAR_CONTROLLER,
        clear_controller_service,
        CLEAR_CONTROLLER_SCHEMA,
    )
    _register_service(
        hass,
        SERVICE_SEND_RAW_COMMAND,
        send_raw_command_service,
        SEND_RAW_COMMAND_SCHEMA,
    )

    _LOGGER.debug("Bromic services registered")


def _register_service(
    hass: HomeAssistant,
    service: str,
    handler: Callable[[ServiceCall], Awaitable[None]] | Callable[[ServiceCall], None],
    schema: vol.Schema,
) -> None:
    """Register a service with schema."""
    hass.services.async_register(DOMAIN, service, handler, schema=schema)


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
