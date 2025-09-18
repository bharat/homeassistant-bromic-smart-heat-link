"""Protocol implementation for Bromic Smart Heat Link."""
from __future__ import annotations

import logging
from typing import NamedTuple

from .const import (
    COMMAND_BYTE,
    ERROR_CODES,
    ERROR_COMMAND,
    ERROR_RESPONSE_LENGTH,
    ACK_RESPONSE,
)
from .exceptions import (
    BromicChecksumError,
    BromicInvalidResponseError,
    BromicProtocolError,
    BromicCommandError,
)

_LOGGER = logging.getLogger(__name__)


class BromicCommand(NamedTuple):
    """Represents a Bromic command."""
    
    id_location: int
    button_code: int
    raw_bytes: bytes


class BromicResponse(NamedTuple):
    """Represents a Bromic response."""
    
    success: bool
    error_code: int | None
    message: str
    raw_bytes: bytes


class BromicProtocol:
    """Handles Bromic Smart Heat Link protocol encoding/decoding."""

    @staticmethod
    def calculate_checksum(data: bytes) -> int:
        """Calculate checksum for a data packet.
        
        Args:
            data: The data bytes to calculate checksum for
            
        Returns:
            The calculated checksum byte
        """
        return sum(data) & 0xFF

    @staticmethod
    def encode_command(id_location: int, button_code: int) -> BromicCommand:
        """Encode a command for transmission.
        
        Protocol structure:
        - Command: 1 byte (0x54 = 'T')
        - ID: 2 bytes (big-endian)
        - Channel/Button: 2 bytes (big-endian)  
        - Checksum: 1 byte
        
        Args:
            id_location: ID location (1-50)
            button_code: Button code (1-7)
            
        Returns:
            BromicCommand with encoded data
            
        Raises:
            BromicProtocolError: If parameters are invalid
        """
        if not (1 <= id_location <= 50):
            raise BromicProtocolError(f"Invalid ID location: {id_location}")
        
        if not (1 <= button_code <= 7):
            raise BromicProtocolError(f"Invalid button code: {button_code}")

        # Build the frame
        cmd_byte = COMMAND_BYTE
        id_bytes = id_location.to_bytes(2, 'big')
        button_bytes = button_code.to_bytes(2, 'big')
        
        # Calculate checksum of all bytes
        frame_data = bytes([cmd_byte]) + id_bytes + button_bytes
        checksum = BromicProtocol.calculate_checksum(frame_data)
        
        # Complete frame
        raw_bytes = frame_data + bytes([checksum])
        
        _LOGGER.debug(
            "Encoded command: ID=%d, Button=%d -> %s",
            id_location,
            button_code,
            raw_bytes.hex().upper()
        )
        
        return BromicCommand(
            id_location=id_location,
            button_code=button_code,
            raw_bytes=raw_bytes
        )

    @staticmethod
    def decode_response(data: bytes) -> BromicResponse:
        """Decode a response from the device.
        
        Args:
            data: Raw response bytes
            
        Returns:
            BromicResponse with decoded information
            
        Raises:
            BromicInvalidResponseError: If response format is invalid
            BromicChecksumError: If checksum validation fails
            BromicCommandError: If device returned an error
        """
        if not data:
            raise BromicInvalidResponseError("Empty response received")

        _LOGGER.debug("Decoding response: %s", data.hex().upper())

        # Check for ACK response (success)
        if data == ACK_RESPONSE:
            return BromicResponse(
                success=True,
                error_code=None,
                message="Command acknowledged",
                raw_bytes=data
            )

        # Check for error response
        if len(data) >= ERROR_RESPONSE_LENGTH and data[0] == ERROR_COMMAND:
            error_code = data[1] if len(data) > 1 else 0
            error_message = ERROR_CODES.get(error_code, f"Unknown error code: {error_code:02X}")
            
            _LOGGER.warning("Device error: %s (code: %02X)", error_message, error_code)
            
            return BromicResponse(
                success=False,
                error_code=error_code,
                message=error_message,
                raw_bytes=data
            )

        # Validate minimum length for standard response
        if len(data) < 3:
            raise BromicInvalidResponseError(f"Response too short: {len(data)} bytes")

        # For other responses, try to validate checksum if long enough
        if len(data) > 1:
            received_checksum = data[-1]
            calculated_checksum = BromicProtocol.calculate_checksum(data[:-1])
            
            if received_checksum != calculated_checksum:
                raise BromicChecksumError(
                    f"Checksum mismatch: received {received_checksum:02X}, "
                    f"calculated {calculated_checksum:02X}"
                )

        # Unknown response format
        return BromicResponse(
            success=False,
            error_code=None,
            message=f"Unknown response format: {data.hex().upper()}",
            raw_bytes=data
        )

    @staticmethod
    def validate_frame(data: bytes) -> bool:
        """Validate a complete frame.
        
        Args:
            data: Frame data to validate
            
        Returns:
            True if frame is valid, False otherwise
        """
        try:
            if len(data) < 6:  # Minimum frame size
                return False
                
            if data[0] != COMMAND_BYTE:
                return False
                
            # Validate checksum
            received_checksum = data[-1]
            calculated_checksum = BromicProtocol.calculate_checksum(data[:-1])
            
            return received_checksum == calculated_checksum
            
        except Exception:
            return False

    @staticmethod
    def get_command_examples() -> dict[int, dict[int, str]]:
        """Get example commands for documentation/testing.
        
        Returns:
            Dictionary mapping ID locations to button codes to hex strings
        """
        examples = {}
        
        # Generate examples for first few IDs
        for id_loc in range(1, 5):
            examples[id_loc] = {}
            for button in range(1, 8):
                try:
                    cmd = BromicProtocol.encode_command(id_loc, button)
                    examples[id_loc][button] = cmd.raw_bytes.hex().upper()
                except BromicProtocolError:
                    pass
        
        return examples

    @staticmethod
    def parse_hex_command(hex_string: str) -> BromicCommand | None:
        """Parse a hex command string back into a BromicCommand.
        
        Args:
            hex_string: Hex string like "540001000156"
            
        Returns:
            BromicCommand if valid, None if invalid
        """
        try:
            # Remove spaces and convert to bytes
            hex_clean = hex_string.replace(" ", "").replace(":", "")
            data = bytes.fromhex(hex_clean)
            
            if len(data) != 6:
                return None
                
            if data[0] != COMMAND_BYTE:
                return None
                
            # Validate checksum
            if not BromicProtocol.validate_frame(data):
                return None
                
            # Extract ID and button
            id_location = int.from_bytes(data[1:3], 'big')
            button_code = int.from_bytes(data[3:5], 'big')
            
            return BromicCommand(
                id_location=id_location,
                button_code=button_code,
                raw_bytes=data
            )
            
        except (ValueError, IndexError):
            return None
