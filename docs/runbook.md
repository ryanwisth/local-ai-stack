# Runbook

How the stack is operated day to day. Paths assume the defaults in `scripts/env.sh`
(`STACK_HOME=~/AI`, ports as listed in the README). Every command here is read-only
unless the section says otherwise.

## Layout of STACK_HOME

The scripts live in this repo; the runtime side lives in `STACK_HOME`:

| Path under `STACK_HOME` | What |
|---|---|
| `stack.env` | Machine-specific values (`MTPLX_MODEL`, optional overrides). Sourced by `scripts/env.sh` |
| `mtplx/.venv/` | Python venv with `mtplx` installed; `server.log` |
| `open-webui/.venv/`, `open-webui/data/` | Open WebUI install; `data/webui.db` holds all of its configuration |
| `mcp/mcpo-config.json`, `mcp/.bearer` | Tool roster and the mcpo API key (mode 600) |
| `mcp/data/` | Data written by tool servers (for example the `memory` server's JSONL) |
| `kokoro/.venv/`, `kokoro/*.onnx`, `kokoro/*.bin` | TTS venv, model and voice pack |
| `searxng/settings.yml` | Mounted into the SearXNG container |
| `launchd.log` | Supervisor output |

## Start, stop, restart

The launchd supervisor owns the stack. It runs `scripts/start-stack.sh` at login and every
60 seconds, and the launcher starts only what is down. So:

```bash
# Enable the supervisor (first time, or after a stop)
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.ai-stack.plist

# Stop everything. Unloads the supervisor first; a bare pkill is undone within 60 s.
scripts/stop-stack.sh

# Restart ONE service: kill just that process and let the supervisor bring it back.
pkill -f 'bin/mcpo --config'        # example: mcpo
```

Running `scripts/start-stack.sh` by hand works, but the services then become children of
your shell. Do it from a plain terminal, not from inside an AI agent's shell: processes an
agent session spawns inherit its lower scheduling priority (nice 5 on this machine) and die
when the session exits. See `lessons-learned.md`.

Any restart interrupts every chat and tool call in flight. mtplx runs a serial scheduler,
so check the model is idle first.

## Health checks (read-only)

```bash
launchctl list | grep ai-stack                       # supervisor loaded? last exit status
lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8000|8080|8600|8880|8888|5001) '
tools/mtplx-watch --once                             # is the model busy? prefill or decode?
tail -30 ~/AI/mtplx/server.log
tail -20 ~/AI/launchd.log
ps -o ni -p $(lsof -nP -iTCP:8000 -sTCP:LISTEN -t)   # nice level of the real server pid
```

Check the listening address column too: every service should show `127.0.0.1:<port>`,
never `*:<port>`.

## Seeing what the model server is doing

mtplx records a flight log and per-request forensics. Read them instead of guessing:

```bash
tools/mtplx-watch            # refresh every 2 s: phase, elapsed, prefill ETA, tok/s, last ~400 chars
tools/mtplx-watch --tail     # plus the saved text of the last abnormal turn
curl -s http://127.0.0.1:8000/v1/mtplx/flight | python3 -m json.tool
tail -3 ~/.mtplx/logs/request-log-8000.jsonl | python3 -m json.tool
```

- `~/.mtplx/logs/request-log-<port>.jsonl`: per-request fields such as `cached_tokens`,
  `new_prefill_tokens`, `ttft_s`, session restore and store reasons, `keep_live_ref`, tool names.
- `~/.mtplx/metrics/flight-<port>.jsonl`: begin, prefill and end events, numbers only.
- `~/.mtplx/metrics/gen/<rid>.txt`: full generated text, only for abnormal endings
  unless `MTPLX_FLIGHT_TEXT=always` is set at start.
- The `watch` tail shows tool-call bodies that Open WebUI hides until the call completes.

Reading the signals: `mtplx_stream_silence` with `completion_tokens: 0` means prefill is in
progress, not a hang. GPU near 100 % with zero output tokens is prefill. A 30 to 60 second
first token after a tool-heavy prompt is normal.

To confirm speculative decoding is live, throughput alone is not the test. Read `mtplx_stats`
in a non-streaming response: `drafted_tokens` and `verify_calls` must be non-zero and
`generation_mode` must be `"mtp"`. Use `decode_tok_s`, not `request_tok_s`.

## Changing the tool roster

1. Edit `$STACK_HOME/mcp/mcpo-config.json` (start from `config/mcpo-config.example.json`).
2. Restart mcpo: `pkill -f 'bin/mcpo --config'`; the supervisor brings it back.
3. Add or remove the matching tool-server row in Open WebUI (Admin, Tools). Each row is
   `http://127.0.0.1:8600/<server-name>` with the bearer from `.bearer`.
4. Reload the browser. Open WebUI caches the tool list per page load.

Test a new stdio MCP server through mcpo's HTTP endpoint, not with a hand-written stdio
handshake (see `lessons-learned.md`).

## Restricting a tool's surface

Open WebUI can filter which of a tool server's functions reach the model
(`function_name_filter_list` on the tool-server connection). mcpo rewrites every operation id
to `tool_<name>_post`, so the list must use those names, for example
`tool_list_emails_metadata_post`. Bare tool names match nothing.

This is how the email server was cut from 18 tools (including send, delete and move) to six
read-only ones.

## Installing an Open WebUI Function

```bash
scripts/install-owui-function.sh owui-functions/latex_normalizer.py latex_normalizer "LaTeX Delimiter Normalizer" filter 1
scripts/install-owui-function.sh owui-functions/consensus_vote.py consensus_vote "Multiple-Choice Consensus" pipe
```

Needs Open WebUI listening. Pipes appear in the model dropdown; filters with `global=1`
apply to every model.

## SearXNG container

The launcher only runs `docker start searxng` on an existing container; it does not create
one. A create line consistent with the config (reconstructed from the setup, verify against
`docker inspect` on a working install):

```bash
docker run -d --name searxng --restart unless-stopped \
  -p 127.0.0.1:8888:8080 \
  -v "$STACK_HOME/searxng/settings.yml:/etc/searxng/settings.yml" \
  searxng/searxng:latest
```

Docker Desktop's VM reserved about 8 GB for this one small container on the 64 GB machine.
Size it down in Docker Desktop settings if memory is tight.

## Backups

```bash
scripts/backup.sh     # -> $BACKUP_ROOT/<date>/, keeps 10
```

Copies `webui.db` with `sqlite3 .backup` (safe while Open WebUI runs with its WAL), uploads,
the `mcp/` folder without the bearer or logs, the launch scripts and the supervisor plist.
Run it before any change you would hate to lose. Treat the backup folder as secret, since
`mcpo-config.json` can hold tokens.

Never edit `webui.db` while Open WebUI is running (the one tolerated exception is the
single-row `function` update in `install-owui-function.sh`). For read-only inspection:

```bash
sqlite3 "file:$HOME/AI/open-webui/data/webui.db?mode=ro&immutable=1" ".tables"
```

## Upgrading mtplx

Keep offline wheels for the current version, the target and the rollback. The swap is a
package install while the server is stopped:

```bash
pkill -f 'python -m mtplx.server.openai'; sleep 2
uv pip install --python ~/AI/mtplx/.venv/bin/python /path/to/wheels/mtplx-<version>-py3-none-any.whl
# the supervisor relaunches the server within 60 s plus ~30 s model load
curl -s http://127.0.0.1:8000/health
```

Pin the exact version. Upstream once published a release under a mis-stamped higher version
number, so an unpinned upgrade can land on the wrong build.

## Coding agent on the local model (pi)

[pi](https://www.npmjs.com/package/@earendil-works/pi-coding-agent) is a terminal coding
agent (read, write, edit, bash tools). It was pointed at the same mtplx server through
`~/.pi/agent/models.json` (provider base URL `http://127.0.0.1:8000/v1`, context window
131,072), with:

- a small request-policy extension that sends a stable `x-mtplx-session-id` header, so mtplx
  keeps the live KV cache between tool turns;
- auto-compaction at about 79k tokens (`reserveTokens` 52,000, `keepRecentTokens` 20,000);
- a skill that documents the mcpo endpoints and calls them through a small helper script
  with the bearer, since pi has no built-in MCP client.

`mtplx doctor pi --port 8000` checks the wiring. Do not run pi while Open WebUI has a
generation in flight; the serial scheduler queues them behind each other. The pi config
files are not included in this repo.

## Optional task model

`scripts/start-taskmodel.sh` serves `mlx-community/Qwen3-1.7B-4bit` on `:8001` for Open WebUI
background tasks or a future LoRA adapter. It is not part of `start-stack.sh`. Download with
`hf download`, not the deprecated `huggingface-cli`, and verify real weights landed
(`find ~/.cache/huggingface -name '*.safetensors' -size +100M`): `mlx_lm.server`'s
`/v1/models` lists partial downloads, and a completion against one hangs.
