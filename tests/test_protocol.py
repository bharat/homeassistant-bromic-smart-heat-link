"""Tests for the Bromic protocol encoding / decoding layer.

The protocol is the most testable piece of the integration: pure functions
operating on bytes. These tests pin down the wire-format behavior — exactly
what bytes go out for a given (id, button), how each response shape is
classified (ACK / error / unknown), checksum validation, and the round-trip
through `parse_hex_command`.
"""

from __future__ import annotations

import pytest

from custom_components.bromic_smart_heat_link.const import (
    ACK_RESPONSE,
    COMMAND_BYTE,
    ERROR_CODES,
    ERROR_COMMAND,
    MAX_BUTTON_CODE,
    MAX_ID_LOCATION,
)
from custom_components.bromic_smart_heat_link.exceptions import (
    BromicChecksumError,
    BromicInvalidResponseError,
    BromicProtocolError,
)
from custom_components.bromic_smart_heat_link.protocol import (
    BromicCommand,
    BromicProtocol,
    BromicResponse,
)


class TestCalculateChecksum:
    """`calculate_checksum` is a sum-mod-256 over the input bytes."""

    def test_empty_returns_zero(self) -> None:
        assert BromicProtocol.calculate_checksum(b"") == 0

    def test_single_byte(self) -> None:
        assert BromicProtocol.calculate_checksum(bytes([0x42])) == 0x42

    def test_known_canonical_frame(self) -> None:
        # The docstring example "540001000156" decomposes as T+ID(0001)+BTN(0001)+CK(56).
        # Checksum over the first 5 bytes: 0x54 + 0x00 + 0x01 + 0x00 + 0x01 = 0x56.
        data = bytes([0x54, 0x00, 0x01, 0x00, 0x01])
        assert BromicProtocol.calculate_checksum(data) == 0x56

    def test_wraps_mod_256(self) -> None:
        # 0xFF + 0xFF = 0x1FE → 0xFE after mod 256.
        assert BromicProtocol.calculate_checksum(bytes([0xFF, 0xFF])) == 0xFE

    def test_all_ones_wraps_to_zero(self) -> None:
        # 256 * 0x01 = 0x100 → 0x00 after mod 256.
        assert BromicProtocol.calculate_checksum(bytes([0x01] * 256)) == 0x00


class TestEncodeCommand:
    """`encode_command` produces a 6-byte frame: T + ID(big-endian, 2B) + BTN(2B) + checksum."""

    def test_minimum_id_minimum_button(self) -> None:
        cmd = BromicProtocol.encode_command(1, 1)
        assert isinstance(cmd, BromicCommand)
        assert cmd.id_location == 1
        assert cmd.button_code == 1
        assert cmd.raw_bytes == bytes([0x54, 0x00, 0x01, 0x00, 0x01, 0x56])
        assert len(cmd.raw_bytes) == 6

    def test_id_byte_layout_is_big_endian_two_bytes(self) -> None:
        # Legal IDs are 1..50 — they fit in 1 byte. The protocol still
        # reserves 2 bytes for ID, with the high byte zeroed.
        cmd = BromicProtocol.encode_command(25, 4)
        assert cmd.raw_bytes[1] == 0x00  # high byte
        assert cmd.raw_bytes[2] == 25  # low byte

    def test_button_byte_layout_is_big_endian_two_bytes(self) -> None:
        # Legal buttons are 1..8 — also single-byte values. Verify the
        # 2-byte big-endian slot is laid out correctly.
        cmd = BromicProtocol.encode_command(1, 7)
        assert cmd.raw_bytes[3] == 0x00  # high byte
        assert cmd.raw_bytes[4] == 7  # low byte

    def test_checksum_is_last_byte(self) -> None:
        cmd = BromicProtocol.encode_command(25, 4)
        expected_ck = BromicProtocol.calculate_checksum(cmd.raw_bytes[:-1])
        assert cmd.raw_bytes[-1] == expected_ck

    def test_max_id_max_button(self) -> None:
        cmd = BromicProtocol.encode_command(MAX_ID_LOCATION, MAX_BUTTON_CODE)
        assert cmd.id_location == MAX_ID_LOCATION
        assert cmd.button_code == MAX_BUTTON_CODE
        # Frame validates against the round-trip.
        assert BromicProtocol.validate_frame(cmd.raw_bytes) is True

    @pytest.mark.parametrize("bad_id", [0, -1, MAX_ID_LOCATION + 1, 1000])
    def test_invalid_id_raises(self, bad_id: int) -> None:
        with pytest.raises(BromicProtocolError, match="Invalid ID location"):
            BromicProtocol.encode_command(bad_id, 1)

    @pytest.mark.parametrize("bad_btn", [0, -1, MAX_BUTTON_CODE + 1, 1000])
    def test_invalid_button_raises(self, bad_btn: int) -> None:
        with pytest.raises(BromicProtocolError, match="Invalid button code"):
            BromicProtocol.encode_command(1, bad_btn)

    def test_off_button_code_8_accepted(self) -> None:
        # OFF_BUTTON_CODE = 8 must be in range [1, MAX_BUTTON_CODE].
        cmd = BromicProtocol.encode_command(1, 8)
        assert cmd.button_code == 8


