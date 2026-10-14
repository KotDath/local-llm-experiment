#!/usr/bin/env bash
set -euo pipefail
LLAMA_ROOT="${LLAMA_ROOT:-/home/kotdath/omp/personal/llama.cpp}"
MODEL_DIR="${MODEL_DIR:-/home/kotdath/omp/personal/amd-strix-halo-toolboxes/models/tiel-coder}"
QUANT="${QUANT:-Q8}"
case "$QUANT" in
 Q8) filename=Tiel-Coder-35B-A3B-MTP-UD-Q8_K_XL.gguf ;;
 Q4) filename=Tiel-Coder-35B-A3B-MTP-UD-Q4_K_XL.gguf ;;
 *) echo 'QUANT must be Q8 or Q4' >&2; exit 2 ;;
esac
MODEL="${MODEL:-$MODEL_DIR/$filename}"
BACKEND="${BACKEND:-vulkan}"
case "$BACKEND" in
 vulkan) SERVER="${SERVER:-$LLAMA_ROOT/build-vulkan-radv-opt/bin/llama-server}"; DEVICE=Vulkan0 ;;
 rocm) SERVER="${SERVER:-$LLAMA_ROOT/build-rocm-7.2.2/bin/llama-server}"; DEVICE=ROCm0 ;;
 *) echo 'BACKEND must be vulkan or rocm' >&2; exit 2 ;;
esac
PARALLEL="${PARALLEL:-3}"
CTX_PER_SLOT="${CTX_PER_SLOT:-32768}"
PORT="${PORT:-8772}"
test -f "$MODEL" && test -x "$SERVER"
export LD_LIBRARY_PATH="$(dirname "$SERVER"):/opt/rocm-7.2.2/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$SERVER" --model "$MODEL" --alias tiel-coder --device "$DEVICE" \
 --ctx-size "$((PARALLEL * CTX_PER_SLOT))" --parallel "$PARALLEL" \
 --gpu-layers 999 --flash-attn on --no-mmap --cache-type-k f16 --cache-type-v f16 \
 --batch-size 2048 --ubatch-size 1024 --threads 16 --jinja --reasoning off \
 --no-context-shift --temp 1 --top-p 0.95 --top-k 20 --min-p 0 \
 --repeat-penalty 1 --host 127.0.0.1 --port "$PORT" "$@"
