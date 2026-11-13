#!/bin/bash
# Install (or update) an Open WebUI Function from a file and activate it.
# usage: install-owui-function.sh <file.py> <id> "<Name>" <pipe|filter|action> [global:0|1]
# Pipes show up as selectable MODELS; filters/actions attach to models (global=1 = all models).
# Assumes Open WebUI runs with WEBUI_AUTH=False (single local user), as start-webui.sh sets it.
#
# The only direct database write is a single-row UPDATE on the `function` table to set
# is_active/is_global after the API create; Open WebUI tolerates that while running.
# Never write the `config` table while Open WebUI is up.
set -e
source "$(dirname "$0")/env.sh"
F="$1"; ID="$2"; NAME="$3"; TYPE="$4"; GLOBAL="${5:-0}"
[ -n "$TYPE" ] || { echo "usage: $0 <file.py> <id> \"<Name>\" <pipe|filter|action> [global:0|1]"; exit 2; }
PY="$STACK_HOME/open-webui/.venv/bin/python"
BASE="http://127.0.0.1:$WEBUI_PORT"
DB="$STACK_HOME/open-webui/data/webui.db"
T=$(curl -s -m 10 -X POST "$BASE/api/v1/auths/signin" -H 'Content-Type: application/json' -d '{"email":"","password":""}' | "$PY" -c "import json,sys;print(json.load(sys.stdin).get('token',''))")
"$PY" - "$F" "$ID" "$NAME" "$TYPE" "$T" "$BASE" <<'PYEOF'
import httpx, sys
f, fid, name, ftype, tok, base = sys.argv[1:7]
c = httpx.Client(base_url=base, timeout=60, headers={'Authorization': f'Bearer {tok}'})
content = open(f).read()
c.post(f'/api/v1/functions/id/{fid}/delete')                       # idempotent re-install
r = c.post('/api/v1/functions/create', json={'id': fid, 'name': name, 'type': ftype, 'content': content, 'meta': {'description': name}})
print('create:', r.status_code, '' if r.status_code < 300 else r.text[:300])
if r.status_code >= 300: sys.exit(1)
PYEOF
"$PY" - "$ID" "$GLOBAL" "$DB" <<'PYEOF'
import sqlite3, sys, time
fid, g, db_path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
db = sqlite3.connect(db_path)
db.execute("update function set is_active=1, is_global=?, updated_at=? where id=?", (g, int(time.time()), fid)); db.commit()
print('activated:', db.execute("select id,type,is_active,is_global from function where id=?", (fid,)).fetchone())
PYEOF
# refresh the model list so a new pipe appears without a restart
curl -s -m 30 "$BASE/api/models" -H "Authorization: Bearer $T" >/dev/null && echo "model cache refreshed"
