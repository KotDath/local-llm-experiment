#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
if test -x "$ROOT/.venv/bin/python"; then
 export DOWNLOAD_BACKEND="${DOWNLOAD_BACKEND:-range}"
 export DOWNLOAD_WORKERS="${DOWNLOAD_WORKERS:-24}"
 export DOWNLOAD_SMALL_RANGES="${DOWNLOAD_SMALL_RANGES:-1}"
 export DOWNLOAD_SIGNED_URL="${DOWNLOAD_SIGNED_URL:-1}"
 exec "$ROOT/.venv/bin/python" "$ROOT/download_q4.py"
fi
exec python3 "$ROOT/download_q4.py"
