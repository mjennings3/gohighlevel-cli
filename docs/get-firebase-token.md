# Getting your GHL Firebase refresh token

You only need this if you want to **build/update workflows** (the internal-API
`--experimental` commands). Everything else works with just `GHL_API_KEY`.

The token is read straight out of your own logged-in GoHighLevel session — no
extension, no install, nothing leaves your browser. You copy it by hand from the
browser's DevTools, so there's nothing to run and nothing that can break.

> The refresh token is scoped to **whichever agency you're currently logged into**.
> If you manage more than one agency, switch GHL to the right agency *first*, then
> grab the token. With the `ghl-as` multi-agency setup you grab one token per
> agency.

## Steps (manual — Chrome / Edge / any Chromium browser)

1. Open and log into `https://app.gohighlevel.com`. Make sure you're in the
   **agency** you want a token for.
2. Open DevTools: **⌘⌥I** (Mac) / **F12** (Windows/Linux).
3. Click the **Application** tab (in Firefox this tab is called **Storage**).
4. In the left sidebar, expand:
   **Storage → IndexedDB → `firebaseLocalStorageDb` → `firebaseLocalStorage`**
5. Click the single row in that store. Its key looks like
   `firebase:authUser:AIza…:[DEFAULT]`. The value object shows in the panel below.
6. Expand the value tree to:
   **`value` → `stsTokenManager` → `refreshToken`**
7. Right-click the `refreshToken` value and choose **Copy** (or double-click the
   value to select it and press ⌘C / Ctrl-C). It's a long string that starts with
   `AMf-…`.

That string is your refresh token. Paste it into the right env file (below).

```
firebaseLocalStorageDb
└── firebaseLocalStorage
    └── firebase:authUser:AIza…:[DEFAULT]
        └── value
            └── stsTokenManager
                ├── accessToken    (short-lived — ignore)
                └── refreshToken   ← copy THIS  (starts with "AMf-…")
```

## Where the token goes

- **Multi-agency (`ghl-as`)** — paste it into that agency's file,
  `~/.ghl/agencies/<agency>.env`:

  ```env
  GHL_FIREBASE_REFRESH_TOKEN=AMf-…paste here…
  ```

  Then lock it down: `chmod 600 ~/.ghl/agencies/<agency>.env`. Every sub-account
  whose profile points at that agency (`GHL_AGENCY=<agency>`) picks it up
  automatically.

- **Single account (`ghl`)** — paste it into the project `.env`:

  ```env
  GHL_FIREBASE_REFRESH_TOKEN=AMf-…paste here…
  ```

## Notes

- The refresh token is sensitive — it's your full GHL agency session. Treat it
  like a password, `chmod 600` the file, and never commit it.
- You only **read** it; nothing is sent anywhere. There is no script to run.
- Tokens refresh automatically once they're in the env file. Re-grab one only if
  you get an "expired/revoked" error (e.g. after logging out of GHL or a forced
  re-auth).
