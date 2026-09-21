#!/usr/bin/env python3
"""ROY_PAGE_V1 (2026-09-21): turn the greyed 'Royalties & Streams' tab in portal/pages.py into a link.

  patch_pages_roy.py SRC OUT             write the patched pages.py to OUT (SRC untouched)
  patch_pages_roy.py --unpatch SRC OUT   the exact inverse

Refuses unless SRC is the pages.py this was written against (sha256 prefix).
"""
import hashlib
import sys

EXPECT = "5598ff820a41"
OLD = '{"label": "Royalties & Streams"},'
NEW = '{"label": "Royalties & Streams", "href": "/royalties-streams", "key": "royalties"},'


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "--unpatch":
        src = open(a[1], encoding="utf-8").read()
        assert src.count(NEW) == 1, "not patched"
        out = src.replace(NEW, OLD, 1)
        if not sha(out).startswith(EXPECT):
            raise SystemExit("unpatch did not restore the original (%s)" % sha(out)[:12])
    else:
        src = open(a[0], encoding="utf-8").read()
        if not sha(src).startswith(EXPECT):
            raise SystemExit("refused: pages.py is %s, this patch expects %s" % (sha(src)[:12], EXPECT))
        assert src.count(OLD) == 1, "anchor"
        out = src.replace(OLD, NEW, 1)
        compile(out, "pages.py", "exec")
        print("patched: %s -> %s" % (sha(src)[:12], sha(out)[:12]))
    open(a[-1], "w", encoding="utf-8").write(out)
