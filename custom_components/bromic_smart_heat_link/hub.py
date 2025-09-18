"""Hub for managing Bromic Smart Heat Link communication."""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import serial
import serial.tools.list_ports
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    COMMAND_TIMEOUT,
    INTER_FRAME_DELAY,
    MAX_RETRIES,
    SERIAL_CONFIG,
)
from .exceptions import (
    BromicConnectionError,
    BromicSerialError,
    BromicTimeoutError,
)
from .protocol import BromicCommand, BromicProtocol, BromicResponse

_LOGGER = logging.getLogger(__name__)


class BromicHub:
    """Manages communication with Bromic Smart Heat Link device."""

    def __init__(self, hass: HomeAssistant, port: str) -> None:
        """Initialize the hub.
        
        Args:
            hass: Home Assistant instance
            port: Serial port path
        """
        self.hass = hass
        self.port = port
        self._serial: serial.Serial | None = None
        self._lock = threading.RLock()
        self._connected = False
        self._last_command_time = 0.0
        
        # Statistics
        self._stats = {
            "commands_sent": 0,
            "commands_successful": 0,
            "commands_failed": 0,
            "connection_errors": 0,
            "last_error": None,
            "last_success": None,
        }
        
        # Event callbacks
        self._connection_callbacks: list[Callable[[bool], None]] = []
        
    @property
    def connected(self) -> bool:
        """Return if hub is connected."""
        return self._connected

    @property
    def stats(self) -> dict[str, Any]:
        """Return hub statistics."""
        return self._stats.copy()

    def add_connection_callback(self, callback: Callable[[bool], None]) -> None:
        """Add a callback for connection state changes."""
        self._connection_callbacks.append(callback)

    def remove_connection_callback(self, callback: Callable[[bool], None]) -> None:
        """Remove a connection callback."""
        if callback in self._connection_callbacks:
            self._connection_callbacks.remove(callback)

    @callback
    def _notify_connection_state(self, connected: bool) -> None:
        """Notify all callbacks of connection state change."""
        for callback in self._connection_callbacks:
            try:
                callback(connected)
            except Exception as err:
                _LOGGER.exception("Error in connection callback: %s", err)

    async def async_connect(self) -> None:
        """Connect to the device."""
        if self._connected:
            return

        try:
            await self.hass.async_add_executor_job(self._connect)
            self._connected = True
            self._stats["last_success"] = time.time()
            _LOGGER.info("Connected to Bromic device on %s", self.port)
            self._notify_connection_state(True)
            
        except Exception as err:
            self._connected = False
            self._stats["connection_errors"] += 1
            self._stats["last_error"] = str(err)
            _LOGGER.error("Failed to connect to %s: %s", self.port, err)
            self._notify_connection_state(False)
            raise BromicConnectionError(f"Failed to connect to {self.port}: {err}") from err

    def _connect(self) -> None:
        """Connect to the serial port (sync)."""
        try:
            self._serial = serial.Serial(
                port=self.port,
                **SERIAL_CONFIG
            )
            
            # Clear any pending data
            if self._serial.in_waiting > 0:
                self._serial.read(self._serial.in_waiting)
                
        except serial.SerialException as err:
            raise BromicSerialError(f"Serial port error: {err}") from err

    async def async_disconnect(self) -> None:
        """Disconnect from the device."""
        if not self._connected:
            return

        try:
            await self.hass.async_add_executor_job(self._disconnect)
        finally:
            self._connected = False
            _LOGGER.info("Disconnected from Bromic device")
            self._notify_connection_state(False)

    def _disconnect(self) -> None:
        """Disconnect from the serial port (sync)."""
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                except Exception as err:
                    _LOGGER.warning("Error closing serial port: %s", err)
                finally:
                    self._serial = None

    async def async_send_command(
        self, 
        id_location: int, 
        button_code: int,
        retries: int = MAX_RETRIES
    ) -> BromicResponse:
        """Send a command to the device.
        
        Args:
            id_location: ID location (1-50)
            button_code: Button code (1-7)
            retries: Number of retries on failure
            
        Returns:
            BromicResponse with the result
            
        Raises:
            BromicConnectionError: If not connected
            BromicTimeoutError: If command times out
        """
        if not self._connected:
            raise BromicConnectionError("Not connected to device")

        command = BromicProtocol.encode_command(id_location, button_code)
        
        for attempt in range(retries + 1):
            try:
                response = await self.hass.async_add_executor_job(
                    self._send_command_sync, command
                )
                
                self._stats["commands_sent"] += 1
                
                if response.success:
                    self._stats["commands_successful"] += 1
                    self._stats["last_success"] = time.time()
                    _LOGGER.debug(
                        "Command successful: ID=%d, Button=%d (attempt %d)",
                        id_location, button_code, attempt + 1
                    )
                else:
                    self._stats["commands_failed"] += 1
                    self._stats["last_error"] = response.message
                    
                return response
                
            except Exception as err:
                self._stats["commands_failed"] += 1
                self._stats["last_error"] = str(err)
                
                if attempt < retries:
                    _LOGGER.warning(
                        "Command failed (attempt %d/%d): %s",
                        attempt + 1, retries + 1, err
                    )
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                else:
                    _LOGGER.error(
                        "Command failed after %d attempts: %s",
                        retries + 1, err
                    )
                    raise

        # Should never reach here
        raise BromicTimeoutError("Command failed after all retries")

    def _send_command_sync(self, command: BromicCommand) -> BromicResponse:
        """Send command synchronously.
        
        Args:
            command: Command to send
            
        Returns:
            BromicResponse with the result
        """
        with self._lock:
            if not self._serial or not self._serial.is_open:
                raise BromicConnectionError("Serial port not open")

            # Enforce inter-frame delay
            current_time = time.time()
            time_since_last = current_time - self._last_command_time
            if time_since_last < INTER_FRAME_DELAY:
                time.sleep(INTER_FRAME_DELAY - time_since_last)

            try:
                # Clear any pending input
                if self._serial.in_waiting > 0:
                    self._serial.read(self._serial.in_waiting)
                
                # Send command
                _LOGGER.debug("Sending: %s", command.raw_bytes.hex().upper())
                self._serial.write(command.raw_bytes)
                self._serial.flush()
                
                self._last_command_time = time.time()
                
                # Wait for response
                response_data = self._read_response()
                return BromicProtocol.decode_response(response_data)
                
            except serial.SerialTimeoutException as err:
                raise BromicTimeoutError(f"Command timeout: {err}") from err
            except serial.SerialException as err:
                # Connection may have been lost
                self._connected = False
                raise BromicSerialError(f"Serial error: {err}") from err

    def _read_response(self) -> bytes:
        """Read response from device.
        
        Returns:
            Response bytes
            
        Raises:
            BromicTimeoutError: If no response received
        """
        if not self._serial:
            raise BromicConnectionError("Serial port not available")

        # Read response with timeout
        start_time = time.time()
        response = b""
        
        while time.time() - start_time < COMMAND_TIMEOUT:
            if self._serial.in_waiting > 0:
                chunk = self._serial.read(self._serial.in_waiting)
                response += chunk
                _LOGGER.debug("Received chunk: %s", chunk.hex().upper())
                
                # Check if we have a complete response
                if len(response) >= 3:
                    # For ACK response (3 bytes) or error response (3+ bytes)
                    _LOGGER.debug("Complete response: %s", response.hex().upper())
                    return response
            else:
                time.sleep(0.01)  # Small delay to avoid busy waiting
        
        if response:
            _LOGGER.debug("Partial response: %s", response.hex().upper())
            return response
            
        raise BromicTimeoutError("No response received from device")

    async def async_test_connection(self) -> bool:
        """Test if connection is working.
        
        Returns:
            True if connection is working
        """
        if not self._connected:
            return False
            
        try:
            # Try to send a harmless command to test communication
            # Use ID 1, Button 1 but we're just testing communication
            await self.async_send_command(1, 1, retries=1)
            return True
        except Exception as err:
            _LOGGER.debug("Connection test failed: %s", err)
            return False

    @staticmethod
    async def discover_ports() -> list[dict[str, str]]:
        """Discover available serial ports.
        
        Returns:
            List of port information dictionaries
        """
        def _discover() -> list[dict[str, str]]:
            ports = []
            for port in serial.tools.list_ports.comports():
                port_info = {
                    "device": port.device,
                    "name": port.device,
                    "description": port.description or "Unknown",
                }
                
                # Add vendor/product info if available
                if port.vid and port.pid:
                    port_info["vid_pid"] = f"{port.vid:04X}:{port.pid:04X}"
                    
                if port.manufacturer:
                    port_info["manufacturer"] = port.manufacturer
                    
                if port.product:
                    port_info["product"] = port.product
                    
                # Prefer by-id paths on Linux for stability
                if hasattr(port, 'device_path'):
                    port_info["device_path"] = port.device_path
                    
                ports.append(port_info)
            
            return sorted(ports, key=lambda x: x["device"])
        
        return await asyncio.get_event_loop().run_in_executor(None, _discover)

    @staticmethod
    async def test_port(port: str) -> bool:
        """Test if a port can be opened.
        
        Args:
            port: Port path to test
            
        Returns:
            True if port can be opened
        """
        def _test() -> bool:
            try:
                with serial.Serial(port, **SERIAL_CONFIG) as ser:
                    return ser.is_open
            except Exception:
                return False
                
        return await asyncio.get_event_loop().run_in_executor(None, _test)
