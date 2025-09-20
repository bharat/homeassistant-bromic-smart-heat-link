#!/usr/bin/env bash
set -Eeuo pipefail

# tty-bridge-container.sh
# Creates a PTY inside the container that bridges to the host TCP listener.
#
# Usage:
#   scripts/tty-bridge-container.sh [-H host.docker.internal] [-p 7777]
#
# Prints the created PTY path to stdout, then keeps the bridge running in the foreground.

print_usage() {
  cat <<'USAGE'
Usage: tty-bridge-container.sh [-H <host>] [-p <tcp_port>]

Options:
  -H, --host   Hostname or IP of the TCP bridge (default: host.docker.internal)
  -p, --port   TCP port of the bridge (default: 7777)
  -h, --help   Show this help message

Examples:
  scripts/tty-bridge-container.sh
  scripts/tty-bridge-container.sh -H 172.17.0.1 -p 7777
USAGE
}

HOST="host.docker.internal"
PORT="7777"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -H|--host)
      HOST="$2"; shift 2 ;;
    -p|--port)
      PORT="$2"; shift 2 ;;
    -h|--help)
      print_usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      print_usage
      exit 1 ;;
  esac
done

if ! command -v socat >/dev/null 2>&1; then
  echo "Error: socat is not installed or not in PATH" >&2
  exit 1
fi

LOG_FILE=$(mktemp)
cleanup() {
  rm -f "$LOG_FILE" || true
}
trap cleanup EXIT

echo "[tty-bridge-container] Connecting to ${HOST}:${PORT} and creating PTY" >&2

# Start socat in the background and log to a file to avoid killing it when parsing output
socat -d -d -lf "$LOG_FILE" pty,raw,echo=0 TCP:"${HOST}":"${PORT}" &
SOCAT_PID=$!

# Ensure child is terminated when this script receives termination
trap 'kill -TERM ${SOCAT_PID} 2>/dev/null || true' INT TERM

# Wait until the PTY is announced in the log (with a timeout)
PTY=""
for _ in {1..50}; do
  if grep -qE 'PTY is (/dev/pts/[0-9]+)' "$LOG_FILE"; then
    PTY=$(sed -nE 's/.*PTY is ((\/dev\/pts\/[0-9]+)).*/\1/p' "$LOG_FILE" | head -n1)
    break
  fi
  sleep 0.1
done

if [[ -z "$PTY" ]]; then
  echo "[tty-bridge-container] Failed to detect PTY path" >&2
  kill -TERM ${SOCAT_PID} 2>/dev/null || true
  wait ${SOCAT_PID} 2>/dev/null || true
  exit 1
fi

# Output PTY path to stdout for scripts to capture
echo "$PTY"

echo "[tty-bridge-container] PTY is $PTY (bridge running). Press Ctrl-C to stop." >&2

# Stream logs to stderr while keeping the process in foreground
tail -f "$LOG_FILE" 1>&2 &
TAIL_PID=$!

wait ${SOCAT_PID}
kill ${TAIL_PID} 2>/dev/null || true
wait ${TAIL_PID} 2>/dev/null || true
