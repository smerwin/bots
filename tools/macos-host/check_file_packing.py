"""No single test file may be what bounds the parallel run.

Issue #199. CI runs `pytest -n auto --dist loadfile`, which keeps every case in
a file on the one worker that took the file. That used to be a constraint: each
file built its own scratch copy of the app, so splitting a file across workers
built it twice. #172 spent that reason -- `prerequisites.built_app` builds one
copy per app per worker *process* now, whatever the distribution.

What keeps `--dist loadfile` is a measurement rather than a constraint, and a
measurement is the kind of claim that stops holding without saying so. The
suite's case time spread evenly over the workers is the fastest any
distribution could finish; today no single file comes near that floor, so
`loadscope` has nothing to recover and the coarser split costs nothing. A file
that grows past the floor ends that: it sets the wall clock by itself and every
other worker waits on it, while the run still looks healthy.

So the relation the choice rests on is asserted on the run's own report rather
than remembered in a comment. **It compares times within one run** -- a loaded
runner stretches the longest file and the floor together -- so what it reads is
the shape of the suite and not the speed of the machine.

The other half of the same premise, that the build really is shared per process
rather than per class, is asserted by
`tests/test_prerequisites.OneBuiltAppIsHandedToEveryClass`.

    python3 tools/macos-host/check_file_packing.py report.xml [workers]
"""
import collections
import os
import sys
import xml.etree.ElementTree as ElementTree


def module_of(classname):
    """The test file a case belongs to, from its dotted `classname`.

    pytest writes `tools.macos-host.tests.test_thing.SomeClass` and no `file`
    attribute, so the file is the last segment named the way a test module is.
    """
    for segment in reversed(classname.split(".")):
        if segment.startswith("test_"):
            return segment
    return classname


def file_totals(paths):
    """Seconds of case time per test file across `paths`, and the total."""
    totals = collections.Counter()
    for path in paths:
        for case in ElementTree.parse(path).iter("testcase"):
            totals[module_of(case.get("classname") or "")] += float(
                case.get("time") or 0.0)
    return totals, sum(totals.values())


def report(paths, workers, out=sys.stdout):
    """Print the packing and answer whether `--dist loadfile` still holds."""
    totals, total = file_totals(paths)
    if not totals:
        print("no cases at all: the suite did not run", file=out)
        return False

    floor = total / workers
    longest, longest_time = max(totals.items(), key=lambda pair: pair[1])

    print("%d files, %.0fs of case time, %d workers -- perfect packing %.0fs"
          % (len(totals), total, workers, floor), file=out)
    for name, seconds in sorted(totals.items(), key=lambda pair: -pair[1])[:5]:
        print("%8.0fs  %s" % (seconds, name), file=out)

    if longest_time > floor:
        print("\n%s alone is %.0fs, past the %.0fs floor: with --dist loadfile "
              "that one file sets the wall clock and the other workers wait on "
              "it. Either split it, or reconsider the distribution -- the "
              "measurement recorded in .github/workflows/build-and-test.yml "
              "and CLAUDE.md no longer describes this suite."
              % (longest, longest_time, floor), file=out)
        return False

    print("\nlongest file %s is %.0fs against a %.0fs floor: granularity is "
          "not what bounds this run" % (longest, longest_time, floor), file=out)
    return True


def main(argv):
    # No worker count in the report, so it is asked of the machine that ran it
    # -- which is what `-n auto` asked too, in the same job.
    given_workers = len(argv) > 2 and argv[-1].isdigit()
    workers = int(argv[-1]) if given_workers else (os.cpu_count() or 1)
    paths = argv[1:-1] if given_workers else argv[1:]
    if not paths:
        print("usage: check_file_packing.py <junit.xml> [...] [workers]",
              file=sys.stderr)
        return 2
    return 0 if report(paths, workers) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
