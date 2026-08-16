"""Buy a stack of one item from the station's own sell orders, through the
client's market window.

Standalone one-off, like `reload_drones.py` and `route_setter.py`: it drives
real mouse and keyboard directly and is **not** part of the bot loop. Never run
it alongside a launcher session -- both fight for the same cursor. Check with
the same `pgrep`/`Get-Process` patterns the launchers' guard uses first.

## Why this is mostly guard

The obvious implementation -- open the market, pick the item, click Buy on the
order in this station -- works, and on the run this was written for it would
have spent **1.2 billion ISK**. The only Acolyte I sell order in Amarr VIII
(Oris) - Emperor Family Academy is priced at 120,000,000 ISK a unit against a
regional market of 3,149-6,200: a park-and-pray order sitting where a buyer in
a hurry will take it, and the *only* local one, so "cheapest in this station"
and "the scam" were the same row. The wallet held 13,095,092 ISK, so the
purchase would have failed for want of funds rather than being caught -- which
is luck, not a safeguard, and it would have been a different story on a fuller
wallet.

So the price is not something this tool discovers and accepts. It is something
the caller states (`--max-unit-price`), and every field the total depends on is
re-read from the dialog on the reading the Buy click is issued from:

  * the dialog names the item asked for,
  * the location names the station asked for,
  * the unit price is at or under the stated ceiling,
  * the quantity box really took the number typed into it,
  * and the total the *client* computed equals unit x quantity.

That last one is checked against the product rather than against a figure
computed here, so a dialog cannot satisfy the guard merely by agreeing with a
number this script already believes. Any disagreement clicks Cancel.

## Two client details that cost a rewrite each

**The market search returns groups, not items.** Typing into `QuickFilterEdit`
(`_name=searchField`) and pressing Return leaves the item list showing whatever
group was last browsed, and renders `<center>Searching</center>` while it works.
The results arrive as collapsed group rows -- `Drones`, `Blueprints &
Reactions` -- and the item only exists as a row once its group is clicked. A
search that "returned nothing" is usually a group nobody expanded.

**`Buy_Btn` is not unique.** The market's featured-items strip carries one per
tile ("Buy this item where it is available"), so the first node with that name
is three panels away from the dialog. Taking it is the overview's recycled-row
failure in another window: the click lands, on the wrong control, and every
layer reports success. `dialog_node` therefore scopes by region *and* node type
and refuses an ambiguous match rather than picking one.

Quantity is typed rather than stepped: the up/down buttons are one click per
unit, and the box starts at 1.
"""
import argparse
import re
import sys
import time

sys.path.insert(0, ".")
import eve_repl

# The Buy dialog's own bounds. It opens centred-left of the market window, which
# starts at x=1020 on a 1920-wide canvas, so this region excludes the market
# entirely -- which is the point, since that is where the duplicate buttons are.
DIALOG_X0, DIALOG_X1 = 600, 1010
DIALOG_Y0, DIALOG_Y1 = 500, 800

# Where the dialog draws the two figures, relative to the same region.
UNIT_Y0, UNIT_Y1 = 580, 610
TOTAL_Y0, TOTAL_Y1 = 650, 680

SEARCH_SETTLE = 5.0
MENU_SETTLE = 2.0


def labels(eve):
    eve.read()
    out = []
    for n, x, y in eve.nodes():
        d = n.get("dictEntriesOfInterest", {})
        s = d.get("_setText") or d.get("_text")
        if s and str(s).strip():
            out.append((x, y, n, str(s)))
    return out


def money(s):
    m = re.search(r"([\d,]+\.\d\d)\s*ISK", s)
    return float(m.group(1).replace(",", "")) if m else None


def dialog_node(eve, name, kind=None, quiet=False):
    hits = [(n, x, y) for n, x, y in eve.nodes()
            if n.get("dictEntriesOfInterest", {}).get("_name") == name
            and DIALOG_X0 <= x <= DIALOG_X1 and DIALOG_Y0 <= y <= DIALOG_Y1
            and (kind is None or kind in n.get("pythonObjectTypeName", ""))]
    if len(hits) != 1:
        if not quiet:
            print("   !! %s matched %d nodes in the dialog region: %s"
                  % (name, len(hits),
                     [(n.get("pythonObjectTypeName"), x, y) for n, x, y in hits]))
        return None
    return hits[0][0]


def clear_and_type(eve, node, text, backspaces=40):
    """Get a field to a known state before typing. The market search field in
    particular holds whatever was last searched for, and typing appends."""
    eve.click_node(node, settle=1.2)
    time.sleep(0.8)
    eve.key(eve_repl.KEY_END, settle=0.4)
    for _ in range(backspaces):
        eve._cg_send("keydown %d" % eve_repl.KEY_BACKSPACE)
        eve._cg_send("keyup %d" % eve_repl.KEY_BACKSPACE)
    time.sleep(0.6)
    eve.type_text(text)
    time.sleep(1.0)


def open_market(eve):
    eve.read()
    btn = next((n for n, x, y in eve.nodes()
                if n.get("pythonObjectTypeName") == "StationServiceBtn"
                and n.get("dictEntriesOfInterest", {}).get("_name") == "market"), None)
    if btn is None:
        return False
    if not any(n.get("pythonObjectTypeName") == "RegionalMarket"
               for n, x, y in eve.nodes()):
        eve.click_node(btn, settle=3.0)
        time.sleep(4)
    return True


