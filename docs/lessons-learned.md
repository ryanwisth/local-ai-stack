# Lessons learned

Each entry comes from a real incident or measurement while building and running this stack
on one Apple-silicon Mac (Aug to Sep 2026). They are written as general rules, with what
happened and what changed.

## Process ownership and supervision

**Services started from a session die with the session.** The first launcher `nohup`ed each
service from the calling shell. When that shell belonged to an AI coding-agent session, quitting
the agent sent SIGTERM to the whole stack. Long-lived processes spawned from that session also
inherited its nice 5 priority, which quietly slowed the model server.
*Fix:* a launchd agent runs the idempotent launcher at login and every 60 seconds, with
`AbandonProcessGroup` so the services are reparented to launchd at nice 0. The launcher only
starts what is down, so the same job is also crash-restart. When checking priority, check the
server's own pid, not your shell: a short-lived child reports nice 0 even when the long-lived
server does not. Benchmarks taken against a session-spawned server are floor numbers.

**A supervisor turns `pkill` into a no-op.** Killing every service by hand is undone within a
minute. *Fix:* `stop-stack.sh` unloads the supervisor first, then stops the services. Killing a
single service is now the intended way to restart it.

**launchd starts jobs in `/`.** Open WebUI writes its session-signing key file into the current
directory. Under launchd that is the read-only root, and the service crash-looped 59 times.
*Fix:* the launcher `cd`s into the Open WebUI folder. Keep every launcher independent of the
caller's working directory, and set `PATH` and `HOME` explicitly, since launchd provides almost
no environment.

**Start order matters for tool discovery.** mcpo mounts its servers one at a time and only
listens once all are up (about 30 seconds). Open WebUI fetches every tool spec on the first page
load, so starting it early left the tool list nearly empty. *Fix:* the launcher waits up to 90
seconds for mcpo's port before starting Open WebUI.

## Network exposure

**One service listened on all interfaces after a hardening pass said it did not.** The
loopback-only pass fixed a Docling launcher by adding `--host 127.0.0.1`, but there were two
launcher files, and the stack launcher called the other one. `lsof` later showed `*:5001`.
*Fix:* one launcher per service, all in one folder (`scripts/`), and verify bindings by reading
`lsof -nP -iTCP -sTCP:LISTEN` after any change rather than by reading the scripts.

**Container configs can look exposed when they are not.** SearXNG's settings say
`bind_address: 0.0.0.0`, which is the address inside the container. The Docker port mapping
`-p 127.0.0.1:8888:8080` is what keeps it on loopback on the host.

## Tool exposure to the model

**Scope the filesystem tool.** The first filesystem MCP root was the whole home folder, which
reached SSH keys, agent configs and an API key file. It was narrowed to four working folders.

**Filter destructive tools at the UI layer, with the right names.** The email MCP server exposes
send, forward, delete, move and archive even with no outgoing mail configured. Open WebUI's
per-connection function filter cut it to six read tools. mcpo rewrites every operation id to
`tool_<name>_post`, so a filter written with bare tool names matched nothing.

**Keep risky tools opt-in.** The hand-written shell tool has a timeout cap and an output cap but
no allow or deny list. It is off by default and enabled per chat, and the same goes for browser
automation.

**Check tool servers for telemetry.** One third-party MCP bridge shipped prompts, executed code
and screenshots to its author's backend with consent on by default. It was switched off in the
add-on and with an environment variable in the mcpo entry.

**Do not test stdio MCP servers with a hand-written handshake.** It gave false "connection
closed" results and leaked about 16 orphaned wrapper processes. Mount the server in mcpo and
call its HTTP endpoint instead.

**Every tool schema costs prefill.** Open WebUI's own builtin tools added about 7.1k tokens to
every cold prompt, 16 to 38 seconds of time to first token on this machine. A filesystem server
with 17 tools costs about 2.3k tokens. Attach only what a persona needs.

## The model server

**A silent guard dropped large tool calls.** mtplx discards any streamed tool call whose hidden
arguments exceed 2,048 tokens by default (a chat-latency setting). An agent writing a whole
source file through a tool call lost the call, and the turn ended with the model announcing a
file it never wrote. *Fix:* `MTPLX_STREAM_HIDDEN_TOOL_GUARD_TOKENS=262144`, the full context
window, in the launcher. The backup script now copies the launchers so a setting like this is
not lost.

**A server bug looked like a client bug.** In mtplx 2.9.2, past about 50k tokens of context the
decode step took longer than the server's 0.25 second poll, and the server misread its own
post-tool-call cancel as an external one, returning an error instead of the tool call. The coding
agent aborted the turn. The cause was found in the server source; 2.10.2 adds the guard.
*Fix:* upgrade with offline wheels kept for the target and the rollback.

**Long agent chats in the web UI stalled on re-prefill.** At about 190k tokens, an Open WebUI agent
chat re-read about 188k tokens before every tool step: 21 to 25 minutes of time to first token
for a few hundred output tokens. The request log showed three causes:

- the session needed 8.1 to 10.6 GiB of KV cache, above the 8 GiB per-session cap, so it was
  never stored;
- mtplx keeps a session's KV cache live between tool turns only for clients it trusts (a stable
  session id plus coding-agent tool names), and Open WebUI sent neither;
- the web UI's next request arrived within a second and aborted the post-commit, so the
  restore point fell back to 2,048 tokens.

Both server-side fixes (forwarding the chat id header, a larger per-session cap) are restart-time,
and the larger cap is risky when a big turn already peaks at 62.6 of 64 GB. The working answer
was shorter chats in the web UI, and running agent work in the terminal coding agent, which sends
a stable session id and passes the trust test (`new_prefill_tokens` in the low thousands per
tool turn).

## Performance

**Measure the phase before theorizing.** Most "it hung" reports were prefill. The flight log and
`tools/mtplx-watch` answer that in one read, without restarting anything.

**The biggest real-world slowdown was the host, not the config.** Idle decode reached the
memory-bandwidth ceiling (see `performance.md`), yet the median in real use was 23.4 tok/s
against 37.5 idle. The slow windows lined up with other heavy work on the same machine: an
embedding build, tool installs, model downloads, an eval run. On a shared 64 GB machine, do not
overlap heavy jobs with chat turns.

**Write down dead ends.** A 41-agent speed audit with live A/B runs closed a long list of ideas
(KV quantization, chunk size, deeper drafts, other runtimes). Keeping that list stopped the same
ideas from being re-investigated.

## Downloads and staging

**A deprecated CLI can look like a rate limit.** `huggingface-cli` in that version printed usage
and exited 1, which read as throttling for an afternoon. Use `hf download`.

**A model list is not proof of a model.** `mlx_lm.server` lists partial cache folders in
`/v1/models`; a completion against one hangs. Check for real weight files.

**Measure link speed before a multi-GB pull,** serialize big downloads, and never chain a restart
behind an uncapped download.

## Backups

**Back up what is not rebuildable, and know what that is.** Open WebUI keeps all of its
configuration, personas and tool wiring in one SQLite file; `sqlite3 .backup` copies it safely
while the WAL is hot. The first backup script missed the launchers and the supervisor plist,
which hold tuned settings, and copied the mcpo bearer in clear. The version here copies the
launchers and plist and skips the bearer.

**Uncapped caches grow.** The on-disk KV session bank had no cap and grew past 100 GB.
`MTPLX_SESSION_BANK_MAX_BYTES` caps it at start time. Logs were unrotated too; rotate or truncate
them on a schedule.
