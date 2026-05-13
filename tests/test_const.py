"""Tests for protocol constants and the storage normalizer.

The constants in `const.py` encode the wire-format contract with the
Bromic bridge — getting them wrong would break every command silently or
cause spurious checksum failures. These tests pin the values so any
accidental edit lands a red CI.
"""

from __future__ import annotations

from custom_components.bromic_smart_heat_link.const import (
    ACK_RESPONSE,
    BRIGHTNESS_LEVELS,
    BUTTON_SEQUENCE_DIMMER,
    COMMAND_BYTE,
    COMMAND_TIMEOUT,
    DIMMER_BUTTONS,
    DOMAIN,
    ERROR_CODES,
    ERROR_COMMAND,
    INTER_FRAME_DELAY,
    MAX_BUTTON_CODE,
    MAX_ID_LOCATION,
    MAX_RETRIES,
    MIN_ID_LOCATION,
    OFF_BUTTON_CODE,
    ONOFF_BUTTONS,
    SERIAL_CONFIG,
    normalize_controller_data,
)


def test_domain_string_unchanged() -> None:
    # Renaming the domain breaks every existing config entry and entity ID.
    assert DOMAIN == "bromic_smart_heat_link"


def test_command_byte_is_ascii_T() -> None:
    # The bridge protocol opens every frame with 'T' (0x54).
    assert COMMAND_BYTE == 0x54
    assert ord("T") == COMMAND_BYTE


def test_error_command_is_ascii_E() -> None:
    # The bridge marks error responses with 'E' (0x45) as the first byte.
    assert ERROR_COMMAND == 0x45
    assert ord("E") == ERROR_COMMAND


def test_ack_response_shape() -> None:
    # Bromic documented ACK: 'T' + 0x06 + 'Z'.
    assert bytes([0x54, 0x06, 0x5A]) == ACK_RESPONSE
    assert len(ACK_RESPONSE) == 3


def test_serial_config_matches_vendor_spec() -> None:
    # 19200 baud 8N1 — the published Bromic bridge spec.
    assert SERIAL_CONFIG["baudrate"] == 19200
    assert SERIAL_CONFIG["bytesize"] == 8
    assert SERIAL_CONFIG["parity"] == "N"
    assert SERIAL_CONFIG["stopbits"] == 1
    # No hardware/software flow control.
    assert SERIAL_CONFIG["xonxoff"] is False
    assert SERIAL_CONFIG["rtscts"] is False
    assert SERIAL_CONFIG["dsrdtr"] is False


def test_id_range() -> None:
    assert MIN_ID_LOCATION == 1
    assert MAX_ID_LOCATION == 50


def test_safety_retry_bound() -> None:
    # Safety-critical: don't allow unbounded retries on outdoor heater commands.
    # If MAX_RETRIES grows without bharat's review, that's a regression.
    assert MAX_RETRIES == 3
    assert INTER_FRAME_DELAY == 0.1
    assert COMMAND_TIMEOUT == 1.5


def test_off_button_code() -> None:
    assert OFF_BUTTON_CODE == 8
    assert OFF_BUTTON_CODE == MAX_BUTTON_CODE


def test_onoff_buttons_have_on_and_off() -> None:
    assert 1 in ONOFF_BUTTONS
    assert 2 in ONOFF_BUTTONS
    assert ONOFF_BUTTONS[1]["function"] == "turn_on"
    assert ONOFF_BUTTONS[2]["function"] == "turn_off"


def test_dimmer_buttons_have_4_levels_plus_off() -> None:
    assert set(DIMMER_BUTTONS) == {1, 2, 3, 4, OFF_BUTTON_CODE}
    # Higher button number = lower power level (1=100%, 2=75%, 3=50%, 4=25%).
    assert DIMMER_BUTTONS[1]["level"] == 100
    assert DIMMER_BUTTONS[2]["level"] == 75
    assert DIMMER_BUTTONS[3]["level"] == 50
    assert DIMMER_BUTTONS[4]["level"] == 25


def test_brightness_levels_discrete_mapping() -> None:
    # HA 0-255 brightness scale → 5 discrete bridge levels.
    assert set(BRIGHTNESS_LEVELS) == {0, 64, 128, 191, 255}
    assert BRIGHTNESS_LEVELS[0]["button"] == OFF_BUTTON_CODE
    assert BRIGHTNESS_LEVELS[64]["button"] == 4  # 25%
    assert BRIGHTNESS_LEVELS[128]["button"] == 3  # 50%
    assert BRIGHTNESS_LEVELS[191]["button"] == 2  # 75%
    assert BRIGHTNESS_LEVELS[255]["button"] == 1  # 100%


def test_learning_button_sequence_dimmer() -> None:
    # The learning UI walks the user through buttons in this order. Off last.
    assert BUTTON_SEQUENCE_DIMMER == [1, 2, 3, 4, OFF_BUTTON_CODE]


def test_error_codes_cover_vendor_documented_set() -> None:
    # Every documented error code should be present; arbitrary new codes
    # would map to "Unknown error code: XX" in decode_response.
    expected = {
        0x00,  # Framing error
        0x01,  # Checksum error
        0x02,  # Wrong command error
        0x03,  # ID = 0 error
        0x04,  # ID > 2000 error
        0x05,  # Number of code to read/delete = 0 error
        0x06,  # Number of code to read > 16 or >128 error
        0x07,  # Number of code to read/delete > 2000 (out of range) error
        0x08,  # Serial code already stored error
        0x09,  # ID < 201 error
        0x10,  # Empty location transmission attempt error
        0x11,  # Value out of valid codes range memorization attempt error
    }
    assert set(ERROR_CODES) == expected


class TestNormalizeControllerData:
    """Storage-loaded controller data has string keys; we coerce to ints."""

    def test_string_keys_become_ints(self) -> None:
        result = normalize_controller_data(
            {"learned_buttons": {"1": True, "2": False, "8": True}}
        )
        assert result["learned_buttons"] == {1: True, 2: False, 8: True}

    def test_int_keys_pass_through(self) -> None:
        result = normalize_controller_data({"learned_buttons": {1: True, 2: False}})
        assert result["learned_buttons"] == {1: True, 2: False}

    def test_missing_learned_buttons_returns_empty_dict(self) -> None:
        result = normalize_controller_data({"controller_type": "onoff"})
        assert result["learned_buttons"] == {}
        # Other keys are preserved.
        assert result["controller_type"] == "onoff"

    def test_non_castable_keys_swallowed(self) -> None:
        # The function uses `contextlib.suppress(Exception)` — if a key can't
        # be int-cast, it returns the original dict rather than raising.
        result = normalize_controller_data({"learned_buttons": {"not-a-number": True}})
        assert "learned_buttons" in result
