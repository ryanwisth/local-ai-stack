#!/bin/bash
# Bring up the local AI stack in order, skipping anything already running:
#   :8000  mtplx        local LLM server (Qwen3.8-27B, MTP speculative decoding)
#   :8600  mcpo         MCP -> OpenAPI bridge for the tool servers in mcpo-config.json
#   :8880  kokoro       local neural TTS (OpenAI-compatible)
#   :8888  searxng      private web search (Docker container, started if it exists)
#   :5001  docling      layout-aware document extraction for RAG
#   :8080  Open WebUI   browser chat UI
# Idempotent: the launchd supervisor runs it at login and every 60 s, so it doubles
# as crash-restart. Run it by hand only from a plain terminal (see docs/runbook.md).
set -e
source "$(dirname "$0")/env.sh"

up() { lsof -iTCP:"$1" -sTCP:LISTEN -P -n >/dev/null 2>&1; }

if up "$LLM_PORT"; then echo "mtplx already up on :$LLM_PORT"
else
  nohup "$SCRIPTS_DIR/start-mtplx.sh" >> "$STACK_HOME/mtplx/server.log" 2>&1 &
  echo "mtplx starting on :$LLM_PORT (model load takes ~30s)"
fi

if pgrep -f 'bin/mcpo --config' >/dev/null 2>&1; then echo "mcpo already running (pid $(pgrep -f 'bin/mcpo --config' | head -1))"
else
  nohup "$SCRIPTS_DIR/start-mcpo.sh" >> "$STACK_HOME/mcp/mcpo.log" 2>&1 &
  echo "mcpo starting on :$MCPO_PORT"
fi

if up "$KOKORO_PORT"; then echo "kokoro TTS already up on :$KOKORO_PORT"
else
  nohup "$SCRIPTS_DIR/start-kokoro.sh" >> "$STACK_HOME/kokoro/kokoro.log" 2>&1 &
  echo "kokoro TTS starting on :$KOKORO_PORT"
fi

if up "$DOCLING_PORT"; then echo "docling already up on :$DOCLING_PORT"
else
  nohup "$SCRIPTS_DIR/start-docling.sh" >> "$STACK_HOME/mcp/docling.log" 2>&1 &
  echo "docling starting on :$DOCLING_PORT"
fi

# searxng is a Docker container with --restart unless-stopped; start it if Docker is up and it is stopped.
if up "$SEARXNG_PORT"; then echo "searxng already up on :$SEARXNG_PORT"
elif docker ps -a --filter name=searxng --format '{{.Names}}' 2>/dev/null | grep -q searxng; then
  docker start searxng >/dev/null 2>&1 && echo "searxng container started on :$SEARXNG_PORT" || echo "searxng: start Docker Desktop first"
else
  echo "searxng: container missing (Docker not running?)"
fi

if up "$WEBUI_PORT"; then echo "Open WebUI already up on :$WEBUI_PORT"
else
  # mcpo mounts its servers one at a time and only listens once all are up (~30 s).
  # Open WebUI fetches every tool spec on first page load, so start it only after mcpo answers,
  # otherwise the tool list comes up nearly empty until the next reload.
  for i in $(seq 1 90); do up "$MCPO_PORT" && break; sleep 1; done
  up "$MCPO_PORT" || echo "warning: mcpo still not listening after 90s; starting Open WebUI anyway"
  nohup "$SCRIPTS_DIR/start-webui.sh" >> "$STACK_HOME/open-webui/webui.log" 2>&1 &
  echo "Open WebUI starting on :$WEBUI_PORT"
fi

echo "UI: http://127.0.0.1:$WEBUI_PORT"
