#!/bin/bash
# Back up the parts of the stack that cannot be rebuilt from a download.
# Safe to run while services are up. Keeps the newest 10 backups.
#
# Treat $BACKUP_ROOT as secret: mcpo-config.json can hold tool tokens.
# The mcpo bearer key (.bearer) is deliberately NOT copied; regenerate it on restore
# and update the Open WebUI tool-server rows to match.
set -e
source "$(dirname "$0")/env.sh"
D="$BACKUP_ROOT/$(date +%F_%H%M)"; mkdir -p "$D"

# Open WebUI keeps ALL of its configuration (models/personas, prompts, functions, tool wiring,
# knowledge bases, chats) in one SQLite file. sqlite's .backup is consistent even with the WAL hot.
sqlite3 "$STACK_HOME/open-webui/data/webui.db" ".backup '$D/webui.db'"
rsync -a "$STACK_HOME/open-webui/data/uploads/" "$D/uploads/" 2>/dev/null || true

# Tool layer: mcpo roster and any local MCP wrappers, minus the bearer and logs.
rsync -a --exclude '.bearer' --exclude '*.log' "$STACK_HOME/mcp/" "$D/mcp/"

# Launchers and the supervisor plist: losing these silently loses tuned settings
# (for example the raised tool-call guard in start-mtplx.sh).
rsync -a "$SCRIPTS_DIR/" "$D/scripts/"
cp "$STACK_PLIST" "$D/" 2>/dev/null || true

# Optional extra folders, space-separated: BACKUP_EXTRA="$HOME/notes $HOME/.config/some-tool"
for extra in ${BACKUP_EXTRA:-}; do
  [ -e "$extra" ] && rsync -a "$extra" "$D/extra/" || true
done

ls -dt "$BACKUP_ROOT"/* | tail -n +11 | xargs rm -rf 2>/dev/null || true   # keep last 10
echo "backup -> $D ($(du -sh "$D" | cut -f1))"
