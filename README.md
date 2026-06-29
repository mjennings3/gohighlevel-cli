# GoHighLevel CLI

A command-line interface for GoHighLevel that lets you (or Claude Code) drive your CRM from the terminal — contacts, opportunities, calendars, conversations, workflows, emails, payments, forms, social media, locations, and documents.

Built by [Lead Gen Jay](https://leadgenjay.com).

---

## What you get

- **11 command groups** covering the full GHL surface (contacts, opportunities, calendars, workflows, conversations, emails, payments, forms, social, locations, documents).
- **A REPL** — type `ghl` with no args and you get an interactive shell with autocomplete.
- **Workflow builders** — Python scripts that take a markdown file and turn it into a live GHL workflow (see `builders/`).
- **Recipes** — reusable, deterministic task automations for things the plain API can't do in one call (see `recipes/`). Run them directly or via a matching CLI subcommand.
- **A Firebase token how-to** — a short manual DevTools walkthrough to grab the token you need for the "internal" GHL API (the public API can't create workflows; the internal one can). See [`docs/get-firebase-token.md`](docs/get-firebase-token.md).
- **A Claude Code skill** at `cli_anything/gohighlevel/skills/SKILL.md` so Claude can use the CLI on your behalf.

---

## Install (60 seconds)

Requirements: **Python 3.10+** and a GoHighLevel sub-account.

```bash
git clone <this repo> gohighlevel-cli
cd gohighlevel-cli
./install.sh
```

The installer creates a `.venv/`, installs the package, and copies `.env.example` → `.env`.

Open `.env` and fill in:

```env
GHL_API_KEY=pit-xxxxxxxx-...        # GHL Settings → Private Integrations
GHL_LOCATION_ID=YOUR_LOCATION_ID    # the long ID in your GHL URL
```

Smoke test:

```bash
./ghl contacts list --limit 5
```

You should see 5 contacts (or an empty list, depending on the account). Done.

---

## Quickstart examples

```bash
# Contacts
./ghl contacts search --query "jay@"
./ghl contacts create --first-name Jay --last-name Test --email jay@test.com
./ghl contacts tags add --contact-id <id> --tag consulti_trial

# Workflows
./ghl --json workflows list
./ghl workflows enroll --contact-id <id> --workflow-id <id>

# Opportunities
./ghl opportunities list --pipeline-id <id>

# Conversations
./ghl conversations list --contact-id <id>

# REPL (no args = interactive shell with autocomplete)
./ghl
```

`--json` works on most read commands and pipes cleanly into `jq`.

---

## Multi-account & multi-agency (`ghl-as`)

`ghl` drives a single account from the project `.env`. To manage many sub-accounts
— including across **different agencies**, each with its own Firebase token — use
the `ghl-as` wrapper, which loads per-account credentials from `~/.ghl/`.

### The 3-layer cascade

```
~/.ghl/
  common.env                 # global, agency-agnostic defaults (rarely needed)
  example.env                # template for a new sub-account profile (copy & rename)
  agencies/
    example.env              # template for a new agency Firebase-token file
    ascend.env               # ONE Firebase refresh token per agency (full agency login), chmod 600
    gmm.env
  snapshot.env               # a sub-account: GHL_AGENCY + GHL_API_KEY + GHL_LOCATION_ID
  thelift.env
```

Starter copies of `common.env`, `example.env`, and `agencies/example.env` ship in
the repo under [`examples/ghl/`](examples/ghl/) — copy that tree to `~/.ghl/` to
get going (the `example.env` files are harmless templates; `ghl-as` ignores
`common.env` and skips anything you don't rename).

`ghl-as <profile>` loads, in order (later wins):
`common.env` → `agencies/<profile's GHL_AGENCY>.env` → `<profile>.env`.

Two credential types, two scopes:

| Credential | Scope | Lives in | Authenticates |
|-----------|-------|----------|---------------|
| `GHL_API_KEY` (`pit-...`) | one sub-account | the profile | **public** API |
| `GHL_FIREBASE_REFRESH_TOKEN` | one agency (all its sub-accounts) | `agencies/<agency>.env` | **internal** API (workflow building) |

A profile (`~/.ghl/<account>.env`):

```env
GHL_LABEL="The Lift"          # optional friendly name in the picker
GHL_AGENCY=gmm                # → ~/.ghl/agencies/gmm.env supplies the Firebase token
GHL_API_KEY=pit-xxxxxxxx-...  # this sub-account's Private Integration Token
GHL_LOCATION_ID=AbCd123...
```

### Usage

```bash
ghl-as                            # visual picker (fzf or numbered menu), then REPL
ghl-as snapshot                   # straight into the REPL as that account
ghl-as snapshot --json workflows list   # one-off command
ghl-as snapshot --experimental ...      # internal API, uses the agency's Firebase token
```

### Adding a sub-account from a new agency

1. **Per agency (once):** create `~/.ghl/agencies/<agency>.env` with
   `GHL_FIREBASE_REFRESH_TOKEN=...` (grabbed while logged into *that* agency — see
   [`docs/get-firebase-token.md`](docs/get-firebase-token.md)), then `chmod 600` it.
2. **Per sub-account:** create `~/.ghl/<account>.env` with `GHL_AGENCY=<agency>`,
   its `GHL_API_KEY`, and `GHL_LOCATION_ID`.

Rotating a revoked agency token is then a one-file edit that every sub-account
under that agency picks up automatically.

> Install both wrappers on your PATH once: `ln -sf "$PWD/ghl" "$PWD/ghl-as" ~/.local/bin/`.
> They resolve symlinks, so they still find the project `.venv`.

---

## Workflow building (the powerful part)

The public GHL API is read-only for workflows. To **create or update** workflows, the CLI uses GHL's internal API — and that needs a Firebase refresh token.

### Step 1 — grab the token

You copy it by hand out of your logged-in GHL session — no script to run:

1. Open `app.gohighlevel.com` (logged into the agency you want a token for) and
   open DevTools (**⌘⌥I** / **F12**).
2. Go to the **Application** tab → **Storage → IndexedDB →
   `firebaseLocalStorageDb` → `firebaseLocalStorage`**.
3. Click the single row, then expand **`value` → `stsTokenManager` →
   `refreshToken`** and copy that value (a long string starting with `AMf-…`).

Paste it into the right env file — `~/.ghl/agencies/<agency>.env` for the
`ghl-as` multi-agency setup, or the project `.env` for a single account — as
`GHL_FIREBASE_REFRESH_TOKEN=...`. Full walkthrough with screenshots of the tree:
[`docs/get-firebase-token.md`](docs/get-firebase-token.md).

### Step 2 — build a workflow

`builders/` has example builders that turn a markdown email-sequence doc into a live workflow:

```bash
# Course Interest sequence (10 emails, 14 days)
python builders/wf1-course-interest-builder.py

# High Ticket Interest sequence (5 emails + 1 SMS)
python builders/wf5-ht-interest-builder.py

# Post-Call Sales (3 tag-triggered branch workflows)
python builders/wf6-post-call-sales-builder.py

# Consulti free-trial nurture (8 emails)
python builders/consulti-nurture-builder.py

# Post-purchase nurture (6 emails)
python builders/post-purchase-nurture-builder.py
```

Each builder supports `--update` to re-deploy without creating a duplicate workflow.

---

## Recipes (reusable task automations)

Some GHL tasks aren't a single API call. The clearest example: you **cannot**
change a calendar's type in place — GHL silently ignores it — so "make this event
calendar a round robin" really means *recreate it as round_robin with every
setting copied, assign the team, deactivate the original*. `recipes/` encodes
those known-good sequences once so any teammate (or AI agent) can run them fast
instead of re-deriving the steps.

Recipes are **pure Python stdlib — no venv, no dependencies** — and load the same
`~/.ghl` credential cascade as `ghl-as`, so you just pass a profile:

```bash
# Recreate the single active event calendar as a round robin, assign Rob,
# and deactivate the old one. Preview first with --dry-run.
python3 recipes/convert_calendar_to_round_robin.py --profile falcontax --user "Rob" --dry-run
```

Every recipe that also makes sense as a CLI command is wired into the CLI from the
**same source file**, so it's reachable through `ghl-as` and the MCP server too:

```bash
ghl-as falcontax calendars convert-to-round-robin --user "Rob" --dry-run
```

Conventions: `--dry-run` (preview, no changes) and `--json` on every recipe;
actionable single-line errors; recreate/deactivate rather than delete (reversible).
Index, full flags, and how to add new recipes live in
[`recipes/README.md`](recipes/README.md).

---

## Project layout

```
gohighlevel-cli/
├── ghl                         # the executable wrapper
├── setup.py                    # package definition
├── install.sh                  # one-shot installer
├── .env.example                # template for your secrets
│
├── cli_anything/               # the actual Python package
│   ├── gohighlevel/            # GHL commands (the main thing)
│   │   ├── gohighlevel_cli.py  # ~1,260 lines of CLI
│   │   ├── utils/              # API clients (public + internal + workflow builder)
│   │   └── skills/SKILL.md     # Claude Code skill manifest
│   ├── nextcloud/              # bonus: Nextcloud CLI
│   └── blotato/                # bonus: Blotato CLI
│
├── docs/
│   └── get-firebase-token.md   # manual DevTools steps for the internal-API token
│
├── examples/ghl/               # starter templates for the ~/.ghl config tree
│   ├── common.env
│   ├── example.env             # a sub-account profile
│   └── agencies/example.env    # an agency Firebase-token file
│
├── builders/                   # example workflow builders
│   ├── wf1-course-interest-builder.py
│   ├── wf5-ht-interest-builder.py
│   ├── wf6-post-call-sales-builder.py
│   ├── consulti-nurture-builder.py
│   ├── post-purchase-nurture-builder.py
│   ├── email-sequences-doc-builder.py
│   └── _email_sequences_parser.py
│
└── recipes/                    # reusable task automations (stdlib, no deps)
    ├── README.md               # index + how to run / write recipes
    ├── _ghl_recipe_lib.py      # shared client: creds cascade + public + internal API
    └── convert_calendar_to_round_robin.py
```

---

## Using it with Claude Code

The repo includes a Claude Code skill so Claude can call the CLI on your behalf:

1. Copy `cli_anything/gohighlevel/skills/SKILL.md` into a Claude Code skills directory (e.g. `~/.claude/skills/gohighlevel-cli/SKILL.md`).
2. Symlink both wrappers onto your PATH: `ln -sf "$PWD/ghl" "$PWD/ghl-as" ~/.local/bin/`.
3. In any Claude Code session, say "use the gohighlevel-cli skill" and Claude will run `ghl-as <profile> ...` for you. The skill instructs Claude to always pass an explicit profile (so it targets a specific sub-account/agency) and to ask which account when it isn't specified.

---

## Using it with other AIs (MCP)

To expose the CLI to any MCP-capable harness (OpenCode, Cursor, Cline, ...), run
the bundled MCP server — it works regardless of the underlying model (DeepSeek,
Hermes, Claude, ...) because the harness handles tool-calling.

```bash
pip install -e ".[mcp]"      # adds the `mcp` dependency + the `ghl-mcp` command
which ghl-mcp                 # absolute path to register in your MCP client
```

It exposes three tools: `ghl_profiles` (list accounts), `ghl_help` (discover
commands), and `ghl_run(profile, args)` (run any command, full access). See
[`AGENTS.md`](AGENTS.md) for tool details, an OpenCode config snippet, and a
model-neutral shell-only path for harnesses that do not speak MCP.

---

## Two layers of GHL API

The CLI talks to two APIs:

| API | What it can do | How it authenticates |
|-----|----------------|----------------------|
| **Public** (`services.leadconnectorhq.com`) | Read everything, create contacts/opportunities/etc. **Workflows are GET-only here.** | `GHL_API_KEY` (Private Integration Token) |
| **Internal** (`backend.leadconnectorhq.com`) | Everything the GHL UI can do — including **creating workflows**. Hidden behind a `--experimental` flag on commands that use it. | Firebase JWT, refreshed from `GHL_FIREBASE_REFRESH_TOKEN` |

You only need the Firebase token if you want to **build** workflows. Everything else works with just the API key.

---

## Security notes

- `.env` is gitignored. **Never** commit it.
- The Firebase refresh token is sensitive (it's your full GHL session). Treat it like a password.
- Grabbing the token only **reads** it out of your own browser's IndexedDB on the GHL tab — you copy it by hand, nothing runs and nothing is sent anywhere. `chmod 600` the file you store it in. See [`docs/get-firebase-token.md`](docs/get-firebase-token.md).

---

## License

Private / personal use.
