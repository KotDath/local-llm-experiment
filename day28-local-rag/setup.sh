#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
uv venv --python python3.12 --allow-existing .venv
uv pip sync --python .venv/bin/python requirements.txt
.venv/bin/python local_models/prepare_tokenizers.py
