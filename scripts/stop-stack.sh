#!/bin/bash
# Stop the whole stack. Unloads the launchd supervisor FIRST; otherwise it would
# restart everything within 60 s. Re-enable with:
#   launchctl bootstrap gui/$(id -u) "$STACK_PLIST"
source "$(dirname "$0")/env.sh"
launchctl bootout "gui/$(id -u)/$STACK_LABEL" 2>/dev/null && echo "supervisor unloaded" || echo "supervisor was not loaded"
pkill -f 'open-webui serve'      && echo "stopped Open WebUI"  || true
pkill -f 'bin/mcpo --config'     && echo "stopped mcpo"        || true
pkill -f 'kokoro-server.py'      && echo "stopped kokoro"      || true
pkill -f 'docling-serve run'     && echo "stopped docling"     || true
pkill -f 'mtplx.server.openai|mtplx quickstart' && echo "stopped mtplx" || true   # the real server is 'python -m mtplx.server.openai'; 'quickstart' is only its launcher
echo "searxng (Docker) left as-is; 'docker stop searxng' if you want it down too"
