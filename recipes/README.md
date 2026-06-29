# Recipes — reusable GHL task automations

**For agents and humans.** Each recipe in this folder performs a complete,
multi-step GoHighLevel task that the plain CLI can't do in one call (usually
because it needs the internal API the web UI uses, or several coordinated
steps). Run a recipe instead of re-deriving the task from scratch.

## Why these exist

Some GHL operations are not single API calls. Example: you **cannot** change a
calendar's type in place — GHL silently ignores it — so "make this event
calendar a round robin" actually means *recreate it as round_robin with every
setting copied, assign the team, deactivate the original*. A recipe encodes that
known-good sequence once so it's fast and repeatable.

## How to run one

Recipes are **pure Python stdlib — no venv, no pip, no dependencies.** They load
the same `~/.ghl` credential cascade that `ghl-as` uses, so you only pass a
profile name:

```bash
python3 recipes/<recipe>.py --profile <profile> [options]
```

Recipes that also make sense as a CLI command are wired into the CLI from the
**same source file** (one implementation), so they're reachable through `ghl-as`
and the MCP server too. When running via the CLI you don't pass `--profile`
(the `ghl-as` wrapper already supplies credentials):

```bash
ghl-as <profile> calendars convert-to-round-robin [options]
```

Conventions every recipe follows:

- `--profile <name>` is **required** (a sub-account; see `ls ~/.ghl/*.env`).
- `--dry-run` shows exactly what it would do and changes nothing. **Run this
  first** on anything destructive or outward-facing.
- `--json` emits a machine-readable result for programmatic use.
- Errors are actionable, single-line, and never leave things half-changed:
  recipes verify their own result and abort before destructive steps if the
  safe part didn't succeed.
- They prefer to recreate/deactivate rather than delete, so changes are
  reversible.

## Available recipes

| Recipe | CLI equivalent | What it does |
|--------|----------------|--------------|
| `convert_calendar_to_round_robin.py` | `calendars convert-to-round-robin` | Recreate an **event** calendar as a **round robin** calendar with the same settings, assign team member(s), and deactivate the original. `--help` for flags. |

### `convert_calendar_to_round_robin.py`

```bash
# Auto-detect the single active event calendar, assign Rob, deactivate the old one:
python3 recipes/convert_calendar_to_round_robin.py --profile falcontax --user "Rob"

# Be explicit and preview first:
python3 recipes/convert_calendar_to_round_robin.py \
    --profile falcontax --calendar "Schedule an Appointment" \
    --user "Robert Valenzo" --user "Second Person" \
    --distribution equal --dry-run
```

Known limits it warns about: Google 2-way sync doesn't transfer (it comes from a
Google OAuth connection, not a setting), and the new calendar has a new id /
booking link.

## Writing a new recipe

1. Add `your_recipe.py` here. Import the shared helpers:
   `import _ghl_recipe_lib as ghl`.
2. Use `ghl.load_profile(args.profile)` first, then the `ghl.*` helpers
   (`list_calendars`, `get_calendar`, `create_calendar`, `update_calendar`,
   `list_users`, `resolve_user`, `public_request`, `backend_request`, …).
3. Support `--dry-run` and `--json`. Raise `ghl.RecipeError(msg)` for anything
   the user must fix; `main()` should catch it, print `Error: …`, and exit 1.
4. Verify your own result before any irreversible step.
5. Add a row to the table above.

`_ghl_recipe_lib.py` is the shared, dependency-free client (credential cascade +
public API + internal/Firebase API + calendar/user helpers). Keep recipes thin;
put reusable plumbing in the lib.
