#!/usr/bin/env python3
"""ROY_PAGE_V1 (2026-09-21): give /royalties-streams its own route.

  patch_app_roy.py SRC OUT ROUTE_BLOCK     write the patched app.py to OUT (SRC untouched)
  patch_app_roy.py --unpatch SRC OUT       the exact inverse

Refuses unless SRC is the app.py this patch was written against (EXPECT, or the value of ROY_APP_EXPECT when
another session has changed app.py since), and checks the result before writing anything. One edit: the
route block is inserted right after the /production-results route. There is no category page to retire --
the site had no Royalties & Streams page.
"""
import hashlib
import os
import sys

EXPECT = os.environ.get("ROY_APP_EXPECT", "532599fb4d9a")      # sha256 prefix of the live portal/app.py, 2026-09-21
ANCHOR = "# ====== end /production-results route ======\n"
BEGIN = "# ====== /royalties-streams route (Royalties & Streams) ROY_PAGE_V1 (2026-09-21) ======"
END = "# ====== end /royalties-streams route ======\n"


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def patch(src, block):
    if not sha(src).startswith(EXPECT):
        raise SystemExit("refused: app.py is %s, this patch expects %s" % (sha(src)[:12], EXPECT))
    if BEGIN in src or '"/royalties-streams"' in src:
        raise SystemExit("refused: already patched")
    assert src.count(ANCHOR) == 1, "anchor"
    assert block.strip().startswith(BEGIN) and block.rstrip().endswith(END.strip()), "route block"
    out = src.replace(ANCHOR, ANCHOR + block.rstrip("\n") + "\n", 1)
    assert out.count(BEGIN) == 1
    compile(out, "app.py", "exec")
    return out


def unpatch(src):
    i, j = src.index(BEGIN), src.index(END) + len(END)
    out = src[:i] + src[j:]
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
