#!/usr/bin/env python3
"""Clone one EVE pilot's overview/UI layout to other pilots on this machine, by
linking their client settings files together instead of copying them.

    python3 link_pilot_overview.py --dir "<settings_Default dir>"
    python3 link_pilot_overview.py --dir "<settings_Default dir>" --apply

Why linking rather than copying: EVE keeps per-character UI state (the overview
tabs and columns, window layout, etc.) in one file per character,
`core_char_<characterID>.dat`, inside a client "settings_*" profile directory.
There is no in-game "copy my overview to another character" -- the file itself
is the setting. Linking the other pilots' files to the good one means every
pilot reads the same bytes; it is the same trick `Scripts/mg-greta.bat` already
uses on Windows with `mklink /H` (a hardlink) for one pilot ("jazz"). On
macOS/Linux the natural equivalent is a symlink, which is what this defaults to
there; on Windows it defaults to a hardlink instead, matching that existing
convention (a plain symlink needs Developer Mode or admin on Windows, a
hardlink does not).

What this does NOT do by default: link the *account* file
(`core_user_<userID>.dat`). Overview and window layout are per-character, not
per-account, so only the char file is linked unless `--include-user` is given.
The account/character pairing for that file is a guess (closest-mtime match --
there is no ID that ties the two together in the file itself), so treat
`--include-user` as best-effort and check the pairing this script prints before
trusting it.

The one real hazard: because a client fully rewrites its own file on ordinary
play, linking is a two-way street. If pilot B's file becomes a link to pilot
A's, then B moving a window or touching the overview *while logged in*
overwrites A's layout too -- there is no direction where changes only flow one
way. Do this with every relevant client closed, and expect that this is a
standing arrangement (all linked pilots now share one profile) rather than a
one-time copy.

Character names are resolved from their numeric IDs via EVE's public ESI
`/universe/names/` endpoint -- no login or API credentials needed, since a
character's name is public data. Account/user IDs are not resolvable that way
(ESI has no notion of them at all); they are only ever shown by ID and by their
guessed pairing with a character.

Nothing is written unless `--apply` is given. Without it this only prints the
detected pilots and, if you answer the prompts, the plan it *would* carry out.
Every file this would overwrite is renamed aside first (`<name>.bak-<timestamp>`),
never deleted.
"""
import argparse
import json
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ESI_NAMES_URL = "https://esi.evetech.net/latest/universe/names/?datasource=tranquility"
ESI_BATCH_LIMIT = 1000  # ESI's own cap on ids per call

CHAR_FILE_RE = re.compile(r"^core_char_(\d+)\.dat$")
USER_FILE_RE = re.compile(r"^core_user_(\d+)\.dat$")

DEFAULT_LINK_TYPE = "hardlink" if os.name == "nt" else "symlink"

# Where a "settings_*" directory is likely to live, searched only when --dir is
# not given. Best-effort -- if nothing turns up, pass --dir yourself.
AUTO_SEARCH_ROOTS = [
    os.environ.get("LOCALAPPDATA", ""),                       # Windows
    os.path.expanduser("~/Library/Application Support"),      # macOS
    os.path.expanduser("~/.local/share"),                      # Linux, native
    os.path.expanduser("~/.wine/drive_c/users"),               # Linux, Wine
]


class Pilot:
    """One detected `core_char_<id>.dat`, with whatever else is known about it."""

    def __init__(self, char_id, char_path):
        self.char_id = char_id
        self.char_path = char_path
        self.name = None            # filled in by resolve_names, or left None
        self.user_id = None         # filled in by pair_user_files, or left None
        self.user_path = None

    @property
    def label(self):
        who = self.name if self.name else "unknown"
        return "%s (char %d)" % (who, self.char_id)


# --------------------------------------------------------------------------
# discovery


def find_settings_dirs(roots):
    """Directories under `roots` that hold at least one core_char_<id>.dat."""
    found = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if any(CHAR_FILE_RE.match(name) for name in filenames):
                found.append(dirpath)
            # Don't descend into the huge SharedCache texture/cache trees.
            dirnames[:] = [d for d in dirnames
                           if d.lower() not in ("cache", "texture", "shader")]
    return sorted(set(found))


def discover(settings_dir):
    """(char files, user files), each {id: Path}, from one settings directory."""
    settings_dir = Path(settings_dir)
    char_files, user_files = {}, {}
    for entry in settings_dir.iterdir():
        if not entry.is_file():
            continue
        m = CHAR_FILE_RE.match(entry.name)
        if m:
            char_files[int(m.group(1))] = entry
            continue
        m = USER_FILE_RE.match(entry.name)
        if m:
            user_files[int(m.group(1))] = entry
    return char_files, user_files


# --------------------------------------------------------------------------
# name resolution (character IDs only -- ESI has no notion of a user/account id)


