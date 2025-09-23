#!/usr/bin/env python3
"""
Quick serial round-trip test that writes one command and dumps the reply.

Usage: scripts/serial_test.py /dev/pts/N
"""

from __future__ import annotations

import binascii
import sys

import serial

USAGE_EXIT_CODE = 2
MIN_ARGS = 2


def main() -> int:
    """Run the serial round-trip test."""
    if len(sys.argv) < MIN_ARGS:
        sys.stderr.write("Usage: serial_test.py <tty>\n")
        return USAGE_EXIT_CODE

    port = sys.argv[1]
    with serial.Serial(
        port,
        baudrate=19200,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=1,
        xonxoff=False,
        rtscts=False,
    ) as s:
        s.reset_input_buffer()
        s.write(binascii.unhexlify("540001000156"))
        s.flush()
        data = binascii.hexlify(s.read(16)).decode()
        sys.stdout.write(f"{data}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
