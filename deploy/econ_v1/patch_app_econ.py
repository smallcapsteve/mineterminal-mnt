#!/usr/bin/env python3
"""ECON_PAGE_V1 (2026-09-21): give /economic-studies its own route.

  patch_app_econ.py SRC OUT ROUTE_BLOCK     write the patched app.py to OUT (SRC untouched)
  patch_app_econ.py --unpatch SRC OUT       the exact inverse

Refuses unless SRC is the app.py this patch was written against, byte for byte, and checks that the
result is what it should be before writing anything. Two edits:
  1. '/economic-studies' leaves _CATEGORY_PAGES, the plain list of tagged releases it showed;
  2. the route block is inserted after the /resources route, which is registered before the
     category loop, so it would win even without edit 1 -- edit 1 removes the dead duplicate.
"""
import hashlib
import sys

EXPECT = "c5d3d5155f60"          # sha256 prefix of the live portal/app.py, 2026-09-21
CAT_LINE = '    ("/economic-studies",     "Economic Studies",       "economic"),\n'
ANCHOR = "# ====== end /resources route ======\n"
BEGIN = "# ====== /economic-studies route (Economic Studies) ECON_PAGE_V1 (2026-09-21) ======"
END = "# ====== end /economic-studies route ======\n"


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def patch(src, block):
    if not sha(src).startswith(EXPECT):
        raise SystemExit("refused: app.py is %s, this patch expects %s" % (sha(src)[:12], EXPECT))
    if BEGIN in src:
        raise SystemExit("refused: already patched")
    assert src.count(CAT_LINE) == 1, "category line"
    assert src.count(ANCHOR) == 1, "anchor"
    assert block.strip().startswith(BEGIN) and block.rstrip().endswith(END.strip()), "route block"
    out = src.replace(CAT_LINE, "", 1)
    out = out.replace(ANCHOR, ANCHOR + block.rstrip("\n") + "\n", 1)
    assert out.count(BEGIN) == 1 and '"/economic-studies",     "Economic Studies"' not in out
    compile(out, "app.py", "exec")
    return out


def unpatch(src):
    i, j = src.index(BEGIN), src.index(END) + len(END)
    out = src[:i].rstrip("\n") + "\n" + src[j:]
    # the block was inserted right after ANCHOR; put the category line back first in its list
    out = out.replace("_CATEGORY_PAGES = [\n", "_CATEGORY_PAGES = [\n" + CAT_LINE, 1)
    if not sha(out).startswith(EXPECT):
        raise SystemExit("unpatch did not restore the original (%s)" % sha(out)[:12])
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--unpatch":
        src = open(a[1], encoding="utf-8").read()
        open(a[2], "w", encoding="utf-8").write(unpatch(src))
    else:
        src = open(a[0], encoding="utf-8").read()
        block = open(a[2], encoding="utf-8").read()
        out = patch(src, block)
        assert unpatch(out) == src, "the patch is not reversible"
        open(a[1], "w", encoding="utf-8").write(out)
        print("patched: %s -> %s" % (sha(src)[:12], sha(out)[:12]))
