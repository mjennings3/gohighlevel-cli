"""GoHighLevel MCP server — exposes the multi-account/multi-agency `ghl-as` CLI
to any MCP-capable AI harness (OpenCode, Claude, Cursor, Cline, ...).

Model-agnostic: the harness does the tool-calling, so the underlying model
(DeepSeek, Hermes, Claude, ...) does not matter.

FULL-ACCESS build: every command `ghl-as` can run is reachable, including the
internal API (`--experimental` workflow building) across all configured
agencies. Agents never see raw tokens; they call tools and the server shells out
to `ghl-as`, which reads credentials from ~/.ghl.

Run:  ghl-mcp           (stdio transport; configured as an MCP server command)
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gohighlevel")

PROFILE_DIR = Path(os.environ.get("GHL_PROFILE_DIR", str(Path.home() / ".ghl")))


def _ghl_as_bin() -> str:
    """Locate the ghl-as wrapper: env override -> PATH -> repo-relative."""
    env = os.environ.get("GHL_AS_BIN")
    if env and Path(env).exists():
        return env
    found = shutil.which("ghl-as")
    if found:
        return found
    # this file lives at <repo>/cli_anything/gohighlevel/mcp_server.py
    repo_bin = Path(__file__).resolve().parents[2] / "ghl-as"
    return str(repo_bin)


def _parse_env(path: Path) -> dict:
    """Read KEY=VALUE lines from a .env file without executing it."""
    out: dict[str, str] = {}
    try:
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def _profiles() -> list[dict]:
    profiles = []
    for f in sorted(PROFILE_DIR.glob("*.env")):
        if f.stem == "common":
            continue
        env = _parse_env(f)
        profiles.append({
            "profile": f.stem,
            "label": env.get("GHL_LABEL", f.stem),
            "agency": env.get("GHL_AGENCY", "none"),
            "location_id": env.get("GHL_LOCATION_ID", ""),
        })
    return profiles


def _run(profile: str, args: list[str], add_json: bool = True) -> str:
    valid = {p["profile"] for p in _profiles()}
    if profile not in valid:
        return (f"ERROR: unknown profile '{profile}'. "
                f"Available: {sorted(valid)}. Use the ghl_profiles tool to list them.")
    cmd = [_ghl_as_bin(), profile]
    flat = [str(a) for a in args]
    # Inject --json at the global level for machine-readable output unless the
    # caller already controls output or is asking for help/version.
    if add_json and "--json" not in flat and not any(
        a in ("--help", "-h", "--version") for a in flat
    ):
        cmd.append("--json")
    cmd.extend(flat)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out after 120s."
    out = proc.stdout.strip()
    err = proc.stderr.strip()
    # ghl-as prints a one-line banner to stderr; surface stderr only on failure.
    if proc.returncode != 0:
        return f"EXIT {proc.returncode}\nstdout:\n{out}\nstderr:\n{err}"
    return out or f"(no output)\n{err}"


# --- tools -----------------------------------------------------------------

@mcp.tool()
def ghl_profiles() -> str:
    """List available GoHighLevel sub-account profiles (and their agency +
    location). Call this FIRST to discover which `profile` values are valid."""
    import json
    return json.dumps(_profiles(), indent=2)


@mcp.tool()
def ghl_help(profile: str, command: str = "") -> str:
    """Show CLI help so you can discover commands and flags. `command` is an
    optional sub-path, e.g. "contacts" or "contacts create". Returns --help text."""
    args = (command.split() if command else []) + ["--help"]
    return _run(profile, args, add_json=False)


@mcp.tool()
def ghl_run(profile: str, args: list[str]) -> str:
    """Run any `ghl-as <profile>` command and return its output (JSON by default).

    FULL ACCESS: includes writes and the internal API. Pass the command as a list
    of tokens WITHOUT the leading `ghl-as` or profile, e.g.:
      profile="snapshot", args=["contacts","list","--limit","5"]
      profile="snapshot", args=["workflows","list"]
      profile="thelift",  args=["--experimental","workflows", ...]   # internal API
    --json is added automatically for machine-readable output. Use ghl_help to
    discover available command groups and flags first if unsure.
    """
    return _run(profile, list(args))


def main():
    mcp.run()


if __name__ == "__main__":
    main()
