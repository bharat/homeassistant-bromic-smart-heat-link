"""Base entity for Bromic Smart Heat Link integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import (
    ATTR_COMMAND_COUNT,
    ATTR_ERROR_COUNT,
    ATTR_ID_LOCATION,
    ATTR_LAST_COMMAND_TIME,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    SW_VERSION,
)

if TYPE_CHECKING:
    from .hub import BromicHub

_LOGGER = logging.getLogger(__name__)


class BromicEntity(Entity):
    """Base entity for Bromic Smart Heat Link devices."""

    def __init__(
        self,
        hub: BromicHub,
        id_location: int,
        controller_type: str,
        entity_type: str,
    ) -> None:
        """
        Initialize the entity.

        Args:
            hub: The Bromic hub
            id_location: ID location (1-50)
            controller_type: Controller type (onoff/dimmer)
            entity_type: Entity type for naming

        """
        self._hub = hub
        self._id_location = id_location
        self._controller_type = controller_type
        self._entity_type = entity_type

        # Generate unique identifiers (no channel concept)
        port_id = self._hub.port.replace("/", "_").replace(":", "_")
        self._attr_unique_id = f"{DOMAIN}_{port_id}_{id_location}_{entity_type}"

        # Entity naming
        self._attr_name = f"Bromic ID{id_location}"

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{port_id}_{id_location}")},
            name=f"Bromic Controller ID{id_location}",
            manufacturer=MANUFACTURER,
            model=f"{MODEL} ({controller_type.upper()})",
            sw_version=SW_VERSION,
            via_device=(DOMAIN, port_id),
        )

        # State tracking
        self._attr_available = True
        self._last_command_time: float | None = None
        self._command_count = 0
        self._error_count = 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = {
            ATTR_ID_LOCATION: self._id_location,
        }

        if self._last_command_time:
            attrs[ATTR_LAST_COMMAND_TIME] = self._last_command_time

        if self._command_count > 0:
            attrs[ATTR_COMMAND_COUNT] = self._command_count

        if self._error_count > 0:
            attrs[ATTR_ERROR_COUNT] = self._error_count

        return attrs

    async def async_send_command(self, button_code: int) -> bool:
        """
        Send a command to the device.

        Args:
            button_code: Button code to send

        Returns:
            True if successful, False otherwise

        """
        try:
            response = await self._hub.async_send_command(
                self._id_location, button_code
            )
            self._command_count += 1

        except Exception:
            self._error_count += 1
            self._attr_available = False
            _LOGGER.exception(
                "Command exception: ID=%d, Button=%d, Entity=%s",
                self._id_location,
                button_code,
                self.entity_id,
            )
            return False
        else:
            if response.success:
                self._last_command_time = self._hub.stats["last_success"]
                self._attr_available = True
                _LOGGER.debug(
                    "Command successful: ID=%d, Button=%d, Entity=%s",
                    self._id_location,
                    button_code,
                    self.entity_id,
                )
                return True
            self._error_count += 1
            _LOGGER.warning(
                "Command failed: ID=%d, Button=%d, Entity=%s, Error=%s",
                self._id_location,
                button_code,
                self.entity_id,
                response.message,
            )
            return False

    async def async_added_to_hass(self) -> None:
        """Call when entity is added to hass."""
        await super().async_added_to_hass()

        # Register for connection state updates
        self._hub.add_connection_callback(self._on_connection_state_changed)

    async def async_will_remove_from_hass(self) -> None:
        """Call when entity will be removed from hass."""
        await super().async_will_remove_from_hass()

        # Unregister connection callback
        self._hub.remove_connection_callback(self._on_connection_state_changed)

    def _on_connection_state_changed(self, connected: bool) -> None:  # noqa: FBT001
        """Handle connection state changes."""
        self._attr_available = connected
        if self.hass:
            self.async_write_ha_state()
