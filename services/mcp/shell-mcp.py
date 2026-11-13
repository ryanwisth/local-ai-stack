"""Shell MCP server for Open WebUI (bridged via mcpo).

Runs commands as the logged-in user through /bin/zsh -lc. Guards: per-call
timeout (capped at 300s), output truncated to 30k chars. No allow/deny list —
this is a single-user machine and the tool is off by default in the UI.
Run with mcpo's venv python (has mcp 1.x installed).
"""

import os
import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP('shell')

MAX_OUTPUT = 30_000
MAX_TIMEOUT = 300


@mcp.tool()
def run_command(command: str, workdir: str = os.path.expanduser('~'), timeout_s: int = 60) -> str:
    """Run a shell command on the Mac and return its output.

    Args:
        command: The shell command to execute (zsh syntax, pipes and && allowed).
        workdir: Directory to run in. Defaults to the home directory.
        timeout_s: Seconds before the command is killed (max 300).
    """
    timeout_s = min(max(1, timeout_s), MAX_TIMEOUT)
    try:
        proc = subprocess.run(
            ['/bin/zsh', '-lc', command],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return f'ERROR: command timed out after {timeout_s}s'
    except FileNotFoundError:
        return f'ERROR: workdir does not exist: {workdir}'

    out = proc.stdout or ''
    err = proc.stderr or ''
    result = out
    if err:
        result += ('\n--- stderr ---\n' + err) if out else err
    if len(result) > MAX_OUTPUT:
        result = result[:MAX_OUTPUT] + f'\n... [truncated at {MAX_OUTPUT} chars]'
    if not result.strip():
        result = '(no output)'
    return f'exit code: {proc.returncode}\n{result}'


if __name__ == '__main__':
    mcp.run()
