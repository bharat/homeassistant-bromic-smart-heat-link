#!/usr/bin/env python3
"""
Send a Bromic raw command over a TTY and print the hex reply.

Usage examples:
  scripts/serial_send.py /dev/pts/8 --raw 540001000156
  scripts/serial_send.py /dev/pts/8 --id 1 --code 0x08
"""

from __future__ import annotations

import argparse
import binascii
import sys

import serial

BAUDRATE = 19200
TIMEOUT_S = 1.0


def calculate_checksum(data: bytes) -> int:
    """Calculate 8-bit checksum of the provided bytes."""
    return sum(data) & 0xFF


MAX_TEST_ID = 2000
MAX_CODE = 0xFFFF


def build_frame_from_id_code(id_location: int, code: int) -> bytes:
    """Build a Bromic frame for an ID/code pair."""
    if not (1 <= id_location <= MAX_TEST_ID):  # generous bounds for testing
        message = "id_location out of range"
        raise ValueError(message)
    if not (0 <= code <= MAX_CODE):
        message = "code out of range"
        raise ValueError(message)
    cmd = 0x54
    id_bytes = id_location.to_bytes(2, "big")
    code_bytes = code.to_bytes(2, "big")
    frame_wo_ck = bytes([cmd]) + id_bytes + code_bytes
    checksum = calculate_checksum(frame_wo_ck)
    return frame_wo_ck + bytes([checksum])


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Send Bromic raw command")
    parser.add_argument("tty", help="Serial device path, e.g., /dev/pts/8")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--raw", help="Raw hex frame, e.g., 540001000156")
    group.add_argument("--id", type=int, help="ID location (1-2000)")
    parser.add_argument("--code", help="Button/code (decimal or 0x..) when using --id")
    parser.add_argument(
        "--read-bytes", type=int, default=16, help="Max bytes to read (default 16)"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Program entrypoint."""
    args = parse_args(argv or sys.argv[1:])

    if args.raw:
        try:
            frame = binascii.unhexlify(args.raw.replace(" ", ""))
        except (binascii.Error, ValueError):
            sys.stderr.write("Invalid --raw hex string\n")
            return 2
    else:
        if args.code is None:
            sys.stderr.write("--code is required when using --id\n")
            return 2
        code_val = int(args.code, 0)
        frame = build_frame_from_id_code(args.id, code_val)

    with serial.Serial(
        args.tty,
        baudrate=BAUDRATE,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=TIMEOUT_S,
        xonxoff=False,
        rtscts=False,
    ) as s:
        s.reset_input_buffer()
        s.write(frame)
        s.flush()
        data = s.read(args.read_bytes)
        sys.stdout.write(binascii.hexlify(data).decode() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
