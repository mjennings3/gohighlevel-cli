---
name: "cli-anything-gohighlevel"
description: "CLI interface for GoHighLevel CRM/Marketing API — contacts, opportunities, calendars, workflows, conversations, emails, payments, forms, social media, locations"
triggers:
  - gohighlevel
  - ghl cli
  - ghl contacts
  - ghl workflows
  - ghl calendars
---

# cli-anything-gohighlevel

CLI interface for the GoHighLevel (GHL) CRM and Marketing API. Manage contacts, pipeline opportunities, calendars, workflows, conversations, emails, payments, forms, social media posts, and locations from the command line or interactive REPL.

## Prerequisites

- Python 3.10+
- Credentials live under `~/.ghl/` in a 3-layer cascade (see below). Each
  sub-account is a profile; each agency owns one Firebase token.

## Multi-account + multi-agency: ALWAYS use `ghl-as <profile>`

This install manages multiple GHL sub-accounts spanning multiple agencies. The
entry point for agents is `ghl-as <profile> <command...>`, which loads that
profile's credentials and runs the CLI. The bare `ghl` command uses only the
project default and is NOT for multi-account work.

### Credential layout (the 3-layer cascade)

```
~/.ghl/
  common.env                 # global, agency-agnostic defaults (rarely needed)
  agencies/
    <agency>.env             # ONE Firebase refresh token per agency (full agency login)
  <account>.env              # per sub-account: GHL_AGENCY + GHL_API_KEY + GHL_LOCATION_ID
```

`ghl-as <profile>` loads, in order (later wins): `common.env` ->
`agencies/<that profile's GHL_AGENCY>.env` -> `<profile>.env`.

Why two credential types matter:
- `GHL_API_KEY` (a `pit-...` Private Integration Token) is **per sub-account** and
  authenticates the **public** API. Each profile has its own.
- `GHL_FIREBASE_REFRESH_TOKEN` is **per agency** (it's a full agency login) and
  authenticates the **internal** API (workflow building, `--experimental`). It
  lives in `agencies/<agency>.env`, shared by all that agency's sub-accounts, and
  is supplied automatically via the profile's `GHL_AGENCY` pointer.

A profile file looks like:
```
GHL_LABEL="Acme Gym"          # optional friendly name
GHL_AGENCY=acmeagency         # -> ~/.ghl/agencies/acmeagency.env supplies the Firebase token
GHL_API_KEY=pit-xxxx...
GHL_LOCATION_ID=AbCd123...
```

RULES for agent use:
- ALWAYS pass an explicit profile name as the first argument:
  `ghl-as <profile> <command> --json`.
- NEVER run `ghl-as` with no profile — that launches an interactive picker that
  requires a human at a TTY and will hang a non-interactive call.
- To discover profiles: `ls ~/.ghl/*.env` (ignore `common.env`); the profile name
  is the filename without `.env`. To see which agency each belongs to:
  `grep -H '^GHL_AGENCY=' ~/.ghl/*.env`. To list agencies: `ls ~/.ghl/agencies/`.
- If the task doesn't specify which account, ASK the user which profile to use
  before running anything that reads or writes data. Note that the same workflow
  name can exist in many sub-accounts across agencies — never assume which one.
- Public-API commands work with just the profile. Internal-API / workflow-building
  needs the agency's Firebase token; if a profile's agency file is missing or its
  token is blank, `ghl-as` warns and internal calls fail (public calls still work).

### Adding a new sub-account / agency
1. Per agency (once): create `~/.ghl/agencies/<agency>.env` with
   `GHL_FIREBASE_REFRESH_TOKEN=<token>` (grabbed while logged into THAT agency via
   the DevTools method in the repo's `docs/get-firebase-token.md`), then
   `chmod 600` it.
2. Per sub-account: create `~/.ghl/<account>.env` with `GHL_AGENCY=<agency>`,
   `GHL_API_KEY` (that sub-account's PIT), and `GHL_LOCATION_ID`.

## Usage

### CLI Mode (one-shot commands) — note the leading `ghl-as <profile>`
```bash
ghl-as <profile> contacts list --json
ghl-as <profile> contacts get <contact_id>
ghl-as <profile> contacts create --email user@example.com --first-name John --last-name Doe
ghl-as <profile> opportunities list --status open
ghl-as <profile> calendars list
ghl-as <profile> workflows list
ghl-as <profile> conversations list --status unread
ghl-as <profile> payments transactions
ghl-as <profile> forms list
ghl-as <profile> social posts
ghl-as <profile> locations get
```

### REPL Mode (interactive, for humans only — do not use from an agent)
```bash
ghl-as <profile>
```

### Global Options
- `--json` — Output as machine-readable JSON (recommended for agents)
- `--location-id <ID>` — Override GHL_LOCATION_ID for this command
- `--version` — Show CLI version
- `--help` — Show help

## Command Groups

| Group | Description | Key Commands |
|-------|-------------|--------------|
| `contacts` | Contact management | list, get, create, update, delete, search, add-tag, remove-tag |
| `opportunities` | Pipeline deals | list, get, create, update, delete, pipelines |
| `calendars` | Scheduling | list, get, slots, appointments, book, groups |
| `workflows` | Automation workflows | list |
| `conversations` | Messaging (SMS, email, chat) | list, get, messages, send |
| `emails` | Email campaigns/templates | list-campaigns |
| `payments` | Financial operations | transactions, orders, invoices, create-invoice |
| `forms` | Form management | list, submissions |
| `social` | Social media posting | accounts, posts, create-post |
| `locations` | Sub-account management | get, search, tags, custom-fields, custom-values |

## Agent Usage Notes

- Always invoke as `ghl-as <profile> ...` with an explicit profile (see the
  multi-account section); never the bare `ghl` and never `ghl-as` alone
- Always use `--json` flag for programmatic consumption
- Contact search uses `contacts search <query>` for name-based search
- Workflow enrollment is done via `contacts` group (not workflows): the GHL API triggers workflows through contact endpoints
- Social media posting requires OAuth-connected accounts
- All endpoints require valid `GHL_API_KEY` bearer token
- API base URL: `https://services.leadconnectorhq.com`
- API version header: `2021-07-28`

## Examples

```bash
# List contacts as JSON (replace <profile> with a name from ~/.ghl/*.env)
ghl-as <profile> --json contacts list --limit 50

# Create a contact with tags
ghl-as <profile> contacts create --email lead@company.com --first-name Jane --last-name Smith --tag "hot-lead" --tag "webinar"

# Search contacts
ghl-as <profile> contacts search "john"

# List pipeline opportunities
ghl-as <profile> --json opportunities list --status open

# Get available calendar slots
ghl-as <profile> calendars slots <calendar_id> --start 2026-03-25 --end 2026-03-30

# Send SMS in conversation
ghl-as <profile> conversations send <conversation_id> --type SMS --message "Thanks for your interest!"

# List transactions
ghl-as <profile> --json payments transactions --limit 50

# Create social post
ghl-as <profile> social create-post --account-id <id> --text "New blog post!" --schedule "2026-03-26T10:00:00Z"
```
