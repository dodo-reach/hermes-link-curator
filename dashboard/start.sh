#!/bin/bash
# Start the link-curator dashboard
# Usage: ./start.sh [PORT]   (default port: 8090, or $ARCHIVIO_PORT)
set -e

PORT="${1:-${ARCHIVIO_PORT:-8090}}"
cd "$(dirname "$0")"
exec python3 -m uvicorn main:app --host 0.0.0.0 --port "$PORT"
