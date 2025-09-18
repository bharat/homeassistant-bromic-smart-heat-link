"""Diagnostics support for Bromic Smart Heat Link integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_SERIAL_PORT, DOMAIN
from .hub import BromicHub

REDACT_KEYS = {CONF_SERIAL_PORT}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    hub_data = hass.data[DOMAIN][entry.entry_id]
    hub: BromicHub = hub_data["hub"]
    
    # Get hub statistics
    stats = hub.stats
    
    # Get controller information
    controllers = entry.options.get("controllers", {})
    controller_info = {}
    
    for id_str, controller_data in controllers.items():
        learned_buttons = controller_data.get("learned_buttons", {})
        controller_info[id_str] = {
            "type": controller_data.get("controller_type"),
            "learned_button_count": sum(learned_buttons.values()),
            "learned_buttons": learned_buttons,
        }
    
    # Collect entity information
    entity_registry = hass.helpers.entity_registry.async_get(hass)
    entities = []
    
    for entity_entry in entity_registry.entities.values():
        if entity_entry.config_entry_id == entry.entry_id:
            entities.append({
                "entity_id": entity_entry.entity_id,
                "platform": entity_entry.platform,
                "unique_id": entity_entry.unique_id,
                "disabled": entity_entry.disabled,
            })
    
    diagnostics_data = {
        "config_entry": {
            "title": entry.title,
            "version": entry.version,
            "data": async_redact_data(entry.data, REDACT_KEYS),
            "options": entry.options,
        },
        "hub": {
            "connected": hub.connected,
            "port": async_redact_data({"port": hub.port}, {"port"})["port"],
            "statistics": stats,
        },
        "controllers": controller_info,
        "entities": entities,
        "entity_count": len(entities),
    }
    
    return diagnostics_data
