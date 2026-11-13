#!/bin/bash
# Optional second, small model next to the 27B: Qwen3-1.7B-4bit via mlx_lm.server (OpenAI-compatible).
# Purpose: Open WebUI background jobs (titles, tags, query rewrite) and, later, serving a LoRA
# adapter (mtplx has no adapter flag):  add  --adapter-path /path/to/adapters
# Register it in Open WebUI as a second OpenAI connection, then Admin > Settings > Interface > Task Model.
# Not started by start-stack.sh. Download the weights first: hf download mlx-community/Qwen3-1.7B-4bit
source "$(dirname "$0")/env.sh"
source "$STACK_HOME/mtplx/.venv/bin/activate"   # the mtplx venv already ships mlx-lm
exec mlx_lm.server \
  --model mlx-community/Qwen3-1.7B-4bit \
  --host 127.0.0.1 --port "$TASKMODEL_PORT"