def resolve_char_names(char_ids, quiet=False):
    """{id: name} for whichever of `char_ids` ESI recognises as a character.

    Best-effort throughout: no network, a timeout, or ESI 404ing the whole
    batch (which it does if *any* id in it is unresolvable) all degrade to
    "resolve nothing" rather than raising, since a name is a convenience here,
    not something anything downstream depends on being present.
    """
    ids = sorted(set(char_ids))
    if not ids:
        return {}
    resolved = {}
    for start in range(0, len(ids), ESI_BATCH_LIMIT):
        chunk = ids[start:start + ESI_BATCH_LIMIT]
        try:
            resolved.update(_esi_names_call(chunk))
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError) as exc:
            if not quiet:
                print("  (ESI batch lookup failed (%s) -- retrying one at a time)"
                      % exc, file=sys.stderr)
            for one_id in chunk:
                try:
                    resolved.update(_esi_names_call([one_id]))
                except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
                    pass  # this one id is simply not resolvable; leave it out
    return resolved


def _esi_names_call(ids):
    body = json.dumps(ids).encode("utf-8")
    req = urllib.request.Request(
        ESI_NAMES_URL, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "link_pilot_overview.py (botlab tool; no contact on file)",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        entries = json.load(resp)
    return {e["id"]: e["name"] for e in entries if e.get("category") == "character"}


# --------------------------------------------------------------------------
# best-effort char/user pairing, by closest mtime


def pair_user_files(char_files, user_files, window_seconds=3600):
    """{char_id: user_id or None} -- the nearest-mtime user file within window.

    There is no field tying a core_char_ file to a core_user_ file; this is a
    guess from when the two were last touched, which is usually the same login.
    A user file already claimed by a closer char file is not reused, so two
    characters logged in back to back don't both grab the one account file
    that actually belongs to whichever was closer.
    """
    remaining = dict(user_files)
    pairing = {}
    by_gap = []
    for char_id, char_path in char_files.items():
        char_mtime = char_path.stat().st_mtime
        for user_id, user_path in user_files.items():
            gap = abs(user_path.stat().st_mtime - char_mtime)
            if gap <= window_seconds:
                by_gap.append((gap, char_id, user_id))
    by_gap.sort(key=lambda row: row[0])
    for gap, char_id, user_id in by_gap:
        if char_id in pairing or user_id not in remaining:
            continue
        pairing[char_id] = user_id
        del remaining[user_id]
    return pairing


# --------------------------------------------------------------------------
# presentation


def build_pilots(settings_dir, use_esi=True, pair_window=3600):
    char_files, user_files = discover(settings_dir)
    pilots = {cid: Pilot(cid, path) for cid, path in char_files.items()}
    if use_esi:
        names = resolve_char_names(char_files.keys())
        for cid, pilot in pilots.items():
            pilot.name = names.get(cid)
    pairing = pair_user_files(char_files, user_files, pair_window)
    for cid, uid in pairing.items():
        pilots[cid].user_id = uid
        pilots[cid].user_path = user_files[uid]
    return pilots, user_files


def print_pilots(pilots):
    if not pilots:
        print("no core_char_<id>.dat files found")
        return
    rows = sorted(pilots.values(), key=lambda p: (p.name is None, p.name or "", p.char_id))
    width = max(len(p.label) for p in rows)
    for p in rows:
        user_bit = ("user %d (guessed)" % p.user_id) if p.user_id else "user: not paired"
        print("  %-*s  %s" % (width, p.label, user_bit))


# --------------------------------------------------------------------------
# picking the main pilot


def find_pilot(pilots, query):
    """A pilot matching `query` by exact name, unique name substring, or char id."""
    query = query.strip()
    if query.isdigit() and int(query) in pilots:
        return pilots[int(query)]
    q = query.lower()
    exact = [p for p in pilots.values() if p.name and p.name.lower() == q]
    if len(exact) == 1:
        return exact[0]
    partial = [p for p in pilots.values() if p.name and q in p.name.lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        print("  ambiguous -- matches: %s"
              % ", ".join(p.label for p in partial), file=sys.stderr)
    return None


def prompt_for_main(pilots):
    while True:
        try:
            answer = input(
                "\nWhich pilot has the overview layout to spread? "
                "(name or char id, blank to cancel): ").strip()
        except EOFError:
            return None
        if not answer:
            return None
        pilot = find_pilot(pilots, answer)
        if pilot is not None:
            return pilot
        print("  no single match for %r -- try the exact name or the char id"
              % answer)


# --------------------------------------------------------------------------
# applying the plan


def already_linked(target_path, main_path):
    try:
        if target_path.is_symlink():
            return target_path.resolve() == main_path.resolve()
        return target_path.stat().st_ino == main_path.stat().st_ino \
            and target_path.stat().st_dev == main_path.stat().st_dev
    except OSError:
        return False


def link_file(main_path, target_path, link_type, apply_changes):
    """Back up `target_path` (if it exists and isn't already this link) and
    point it at `main_path`. Returns a one-line description of what happened
    (or would happen, if `apply_changes` is False)."""
    if target_path.exists() and already_linked(target_path, main_path):
        return "already linked to %s -- left alone" % main_path.name

    backup_name = None
    if target_path.exists() or target_path.is_symlink():
        backup_name = "%s.bak-%s" % (target_path.name, time.strftime("%Y%m%d-%H%M%S"))

    if not apply_changes:
        verb = "hardlink" if link_type == "hardlink" else "symlink"
        return ("would back up to %s, then %s -> %s"
                % (backup_name or "(nothing to back up)", verb, main_path.name))

    if backup_name:
        os.replace(str(target_path), str(target_path.with_name(backup_name)))

    if link_type == "hardlink":
        os.link(str(main_path), str(target_path))
    else:
        os.symlink(main_path.name, str(target_path))  # relative, same directory
    return "linked -> %s%s" % (main_path.name,
                                (" (backed up old file to %s)" % backup_name)
                                if backup_name else "")


# --------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description=__doc__.strip().splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dir", metavar="PATH",
                        help="the client's settings_* directory "
                             "(e.g. .../settings_Default). Auto-searched if omitted.")
    parser.add_argument("--main", metavar="NAME_OR_ID",
                        help="skip the prompt: this pilot's overview is the one to spread")
    parser.add_argument("--apply", action="store_true",
                        help="actually create the links (default: print the plan only)")
    parser.add_argument("--yes", action="store_true",
                        help="skip the confirmation prompt before applying")
    parser.add_argument("--include-user", action="store_true",
                        help="also link the guessed account (core_user_) file")
    parser.add_argument("--link-type", choices=("symlink", "hardlink"),
                        default=DEFAULT_LINK_TYPE,
                        help="default: hardlink on Windows, symlink elsewhere")
    parser.add_argument("--no-esi", action="store_true",
                        help="skip resolving character names over the network")
    parser.add_argument("--pair-window-seconds", type=int, default=3600,
                        help="how close two files' mtimes must be to guess "
                             "they belong to the same login (default 3600)")
    args = parser.parse_args()

    settings_dir = args.dir
    if not settings_dir:
        candidates = find_settings_dirs(AUTO_SEARCH_ROOTS)
        if not candidates:
            parser.error("no settings_* directory found automatically -- pass --dir")
        if len(candidates) > 1:
            print("more than one settings directory found:")
            for c in candidates:
                print("  %s" % c)
            parser.error("pass --dir to pick one")
        settings_dir = candidates[0]
        print("using %s" % settings_dir)

    settings_dir = Path(settings_dir)
    if not settings_dir.is_dir():
        parser.error("%s is not a directory" % settings_dir)

    pilots, all_user_files = build_pilots(
        settings_dir, use_esi=not args.no_esi, pair_window=args.pair_window_seconds)

    print("\nDetected pilot profiles in %s:" % settings_dir)
    print_pilots(pilots)
    unresolved_users = len(all_user_files) - len({p.user_id for p in pilots.values() if p.user_id})
    if args.include_user and unresolved_users:
        print("(%d account file(s) with no guessed pairing -- left untouched)"
              % unresolved_users)

    if len(pilots) < 2:
        print("\nnothing to link -- need at least two pilot profiles")
        return 0

    main_pilot = None
    if args.main:
        main_pilot = find_pilot(pilots, args.main)
        if main_pilot is None:
            print("no pilot matches --main %r" % args.main, file=sys.stderr)
            return 1
    else:
        main_pilot = prompt_for_main(pilots)
        if main_pilot is None:
            print("cancelled")
            return 0

    if main_pilot.user_id is None and args.include_user:
        print("\n%s has no guessed account file -- --include-user will only "
              "touch the char file for this run" % main_pilot.label)

    targets = [p for p in pilots.values() if p.char_id != main_pilot.char_id]
    print("\nMain pilot: %s" % main_pilot.label)
    print("Would link these %d pilot(s) to it:" % len(targets))
    for t in targets:
        print("  %s" % t.label)

    if not args.apply:
        print("\n(dry run -- nothing written; add --apply to actually link)")

    if args.apply and not args.yes:
        try:
            answer = input(
                "\nType 'yes' to apply -- this rewrites those pilots' overview/UI "
                "settings and is a standing link, not a one-time copy: ").strip()
        except EOFError:
            answer = ""
        if answer.lower() != "yes":
            print("cancelled")
            return 0

    print()
    for t in targets:
        result = link_file(main_pilot.char_path, t.char_path, args.link_type, args.apply)
        print("  %s (char): %s" % (t.label, result))
        if args.include_user:
            if main_pilot.user_path and t.user_path:
                result = link_file(main_pilot.user_path, t.user_path,
                                   args.link_type, args.apply)
                print("  %s (user): %s" % (t.label, result))
            else:
                print("  %s (user): skipped -- account file not confidently paired"
                      % t.label)

    if not args.apply:
        print("\nRe-run with --apply once this plan looks right.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