class TestDecodeResponse:
    """`decode_response` classifies inbound bytes into ACK / error / unknown / invalid."""

    def test_ack_response_is_success(self) -> None:
        resp = BromicProtocol.decode_response(ACK_RESPONSE)
        assert isinstance(resp, BromicResponse)
        assert resp.success is True
        assert resp.error_code is None
        assert resp.raw_bytes == ACK_RESPONSE

    def test_empty_data_raises_invalid(self) -> None:
        with pytest.raises(BromicInvalidResponseError, match="Empty response"):
            BromicProtocol.decode_response(b"")

    def test_too_short_raises_invalid(self) -> None:
        # Less than MIN_STD_RESPONSE_LENGTH (3) and not ACK / not error.
        with pytest.raises(BromicInvalidResponseError, match="Response too short"):
            BromicProtocol.decode_response(bytes([0x00, 0x00]))

    @pytest.mark.parametrize("error_code", sorted(ERROR_CODES))
    def test_each_documented_error_code(self, error_code: int) -> None:
        # 'E' + code + filler byte, total 3 bytes — the error-response shape.
        data = bytes([ERROR_COMMAND, error_code, 0x00])
        resp = BromicProtocol.decode_response(data)
        assert resp.success is False
        assert resp.error_code == error_code
        assert resp.message == ERROR_CODES[error_code]
        assert resp.raw_bytes == data

    def test_unknown_error_code_falls_back_to_hex_string(self) -> None:
        # 0xFE is not in ERROR_CODES; message includes the hex.
        data = bytes([ERROR_COMMAND, 0xFE, 0x00])
        resp = BromicProtocol.decode_response(data)
        assert resp.success is False
        assert resp.error_code == 0xFE
        assert "FE" in resp.message

    def test_checksum_mismatch_raises(self) -> None:
        # 4-byte frame starting with neither ACK nor 'E'. Bad checksum.
        data = bytes([0x99, 0x01, 0x02, 0xAA])  # checksum should be 0x9C, not 0xAA
        with pytest.raises(BromicChecksumError, match="Checksum mismatch"):
            BromicProtocol.decode_response(data)

    def test_unknown_response_with_valid_checksum_is_failure_but_no_error_code(
        self,
    ) -> None:
        # Build a frame that's neither ACK nor an error response shape, with a
        # valid checksum, so decode_response classifies it as "unknown".
        body = bytes([0x99, 0x01])
        ck = BromicProtocol.calculate_checksum(body)
        good_frame = body + bytes([ck])
        resp = BromicProtocol.decode_response(good_frame)
        # Not ACK, not error-shape, but checksum valid → unknown but not raise.
        assert resp.success is False
        assert resp.error_code is None
        assert "Unknown response" in resp.message


