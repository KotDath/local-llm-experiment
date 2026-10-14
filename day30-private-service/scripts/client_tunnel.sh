#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${HOST_IP:?Set HOST_IP}" "${SERVER_LOGIN:?Set SERVER_LOGIN}"
key_args=()
key="${TUNNEL_KEY:-$ROOT/runtime/tunnel_key}"
if test -f "$key"; then key_args=(-i "$key"); fi
exec ssh "${key_args[@]}" -p "${SERVER_PORT:-22}" -o IdentitiesOnly=yes \
 -o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes \
 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
 -N -L "${CLIENT_PORT:-8781}:127.0.0.1:8781" "$SERVER_LOGIN@$HOST_IP"
