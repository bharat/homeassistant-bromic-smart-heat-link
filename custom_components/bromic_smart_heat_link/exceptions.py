"""Exceptions for Bromic Smart Heat Link integration."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class BromicError(HomeAssistantError):
    """Base exception for Bromic Smart Heat Link integration."""


class BromicConnectionError(BromicError):
    """Exception raised when connection to the device fails."""


class BromicTimeoutError(BromicError):
    """Exception raised when a command times out."""


class BromicProtocolError(BromicError):
    """Exception raised when there's a protocol error."""


class BromicChecksumError(BromicProtocolError):
    """Exception raised when checksum validation fails."""


class BromicCommandError(BromicError):
    """Exception raised when a command fails."""

    def __init__(self, message: str, error_code: int | None = None) -> None:
        """Initialize the command error."""
        super().__init__(message)
        self.error_code = error_code


class BromicLearningError(BromicError):
    """Exception raised during the learning process."""


class BromicConfigurationError(BromicError):
    """Exception raised when there's a configuration error."""


class BromicSerialError(BromicConnectionError):
    """Exception raised when there's a serial port error."""


class BromicDeviceNotFoundError(BromicConnectionError):
    """Exception raised when the device is not found."""


class BromicInvalidResponseError(BromicProtocolError):
    """Exception raised when an invalid response is received."""
