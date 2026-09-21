#!/usr/bin/env python3
"""ECON_V1 (2026-09-21): the three small edits to files the repo is behind on.

  patch_shared_econ.py DIR            patch DIR/portal/accuracy.py, DIR/portal/extractors/__init__.py and
                                      DIR/sync_structured.py in place
  patch_shared_econ.py --check DIR    report which are patched, change nothing

Each file is refused unless it is byte for byte the live copy this was written against (or already
patched), because mineterminal-mnt is behind the droplet for all three (claude/MNT_REPO_DRIFT_2026-09-18.md)
and a patch written against the repo copy would undo live changes.
"""
import hashlib
import sys

BASE = {
    "portal/accuracy.py": "8af2a842084196eb082581e97e5cec5bd4323ec2b0405a09f27a5231cbaab33d",
    "portal/extractors/__init__.py": "12bbf536e928c89ee43890fb05fddd8fa8f3a8b317d72d2e95cd5db0614a72f2",
    "sync_structured.py": "06b32df53ee058f57b647f6cbb20460dd36aa7804497e43a9e7cf57ca90c8c77",
}
MARK = {
    "portal/accuracy.py": "accuracy_economics",
    "portal/extractors/__init__.py": "_economics",
    "sync_structured.py": "portal.economics_publish",
}


def patch_accuracy(s):
    return s.rstrip("\n") + "\n" + (
        "\n# ECON_SPEC_V1 (2026-09-21): /economic-studies shows one row per scenario, paired by its figures, and\n"
        "# a study a release credits to another company is left out. Imported last for the same reason.\n"
        "from portal import accuracy_economics as _accuracy_economics  # noqa: E402,F401\n")


def patch_registry(s):
    a = "from portal.extractors import resources as _resources\n"
    b = "REGISTRY = [_drill_results.SPEC, _financings.SPEC, _management.SPEC, _resources.SPEC]\n"
    assert s.count(a) == 1 and s.count(b) == 1, "registry anchors"
    s = s.replace(a, a + "from portal.extractors import economics as _economics\n")
    return s.replace(b, (
        "# ECON_V1 (2026-09-21): the Economic Studies reader, one record per scenario; the first reader for a\n"
        "# tag with no page of its own before it. portal/economics_publish.py publishes the active version\n"
        "REGISTRY = [_drill_results.SPEC, _financings.SPEC, _management.SPEC, _resources.SPEC, _economics.SPEC]\n"))


def patch_sync(s):
    a = "    # ACCURACY_V1 (2026-09-16):"
    assert s.count(a) == 1, "sync anchor"
    return s.replace(a, (
        "    # ECON_PUBLISH_V1 (2026-09-21): publish the active economics reader, one row per scenario. There is\n"
        "    # no legacy reader: until a version is active it does nothing.\n"
        "    (['-m', 'portal.economics_publish'],     'economic_studies'),\n") + a)


EDIT = {"portal/accuracy.py": patch_accuracy, "portal/extractors/__init__.py": patch_registry,
        "sync_structured.py": patch_sync}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main(argv):
    check = argv and argv[0] == "--check"
    root = argv[-1].rstrip("/")
    for f, base in BASE.items():
        p = root + "/" + f
        s = open(p, encoding="utf-8").read()
        if MARK[f] in s:
            print("%-32s already patched (%s)" % (f, sha(s.encode())[:12]))
            continue
        if sha(s.encode()) != base:
            raise SystemExit("REFUSED: %s is %s, expected %s" % (f, sha(s.encode())[:12], base[:12]))
        if check:
            print("%-32s unpatched, as expected" % f)
            continue
        out = EDIT[f](s)
        compile(out, f, "exec")
        open(p, "w", encoding="utf-8").write(out)
        print("%-32s %s -> %s" % (f, base[:12], sha(out.encode())[:12]))


if __name__ == "__main__":
    main(sys.argv[1:])
