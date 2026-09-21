#!/usr/bin/env python3
"""PROD_V1 (2026-09-21): the three small edits to shared files the repo is behind on.

  patch_shared_prod.py DIR            patch DIR/portal/accuracy.py, DIR/portal/extractors/__init__.py and
                                      DIR/sync_structured.py in place
  patch_shared_prod.py --check DIR    report which are patched, change nothing

Each file is refused unless it is the live copy this was written against (sha256 prefix) or already
patched: mineterminal-mnt is behind the droplet (claude/MNT_REPO_DRIFT_2026-09-18.md), and a patch written
against the repo copy would undo live changes.
"""
import hashlib
import sys

BASE = {
    "portal/accuracy.py": ("74c5a7d3fd8b",),
    "portal/extractors/__init__.py": ("ce8548fb26e8",),
    "sync_structured.py": ("0787c8d7e4bb",),
}
MARK = {
    "portal/accuracy.py": "accuracy_production",
    "portal/extractors/__init__.py": "_production",
    "sync_structured.py": "portal.production_publish",
}


def patch_accuracy(s):
    return s.rstrip("\n") + "\n" + (
        "\n# PROD_SPEC_V1 (2026-09-21): /production-results shows one row per metal per period (actual or guidance)\n"
        "# and a row per completed milestone, scored through the publisher. Imported last for the same reason.\n"
        "from portal import accuracy_production as _accuracy_production  # noqa: E402,F401\n")


def patch_registry(s):
    a = "from portal.extractors import economics as _economics\n"
    b = "REGISTRY = [_drill_results.SPEC, _financings.SPEC, _management.SPEC, _resources.SPEC, _economics.SPEC]\n"
    assert s.count(a) == 1 and s.count(b) == 1, "registry anchors"
    s = s.replace(a, a + "from portal.extractors import production as _production\n")
    return s.replace(b, (
        "# PROD_V1 (2026-09-21): the Production Results reader, one record per metal per period or milestone;\n"
        "# portal/production_publish.py publishes the active version\n"
        "REGISTRY = [_drill_results.SPEC, _financings.SPEC, _management.SPEC, _resources.SPEC, _economics.SPEC,\n"
        "            _production.SPEC]\n"))


def patch_sync(s):
    a = "    # ACCURACY_V1 (2026-09-16):"
    assert s.count(a) == 1, "sync anchor"
    return s.replace(a, (
        "    # PROD_PUBLISH_V1 (2026-09-21): publish the active production reader, one row per metal per period.\n"
        "    # There is no legacy reader: until a version is active it does nothing.\n"
        "    (['-m', 'portal.production_publish'],    'production_results'),\n") + a)


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
