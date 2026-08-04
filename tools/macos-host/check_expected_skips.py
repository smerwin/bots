"""Every skip in a suite run must be one somebody named in advance.

Issue #71. `unittest` prints `OK (skipped=43)` and nobody reads the number, so a
suite that quietly stopped executing a third of itself reports exactly what a
healthy one does. CI now reads it instead -- but **the assertion cannot be that
there are none.** CI legitimately has no `~/eve-bot-logs`, so every case that
reads the recorded corpus skips there and should: 43 of them at the time of
writing, and that number moves whenever a corpus-reading case is added.

So what is asserted is that each skip is *expected and named*. `EXPECTED` below
is the whole list of reasons a case may be skipped for, each one an absent piece
of **evidence** -- something CI genuinely does not have and cannot report on. A
reason matching none of them fails the build, which means a new kind of skip has
to be added here deliberately, by somebody who has thought about whether the
runner should have had that prerequisite.

`REFUSED` is narrower and louder: reasons that are always a broken environment
rather than an absent one, so the message can say which. The toolchain skip is
the one this issue is about -- `prerequisites.open_repl` only produces it under
`ELM_HARNESS_MAY_SKIP`, and a runner that is supposed to have `elm` must never
pass with it.

Two things are deliberately absent from `EXPECTED`, and both would be a skip CI
should fail on: anything about the vendored parsers or the app sources, which
are checked in and therefore always present; and anything about the toolchain.

    python3 tools/macos-host/check_expected_skips.py report.xml
"""
import collections
import re
import sys
import xml.etree.ElementTree as ElementTree

# Reasons a case may be skipped: absent evidence, one entry per shape the suite
# writes. Matched against the first line of the skip message.
EXPECTED = [
    (r"^none of mission_run\{[^}]*\}\.log is on this machine",
     "the shared corpus gate in prerequisites.recorded_runs"),
    (r"^no recorded mission_run\d+\.log$",
     "one named recorded run this machine does not have"),
    (r"^no recorded runs?\d*\b",
     "the recorded runs in ~/eve-bot-logs"),
    (r"^none of the recorded runs are present$",
     "the recorded runs in ~/eve-bot-logs"),
    (r"^run \d+'s log is not on this machine",
     "one named recorded run this machine does not have"),
    (r"^no recorded game logs\b",
     "the client's own game logs, which only a machine that has played has"),
    (r"^no game log lines recorded under ",
     "recorded runs that carry no game log"),
]

# Reasons that are never acceptable, with what each one means. Anything not in
# EXPECTED already fails; these exist so the failure says why rather than only
# that the reason was unrecognised.
REFUSED = [
    (r"\bno elm toolchain\b",
     "the elm toolchain is missing and ELM_HARNESS_MAY_SKIP was set, so the "
     "cases that execute the bot's own rules did not run. On a runner that is "
     "supposed to have elm this is a broken environment, not an absent one -- "
     "see tools/macos-host/tests/prerequisites.py."),
    (r"\bno vendored parsers\b",
     "the vendored ParseUserInterface copies are checked in, so their absence "
     "means the checkout is wrong rather than that there is nothing to check."),
]


def skips_and_totals(paths):
    """Every skip reason across `paths`, with how many cases ran and skipped."""
    reasons = collections.Counter()
    total = skipped = 0
    for path in paths:
        for case in ElementTree.parse(path).iter("testcase"):
            total += 1
            for skip in case.findall("skipped"):
                skipped += 1
                message = (skip.get("message") or "").strip()
                reasons[message.split("\n")[0] or "(no reason given)"] += 1
    return reasons, total, skipped


def unexpected(reason):
    """Why this reason is not allowed, or `None` if it is."""
    for pattern, meaning in REFUSED:
        if re.search(pattern, reason):
            return meaning
    for pattern, _ in EXPECTED:
        if re.search(pattern, reason):
            return None
    return ("no entry in EXPECTED covers this reason. If the prerequisite it "
            "names is one CI genuinely cannot have, add it there; if it is one "
            "the runner should have had, this is the bug.")


def report(paths, out=sys.stdout):
    """Print the tally and answer whether the run is acceptable."""
    reasons, total, skipped = skips_and_totals(paths)
    print("%d cases, %d executed, %d skipped" % (total, total - skipped, skipped),
          file=out)

    problems = []
    for reason, count in sorted(reasons.items(), key=lambda pair: -pair[1]):
        complaint = unexpected(reason)
        print("%5d  %s  %s" % (count, "!!" if complaint else "ok", reason),
              file=out)
        if complaint:
            problems.append((reason, count, complaint))

    if total == 0:
        print("\nno cases at all: the suite did not run", file=out)
        return False

    if total == skipped:
        print("\nevery case skipped: the suite executed nothing", file=out)
        return False

    for reason, count, complaint in problems:
        print("\nunexpected skip (%d cases): %s\n  %s" % (count, reason, complaint),
              file=out)
    return not problems


def main(argv):
    if len(argv) < 2:
        print("usage: check_expected_skips.py <junit.xml> [...]", file=sys.stderr)
        return 2
    return 0 if report(argv[1:]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
