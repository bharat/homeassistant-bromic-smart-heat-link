#!/usr/bin/env bash
set -Eeuo pipefail

# tty-bridge-host.sh
# Creates a TCP listener that bridges to a local serial TTY using socat.
# Works on macOS and Linux by configuring the serial line with stty first.
#
# Usage:
#   scripts/tty-bridge-host.sh -d /dev/ttys021 [-p 7777] [-b 19200] [--rtscts]
#
# Then, in the container, run the companion script to create a PTY that
# connects to this TCP listener.

print_usage() {
  cat <<'USAGE'
Usage: tty-bridge-host.sh -d <device> [-p <tcp_port>] [-b <baud>] [--rtscts]

Options:
  -d, --device    Serial device path (e.g., /dev/ttys021 or /dev/ttyUSB0) [required]
  -p, --port      TCP port to listen on (default: 7777)
  -b, --baud      Baud rate (default: 19200)
      --rtscts    Enable hardware flow control (RTS/CTS). Default is disabled
  -h, --help      Show this help message

Examples:
  scripts/tty-bridge-host.sh -d /dev/ttys021
  scripts/tty-bridge-host.sh -d /dev/ttyUSB0 -p 7777 -b 38400 --rtscts
USAGE
}

DEVICE=""
PORT="7777"
BAUD="19200"
USE_RTSCTS="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--device)
      DEVICE="$2"; shift 2 ;;
    -p|--port)
      PORT="$2"; shift 2 ;;
    -b|--baud)
      BAUD="$2"; shift 2 ;;
    --rtscts)
      USE_RTSCTS="1"; shift ;;
    -h|--help)
      print_usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      print_usage
      exit 1 ;;
  esac
done

if [[ -z "$DEVICE" ]]; then
  echo "Error: --device is required" >&2
  print_usage
  exit 1
fi

if ! command -v socat >/dev/null 2>&1; then
  echo "Error: socat is not installed or not in PATH" >&2
  exit 1
fi

if ! command -v stty >/dev/null 2>&1; then
  echo "Error: stty is not installed or not in PATH" >&2
  exit 1
fi

OS_NAME="$(uname -s || true)"

# Configure serial line using stty in a portable way
if [[ "$OS_NAME" == "Darwin" ]]; then
  # macOS uses -f to select device
  # 8N1, disable software/hardware flow control by default
  STTY_CMD=(stty -f "$DEVICE" raw "$BAUD" cs8 -parenb -cstopb -ixon -ixoff clocal -hupcl)
  if [[ "$USE_RTSCTS" == "1" ]]; then
    # Enable hardware flow control on macOS
    STTY_CMD+=(crtscts)
  else
    STTY_CMD+=(-crtscts)
  fi
else
  # Linux and others use -F
  STTY_CMD=(stty -F "$DEVICE" raw "$BAUD" cs8 -parenb -cstopb -ixon -ixoff clocal -hupcl)
  if [[ "$USE_RTSCTS" == "1" ]]; then
    STTY_CMD+=(crtscts)
  else
    STTY_CMD+=(-crtscts)
  fi
fi

echo "[tty-bridge-host] Configuring $DEVICE at ${BAUD} 8N1, rtscts=${USE_RTSCTS}" >&2
"${STTY_CMD[@]}"

echo "[tty-bridge-host] Listening on TCP port ${PORT} and bridging to ${DEVICE}" >&2
echo "[tty-bridge-host] Press Ctrl-C to stop" >&2

# Run socat and also pass explicit termios so it does not override stty on open
SOCAT_FILE_OPTS=("raw,echo=0,ispeed=${BAUD},ospeed=${BAUD},cs8,parenb=0,cstopb=0,ixon=0,ixoff=0,clocal,cread")
if [[ "$USE_RTSCTS" == "1" ]]; then
  SOCAT_FILE_OPTS=("raw,echo=0,ispeed=${BAUD},ospeed=${BAUD},cs8,parenb=0,cstopb=0,ixon=0,ixoff=0,crtscts=1,clocal,cread")
else
  SOCAT_FILE_OPTS=("raw,echo=0,ispeed=${BAUD},ospeed=${BAUD},cs8,parenb=0,cstopb=0,ixon=0,ixoff=0,crtscts=0,clocal,cread")
fi

exec socat -d -d -v -x \
  TCP-LISTEN:"${PORT}",reuseaddr,fork \
  FILE:"${DEVICE}",${SOCAT_FILE_OPTS[0]}
