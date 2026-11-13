#!/bin/bash
# Shared settings for every script in this folder. Source it; do not run it.
# Override any value by exporting it before calling a script.
#
# STACK_HOME holds the runtime side of the stack: venvs, model files, configs,
# the Open WebUI data folder and the logs. The scripts themselves live in this repo.
: "${STACK_HOME:=$HOME/AI}"
# Machine-specific values (model path, label, ports) can live in $STACK_HOME/stack.env.
# launchd does not read your shell profile, so this file is how the supervisor sees them.
[ -f "$STACK_HOME/stack.env" ] && source "$STACK_HOME/stack.env"
: "${STACK_LABEL:=com.example.ai-stack}"     # launchd label of the supervisor
: "${STACK_PLIST:=$HOME/Library/LaunchAgents/$STACK_LABEL.plist}"
: "${BACKUP_ROOT:=$HOME/Backups/ai-stack}"

# Ports (defaults; every service binds 127.0.0.1)
: "${LLM_PORT:=8000}"        # mtplx, OpenAI-compatible
: "${WEBUI_PORT:=8080}"      # Open WebUI
: "${MCPO_PORT:=8600}"       # mcpo, MCP -> OpenAPI bridge
: "${KOKORO_PORT:=8880}"     # Kokoro TTS
: "${SEARXNG_PORT:=8888}"    # SearXNG (Docker)
: "${DOCLING_PORT:=5001}"    # Docling document extraction
: "${TASKMODEL_PORT:=8001}"  # optional small task model (not started by start-stack.sh)

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
export STACK_HOME STACK_LABEL STACK_PLIST BACKUP_ROOT LLM_PORT WEBUI_PORT MCPO_PORT \
       KOKORO_PORT SEARXNG_PORT DOCLING_PORT TASKMODEL_PORT SCRIPTS_DIR REPO_DIR

# launchd runs jobs with a bare PATH; make user-installed tools visible (uv, mcpo, docling, node, docker).
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
