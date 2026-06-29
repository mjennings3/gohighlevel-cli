# GoHighLevel CLI — agent instructions (model-neutral)

This repo exposes a multi-account, multi-agency GoHighLevel CLI. Any AI agent
(regardless of model: DeepSeek, Hermes, Claude, ...) can drive GHL through it.
There are two integration paths — use whichever your harness supports.

## Path A — MCP server (preferred)

If your harness speaks MCP, run the bundled server and call its tools. The
underlying model does not matter; your harness handles tool-calling.

- Command: `ghl-mcp` (stdio transport). Installed via `pip install -e ".[mcp]"`.
- Tools:
  - `ghl_profiles()` — list sub-account profiles and their agency/location. Call FIRST.
  - `ghl_help(profile, command="")` — show CLI help to discover commands/flags.
  - `ghl_run(profile, args)` — run any command; `args` is a token list WITHOUT the
    leading `ghl-as`/profile, e.g. `["contacts","list","--limit","5"]`.
- FULL ACCESS: reads, writes, and the internal API (`--experimental` workflow
  building) across all configured agencies. Agents never see raw tokens.

Example OpenCode config (`opencode.json`), adjust the path:
```json
{
  "mcp": {
    "gohighlevel": {
      "type": "local",
      "command": ["/ABSOLUTE/PATH/TO/.venv/bin/ghl-mcp"],
      "enabled": true
    }
  }
}
```
Generic MCP client config is equivalent: a stdio server whose command is the
absolute path to `ghl-mcp` (find it with `which ghl-mcp` inside the venv).

## Path B — shell (any agent that can run commands)

Call the `ghl-as` wrapper directly.

RULES:
- ALWAYS pass an explicit profile as the first arg: `ghl-as <profile> <command> --json`.
- NEVER run `ghl-as` with no profile — it opens an interactive picker and will hang.
- Discover profiles: `ls ~/.ghl/*.env` (ignore `common.env`); name = filename
  without `.env`. Agencies: `ls ~/.ghl/agencies/`. Which agency a profile uses:
  `grep -H '^GHL_AGENCY=' ~/.ghl/*.env`.
- The same workflow/contact name can exist in many sub-accounts across agencies;
  never assume which account — if unspecified, ask the user.

Examples:
```bash
ghl-as snapshot --json contacts list --limit 5
ghl-as snapshot --json workflows list
ghl-as thelift  --json opportunities list --status open
ghl-as snapshot --experimental workflows ...        # internal API
```

## Credential model (how it stays scoped)

Credentials live under `~/.ghl/` in a 3-layer cascade (later wins):
`common.env` -> `agencies/<profile's GHL_AGENCY>.env` -> `<profile>.env`.

- `GHL_API_KEY` (a `pit-...` token) is **per sub-account**, authenticates the
  **public** API. Lives in the profile.
- `GHL_FIREBASE_REFRESH_TOKEN` is **per agency** (a full agency login),
  authenticates the **internal** API (workflow building). Lives in
  `agencies/<agency>.env`, supplied automatically via the profile's `GHL_AGENCY`.

Adding a sub-account/agency: create `~/.ghl/agencies/<agency>.env` with the
Firebase token (once per agency, `chmod 600`), then `~/.ghl/<account>.env` with
`GHL_AGENCY`, `GHL_API_KEY`, and `GHL_LOCATION_ID`.

## Command groups

`contacts`, `opportunities`, `calendars`, `workflows`, `conversations`,
`emails`, `payments`, `forms`, `social`, `locations`. Use `ghl_help` /
`ghl-as <profile> <group> --help` for exact subcommands and flags.

## Recipes — reusable multi-step task automations (check here FIRST)

Before hand-rolling a multi-step GHL task, check `recipes/` — it holds
deterministic, parameterized scripts for tasks the plain CLI can't do in one
call (e.g. operations that need the internal/web-UI API, or several coordinated
steps). Running a recipe is faster and safer than re-deriving the task.

- Pure Python **stdlib, zero dependencies** — no venv/pip needed.
- They load the same `~/.ghl` credential cascade as `ghl-as`; just pass
  `--profile <name>`.
- Every recipe supports `--dry-run` (preview, no changes) and `--json`.
- Index, usage, and how to add new ones: `recipes/README.md`.
- Recipes that map cleanly to a command are also wired into the CLI from the
  **same source file**, so they're reachable via the shell and MCP paths too
  (no `--profile` there — `ghl-as` already supplies creds).

```bash
# standalone (loads the profile cascade itself)
python3 recipes/convert_calendar_to_round_robin.py --profile <profile> --user "Name" --dry-run
# equivalent CLI subcommand (works through ghl_run over MCP, too)
ghl-as <profile> calendars convert-to-round-robin --user "Name" --dry-run
```

Recipes that mutate the internal API need the agency's Firebase token (same
requirement as `--experimental` workflow building).

## Security note

This is a FULL-ACCESS surface: any agent reaching it can read and write GHL
across every configured agency, including building/modifying workflows. Only
expose it to agents you trust at that level. To restrict a given agent, point it
at a profile whose agency has no Firebase token (public-API only), or run a
read-only variant of the server.
