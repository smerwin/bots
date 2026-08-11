"""Run a captured Windows UI tree through the real Elm parser.

Follows `tools/macos-host/tests/prerequisites.py`'s recipe -- copy the app to
scratch, compile against its own vendored `EveOnline.*` -- and differs from it in
one way, for one reason: the tree is handed over a **port** rather than as a
source literal.  A real tree is megabytes and Elm processes backslash escapes
inside a triple-quoted string, which CLAUDE.md records turning a fixture carrying
a double quote into a `Nothing` that reads exactly like a parser answering
nothing.

Usage::

    python verify_tree.py tree.json
    python verify_tree.py --capture          # read the live client first
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
APP = os.path.join(
    REPO, "implement", "applications", "eve-online", "eve-online-mission-runner"
)

DRIVER = """
const fs = require('fs');
const { Elm } = require('./verify.js');
const app = Elm.VerifyTree.init();
app.ports.reportOut.subscribe(function (report) {
  console.log(JSON.stringify(report));
  process.exit(0);
});
app.ports.treeIn.send(fs.readFileSync(process.argv[2], 'utf8'));
"""


def build(scratch: str) -> str:
    app = os.path.join(scratch, "app")
    shutil.copytree(APP, app)
    shutil.copy(os.path.join(HERE, "VerifyTree.elm"), os.path.join(app, "VerifyTree.elm"))
    with open(os.path.join(app, "driver.js"), "w", encoding="utf-8") as handle:
        handle.write(DRIVER)
    result = subprocess.run(
        ["elm", "make", "VerifyTree.elm", "--output=verify.js"],
        cwd=app,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit("elm make failed")
    return app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tree", nargs="?", default=None)
    parser.add_argument("--capture", action="store_true", help="read the live client first")
    parser.add_argument("--pid", type=int, default=None)
    args = parser.parse_args()

    scratch = tempfile.mkdtemp(prefix="verify-tree-")
    try:
        tree_path = args.tree
        if args.capture or tree_path is None:
            sys.path.insert(0, os.path.dirname(HERE))
            import tree_walker  # noqa: E402

            session = tree_walker.open_client(args.pid)
            root = tree_walker.find_ui_root(session.reader, session.py, verbose=True)
            if root is None:
                return 1
            tree = session.walker.read_tree(root)
            tree_path = os.path.join(scratch, "tree.json")
            with open(tree_path, "w", encoding="utf-8") as handle:
                json.dump(tree, handle)
            print(f"# captured {session.walker.nodes} nodes", file=sys.stderr)
            session.reader.close()

        app = build(scratch)
        result = subprocess.run(
            ["node", "driver.js", os.path.abspath(tree_path)],
            cwd=app,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            return 1
        report = json.loads(result.stdout.strip().splitlines()[-1])

        print()
        print("What the real EveOnline.ParseUserInterface made of the tree")
        print("-" * 58)
        if not report.get("decoded"):
            print(f"  decodeMemoryReadingFromString FAILED: {report.get('error')}")
            return 1
        print(f"  decoded                    yes")
        print(f"  nodes in the tree          {report['nodes']}")
        print(f"  nodes with a display region {report['nodesWithRegion']}")
        print(f"  display texts              {report['displayTexts']}")
        print()
        for name, count in report["found"].items():
            mark = "  " if count else "  "
            print(f"  {mark}{name:32s} {count}")
        return 0
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