class TestValidateFrame:
    """`validate_frame` returns True iff frame is well-formed and checksum matches."""

    def test_round_trip_with_encode_command(self) -> None:
        cmd = BromicProtocol.encode_command(10, 3)
        assert BromicProtocol.validate_frame(cmd.raw_bytes) is True

    def test_too_short_is_false(self) -> None:
        assert BromicProtocol.validate_frame(bytes([0x54, 0x00, 0x01])) is False

    def test_wrong_command_byte_is_false(self) -> None:
        # Frame is 6 bytes with valid checksum but wrong command byte.
        body = bytes([0x00, 0x00, 0x01, 0x00, 0x01])
        ck = BromicProtocol.calculate_checksum(body)
        frame = body + bytes([ck])
        assert BromicProtocol.validate_frame(frame) is False

    def test_bad_checksum_is_false(self) -> None:
        # 6-byte frame, command byte right, checksum wrong.
        bad = bytes([COMMAND_BYTE, 0x00, 0x01, 0x00, 0x01, 0xAA])
        assert BromicProtocol.validate_frame(bad) is False

    def test_empty_is_false(self) -> None:
        assert BromicProtocol.validate_frame(b"") is False


class TestGetCommandExamples:
    """`get_command_examples` returns hex strings for the first few IDs × buttons."""

    def test_returns_dict_of_dicts(self) -> None:
        examples = BromicProtocol.get_command_examples()
        assert isinstance(examples, dict)
        assert all(isinstance(v, dict) for v in examples.values())

    def test_covers_first_four_ids(self) -> None:
        examples = BromicProtocol.get_command_examples()
        assert set(examples.keys()) == {1, 2, 3, 4}

    def test_each_example_round_trips(self) -> None:
        examples = BromicProtocol.get_command_examples()
        for id_loc, buttons in examples.items():
            for button, hex_str in buttons.items():
                parsed = BromicProtocol.parse_hex_command(hex_str)
                assert parsed is not None, (
                    f"Round-trip failed for ID={id_loc}, Button={button}"
                )
                assert parsed.id_location == id_loc
                assert parsed.button_code == button


class TestParseHexCommand:
    """`parse_hex_command` is the inverse of `encode_command` for valid frames."""

    def test_canonical_round_trip(self) -> None:
        cmd = BromicProtocol.encode_command(1, 1)
        parsed = BromicProtocol.parse_hex_command(cmd.raw_bytes.hex())
        assert parsed is not None
        assert parsed.id_location == 1
        assert parsed.button_code == 1
        assert parsed.raw_bytes == cmd.raw_bytes

    def test_uppercase_hex_works(self) -> None:
        parsed = BromicProtocol.parse_hex_command("540001000156")
        assert parsed is not None
        assert parsed.id_location == 1

    def test_with_spaces_works(self) -> None:
        parsed = BromicProtocol.parse_hex_command("54 00 01 00 01 56")
        assert parsed is not None
        assert parsed.id_location == 1

    def test_with_colons_works(self) -> None:
        parsed = BromicProtocol.parse_hex_command("54:00:01:00:01:56")
        assert parsed is not None
        assert parsed.id_location == 1

    def test_wrong_length_returns_none(self) -> None:
        # 5 bytes, not 6.
        assert BromicProtocol.parse_hex_command("5400010001") is None

    def test_wrong_command_byte_returns_none(self) -> None:
        # 6-byte frame, valid checksum, but starts with 0x00 not 0x54.
        body = bytes([0x00, 0x00, 0x01, 0x00, 0x01])
        ck = BromicProtocol.calculate_checksum(body)
        bad = (body + bytes([ck])).hex()
        assert BromicProtocol.parse_hex_command(bad) is None

    def test_bad_checksum_returns_none(self) -> None:
        # First 5 bytes correct, last byte wrong.
        assert BromicProtocol.parse_hex_command("5400010001FF") is None

    def test_non_hex_returns_none(self) -> None:
        assert BromicProtocol.parse_hex_command("not hex at all") is None

    def test_empty_returns_none(self) -> None:
        assert BromicProtocol.parse_hex_command("") is None

    def test_round_trips_high_id_and_button(self) -> None:
        cmd = BromicProtocol.encode_command(MAX_ID_LOCATION, MAX_BUTTON_CODE)
        parsed = BromicProtocol.parse_hex_command(cmd.raw_bytes.hex())
        assert parsed is not None
        assert parsed.id_location == MAX_ID_LOCATION
        assert parsed.button_code == MAX_BUTTON_CODE
