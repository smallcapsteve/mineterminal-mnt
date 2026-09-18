# -*- coding: utf-8 -*-
"""Turn RES_V1 1.0.12 into 1.0.13 (2026-09-18).

Measured at 1.0.12: row 91.2%, deposit 88.7%, category 100.0%, tonnes 100.0%, grade 95.5%,
context 95.9%.

  AQ  1.0.12 blocked boilerplate words from project names and took "gold", "metals", "mining",
      "resources", "exploration" and "development" with them. Those are words real projects are
      named with -- Gold Bar, San Francisco Gold -- and 24 rows across the corpus lost their
      deposit name, Military Metals' among them. Only the words that are never part of a name
      stay blocked.

Usage: patch_res_v113.py <resources.py>
"""
import hashlib
import sys

EDITS = [
    ('VERSION = "1.0.12"', 'VERSION = "1.0.13"'),
    ('''disclosure standards standard instrument national report reports technical summary statement
company companies corporation corp inc ltd limited plc holdings resources mining metals gold
exploration development corporate issuer news release filing filings sedar sedarplus""".split())''',
     '''disclosure standards standard instrument national report reports technical summary statement
company companies corporation corp inc ltd limited plc holdings issuer news release
filing filings sedar sedarplus""".split())'''),
]


def main(argv):
    path = argv[0] if argv else "resources.py"
    s = open(path, encoding="utf-8").read()
    for i, (old, new) in enumerate(EDITS, 1):
        if s.count(old) != 1:
            print("edit %d: anchor appears %d times, expected 1" % (i, s.count(old)))
            return 1
        s = s.replace(old, new, 1)
    open(path, "w", encoding="utf-8").write(s)
    print("patched", path, len(EDITS), "edits, sha256",
          hashlib.sha256(s.encode("utf-8")).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
