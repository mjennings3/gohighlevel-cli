"""Shared helpers for GoHighLevel "recipes" (reusable task automations).

Design goals (so this is portable and any AI agent / any machine can run it):
  * ZERO third-party dependencies — pure Python stdlib only. No venv, no pip.
  * Self-contained credentials — loads the same 3-layer ~/.ghl cascade that the
    `ghl-as` wrapper uses, given just a profile name.
  * Talks to BOTH GHL APIs:
      - public  (services.leadconnectorhq.com)  via the per-sub-account pit token
      - internal(backend.leadconnectorhq.com)   via the per-agency Firebase token
    The internal API is what the GHL web UI itself uses; it's required for things
    the public API refuses (e.g. creating calendars with a specific type).

Credential cascade (later wins), mirroring ghl-as:
    ~/.ghl/common.env
    ~/.ghl/agencies/<profile's GHL_AGENCY>.env
    ~/.ghl/<profile>.env
Override the directory with GHL_PROFILE_DIR (same as the wrapper).
"""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PUBLIC_BASE = "https://services.leadconnectorhq.com"
BACKEND_BASE = "https://backend.leadconnectorhq.com"
# Public Firebase web API key for GHL (same value the web app ships; not a secret).
FIREBASE_API_KEY = "AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE"
# A real browser UA — GHL sits behind Cloudflare which bans the default urllib UA.
CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
CALENDAR_VERSION = "2021-04-15"   # internal calendar endpoints want this version header
DEFAULT_VERSION = "2021-07-28"

# Server-managed / read-only calendar fields that must be stripped before a
# create or update. Seeded from observed GHL 422 responses; the create helper
# also auto-strips anything else the API rejects, so this need not be exhaustive.
CALENDAR_READONLY_FIELDS = frozenset({
    "id", "_id", "dateAdded", "dateUpdated", "lastUpdatedBy", "createdBy",
    "version", "deleted", "__v", "order", "originId", "providerId",
    "notificationStatus", "thanksMessage", "isSystemGenerated", "companyId",
    "companyAge", "oldCalendarId",
})

_CTX = ssl.create_default_context()


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class RecipeError(Exception):
    """A user-facing, actionable error. main() prints the message and exits 1."""


# --------------------------------------------------------------------------- #
# Profile / credential loading (mirrors the ghl-as cascade)
# --------------------------------------------------------------------------- #
def profile_dir() -> str:
    return os.environ.get("GHL_PROFILE_DIR", os.path.expanduser("~/.ghl"))


def _parse_env_file(path: str) -> dict[str, str]:
    """Parse a shell-style KEY=value env file (quotes/comments/`export` tolerated)."""
    out: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):]
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                # strip a trailing inline comment only when value is unquoted
                if val[:1] not in {'"', "'"} and " #" in val:
                    val = val.split(" #", 1)[0].rstrip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
                    val = val[1:-1]
                out[key] = val
    except FileNotFoundError:
        pass
    return out


def list_profiles() -> list[str]:
    d = profile_dir()
    try:
        names = [f[:-4] for f in os.listdir(d) if f.endswith(".env")]
    except FileNotFoundError:
        return []
    return sorted(n for n in names if n not in {"common", "example"})


def ensure_creds(profile: str | None = None) -> dict[str, str]:
    """Make GHL credentials available, from a profile OR the existing environment.

    Pass `profile` to load the ~/.ghl cascade. Pass None when already running
    inside `ghl-as <profile> ...` (env vars already exported) — this validates
    and returns them. Raises RecipeError if neither yields usable credentials.
    """
    if profile:
        return load_profile(profile)
    loc = os.environ.get("GHL_LOCATION_ID", "").strip()
    key = os.environ.get("GHL_API_KEY", "").strip()
    if loc and key:
        return {
            "profile": os.environ.get("GHL_LABEL", "(env)"),
            "agency": os.environ.get("GHL_AGENCY", ""),
            "location_id": loc,
            "api_key": key,
            "label": os.environ.get("GHL_LABEL", "(env)"),
        }
    raise RecipeError(
        "No --profile given and no GHL credentials in the environment. "
        "Pass --profile <name>, or run inside `ghl-as <profile> ...`."
    )


