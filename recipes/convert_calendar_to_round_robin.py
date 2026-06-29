#!/usr/bin/env python3
"""Recipe: convert an EVENT calendar into a ROUND ROBIN calendar.

GoHighLevel does NOT allow changing a calendar's type in place — both the public
and internal update endpoints accept the request but silently keep the old type.
The only faithful way is to recreate the calendar as round_robin with every other
setting copied over, assign the team member(s), and deactivate the source.

This script does exactly that, deterministically, in one command.

Two ways to run it:
  * Standalone:  python3 recipes/convert_calendar_to_round_robin.py --profile <p> --user "Name"
  * Via the CLI: ghl-as <p> calendars convert-to-round-robin --user "Name"
    (the CLI subcommand imports convert() from this module — one source of truth)

USAGE
    python3 recipes/convert_calendar_to_round_robin.py --profile <name> \
        [--calendar <id-or-name>] --user <name-or-id> [--user ...] \
        [--distribution optimize-availability|equal] [--name "New name"] \
        [--keep-source] [--dry-run] [--json]

  --profile       Sub-account profile (see `ls ~/.ghl/*.env`). Optional only when
                  already running inside `ghl-as <profile> ...`.
  --calendar      Source calendar (id, or name). If omitted, auto-detects the
                  single ACTIVE event calendar; errors if there are 0 or >1.
  --user          Team member to assign (name, email, or user id). Repeatable;
                  the first becomes the primary. At least one required.
  --distribution  Round-robin distribution. Default: optimize-availability.
  --name          Name for the new calendar. Default: same as the source.
  --keep-source   Leave the source calendar ACTIVE (default: deactivate it).
  --dry-run       Show the plan and the payload; make no changes.
  --json          Emit a machine-readable result object.

KNOWN LIMITS (also surfaced as warnings on a real run):
  * Google 2-way sync (syncOption) does NOT transfer — it derives from an actual
    Google Calendar OAuth connection, not a setting. Reconnect Google in the UI.
  * The new calendar gets a NEW id and (eventually) a new widget slug, so its
    booking link differs from the source's.
"""
from __future__ import annotations

import argparse
import json
import sys

import _ghl_recipe_lib as ghl

DISTRIBUTION = {
    "optimize-availability": "RoundRobin_OptimizeForAvailability",
    "equal": "RoundRobin_OptimizeForEqualDistribution",
}


def build_team_members(users: list[dict]) -> list[dict]:
    members = []
    for i, u in enumerate(users):
        members.append({
            "userId": u["id"],
            "priority": 1,
            "isPrimary": i == 0,
            "meetingLocationType": "custom",
            "meetingLocation": "",
            "locationConfigurations": [
                {"kind": "custom", "location": "", "position": 0, "meetingId": "custom_0"}
            ],
        })
    return members


def pick_source(calendar: str | None) -> dict:
    cals = ghl.list_calendars()
    if calendar:
        return ghl.resolve_calendar(calendar, cals)
    active_event = [c for c in cals if c.get("isActive") and c.get("calendarType") == "event"]
    if len(active_event) == 1:
        return active_event[0]
    if not active_event:
        raise ghl.RecipeError(
            "No active event calendar found to convert. Pass --calendar <id-or-name>. "
            "Calendars: " + ", ".join(
                f"{c.get('name')} ({c.get('calendarType')}, "
                f"{'active' if c.get('isActive') else 'inactive'})" for c in cals))
    opts = ", ".join(f"{c.get('name')} ({c.get('id')})" for c in active_event)
    raise ghl.RecipeError(
        f"Multiple active event calendars — specify which with --calendar: {opts}")


