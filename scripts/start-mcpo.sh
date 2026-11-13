#!/bin/bash
# mcpo: bridges the stdio MCP servers in mcpo-config.json to OpenAPI endpoints
# that Open WebUI registers as tool servers (one per subpath, e.g. :8600/fetch).
# Loopback only; CORS limited to the Open WebUI origin. The bearer key must match
# every tool-server row in Open WebUI (Admin Settings > Tools); rotate both together.
# Create the key once:  umask 077; openssl rand -hex 23 > "$STACK_HOME/mcp/.bearer"
set -e
source "$(dirname "$0")/env.sh"
mkdir -p "$STACK_HOME/mcp/data"

exec mcpo \
  --config "$STACK_HOME/mcp/mcpo-config.json" \
  --host 127.0.0.1 \
  --port "$MCPO_PORT" \
  --cors-allow-origins "http://127.0.0.1:$WEBUI_PORT" \
  --api-key "$(cat "$STACK_HOME/mcp/.bearer")"
