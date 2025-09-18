"""The Bromic Smart Heat Link integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_SERIAL_PORT, DOMAIN
from .hub import BromicHub
from .services import async_remove_services, async_setup_services

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.LIGHT,
    Platform.BUTTON,
    Platform.SELECT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bromic Smart Heat Link from a config entry."""
    _LOGGER.debug("Setting up Bromic Smart Heat Link integration")

    # Get configuration
    port = entry.data[CONF_SERIAL_PORT]

    # Initialize the hub
    hub = BromicHub(hass, port)

    try:
        # Connect to the device
        await hub.async_connect()
    except Exception as err:
        _LOGGER.exception("Failed to connect to Bromic device")
        raise ConfigEntryNotReady from err

    # Store hub in hass data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "hub": hub,
    }

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    await _async_setup_services(hass)

    _LOGGER.info("Bromic Smart Heat Link integration setup complete")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Bromic Smart Heat Link integration")

    # Unload platforms
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Disconnect from device
        hub_data = hass.data[DOMAIN].pop(entry.entry_id)
        hub: BromicHub = hub_data["hub"]
        await hub.async_disconnect()

        # Remove services if this was the last entry
        if not hass.data[DOMAIN]:
            await _async_remove_services(hass)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def _async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for the integration."""
    # Only set up services once (for the first entry)
    if len(hass.data[DOMAIN]) == 1:
        await async_setup_services(hass)


async def _async_remove_services(hass: HomeAssistant) -> None:
    """Remove services for the integration."""
    await async_remove_services(hass)
