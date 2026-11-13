#!/bin/bash
# Local Kokoro neural TTS server (OpenAI-compatible /v1/audio/speech) for Open WebUI.
# Expects kokoro-v1.0.onnx and voices-v1.0.bin in $STACK_HOME/kokoro and a venv there.
set -e
source "$(dirname "$0")/env.sh"
cd "$STACK_HOME/kokoro"
export KOKORO_DIR="$STACK_HOME/kokoro"
exec .venv/bin/python "$REPO_DIR/services/kokoro/kokoro-server.py"
