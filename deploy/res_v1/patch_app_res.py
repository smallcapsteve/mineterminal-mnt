#!/usr/bin/env python3
"""RES_V1: the four places portal/app.py touches resource_estimates (2026-09-18).

app.py is 91 KB and never travels, so the /resources handler is swapped between its two marker
comments and the whole file's sha256 is checked before and after. The other three edits are exact
anchors; each asserts it matched once before anything is written.

  1. the /resources handler        one row per deposit per category instead of one per release
  2. three Jinja filters           tonnages and contained metal printed by the publisher's own
                                   formatters, so the page and the table cannot drift apart
  3. /api/resources/recent.json    MineTerminalPro reads this expecting one row per release, so it
                                   gets the first row of each rather than eight rows off two releases
  4. /api/companies/stage-signals  counts releases, not rows, now that a release has several

Usage: patch_app_res.py <app.py> <resources_page_block.py>
"""
import hashlib
import sys

BEFORE = "ebe067d879d89a22698981fbc8d41ce42ad0a2d7ccccb8932ae95badfa6c110f"
AFTER = "92391b5adbbb81347a9080837a8a97f0f15e7d4caf895a4e32fd5168ae47ccca"

START = "# ====== /resources route (Resource Estimates) (appended) ======"
END = "# ====== end /resources route ======"

OLD_FILTERS = """templates.env.filters['from_json'] = _from_json"""

NEW_FILTERS = """templates.env.filters['from_json'] = _from_json

# RES_V1 (2026-09-18): /resources prints figures with the publisher's own formatters, so a tonnage
# reads the same on the page as in the table it came from and the two cannot drift apart.
from portal.resources_publish import (fmt_tonnes as _res_fmt_t, fmt_grade as _res_fmt_g,   # noqa: E402
                                      fmt_contained as _res_fmt_c)


def _res_t(v):
    return _res_fmt_t(v) or "\\u2014"


def _res_grades(s):
    return [x for x in (_res_fmt_g(g) for g in _from_json(s)) if x]


def _res_contained(s):
    return [x for x in (_res_fmt_c(c) for c in _from_json(s)) if x]


templates.env.filters['res_t'] = _res_t
templates.env.filters['res_grades'] = _res_grades
templates.env.filters['res_contained'] = _res_contained"""

OLD_API = """        FROM resource_estimates r
        LEFT JOIN events e ON e.event_id = r.event_id
        WHERE r.published_at IS NOT NULL
        ORDER BY r.published_at DESC LIMIT ?"""

NEW_API = """        FROM resource_estimates r
        LEFT JOIN events e ON e.event_id = r.event_id
        WHERE r.published_at IS NOT NULL
          -- RES_V1 (2026-09-18): the table now holds one row per deposit per category.
          -- MineTerminalPro reads this endpoint expecting one row per release, so it gets the
          -- first row of each; without this, eight "recent" rows could come off two releases.
          AND r.ordinal = (SELECT MIN(x.ordinal) FROM resource_estimates x
                           WHERE x.event_id = r.event_id)
        ORDER BY r.published_at DESC LIMIT ?"""

OLD_SIGNALS = """    for row in conn.execute("SELECT ticker, COUNT(*) FROM resource_estimates GROUP BY ticker"):"""

NEW_SIGNALS = """    # RES_V1 (2026-09-18): a release now has several rows, so this counts releases, not rows
    for row in conn.execute("SELECT ticker, COUNT(DISTINCT event_id) FROM resource_estimates "
                            "GROUP BY ticker"):"""


def main(argv):
    if len(argv) < 2:
        print("usage: patch_app_res.py <app.py> <resources_page_block.py>")
        return 2
    path, block_path = argv[0], argv[1]
    with open(path, encoding="utf-8") as fh:
        s = fh.read()
    got = hashlib.sha256(s.encode("utf-8")).hexdigest()
    if got == AFTER:
        print("already patched: %s" % got)
        return 0
    if got != BEFORE:
        print("REFUSED: app.py is %s, expected %s" % (got[:16], BEFORE[:16]))
        return 1

    for name, old in (("start marker", START), ("end marker", END), ("filters", OLD_FILTERS),
                      ("recent.json", OLD_API), ("stage-signals", OLD_SIGNALS)):
        n = s.count(old)
        if n != 1:
            print("REFUSED %s: anchor found %d times, expected 1" % (name, n))
            return 1

    block = open(block_path, encoding="utf-8").read().rstrip("\n") + "\n"
    if not block.startswith(START) or END not in block:
        print("REFUSED: the replacement block does not carry both markers")
        return 1
    i = s.index(START)
    j = s.index(END) + len(END)
    s = s[:i] + block.rstrip("\n") + s[j:]

    s = s.replace(OLD_FILTERS, NEW_FILTERS)
    s = s.replace(OLD_API, NEW_API)
    s = s.replace(OLD_SIGNALS, NEW_SIGNALS)

    end = hashlib.sha256(s.encode("utf-8")).hexdigest()
    if AFTER != "__AFTER__" and end != AFTER:
        print("REFUSED: the patched file would be %s, expected %s" % (end[:16], AFTER[:16]))
        return 1
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(s)
    print("patched %s -> sha256 %s" % (path, end))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
