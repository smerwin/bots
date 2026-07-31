---
name: check-ui-parse
description: Verify what the EVE client's live UI tree actually contains, and whether ParseUserInterface.elm can see it. Use when the bot appears blind to something plainly on screen, when checking a guard's premise, or before writing parsing for new UI.
user-invocable: true
allowed-tools:
  - Read
  - Grep
  - Bash
  - Write
---

# /check-ui-parse — what the client really has vs what the parser looks for

The recurring failure in this repo is not a wrong click, it is the parser
returning `Nothing` for something that is on screen, which reads downstream as
"absent" rather than as an error. This checks both halves.

**Safe to run alongside a live bot.** `eve_read.py` only reads memory. Do
**not** reach for `route_setter.py` or `reload_drones.py` here — those drive
real input and will fight the bot for the cursor.

## 1. Read the live tree

`eve_read.py` reuses `botlab_host.py`'s UI-root cache, so it answers in about
two seconds while a bot is or has recently been running. Without that cache it
pays a full process dump (20–40s).

```
python3 tools/macos-host/eve_read.py overview    # rows, rendered flag, cells
python3 tools/macos-host/eve_read.py targets
python3 tools/macos-host/eve_read.py modules
python3 tools/macos-host/eve_read.py window
```

For anything else, use it as a library. Note the `sys.path` insert — the module
does not live on the default path:

```python
import sys; sys.path.insert(0, "/Users/smerwin/code/bots/tools/macos-host")
import eve_read
tree = eve_read.read_tree()
for node, x, y in eve_read.walk(tree):
    t = node.get("pythonObjectTypeName", "")
    if <predicate>:
        d = node.get("dictEntriesOfInterest") or {}
        print(t, x, y, d.get("_name"), eve_read.texts_of(node))
```

**Do one root-level walk and keep those coordinates.** `eve_read.walk(node, x, y)`
accumulates offsets from wherever it starts, so re-walking a subtree with its
own absolute position as the base double-counts that offset. Identify subtrees
by node identity, not by re-walking them.

Useful things to dump when hunting: `pythonObjectTypeName`, `_name` from
`dictEntriesOfInterest`, `texturePath`, and `texts_of(node)`.

## 2. Find what the parser filters on

The parser is vendored per bot — edit the copy belonging to the bot in
question, and check whether the other copies share the problem:

```
grep -rn '"<TypeName>"' implement/applications/eve-online/*/EveOnline/ParseUserInterface.elm
```

Then compare: does the live tree contain a node of the name the parser filters
on? If the count is zero, that is the bug. The Selected Item panel is the
worked example — the upstream parser looked for `ActiveItem`, this client calls
it `SelectedItemWnd`, and the result was `selectedItemWindow = Nothing` on
every reading for as long as the code existed.

When a name diverges, **match both** rather than replacing it. The upstream
name presumably matches some other client build, and these files are vendored
copies of shared code.

## 3. Known traps

- **The overview virtualises.** Every object in space has an entry, but only
  rendered rows are real; hidden ones keep stale regions pointing at rows that
  now belong to something else. Filter on `_display` before acting on a row —
  the region alone will not tell you.
- **Children can nest.** `_childrenObjects` sometimes yields another
  children-list wrapper rather than a stock list. `tree_walker.c` unwraps
  repeatedly; `re_helper.py`'s Python path still does a single hop.
- **Tooltips render outside their window**, so a naive text search can match
  the tooltip before the real row. Scope lookups to the owning window's
  subtree.
- **A column key is the column's header text.** `objectName` is literally
  `cellsTexts["Name"]`, so a renamed or absent overview column silently yields
  `Nothing`.

## 4. Confirm the fix the same way

After changing a filter, re-read the live client and show the node is now
found, then compile: `tools/macos-host/compile_bot.sh [<app>]`. A parser change
that compiles is not evidence it matches the client.
