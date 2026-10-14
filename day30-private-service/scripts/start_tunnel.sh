#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${HOST_IP:?Set HOST_IP}" "${SERVER_LOGIN:?Set SERVER_LOGIN}"
exec ssh -i "${TUNNEL_KEY:-$ROOT/runtime/tunnel_key}" -p "${SERVER_PORT:-22}" \
 -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes \
 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -N \
 -R 127.0.0.1:18780:127.0.0.1:8780 "$SERVER_LOGIN@$HOST_IP"
