"""Tests for the user-facing config flow.

Focused on the initial `async_step_user` and `async_step_manual_port`
paths. The deep learning-wizard options flow is exercised end-to-end
against real hardware and isn't unit-tested here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries, data_entry_flow

from custom_components.bromic_smart_heat_link.const import (
    CONF_SERIAL_PORT,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class TestUserStep:
    """`async_step_user` shows a port-picker form and accepts a selection."""

    async def test_initial_form_shown_when_ports_discovered(
        self, hass: HomeAssistant
    ) -> None:
        # Mock port discovery so the form has options to render.
        discovered = [
            {"device": "/dev/ttyUSB0", "description": "USB UART"},
            {"device": "/dev/ttyUSB1", "description": "Other UART"},
        ]
        with patch(
            "custom_components.bromic_smart_heat_link.config_flow.BromicHub.discover_ports",
            AsyncMock(return_value=discovered),
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "user"
        assert result["errors"] == {}

    async def test_successful_selection_creates_entry(
        self, hass: HomeAssistant
    ) -> None:
        discovered = [{"device": "/dev/ttyUSB0", "description": "USB UART"}]

        with (
            patch(
                "custom_components.bromic_smart_heat_link.config_flow.BromicHub.discover_ports",
                AsyncMock(return_value=discovered),
            ),
            patch(
                "custom_components.bromic_smart_heat_link.config_flow.BromicHub.async_connect",
                AsyncMock(),
            ),
            patch(
                "custom_components.bromic_smart_heat_link.config_flow.BromicHub.async_test_connection",
                AsyncMock(return_value=True),
            ),
            patch(
                "custom_components.bromic_smart_heat_link.config_flow.BromicHub.async_disconnect",
                AsyncMock(),
            ),
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_SERIAL_PORT: "/dev/ttyUSB0"},
            )

        assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_SERIAL_PORT] == "/dev/ttyUSB0"
        # New entries start with no controllers configured.
        assert result["options"]["controllers"] == {}

    async def test_failed_connection_shows_error(self, hass: HomeAssistant) -> None:
        discovered = [{"device": "/dev/ttyUSB0", "description": "USB UART"}]

        with (
            patch(
                "custom_components.bromic_smart_heat_link.config_flow.BromicHub.discover_ports",
                AsyncMock(return_value=discovered),
            ),
            patch(
                "custom_components.bromic_smart_heat_link.config_flow.BromicHub.async_connect",
                AsyncMock(side_effect=RuntimeError("nope")),
            ),
            patch(
                "custom_components.bromic_smart_heat_link.config_flow.BromicHub.async_disconnect",
                AsyncMock(),
            ),
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_SERIAL_PORT: "/dev/ttyUSB0"},
            )

        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}


class TestManualPortStep:
    """`async_step_manual_port` is reached when the user picks 'Other'."""

    async def test_manual_port_accepts_input_and_creates_entry(
        self, hass: HomeAssistant
    ) -> None:
        # Empty discovery → form falls through to manual schema directly.
        with (
            patch(
                "custom_components.bromic_smart_heat_link.config_flow.BromicHub.discover_ports",
                AsyncMock(return_value=[]),
            ),
            patch(
                "custom_components.bromic_smart_heat_link.config_flow.BromicHub.async_connect",
                AsyncMock(),
            ),
            patch(
                "custom_components.bromic_smart_heat_link.config_flow.BromicHub.async_test_connection",
                AsyncMock(return_value=True),
            ),
            patch(
                "custom_components.bromic_smart_heat_link.config_flow.BromicHub.async_disconnect",
                AsyncMock(),
            ),
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            # The user step itself uses the manual schema when there's nothing
            # discovered. Submit a port directly.
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_SERIAL_PORT: "/dev/ttyACM0"},
            )

        assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_SERIAL_PORT] == "/dev/ttyACM0"
