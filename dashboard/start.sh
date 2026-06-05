#!/bin/bash
# Start the link-curator dashboard
# Usage: ./start.sh [PORT]   (default port: 8090, or $ARCHIVE_PORT)
set -e

PORT="${1:-${ARCHIVE_PORT:-8090}}"
HOST="${ARCHIVE_HOST:-127.0.0.1}"
cd "$(dirname "$0")"
exec python3 -m uvicorn main:app --host "$HOST" --port "$PORT"
