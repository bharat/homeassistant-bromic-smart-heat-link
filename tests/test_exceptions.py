"""Tests for the Bromic exception hierarchy.

Verifies that each integration-specific exception inherits the expected
parent class so HA's `HomeAssistantError`-aware handling (e.g. user-facing
notifications) treats them correctly, and that `BromicCommandError` stores
the protocol-level error code.
"""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError

from custom_components.bromic_smart_heat_link.exceptions import (
    BromicChecksumError,
    BromicCommandError,
    BromicConfigurationError,
    BromicConnectionError,
    BromicDeviceNotFoundError,
    BromicError,
    BromicInvalidResponseError,
    BromicLearningError,
    BromicProtocolError,
    BromicSerialError,
    BromicTimeoutError,
)


class TestExceptionHierarchy:
    """Each exception is a HomeAssistantError so HA treats it consistently."""

    def test_base_inherits_homeassistanterror(self) -> None:
        assert issubclass(BromicError, HomeAssistantError)

    def test_connection_inherits_base(self) -> None:
        assert issubclass(BromicConnectionError, BromicError)

    def test_timeout_inherits_base(self) -> None:
        assert issubclass(BromicTimeoutError, BromicError)

    def test_protocol_inherits_base(self) -> None:
        assert issubclass(BromicProtocolError, BromicError)

    def test_checksum_inherits_protocol(self) -> None:
        assert issubclass(BromicChecksumError, BromicProtocolError)

    def test_invalid_response_inherits_protocol(self) -> None:
        assert issubclass(BromicInvalidResponseError, BromicProtocolError)

    def test_serial_inherits_connection(self) -> None:
        # Serial errors are a flavor of connection error — HA can treat them
        # the same way at the entry-setup layer.
        assert issubclass(BromicSerialError, BromicConnectionError)

    def test_device_not_found_inherits_connection(self) -> None:
        assert issubclass(BromicDeviceNotFoundError, BromicConnectionError)

    def test_command_inherits_base(self) -> None:
        assert issubclass(BromicCommandError, BromicError)

    def test_learning_inherits_base(self) -> None:
        assert issubclass(BromicLearningError, BromicError)

    def test_configuration_inherits_base(self) -> None:
        assert issubclass(BromicConfigurationError, BromicError)


class TestCommandErrorCarriesCode:
    """`BromicCommandError` is the only one with a custom __init__ — the device's error code."""

    def test_with_error_code(self) -> None:
        err = BromicCommandError("Wrong command", error_code=0x02)
        assert str(err) == "Wrong command"
        assert err.error_code == 0x02

    def test_without_error_code_defaults_to_none(self) -> None:
        err = BromicCommandError("Generic failure")
        assert str(err) == "Generic failure"
        assert err.error_code is None

    def test_is_raisable_and_catchable_as_base(self) -> None:
        # Critical: code that catches BromicError should catch BromicCommandError.
        try:
            raise BromicCommandError("test", error_code=0x05)
        except BromicError as caught:
            assert isinstance(caught, BromicCommandError)
            assert caught.error_code == 0x05
