"""Tests for the three integration services.

Covers `learn_button`, `clear_controller`, and `send_raw_command`. Each
service finds the first connected hub and dispatches through it; tests
mock the hub and assert the expected dispatch behavior + the
`ServiceValidationError` paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.bromic_smart_heat_link.const import (
    ATTR_BUTTON_NUMBER,
    ATTR_ID_LOCATION,
    ATTR_RAW_COMMAND,
    DOMAIN,
    SERVICE_CLEAR_CONTROLLER,
    SERVICE_LEARN_BUTTON,
    SERVICE_SEND_RAW_COMMAND,
)
from custom_components.bromic_smart_heat_link.protocol import (
    BromicProtocol,
    BromicResponse,
)
from custom_components.bromic_smart_heat_link.services import (
    _get_hub,
    async_remove_services,
    async_setup_services,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def _install_connected_hub(
    hass: HomeAssistant, *, send_result: BromicResponse | None = None
) -> MagicMock:
    if send_result is None:
        send_result = BromicResponse(
            success=True, error_code=None, message="ok", raw_bytes=b""
        )
    hub = MagicMock(name="hub")
    hub.connected = True
    hub.async_send_command = AsyncMock(return_value=send_result)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["test_entry"] = {"hub": hub}
    return hub


class TestGetHub:
    """`_get_hub` returns the first connected hub or None."""

    def test_returns_none_when_domain_data_missing(self, hass: HomeAssistant) -> None:
        # hass.data is empty.
        assert _get_hub(hass) is None

    def test_returns_none_when_no_hub_connected(self, hass: HomeAssistant) -> None:
        hub = MagicMock()
        hub.connected = False
        hass.data[DOMAIN] = {"entry": {"hub": hub}}
        assert _get_hub(hass) is None

    def test_returns_first_connected_hub(self, hass: HomeAssistant) -> None:
        hub = _install_connected_hub(hass)
        assert _get_hub(hass) is hub


class TestRegistration:
    """`async_setup_services` registers exactly 3 services."""

    async def test_registers_three_services(self, hass: HomeAssistant) -> None:
        await async_setup_services(hass)
        assert hass.services.has_service(DOMAIN, SERVICE_LEARN_BUTTON)
        assert hass.services.has_service(DOMAIN, SERVICE_CLEAR_CONTROLLER)
        assert hass.services.has_service(DOMAIN, SERVICE_SEND_RAW_COMMAND)

    async def test_remove_services_unregisters(self, hass: HomeAssistant) -> None:
        await async_setup_services(hass)
        await async_remove_services(hass)
        assert not hass.services.has_service(DOMAIN, SERVICE_LEARN_BUTTON)
        assert not hass.services.has_service(DOMAIN, SERVICE_CLEAR_CONTROLLER)
        assert not hass.services.has_service(DOMAIN, SERVICE_SEND_RAW_COMMAND)


class TestLearnButton:
    async def test_success_dispatches_to_hub(self, hass: HomeAssistant) -> None:
        hub = _install_connected_hub(hass)
        await async_setup_services(hass)

        await hass.services.async_call(
            DOMAIN,
            SERVICE_LEARN_BUTTON,
            {ATTR_ID_LOCATION: 5, ATTR_BUTTON_NUMBER: 1},
            blocking=True,
        )

        hub.async_send_command.assert_awaited_once_with(5, 1)

    async def test_no_hub_raises_validation_error(self, hass: HomeAssistant) -> None:
        await async_setup_services(hass)
        with pytest.raises(ServiceValidationError, match="No Bromic device"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_LEARN_BUTTON,
                {ATTR_ID_LOCATION: 5, ATTR_BUTTON_NUMBER: 1},
                blocking=True,
            )

    async def test_failed_response_raises(self, hass: HomeAssistant) -> None:
        bad = BromicResponse(
            success=False, error_code=0x02, message="Wrong command", raw_bytes=b""
        )
        _install_connected_hub(hass, send_result=bad)
        await async_setup_services(hass)
        with pytest.raises(ServiceValidationError, match="Learning failed"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_LEARN_BUTTON,
                {ATTR_ID_LOCATION: 5, ATTR_BUTTON_NUMBER: 1},
                blocking=True,
            )


class TestClearController:
    async def test_always_raises_not_implemented(self, hass: HomeAssistant) -> None:
        # The Bromic protocol doesn't expose a "clear" command, so the
        # service surfaces an explicit ServiceValidationError.
        _install_connected_hub(hass)
        await async_setup_services(hass)
        with pytest.raises(ServiceValidationError, match="not available"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_CLEAR_CONTROLLER,
                {ATTR_ID_LOCATION: 5},
                blocking=True,
            )


class TestSendRawCommand:
    async def test_valid_hex_dispatches_to_hub(self, hass: HomeAssistant) -> None:
        hub = _install_connected_hub(hass)
        await async_setup_services(hass)

        # Build a real round-trippable hex command for (ID=1, button=1).
        cmd = BromicProtocol.encode_command(1, 1)

        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_RAW_COMMAND,
            {ATTR_RAW_COMMAND: cmd.raw_bytes.hex()},
            blocking=True,
        )

        hub.async_send_command.assert_awaited_once_with(1, 1)

    async def test_invalid_hex_raises(self, hass: HomeAssistant) -> None:
        _install_connected_hub(hass)
        await async_setup_services(hass)
        with pytest.raises(ServiceValidationError, match="Invalid raw command"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SEND_RAW_COMMAND,
                {ATTR_RAW_COMMAND: "not-a-hex-frame"},
                blocking=True,
            )

    async def test_failed_response_raises(self, hass: HomeAssistant) -> None:
        bad = BromicResponse(
            success=False, error_code=0x02, message="Wrong command", raw_bytes=b""
        )
        _install_connected_hub(hass, send_result=bad)
        await async_setup_services(hass)
        cmd = BromicProtocol.encode_command(1, 1)
        with pytest.raises(ServiceValidationError, match="Command failed"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SEND_RAW_COMMAND,
                {ATTR_RAW_COMMAND: cmd.raw_bytes.hex()},
                blocking=True,
            )
