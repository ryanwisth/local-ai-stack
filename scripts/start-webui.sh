#!/bin/bash
# Open WebUI -> mtplx. Chat history, image upload, file attachments, RAG, tools, voice.
# mtplx must already be running (start-stack.sh handles the order).
set -e
source "$(dirname "$0")/env.sh"
# Open WebUI reads/writes .webui_secret_key in the CURRENT DIRECTORY. Under launchd the cwd is /,
# which is read-only, so pin it here or the service crash-loops.
cd "$STACK_HOME/open-webui"
source "$STACK_HOME/open-webui/.venv/bin/activate"

export OPENAI_API_BASE_URL="http://127.0.0.1:$LLM_PORT/v1"
export OPENAI_API_KEY="local"          # mtplx ignores it on loopback
export ENABLE_OLLAMA_API=False         # no Ollama in this stack
export WEBUI_AUTH=False                # single local user, no login screen (loopback only!)
export ANONYMIZED_TELEMETRY=False
export DO_NOT_TRACK=1
export SCARF_NO_ANALYTICS=True
export DATA_DIR="$STACK_HOME/open-webui/data"
export HOST=127.0.0.1
export PORT="$WEBUI_PORT"

exec open-webui serve --host "$HOST" --port "$PORT"