def convert(prof: dict, *, calendar: str | None = None, users: list[str],
            distribution: str = "optimize-availability", name: str | None = None,
            deactivate_source: bool = True, dry_run: bool = False) -> dict:
    """Core conversion. Assumes credentials are already loaded (see ensure_creds).

    Returns a result dict (a plan when dry_run, else the executed outcome).
    Raises ghl.RecipeError on any precondition failure.
    """
    if not users:
        raise ghl.RecipeError("At least one team member (--user) is required.")
    if distribution not in DISTRIBUTION:
        raise ghl.RecipeError(
            f"Unknown distribution '{distribution}'. Choose: {', '.join(sorted(DISTRIBUTION))}.")

    src = pick_source(calendar)
    src_full = ghl.get_calendar(src["id"])
    if src_full.get("calendarType") == "round_robin":
        raise ghl.RecipeError(
            f"Calendar '{src_full.get('name')}' ({src['id']}) is already round_robin.")

    all_users = ghl.list_users()
    members_users = [ghl.resolve_user(u, all_users) for u in users]
    team_members = build_team_members(members_users)
    new_name = name or src_full.get("name")

    body = dict(src_full)
    body["name"] = new_name
    body["calendarType"] = "round_robin"
    body["eventType"] = DISTRIBUTION[distribution]
    body["teamMembers"] = team_members
    body.pop("widgetSlug", None)  # let GHL generate a fresh slug

    result = {
        "profile": prof.get("profile"),
        "location_id": prof.get("location_id"),
        "source": {"id": src_full["id"], "name": src_full.get("name"),
                   "type": src_full.get("calendarType"), "active": src_full.get("isActive")},
        "new_calendar_name": new_name,
        "distribution": DISTRIBUTION[distribution],
        "team_members": [{"id": u["id"], "name": u.get("name"), "email": u.get("email")}
                         for u in members_users],
        "deactivate_source": deactivate_source,
    }

    if dry_run:
        result["dry_run"] = True
        return result

    new_cal = ghl.create_calendar(body)
    new_full = ghl.get_calendar(new_cal["id"])
    if new_full.get("calendarType") != "round_robin" or not new_full.get("teamMembers"):
        raise ghl.RecipeError(
            f"Created calendar {new_cal['id']} but it is not a populated round_robin "
            f"(type={new_full.get('calendarType')}, members={len(new_full.get('teamMembers', []))}). "
            "Source was left untouched.")

    if deactivate_source:
        ghl.update_calendar(src_full["id"], {"isActive": False})

    warnings = []
    if src_full.get("syncOption") == "twoway":
        warnings.append("Source had Google 2-way sync; reconnect Google to the new "
                        "calendar in the UI to restore it (not transferable via API).")
    if not new_full.get("widgetSlug"):
        warnings.append("New calendar's widget slug hasn't generated yet; the by-id "
                        "booking link below works in the meantime.")

    result.update({
        "new_calendar": {"id": new_full["id"], "name": new_full.get("name"),
                         "type": new_full.get("calendarType"), "active": new_full.get("isActive"),
                         "team_member_count": len(new_full.get("teamMembers", []))},
        "booking_link": ghl.booking_link(new_full),
        "source_now_active": (not deactivate_source) and bool(src_full.get("isActive")),
        "warnings": warnings,
    })
    return result


def print_result(d: dict) -> None:
    if d.get("dry_run"):
        header = "DRY RUN — no changes made"
    elif "new_calendar" in d:
        header = "DONE — calendar recreated as round robin"
    else:
        header = "RESULT"
    print(f"\n=== {header} ===")
    print(f"  Profile        : {d['profile']}  (location {d['location_id']})")
    src = d["source"]
    print(f"  Source         : {src['name']}  [{src['id']}]  ({src['type']}, "
          f"{'active' if src['active'] else 'inactive'})")
    print(f"  New name       : {d['new_calendar_name']}")
    print(f"  Distribution   : {d['distribution']}")
    print(f"  Team members   : " + ", ".join(
        f"{m['name']} <{m['email']}>" for m in d["team_members"]))
    print(f"  Deactivate src : {d['deactivate_source']}")
    if "new_calendar" in d:
        nc = d["new_calendar"]
        print(f"  New calendar   : {nc['name']}  [{nc['id']}]  "
              f"({nc['type']}, {nc['team_member_count']} member(s), "
              f"{'active' if nc['active'] else 'inactive'})")
        print(f"  Booking link   : {d['booking_link']}")
    for w in d.get("warnings", []):
        print(f"  !  {w}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="convert_calendar_to_round_robin",
        description="Recreate a GHL event calendar as a round-robin calendar.")
    p.add_argument("--profile", help="Sub-account profile (optional inside `ghl-as`)")
    p.add_argument("--calendar", help="Source calendar id or name (default: the single active event calendar)")
    p.add_argument("--user", action="append", default=[], metavar="NAME|EMAIL|ID",
                   help="Team member to assign (repeatable; first = primary)")
    p.add_argument("--distribution", choices=sorted(DISTRIBUTION), default="optimize-availability")
    p.add_argument("--name", help="Name for the new calendar (default: same as source)")
    p.add_argument("--keep-source", action="store_true", help="Leave the source calendar active")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", dest="as_json", action="store_true")
    args = p.parse_args(argv)

    if not args.user:
        p.error("at least one --user is required (the round-robin team member)")

    prof = ghl.ensure_creds(args.profile)
    result = convert(prof, calendar=args.calendar, users=args.user,
                     distribution=args.distribution, name=args.name,
                     deactivate_source=not args.keep_source, dry_run=args.dry_run)
    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        print_result(result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ghl.RecipeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
