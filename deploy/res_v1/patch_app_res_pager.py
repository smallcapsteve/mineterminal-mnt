#!/usr/bin/env python3
"""RES_PAGER_V1: swap the /resources handler for the one that does not join to count (2026-09-18).

portal/app.py is 91 KB and never travels, so the handler is replaced between its two marker
comments. Integrity is carried by the block file, whose sha256 is checked here before anything is
written, and by app.py's own sha256 before the swap. The resulting sha is printed rather than
asserted, because this is the first version to produce it.

What changes, and why -- measured on the box with nothing else running, five runs each:

  the pager's COUNT(*) over the LEFT JOIN     0.642s
  the same scan with no join at all           0.017s

The plan was already optimal (SCAN e, covering-index probe on re). The cost is that the tag test is
a LIKE on a concatenated string, so it cannot be pushed ahead of the join and the probe ran for all
44,932 events rather than the 672 that carry the tag. The page shows one row per resource figure
plus one row per tagged release that states none, which is an identity needing no join over events:

    tagged releases  +  resource rows  -  tagged releases that have rows

Checked against the old count over 168 combinations of ticker, window and filter: identical every
time, including releases with no publish date, which fall back to their classified date on one side
of the sum only.

The date filter also loses its substr(). Comparing the whole timestamp against a bare date is the
same test for ISO-8601 text and saves building a string for every row scanned.

Usage: patch_app_res_pager.py <app.py> <resources_page_block.py>
"""
import hashlib
import sys

APP_BEFORE = "92391b5adbbb81347a9080837a8a97f0f15e7d4caf895a4e32fd5168ae47ccca"
BLOCK_SHA = "91bca10de91a383040f429f27e61604df4e52eb80ed531cd49a69d2c8db3c70a"

START = "# ====== /resources route (Resource Estimates) (appended) ======"
END = "# ====== end /resources route ======"


def main(argv):
    if len(argv) < 2:
        print("usage: patch_app_res_pager.py <app.py> <resources_page_block.py>")
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
    for name, mark in (("start marker", START), ("end marker", END)):
        if s.count(mark) != 1:
            print("REFUSED %s: found %d times, expected 1" % (name, s.count(mark)))
            return 1

    i = s.index(START)
    j = s.index(END) + len(END)
    s = s[:i] + block.strip("\n") + s[j:]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(s)
    print("patched %s" % path)
    print("  from sha256 %s" % before)
    print("  to   sha256 %s" % hashlib.sha256(s.encode("utf-8")).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
