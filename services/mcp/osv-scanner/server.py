# /// script
# requires-python = ">=3.10"
# dependencies = ["fastmcp>=2"]
# ///
"""Dependency vulnerability audit MCP: wraps Google's osv-scanner CLI.
One tool: scan a project dir / lockfile against the OSV database. Fully local scan
(the CLI queries OSV's public API for advisory data; no code leaves the box)."""
import json
import os
import shutil
import subprocess

from fastmcp import FastMCP

mcp = FastMCP("osv-scanner")
OSV = os.environ.get("OSV_SCANNER") or shutil.which("osv-scanner") or "/opt/homebrew/bin/osv-scanner"


def _run(args):
    return subprocess.run([OSV, *args], capture_output=True, text=True, timeout=300)


@mcp.tool()
def scan_project(path: str) -> str:
    """Audit a project directory or lockfile for known-vulnerable dependencies (OSV database).

    Args:
        path: absolute path to a project folder or a lockfile (requirements.txt, package-lock.json, etc.)
    """
    # v2 CLI syntax first, then fall back to older form
    for args in (["scan", "source", "--recursive", "--format", "json", path],
                 ["scan", "--recursive", "--format", "json", path],
                 ["--format", "json", "--recursive", path]):
        try:
            r = _run(args)
        except Exception as e:
            return f"ERROR running osv-scanner: {e}"
        out = r.stdout.strip()
        if out.startswith("{"):
            break
    else:
        return (r.stdout or r.stderr or "no output")[:3000]
    try:
        data = json.loads(out)
    except Exception:
        return out[:3000]
    vulns = []
    for res in data.get("results", []):
        for pkg in res.get("packages", []):
            p = pkg.get("package", {})
            for v in pkg.get("vulnerabilities", []):
                vulns.append(f"- {p.get('name')} {p.get('version')}: {v.get('id')} — {(v.get('summary') or '')[:90]}")
    if not vulns:
        return "No known vulnerabilities found."
    return f"{len(vulns)} known vulnerabilities:\n" + "\n".join(vulns[:60])


if __name__ == "__main__":
    mcp.run()
