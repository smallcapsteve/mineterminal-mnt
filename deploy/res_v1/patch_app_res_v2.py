#!/usr/bin/env python3
"""RES_PAGE_V2: /resources reads its own table, and the two other consumers skip the markers.

(2026-09-18.) portal/app.py is 91 KB and never travels, so the handler is swapped between its two
marker comments. The block file's sha256 is checked before anything is written, and so is app.py's.

Three edits:

  1. the /resources handler     built from resource_estimates alone, no events, no _cat_where
  2. /api/resources/recent.json markers excluded -- MineTerminalPro must not be served a release
                                that states no figures
  3. /api/companies/stage-signals.json  the same, so a tagged release with no figures does not
                                make a company look like it has a resource

Why the handler changed. /resources was driven off events: _cat_where() against 43,591 approved
releases evaluating four LIKE patterns each, then a LEFT JOIN to resource_estimates. Measured on
the box:

    review_status test alone                 0.006s
    ... plus the four category LIKEs         0.534s
    the page query (LIMIT 200)               0.741s

Two of the four patterns begin with a wildcard, so no index can serve them -- idx_events_categories
exists and cannot help. Replacing them with a single instr() was measured too, at 0.566s: no better.
The scan itself is the cost, and the only way to stop paying it is not to scan.

/financings has always read `SELECT * FROM financings` and answers in 0.2s. This now does the same.
It became possible once the publisher started writing a marker row for each tagged release that
states no figures, so every row the page shows -- 1,100 figures and 343 markers, 1,443 in all,
which is exactly what the page reported before -- lives in one small table.

Usage: patch_app_res_v2.py <app.py> <resources_page_block.py>
"""
import hashlib
import sys

APP_BEFORE = "17898391d3366e15193bf5cca370cdaa4ff88ccdfe3919be66ef8f72970e9eab"
BLOCK_SHA = "4deb0b75ff23e85115c54cd9ecfe101196203d779d19cfb2d9619b963bae192c"

START = "# ====== /resources route (Resource Estimates) (appended) ======"
END = "# ====== end /resources route ======"

OLD_API = """          AND r.ordinal = (SELECT MIN(x.ordinal) FROM resource_estimates x
                           WHERE x.event_id = r.event_id)"""

NEW_API = """          -- RES_PAGE_V2 (2026-09-18): the table also holds a marker row for each tagged
          -- release that states no figures. This feed is a list of resource estimates, so the
          -- markers are not part of it.
          AND r.category IS NOT NULL
          AND r.ordinal = (SELECT MIN(x.ordinal) FROM resource_estimates x
                           WHERE x.event_id = r.event_id AND x.category IS NOT NULL)"""

OLD_SIGNALS = """    for row in conn.execute("SELECT ticker, COUNT(DISTINCT event_id) FROM resource_estimates "
                            "GROUP BY ticker"):"""

NEW_SIGNALS = """    # RES_PAGE_V2 (2026-09-18): markers are tagged releases that state no figures, so they do
    # not make a company look like it has a resource
    for row in conn.execute("SELECT ticker, COUNT(DISTINCT event_id) FROM resource_estimates "
                            "WHERE category IS NOT NULL GROUP BY ticker"):"""


def main(argv):
    if len(argv) < 2:
        print("usage: patch_app_res_v2.py <app.py> <resources_page_block.py>")
        return 2
    path, block_path = argv[0], argv[1]

    block = open(block_path, encoding="utf-8").read()
    got = hashlib.sha256(block.encode("utf-8")).hexdigest()
    if got != BLOCK_SHA:
        print("REFUSED: the block is %s, expected %s" % (got[:16], BLOCK_SHA[:16]))
        return 1
    if not block.lstrip().startswith(START) or END not in block:
        print("REFUSED: the block does not carry both markers")
        return 1

    with open(path, encoding="utf-8") as fh:
        s = fh.read()
    before = hashlib.sha256(s.encode("utf-8")).hexdigest()
    if before != APP_BEFORE:
        print("REFUSED: app.py is %s, expected %s" % (before[:16], APP_BEFORE[:16]))
        return 1
    for name, old in (("start marker", START), ("end marker", END),
                      ("recent.json", OLD_API), ("stage-signals", OLD_SIGNALS)):
        n = s.count(old)
        if n != 1:
            print("REFUSED %s: anchor found %d times, expected 1" % (name, n))
            return 1

    i = s.index(START)
    j = s.index(END) + len(END)
    s = s[:i] + block.strip("\n") + s[j:]
    s = s.replace(OLD_API, NEW_API)
    s = s.replace(OLD_SIGNALS, NEW_SIGNALS)

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(s)
    print("patched %s" % path)
    print("  from sha256 %s" % before)
    print("  to   sha256 %s" % hashlib.sha256(s.encode("utf-8")).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
