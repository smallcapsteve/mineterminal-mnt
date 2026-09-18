#!/usr/bin/env python3
"""RES_V1: register the reader, its spec and its publisher (2026-09-18).

Three small files, three exact anchors, each asserted before anything is written:

  portal/accuracy.py            imports accuracy_resources last, so importing accuracy registers
                                every spec
  portal/extractors/__init__.py adds resources.SPEC to the registry facts_sync walks
  sync_structured.py            the timer publishes the active reader instead of running
                                resource_backfill.py, and the step moves to the end of the list
                                because it now reads the facts store that facts_sync fills

No anchor includes a closing docstring quote: an earlier draft did, and the nested triple quotes
did not survive being written out, so the file arrived on the box a byte different from the one
that had been tested. The anchors below are unique without them, and each edit inserts before the
quotes rather than rewriting them.

Usage: patch_accuracy_res.py <accuracy.py> <extractors/__init__.py> <sync_structured.py>
"""
import hashlib
import sys

EXPECT = {
    "accuracy.py": "f37b88e7f5b8245a1830eb0503496216b99a8e75be232ad3a520d3c35b14cade",
    "__init__.py": "12bbf536e928c89ee43890fb05fddd8fa8f3a8b317d72d2e95cd5db0614a72f2",
    "sync_structured.py": "06b32df53ee058f57b647f6cbb20460dd36aa7804497e43a9e7cf57ca90c8c77",
}

ACC_OLD = "from portal import accuracy_management as _accuracy_management  # noqa: E402,F401\n"
ACC_NEW = ACC_OLD + """
# RES_SPEC_V1 (2026-09-18): /resources shows one row per deposit per category -- a different shape
# again -- and its judge has to set aside field claims the labels do not state, or it measures the
# labels rather than the reader. Imported last for the same reason as the one above.
from portal import accuracy_resources as _accuracy_resources  # noqa: E402,F401
"""

INIT_OLD_DOC = """DRILL_V1 (2026-09-17): the new Drill Results reader is the first extractor here.
It replaces what /drills shows once the accuracy gate activates it; until then
the legacy drill_backfill.py keeps writing drill_results (portal/drill_publish.py
decides which runs). Resources are NOT here yet; they keep their own table until
they are rebuilt.
"""
INIT_NEW_DOC = """DRILL_V1 (2026-09-17): the new Drill Results reader is the first extractor here.
It replaces what /drills shows once the accuracy gate activates it; until then
the legacy drill_backfill.py keeps writing drill_results (portal/drill_publish.py
decides which runs).

RES_V1 (2026-09-18): the Resource Estimates reader completes the set -- financings,
management and now resources all read from the facts store. Every page MNT extracts
is version-stamped, backfilled and gated; no legacy backfill writes a page any more
once its reader is active.
"""

INIT_OLD_IMP = "from portal.extractors import management as _management\n"
INIT_NEW_IMP = INIT_OLD_IMP + "from portal.extractors import resources as _resources\n"

INIT_OLD_REG = "REGISTRY = [_drill_results.SPEC, _financings.SPEC, _management.SPEC]"
INIT_NEW_REG = """# RES_V1 (2026-09-18): the new Resource Estimates reader, one record per deposit per category;
# portal/resources_publish.py publishes the active version
REGISTRY = [_drill_results.SPEC, _financings.SPEC, _management.SPEC, _resources.SPEC]"""

SYNC_OLD_STEP = "    (['/opt/mnt/app/resource_backfill.py'],   'resource_estimates'),\n"
SYNC_OLD_LAST = "    (['-m', 'portal.management_publish'],     'management_changes'),\n"
SYNC_NEW_LAST = SYNC_OLD_LAST + (
    "    # RES_PUBLISH_V1 (2026-09-18): publish the active resources reader, one row per deposit per\n"
    "    # category (or run the legacy resource_backfill.py until one is active). It moved from first\n"
    "    # to last in this list because it now reads the facts store, which facts_sync fills.\n"
    "    (['-m', 'portal.resources_publish'],      'resource_estimates'),\n")

SYNC_OLD_DOC = ("MGMT_PUBLISH_V1 (2026-09-17): management_changes is written by portal.management_publish, on the same terms.\n"
                "It moved from first to last in this list because it now reads the facts store, which facts_sync fills.")
SYNC_NEW_DOC = SYNC_OLD_DOC + (
    "\n\nRES_PUBLISH_V1 (2026-09-18): resource_estimates is written by portal.resources_publish, on the same\n"
    "terms, and moved for the same reason. With it, every structured page MNT builds comes from a\n"
    "version-stamped, gated reader rather than a backfill script.")


def edit(path, label, edits):
    with open(path, encoding="utf-8") as fh:
        s = fh.read()
    if hashlib.sha256(s.encode("utf-8")).hexdigest() == EXPECT[label]:
        print("%-22s already patched" % label)
        return 0
    for name, old, new in edits:
        n = s.count(old)
        if n != 1:
            print("REFUSED %s / %s: anchor found %d times, expected 1" % (label, name, n))
            return 1
    for _name, old, new in edits:
        s = s.replace(old, new)
    got = hashlib.sha256(s.encode("utf-8")).hexdigest()
    if got != EXPECT[label]:
        print("REFUSED %s: the patched file would be %s, expected %s"
              % (label, got[:16], EXPECT[label][:16]))
        return 1
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(s)
    print("%-22s -> %s" % (label, got))
    return 0


def main(argv):
    if len(argv) < 3:
        print("usage: patch_accuracy_res.py <accuracy.py> <extractors/__init__.py> <sync_structured.py>")
        return 2
    rc = edit(argv[0], "accuracy.py", [("spec import", ACC_OLD, ACC_NEW)])
    rc |= edit(argv[1], "__init__.py", [("docstring", INIT_OLD_DOC, INIT_NEW_DOC),
                                        ("import", INIT_OLD_IMP, INIT_NEW_IMP),
                                        ("registry", INIT_OLD_REG, INIT_NEW_REG)])
    rc |= edit(argv[2], "sync_structured.py", [("legacy step", SYNC_OLD_STEP, ""),
                                               ("publish step", SYNC_OLD_LAST, SYNC_NEW_LAST),
                                               ("docstring", SYNC_OLD_DOC, SYNC_NEW_DOC)])
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
