"""What the probe scanner actually holds, so `anomaly-name` can be read rather than guessed.

    python scan_results.py            # the probe scanner's rows, cell by cell
    python scan_results.py --all      # every scanner-ish window, and all their text

**Read-only.**  It posts no input and is safe to run beside a live bot; the host
only stands down for *input*, and this takes one memory read (~0.4 s).

Why this exists.  `anomaly-name` is matched against the probe scanner's **Name**
column, and for a long time neither bot logged that cell -- what a run printed
about an anomaly was the *ID* the scanner gives it (`We are in anomaly
'AIC-176'`), so across every run recorded before #197 was acted on the site
words the launcher itself asks for (`Hideaway`, `Refuge`, `Rally Point`,
`Sanctum`, ...) occur exactly **zero** times.  saxrat now prints the Name and
Group beside the ID, so runs flown since write the column down by themselves.

This is still the instrument for reading it *directly*, which the log cannot be:
it answers on demand rather than only when the ship happens to be in a site, it
shows the header cells and every row rather than the one the bot is in, and it
works while a run is stopped.

**An absent window is reported, not printed as emptiness.**  A scanner that is
closed and a scanner holding nothing are the same silence otherwise, and this
project's signature failure is exactly that confusion -- so the two get
different words, and the closed case says which scanner-ish windows *are* open.
"""
import argparse
import sys

sys.path.insert(0, r"C:\botlab\smerwin-bots\tools\windows-host")
import tree_walker  # noqa: E402
from eve_mem import find_client_pid  # noqa: E402

# Types worth naming when the probe scanner is not the one open.  Deliberately a
# substring list rather than an exact set: the point of the closed branch is to
# say what *is* there, and a window whose type nobody predicted is precisely the
# one worth seeing.
SCANNERISH = ("Scanner", "ScanResult", "Scan")


def flatten(node, depth=0):
    yield node, depth
    for child in node.get("children") or []:
        yield from flatten(child, depth + 1)


def own_text(node):
    """The text this node carries itself, not its subtree's.

    Cells are what the Name column question is about, and a container's joined
    text answers a different question -- it is how a row's Name and its Type run
    together into one string that matches things neither of them says.
    """
    entries = node.get("dictEntriesOfInterest") or {}
    for key in ("_setText", "_text"):
        value = entries.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def texts_under(node):
    return [t for n, _ in flatten(node) if (t := own_text(n))]


def main():
    parser = argparse.ArgumentParser(
        description="read the probe scanner's rows out of the live client")
    parser.add_argument("--all", action="store_true",
                        help="dump every scanner-ish window's full text")
    args = parser.parse_args()

    pid = find_client_pid()
    if not pid:
        return "no EVE client running"
    session = tree_walker.open_client(pid)
    try:
        root = tree_walker.find_ui_root(session.reader, session.py)
        if not root:
            return "no UIRoot -- the client is running but not in game"
        tree = session.walker.read_tree(root)
        nodes = [n for n, _ in flatten(tree)]
    finally:
        session.reader.close()

    print("client pid %d, %d nodes" % (pid, len(nodes)))

    probe = [n for n in nodes
             if n.get("pythonObjectTypeName") == "ProbeScannerWindow"]
    if not probe:
        others = sorted({
            t for n in nodes
            if (t := n.get("pythonObjectTypeName"))
            and any(k in t for k in SCANNERISH)
        })
        print()
        print("NO ProbeScannerWindow IS OPEN.")
        print("  This is not 'the scanner is empty' -- nothing was read at all.")
        print("  Open it (Alt+P, in space; it reopens on undock) and run again.")
        print("  scanner-ish types present meanwhile: %s"
              % (", ".join(others) if others else "none"))
        return 0

    for window in probe:
        kids = [n for n, _ in flatten(window)]
        types = sorted({t for n in kids if (t := n.get("pythonObjectTypeName"))})
        print()
        print("ProbeScannerWindow: %d nodes" % len(kids))
        print("  types present: %s" % ", ".join(types))

        rows = [n for n in kids
                if (n.get("pythonObjectTypeName") or "").endswith("Entry")
                or "ScanResult" in (n.get("pythonObjectTypeName") or "")]
        print()
        if not rows:
            print("  no row-shaped nodes -- the scanner is open and holds nothing,")
            print("  which is a different answer from the one above.")
        for row in rows:
            cells = texts_under(row)
            print("  %-28s %s" % (row.get("pythonObjectTypeName"), cells))

        if args.all:
            print()
            print("  --- every text in the window ---")
            for text in texts_under(window):
                print("   ", repr(text))

    print()
    print("The Name cell is what `anomaly-name` matches, and `*` is its only")
    print("wildcard. A name containing a comma cannot be configured at all --")
    print("`splitSettingIntoNames` splits every setting value on commas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
