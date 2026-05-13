"""Tests for `BromicEntity` — the base class shared by switch and light.

Covers: identifier generation, device_info, stats-attribute reporting,
the success/failure command paths, and the connection-state callback
that toggles `_attr_available`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.bromic_smart_heat_link.const import (
    ATTR_COMMAND_COUNT,
    ATTR_ERROR_COUNT,
    ATTR_ID_LOCATION,
    ATTR_LAST_COMMAND_TIME,
    DOMAIN,
)
from custom_components.bromic_smart_heat_link.entity import BromicEntity
from custom_components.bromic_smart_heat_link.protocol import BromicResponse


def _make_hub(
    port: str = "/dev/ttyUSB0", *, last_success: float = 12345.0
) -> MagicMock:
    """Mock just enough of `BromicHub` for `BromicEntity` to use."""
    hub = MagicMock(name="hub")
    hub.port = port
    hub.stats = {"last_success": last_success}
    hub.async_send_command = AsyncMock()
    return hub


def _make_entity(hub: MagicMock, id_location: int = 5) -> BromicEntity:
    return BromicEntity(
        hub=hub,
        id_location=id_location,
        controller_type="onoff",
        entity_type="switch",
    )


class TestIdentifiers:
    """Identifier construction is deterministic and port-derived."""

    def test_unique_id_includes_domain_port_id_and_entity_type(self) -> None:
        hub = _make_hub(port="/dev/ttyUSB0")
        entity = _make_entity(hub, id_location=7)
        assert entity.unique_id == f"{DOMAIN}__dev_ttyUSB0_7_switch"

    def test_slashes_and_colons_in_port_become_underscores(self) -> None:
        # The port identifier is munged so it can be used in device.identifiers
        # without quoting; / and : are the two characters that get replaced.
        hub = _make_hub(port="socket://192.168.1.10:7777")
        entity = _make_entity(hub, id_location=1)
        assert "/" not in entity.unique_id
        assert ":" not in entity.unique_id

    def test_device_info_uses_id_in_identifier(self) -> None:
        hub = _make_hub(port="/dev/ttyUSB0")
        entity = _make_entity(hub, id_location=12)
        identifiers = entity.device_info["identifiers"]
        assert (DOMAIN, "_dev_ttyUSB0_12") in identifiers

    def test_device_info_via_device_links_to_bridge(self) -> None:
        hub = _make_hub(port="/dev/ttyUSB0")
        entity = _make_entity(hub, id_location=1)
        # via_device points at the bridge for this serial port (without ID suffix).
        assert entity.device_info["via_device"] == (DOMAIN, "_dev_ttyUSB0")

    def test_device_info_name_includes_id(self) -> None:
        hub = _make_hub()
        entity = _make_entity(hub, id_location=3)
        assert entity.device_info["name"] == "Bromic ID3"

    def test_has_entity_name_true_with_no_entity_name(self) -> None:
        # The base sets `_attr_has_entity_name=True` and `_attr_name=None` so
        # the object_id derives solely from the device name.
        hub = _make_hub()
        entity = _make_entity(hub)
        assert entity.has_entity_name is True
        assert entity.name is None


class TestExtraStateAttributes:
    """The stats panel exposes only the non-zero / non-empty fields."""

    def test_only_id_location_when_no_activity(self) -> None:
        hub = _make_hub()
        entity = _make_entity(hub, id_location=4)
        attrs = entity.extra_state_attributes
        assert attrs == {ATTR_ID_LOCATION: 4}

    def test_command_count_appears_after_successful_command(self) -> None:
        hub = _make_hub(last_success=42.0)
        hub.async_send_command.return_value = BromicResponse(
            success=True, error_code=None, message="ok", raw_bytes=b""
        )
        entity = _make_entity(hub, id_location=4)

        # Drive a successful command through the entity.
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            entity.async_send_command(1)
        )
        assert result is True

        attrs = entity.extra_state_attributes
        assert attrs[ATTR_COMMAND_COUNT] == 1
        assert attrs[ATTR_LAST_COMMAND_TIME] == 42.0
        assert ATTR_ERROR_COUNT not in attrs  # error_count == 0, hidden


class TestAsyncSendCommand:
    """The base entity owns success/failure bookkeeping and availability flipping."""

    async def test_success_returns_true_marks_available(self) -> None:
        hub = _make_hub()
        hub.async_send_command.return_value = BromicResponse(
            success=True, error_code=None, message="ok", raw_bytes=b""
        )
        entity = _make_entity(hub)
        # Force an initial "unavailable" to verify success flips back.
        entity._attr_available = False

        ok = await entity.async_send_command(2)
        assert ok is True
        assert entity.available is True
        assert entity.extra_state_attributes[ATTR_COMMAND_COUNT] == 1

    async def test_failed_response_returns_false_keeps_available(self) -> None:
        # A protocol-level failure (e.g. error response from the bridge)
        # does NOT mark the entity unavailable — only thrown exceptions do.
        # That matches the integration's documented retry semantics: failures
        # are noted in stats but the entity stays online.
        hub = _make_hub()
        hub.async_send_command.return_value = BromicResponse(
            success=False, error_code=0x02, message="Wrong command", raw_bytes=b""
        )
        entity = _make_entity(hub)

        ok = await entity.async_send_command(2)
        assert ok is False
        assert entity.available is True  # not flipped to False
        # error_count incremented; command_count NOT incremented (only on success path).
        attrs = entity.extra_state_attributes
        assert attrs.get(ATTR_ERROR_COUNT) == 1

    async def test_exception_returns_false_marks_unavailable(self) -> None:
        # A thrown exception flips _attr_available=False (the connection is
        # suspect). This is the "device disappeared" case.
        hub = _make_hub()
        hub.async_send_command.side_effect = RuntimeError("connection lost")
        entity = _make_entity(hub)

        ok = await entity.async_send_command(2)
        assert ok is False
        assert entity.available is False
        assert entity.extra_state_attributes.get(ATTR_ERROR_COUNT) == 1


class TestConnectionCallback:
    """`_on_connection_state_changed` toggles `_attr_available`."""

    def test_callback_toggles_availability(self) -> None:
        hub = _make_hub()
        entity = _make_entity(hub)
        # hass not set on the entity → async_write_ha_state should be guarded.
        entity._on_connection_state_changed(connected=False)
        assert entity.available is False
        entity._on_connection_state_changed(connected=True)
        assert entity.available is True
