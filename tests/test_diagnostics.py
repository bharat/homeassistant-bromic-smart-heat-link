"""Tests for the diagnostics payload.

Critical assertions:
- The serial port is redacted (it can contain identifying USB IDs).
- Hub stats are surfaced.
- Controller metadata is summarized (type + learned button count).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bromic_smart_heat_link.const import (
    CONF_CONTROLLER_TYPE,
    CONF_CONTROLLERS,
    CONF_LEARNED_BUTTONS,
    CONF_SERIAL_PORT,
    CONTROLLER_TYPE_DIMMER,
    CONTROLLER_TYPE_ONOFF,
    DOMAIN,
)
from custom_components.bromic_smart_heat_link.diagnostics import (
    async_get_config_entry_diagnostics,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def test_serial_port_redacted_in_data(hass: HomeAssistant) -> None:
    """`async_redact_data` should hide CONF_SERIAL_PORT in entry.data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_SERIAL_PORT: "/dev/ttyUSB0"},
        options={CONF_CONTROLLERS: {}},
        title="Test",
    )
    entry.add_to_hass(hass)

    hub = MagicMock()
    hub.connected = True
    hub.port = "/dev/ttyUSB0"
    hub.stats = {"commands_sent": 5}
    hass.data[DOMAIN] = {entry.entry_id: {"hub": hub}}

    diag = await async_get_config_entry_diagnostics(hass, entry)
    # Redacted form is **REDACTED** (HA's standard sentinel).
    assert diag["config_entry"]["data"][CONF_SERIAL_PORT] != "/dev/ttyUSB0"


async def test_hub_port_redacted_in_hub_section(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_SERIAL_PORT: "/dev/ttyUSB0"},
        options={},
        title="Test",
    )
    entry.add_to_hass(hass)

    hub = MagicMock()
    hub.connected = True
    hub.port = "/dev/ttyUSB0"
    hub.stats = {"commands_sent": 0}
    hass.data[DOMAIN] = {entry.entry_id: {"hub": hub}}

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["hub"]["port"] != "/dev/ttyUSB0"


async def test_hub_stats_surface(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_SERIAL_PORT: "/dev/ttyUSB0"},
        options={},
        title="Test",
    )
    entry.add_to_hass(hass)

    hub = MagicMock()
    hub.connected = True
    hub.port = "/dev/ttyUSB0"
    hub.stats = {
        "commands_sent": 7,
        "commands_successful": 5,
        "commands_failed": 2,
    }
    hass.data[DOMAIN] = {entry.entry_id: {"hub": hub}}

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["hub"]["connected"] is True
    assert diag["hub"]["statistics"]["commands_sent"] == 7
    assert diag["hub"]["statistics"]["commands_successful"] == 5
    assert diag["hub"]["statistics"]["commands_failed"] == 2


async def test_controllers_summary(hass: HomeAssistant) -> None:
    """The 'controllers' section summarizes type + learned button count per ID."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_SERIAL_PORT: "/dev/ttyUSB0"},
        options={
            CONF_CONTROLLERS: {
                "1": {
                    CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_ONOFF,
                    CONF_LEARNED_BUTTONS: {1: True, 2: True},
                },
                "5": {
                    CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_DIMMER,
                    CONF_LEARNED_BUTTONS: {
                        1: True,
                        2: True,
                        3: False,
                        4: True,
                        8: True,
                    },
                },
            },
        },
        title="Test",
    )
    entry.add_to_hass(hass)

    hub = MagicMock()
    hub.connected = True
    hub.port = "/dev/ttyUSB0"
    hub.stats = {}
    hass.data[DOMAIN] = {entry.entry_id: {"hub": hub}}

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert "1" in diag["controllers"]
    assert diag["controllers"]["1"]["type"] == CONTROLLER_TYPE_ONOFF
    assert diag["controllers"]["1"]["learned_button_count"] == 2  # both True

    assert diag["controllers"]["5"]["type"] == CONTROLLER_TYPE_DIMMER
    # 4 of 5 buttons learned (one is False).
    assert diag["controllers"]["5"]["learned_button_count"] == 4
