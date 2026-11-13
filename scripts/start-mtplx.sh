#!/bin/bash
# mtplx: OpenAI-compatible server for Qwen3.8-27B with native MTP (Multi-Token Prediction)
# speculative decoding. Measured on an M5 Pro / 64 GB: 13.2 tok/s plain decode -> 31.8 tok/s MTP (2.41x).
# Flags were checked against `mtplx quickstart --help` on 2.9.2 and run unchanged on 2.10.2.
set -e
source "$(dirname "$0")/env.sh"

# Path to the downloaded model snapshot, for example
#   ~/.cache/huggingface/hub/models--Youssofal--Qwen3.8-27B-MTPLX-Optimized-Speed/snapshots/<revision>
: "${MTPLX_MODEL:?set MTPLX_MODEL to the model snapshot directory}"
source "$STACK_HOME/mtplx/.venv/bin/activate"

# mtplx silently DROPS any streamed tool call whose hidden arguments exceed this many tokens
# (default 2048 / 30 s, tuned for chat UX). Agent runs write whole source files as tool
# arguments, so a big write_file tripped the guard and the turn ended with the model announcing
# a file it never wrote. Set to the full context window so the guard never fires before the context does.
export MTPLX_STREAM_HIDDEN_TOOL_GUARD_TOKENS=262144
export MTPLX_STREAM_HIDDEN_TOOL_GUARD_S=86400

# Optional: cap the on-disk warm KV session bank (it is uncapped by default and grew past 100 GB).
# export MTPLX_SESSION_BANK_MAX_BYTES=20G

exec mtplx quickstart \
  --model "$MTPLX_MODEL" \
  --host 127.0.0.1 --port "$LLM_PORT" \
  --profile turbo \
  --mtp --depth 3 \
  --default-temperature 1.0 \
  --default-top-p 0.95 \
  --default-top-k 20 \
  --default-presence-penalty 0 \
  --default-frequency-penalty 0 \
  --paged-kv-quantization off \
  --scheduler-mode serial \
  --ssd-session-cache on