def load_profile(profile: str) -> dict[str, str]:
    """Load the credential cascade for `profile` into os.environ; return key vars.

    Raises RecipeError with an actionable message if the profile or required
    credentials are missing.
    """
    if not profile:
        raise RecipeError(
            "No profile given. Pass --profile <name>. "
            f"Available: {', '.join(list_profiles()) or '(none found in ' + profile_dir() + ')'}"
        )
    d = profile_dir()
    prof_path = os.path.join(d, f"{profile}.env")
    if not os.path.exists(prof_path):
        raise RecipeError(
            f"Profile '{profile}' not found at {prof_path}. "
            f"Available: {', '.join(list_profiles()) or '(none)'}"
        )
    agency = _parse_env_file(prof_path).get("GHL_AGENCY", "")
    merged: dict[str, str] = {}
    merged.update(_parse_env_file(os.path.join(d, "common.env")))
    if agency:
        merged.update(_parse_env_file(os.path.join(d, "agencies", f"{agency}.env")))
    merged.update(_parse_env_file(prof_path))
    for k, v in merged.items():
        os.environ[k] = v
    if not merged.get("GHL_LOCATION_ID"):
        raise RecipeError(f"Profile '{profile}' is missing GHL_LOCATION_ID.")
    if not merged.get("GHL_API_KEY"):
        raise RecipeError(f"Profile '{profile}' is missing GHL_API_KEY.")
    return {
        "profile": profile,
        "agency": agency,
        "location_id": merged["GHL_LOCATION_ID"],
        "api_key": merged["GHL_API_KEY"],
        "label": merged.get("GHL_LABEL", profile),
    }


# --------------------------------------------------------------------------- #
# Low-level HTTP (stdlib)
# --------------------------------------------------------------------------- #
def _request(method: str, url: str, headers: dict, body: dict | None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=_CTX, timeout=30) as resp:
            text = resp.read().decode()
            return resp.status, (json.loads(text) if text else {})
    except urllib.error.HTTPError as e:
        text = e.read().decode() if e.fp else ""
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {"raw": text[:500]}
        return e.code, parsed
    except urllib.error.URLError as e:
        raise RecipeError(f"Network error calling {url}: {e}") from e


# --------------------------------------------------------------------------- #
# Public API client (per-sub-account pit token)
# --------------------------------------------------------------------------- #
def public_request(method: str, path: str, params: dict | None = None,
                   body: dict | None = None, version: str = DEFAULT_VERSION):
    key = os.environ.get("GHL_API_KEY", "").strip()
    if not key:
        raise RecipeError("GHL_API_KEY not set — call load_profile() first.")
    url = PUBLIC_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Version": version,
        "User-Agent": CHROME_UA,
    }
    return _request(method, url, headers, body)


# --------------------------------------------------------------------------- #
# Internal API client (per-agency Firebase token) — used by the GHL web UI
# --------------------------------------------------------------------------- #
_token_cache: dict[str, object] = {"id_token": None, "ts": 0.0}


def _firebase_id_token(force: bool = False) -> str:
    if (not force and _token_cache["id_token"]
            and (time.time() - float(_token_cache["ts"])) < 3000):
        return str(_token_cache["id_token"])
    refresh = os.environ.get("GHL_FIREBASE_REFRESH_TOKEN", "").strip()
    if refresh:
        body = f"grant_type=refresh_token&refresh_token={refresh}".encode()
        req = urllib.request.Request(
            f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "User-Agent": CHROME_UA},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, context=_CTX, timeout=15) as r:
                tok = json.loads(r.read()).get("id_token", "")
        except Exception as e:  # noqa: BLE001
            raise RecipeError(
                "Firebase token refresh failed — the agency's refresh token may be "
                "expired/revoked. Re-grab it via docs/get-firebase-token.md.\n"
                f"  ({e})"
            ) from e
        if tok:
            _token_cache.update(id_token=tok, ts=time.time())
            return tok
    direct = os.environ.get("GHL_FIREBASE_TOKEN", "").strip()
    if direct:
        _token_cache.update(id_token=direct, ts=time.time())
        return direct
    raise RecipeError(
        "No Firebase token for the internal API. This recipe needs the agency's "
        "GHL_FIREBASE_REFRESH_TOKEN (in ~/.ghl/agencies/<agency>.env). "
        "Public-API-only profiles cannot run calendar-type changes."
    )


def backend_request(method: str, path: str, body: dict | None = None,
                    version: str = CALENDAR_VERSION, _retry: bool = True):
    token = _firebase_id_token()
    headers = {
        "token-id": token.encode("ascii", "ignore").decode("ascii").strip(),
        "channel": "APP",
        "source": "WEB_USER",
        "version": version,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": CHROME_UA,
    }
    status, data = _request(method, BACKEND_BASE + path, headers, body)
    if status in (401, 403) and _retry:
        _firebase_id_token(force=True)
        return backend_request(method, path, body, version, _retry=False)
    return status, data


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
def list_users() -> list[dict]:
    status, data = public_request("GET", "/users/",
                                  params={"locationId": os.environ["GHL_LOCATION_ID"]})
    if status != 200:
        raise RecipeError(f"Failed to list users (HTTP {status}): {json.dumps(data)[:200]}")
    return data.get("users", data if isinstance(data, list) else [])


