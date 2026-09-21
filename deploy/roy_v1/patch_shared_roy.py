#!/usr/bin/env python3
"""ROY_V1 (2026-09-21): the three small edits to shared files.

  patch_shared_roy.py DIR            patch DIR/portal/accuracy.py, DIR/portal/extractors/__init__.py and
                                     DIR/sync_structured.py in place
  patch_shared_roy.py --check DIR    report which are patched, change nothing

Each file is refused unless it is the live copy this was written against (sha256 prefix, as PROD_V1 left
them) or already patched: other sessions edit these files too, and a patch written against another copy
would undo their changes.
"""
import hashlib
import sys

BASE = {
    "portal/accuracy.py": ("193f37cabecb",),
    "portal/extractors/__init__.py": ("c8af2eb32080",),
    "sync_structured.py": ("982c3f99f96a",),
}
MARK = {
    "portal/accuracy.py": "accuracy_royalties",
    "portal/extractors/__init__.py": "_royalties",
    "sync_structured.py": "portal.royalties_publish",
}


def patch_accuracy(s):
    return s.rstrip("\n") + "\n" + (
        "\n# ROY_SPEC_V1 (2026-09-21): /royalties-streams shows one row per royalty or stream interest a release\n"
        "# reports as news, scored through the publisher. Imported last for the same reason.\n"
        "from portal import accuracy_royalties as _accuracy_royalties  # noqa: E402,F401\n")


def patch_registry(s):
    a = "from portal.extractors import production as _production\n"
    b = ("REGISTRY = [_drill_results.SPEC, _financings.SPEC, _management.SPEC, _resources.SPEC, _economics.SPEC,\n"
         "            _production.SPEC]\n")
    assert s.count(a) == 1 and s.count(b) == 1, "registry anchors"
    s = s.replace(a, a + "from portal.extractors import royalties as _royalties\n")
    return s.replace(b, (
        "REGISTRY = [_drill_results.SPEC, _financings.SPEC, _management.SPEC, _resources.SPEC, _economics.SPEC,\n"
        "            _production.SPEC,\n"
        "            # ROY_V1 (2026-09-21): the Royalties & Streams reader, one record per interest in a deal;\n"
        "            # portal/royalties_publish.py publishes the active version\n"
        "            _royalties.SPEC]\n"))


def patch_sync(s):
    a = "    # ACCURACY_V1 (2026-09-16):"
    assert s.count(a) == 1, "sync anchor"
    return s.replace(a, (
        "    # ROY_PUBLISH_V1 (2026-09-21): publish the active royalties reader, one row per interest in a deal.\n"
        "    # There is no legacy reader: until a version is active it does nothing.\n"
        "    (['-m', 'portal.royalties_publish'],     'royalty_deals'),\n") + a)


EDIT = {"portal/accuracy.py": patch_accuracy, "portal/extractors/__init__.py": patch_registry,
        "sync_structured.py": patch_sync}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main(argv):
    check = argv and argv[0] == "--check"
    root = argv[-1].rstrip("/")
    for f, bases in BASE.items():
        p = root + "/" + f
        s = open(p, encoding="utf-8").read()
        h = sha(s.encode())
        if MARK[f] in s:
            print("%-32s already patched (%s)" % (f, h[:12]))
            continue
        if not any(h.startswith(b) for b in bases):
            raise SystemExit("REFUSED: %s is %s, expected %s" % (f, h[:12], "/".join(bases)))
        if check:
            print("%-32s unpatched, as expected" % f)
            continue
        out = EDIT[f](s)
        compile(out, f, "exec")
        open(p, "w", encoding="utf-8").write(out)
        print("%-32s %s -> %s" % (f, h[:12], sha(out.encode())[:12]))


if __name__ == "__main__":
    main(sys.argv[1:])
