"""Constants for the Bromic Smart Heat Link integration."""

from __future__ import annotations

from contextlib import suppress
from typing import Final

DOMAIN: Final = "bromic_smart_heat_link"

# Configuration keys
CONF_SERIAL_PORT: Final = "serial_port"
CONF_CONTROLLERS: Final = "controllers"
CONF_CONTROLLER_TYPE: Final = "controller_type"
CONF_ID_LOCATION: Final = "id_location"
CONF_LEARNED_BUTTONS: Final = "learned_buttons"

# Controller types
CONTROLLER_TYPE_ONOFF: Final = "onoff"
CONTROLLER_TYPE_DIMMER: Final = "dimmer"

# Serial configuration
SERIAL_CONFIG: Final = {
    "baudrate": 19200,
    "bytesize": 8,
    "parity": "N",
    "stopbits": 1,
    "timeout": 1.0,
    "write_timeout": 1.0,
    "xonxoff": False,
    "rtscts": False,
    "dsrdtr": False,
}

# Protocol constants
COMMAND_BYTE: Final = 0x54  # 'T' in ASCII
ACK_RESPONSE: Final = bytes([0x54, 0x06, 0x5A])
LEARN_TIMEOUT: Final = 5.0  # seconds
COMMAND_TIMEOUT: Final = 1.5  # seconds
MAX_RETRIES: Final = 3
INTER_FRAME_DELAY: Final = 0.1  # seconds between commands

# ID location limits
MIN_ID_LOCATION: Final = 1
MAX_ID_LOCATION: Final = 50

# Protocol limits
MAX_BUTTON_CODE: Final = 8
OFF_BUTTON_CODE: Final = 8
MIN_STD_RESPONSE_LENGTH: Final = 3
MIN_FRAME_LENGTH: Final = 6

# Button mappings for different controller types (simplified - no channels)
ONOFF_BUTTONS: Final = {
    1: {"name": "ON", "function": "turn_on"},
    2: {"name": "OFF", "function": "turn_off"},
}

DIMMER_BUTTONS: Final = {
    1: {"name": "100%", "function": "set_brightness", "level": 100},
    2: {"name": "75%", "function": "set_brightness", "level": 75},
    3: {"name": "50%", "function": "set_brightness", "level": 50},
    4: {"name": "25%", "function": "set_brightness", "level": 25},
    5: {"name": "Dim Up", "function": "dim_up"},
    6: {"name": "Dim Down", "function": "dim_down"},
    8: {"name": "Off", "function": "turn_off"},
}

# Brightness level mappings (HA 0-255 to Bromic levels); names map to translation keys
BRIGHTNESS_LEVELS: Final = {
    0: {"button": OFF_BUTTON_CODE, "name": "off"},
    64: {"button": 4, "name": "25"},
    128: {"button": 3, "name": "50"},
    191: {"button": 2, "name": "75"},
    255: {"button": 1, "name": "100"},
}

# Learning sequence for dimmer controllers (show Off last)
BUTTON_SEQUENCE_DIMMER: Final = [1, 2, 3, 4, 5, 6, OFF_BUTTON_CODE]

# Error codes from Bromic documentation
ERROR_CODES: Final = {
    0x00: "Framing error",
    0x01: "Checksum error",
    0x02: "Wrong command error",
    0x03: "ID = 0 error",
    0x04: "ID > 2000 error",
    0x05: "Number of code to read/delete = 0 error",
    0x06: "Number of code to read > 16 or >128 error",
    0x07: "Number of code to read/delete > 2000 (out of range) error",
    0x08: "Serial code already stored error",
    0x09: "ID < 201 error",
    0x10: "Empty location transmission attempt error",
    0x11: "Value out of valid codes range memorization attempt error",
}

# Error response format
ERROR_COMMAND: Final = 0x45  # 'E' in ASCII
ERROR_RESPONSE_LENGTH: Final = 3

# Device information
MANUFACTURER: Final = "Bromic"
MODEL: Final = "Smart Heat Link"
SW_VERSION: Final = "Bridge"

# Dispatcher signal format for syncing UI state across entities
SIGNAL_LEVEL_FMT: Final = f"{DOMAIN}_level_{{port_id}}_{{id_location}}"

# Default configuration
DEFAULT_NAME: Final = "Bromic Smart Heat Link"
DEFAULT_SCAN_INTERVAL: Final = 30  # seconds (for diagnostics only)

# Service names
SERVICE_LEARN_BUTTON: Final = "learn_button"
SERVICE_CLEAR_CONTROLLER: Final = "clear_controller"
SERVICE_SEND_RAW_COMMAND: Final = "send_raw_command"

# Attributes
ATTR_ID_LOCATION: Final = "id_location"
ATTR_BUTTON_NUMBER: Final = "button_number"
ATTR_CONTROLLER_TYPE: Final = "controller_type"
ATTR_BRIGHTNESS_LEVEL: Final = "brightness_level"
ATTR_RAW_COMMAND: Final = "raw_command"
ATTR_LAST_COMMAND_TIME: Final = "last_command_time"
ATTR_COMMAND_COUNT: Final = "command_count"
ATTR_ERROR_COUNT: Final = "error_count"


# Helpers
def normalize_controller_data(controller_info: dict) -> dict:
    """Normalize controller data loaded from storage (convert keys to ints)."""
    learned = controller_info.get(CONF_LEARNED_BUTTONS, {})
    with suppress(Exception):
        learned = {int(k): v for k, v in learned.items()}
    return {**controller_info, CONF_LEARNED_BUTTONS: learned}
