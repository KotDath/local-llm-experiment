#!/usr/bin/env bash
set -euo pipefail
LLAMA_ROOT="${LLAMA_ROOT:-/home/kotdath/omp/personal/llama.cpp}"
BGE_MODEL="${BGE_MODEL:-/home/kotdath/.local/share/domovoy-rag/models/bge-reranker-v2-m3-f16.gguf}"
SERVER="$LLAMA_ROOT/build-vulkan-radv-opt/bin/llama-server"
export LD_LIBRARY_PATH="$(dirname "$SERVER")${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$SERVER" --model "$BGE_MODEL" --embedding --pooling rank --reranking \
 --alias bge-reranker-v2-m3-0c5784a1f340 --host 127.0.0.1 --port 8766 \
 --ctx-size 8192 --parallel 1 --batch-size 8192 --ubatch-size 8192 --threads 8 --gpu-layers 99