def resolve_user(query: str, users: list[dict] | None = None) -> dict:
    """Resolve a user by exact id, exact email, or case-insensitive name substring."""
    users = users if users is not None else list_users()
    q = query.strip()
    for u in users:
        if u.get("id") == q:
            return u
    ql = q.lower()
    by_email = [u for u in users if (u.get("email", "") or "").lower() == ql]
    if len(by_email) == 1:
        return by_email[0]
    matches = [u for u in users if ql in (u.get("name", "") or "").lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        opts = ", ".join(f"{u.get('name')} <{u.get('email')}>" for u in users)
        raise RecipeError(f"No user matched '{query}'. Users in this location: {opts}")
    opts = ", ".join(f"{u.get('name')} ({u.get('id')})" for u in matches)
    raise RecipeError(f"'{query}' is ambiguous — matched: {opts}. Use a fuller name or the user id.")


# --------------------------------------------------------------------------- #
# Calendars
# --------------------------------------------------------------------------- #
def list_calendars() -> list[dict]:
    status, data = backend_request(
        "GET", f"/calendars/?locationId={os.environ['GHL_LOCATION_ID']}")
    if status != 200:
        raise RecipeError(f"Failed to list calendars (HTTP {status}): {json.dumps(data)[:200]}")
    return data.get("calendars", data if isinstance(data, list) else [])


def get_calendar(calendar_id: str) -> dict:
    status, data = backend_request("GET", f"/calendars/{calendar_id}")
    if status != 200:
        raise RecipeError(f"Failed to get calendar {calendar_id} (HTTP {status}): {json.dumps(data)[:200]}")
    return data.get("calendar", data)


def resolve_calendar(query: str, calendars: list[dict] | None = None) -> dict:
    """Resolve a calendar by exact id or case-insensitive exact/substring name."""
    calendars = calendars if calendars is not None else list_calendars()
    for c in calendars:
        if c.get("id") == query:
            return c
    ql = query.strip().lower()
    exact = [c for c in calendars if (c.get("name", "") or "").lower() == ql]
    if len(exact) == 1:
        return exact[0]
    subs = [c for c in calendars if ql in (c.get("name", "") or "").lower()]
    if len(subs) == 1:
        return subs[0]
    if not subs:
        raise RecipeError(f"No calendar matched '{query}'.")
    opts = ", ".join(f"{c.get('name')} ({c.get('id')}, {c.get('calendarType')})" for c in subs)
    raise RecipeError(f"'{query}' is ambiguous — matched: {opts}. Pass the calendar id.")


def create_calendar(body: dict, max_strips: int = 25) -> dict:
    """POST a new calendar, auto-stripping any read-only field the API rejects.

    Deterministic: the same input always produces the same sequence of strips.
    Returns the created calendar dict.
    """
    payload = {k: v for k, v in body.items() if k not in CALENDAR_READONLY_FIELDS}
    for _ in range(max_strips):
        status, data = backend_request("POST", "/calendars/", payload)
        if status in (200, 201):
            return data.get("calendar", data)
        offending = _unexpected_properties(status, data)
        if offending:
            for prop in offending:
                payload.pop(prop, None)
            continue
        raise RecipeError(f"Calendar create failed (HTTP {status}): {json.dumps(data)[:300]}")
    raise RecipeError("Calendar create kept failing validation after stripping fields; aborting.")


def update_calendar(calendar_id: str, patch: dict) -> dict:
    status, data = backend_request("PUT", f"/calendars/{calendar_id}", patch)
    if status not in (200, 201):
        raise RecipeError(f"Calendar update failed (HTTP {status}): {json.dumps(data)[:300]}")
    return data.get("calendar", data)


def _unexpected_properties(status: int, data: dict) -> list[str]:
    """Extract field names from a 422 'property X should not exist' response."""
    if status != 422 or not isinstance(data, dict):
        return []
    msgs = data.get("message", [])
    if isinstance(msgs, str):
        msgs = [msgs]
    found = []
    for m in msgs:
        mo = re.search(r"property (\w+) should not exist", str(m))
        if mo:
            found.append(mo.group(1))
    return found


def booking_link(calendar: dict) -> str:
    """Best-effort public booking permalink for a calendar."""
    slug = calendar.get("widgetSlug")
    if slug:
        return f"https://api.leadconnectorhq.com/widget/bookings/{slug}"
    return f"https://api.leadconnectorhq.com/widget/booking/{calendar.get('id')}"
