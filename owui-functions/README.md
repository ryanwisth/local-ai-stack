# Open WebUI Functions

Python plugins that run inside Open WebUI once installed (`scripts/install-owui-function.sh`).

| File | Type | What it does | State |
|---|---|---|---|
| `latex_normalizer.py` | filter (outlet) | Rewrites `\(..\)` and `\[..\]`, which Qwen emits and Open WebUI does not render, into `$..$` and `$$..$$` so KaTeX renders them | Installed as a global filter in the original setup |
| `consensus_vote.py` | pipe | Self-consistency voting: sends N samples to the local server, majority-votes the `Answer: X` letter, breaks ties toward the most worked answer, and returns the tally plus one explanation. Admin-editable valves for base URL, model, N, temperature and timeouts | Complete and tested against mocks; never installed in the original setup |

On a serial scheduler, N samples take about N times one full answer. Requires `aiohttp`, which
Open WebUI ships.