def find_item_row(eve, item):
    """Search, then expand the group the result is filed under."""
    fld = next((n for n, x, y in eve.nodes()
                if n.get("pythonObjectTypeName") == "QuickFilterEdit"
                and n.get("dictEntriesOfInterest", {}).get("_name") == "searchField"), None)
    if fld is None:
        print("no market search field")
        return None
    clear_and_type(eve, fld, item.lower())
    eve.key("return", settle=3.0)
    time.sleep(SEARCH_SETTLE)

    for _ in range(8):
        ls = [(x, y, n, s) for x, y, n, s in labels(eve) if 1020 <= x <= 1210]
        row = next((n for x, y, n, s in ls if s.strip().lower() == item.lower()), None)
        if row is not None:
            return row
        # The item is inside a collapsed group -- expand whatever groups there are.
        opened = False
        for x, y, n, s in ls:
            t = s.strip()
            if t and t.lower() != item.lower() and "Searching" not in t and len(t) < 40:
                eve.click_node(n, settle=1.5)
                time.sleep(2)
                opened = True
                break
        if not opened:
            break
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--item", required=True, help="exact item name, e.g. 'Acolyte I'")
    p.add_argument("--quantity", type=int, required=True)
    p.add_argument("--max-unit-price", type=float, required=True,
                   help="refuse to buy above this per unit -- there is no default, "
                        "because the whole point is that the caller states it")
    p.add_argument("--station", required=True,
                   help="substring of the station the order must be in, so the "
                        "goods end up where the ship is")
    p.add_argument("--dry-run", action="store_true",
                   help="read and check everything, then cancel instead of buying")
    a = p.parse_args()

    eve = eve_repl.connect()
    eve.read()
    if not eve.docked():
        print("not docked -- this drives the station's market service")
        return 1
    if not open_market(eve):
        print("no market service button in this station")
        return 1

    row = find_item_row(eve, a.item)
    if row is None:
        print("could not reach a row for %r" % a.item)
        return 1
    eve.click_node(row, settle=2.5)
    time.sleep(5)
    eve.read()

    order = None
    for n, x, y in eve.nodes():
        if n.get("pythonObjectTypeName") != "MarketOrder":
            continue
        txt = " ".join(s.strip() for s in eve.texts(n) if s and s.strip())
        if a.station in txt and "ISK" in txt:
            price = money(txt)
            if price is not None and price <= a.max_unit_price:
                order = n
                print("order in %s at %.2f ISK" % (a.station, price))
                break
            print("order in %s is %.2f ISK, over the %.2f ceiling -- refusing"
                  % (a.station, price or -1, a.max_unit_price))
            return 1
    if order is None:
        print("no sell order for %r in a station matching %r" % (a.item, a.station))
        return 1

    eve.click_node(order, button=eve_repl.RIGHT, settle=MENU_SETTLE)
    time.sleep(2)
    if not eve.menu_click("Buy this"):
        print("no 'Buy this' entry on the order's menu")
        return 1
    time.sleep(4)

    qty = dialog_node(eve, "Quantity", "Edit")
    if qty is None:
        print("the buy dialog did not open")
        return 1
    clear_and_type(eve, qty, str(a.quantity), backspaces=12)
    time.sleep(2.0)

    ls = labels(eve)
    unit = total = None
    for x, y, n, s in ls:
        if DIALOG_X0 <= x <= DIALOG_X1:
            v = money(s)
            if v is None:
                continue
            if UNIT_Y0 <= y <= UNIT_Y1:
                unit = v
            elif TOTAL_Y0 <= y <= TOTAL_Y1:
                total = v

    qty_shown = None
    q = dialog_node(eve, "Quantity", "Edit")
    if q is not None:
        m = re.search(r"\d[\d,]*", " ".join(t for t in eve.texts(q) if t))
        qty_shown = int(m.group(0).replace(",", "")) if m else None

    expected = (unit or 0) * a.quantity
    checks = {
        "dialog names the item": any(a.item in s for _, _, _, s in ls),
        "dialog names the station": any(a.station in s for _, _, _, s in ls),
        "unit price within ceiling": unit is not None and unit <= a.max_unit_price,
        "quantity box took the number": qty_shown == a.quantity,
        "client's total == unit x qty": total is not None and abs(total - expected) < 0.5,
    }
    print()
    print("  item %r  station %r" % (a.item, a.station))
    print("  unit %s   qty %s   total %s" % (unit, qty_shown, total))
    for k, v in checks.items():
        print("   %-30s %s" % (k, "ok" if v else "FAILED"))

    if not all(checks.values()) or a.dry_run:
        print()
        print("cancelling" if a.dry_run else "NOT BUYING -- cancelling")
        c = dialog_node(eve, "Cancel_Btn", "Button")
        if c is not None:
            eve.click_node(c, settle=1.5)
        return 0 if a.dry_run else 1

    b = dialog_node(eve, "Buy_Btn", "Button")
    if b is None:
        print("no Buy button in the dialog region")
        return 1
    print()
    print("buying %d x %s for %.2f ISK" % (a.quantity, a.item, total))
    eve.click_node(b, settle=3.0)
    time.sleep(4)
    print("clicked Buy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
