# -*- coding: utf-8 -*-
"""Turn RES_V1 1.0.11 into 1.0.12 (2026-09-18).

Measured at 1.0.11 against labels draft-2: detection 25/0/0/25; row 92.4%, deposit 85.9%,
category 100.0%, tonnes 100.0%, grade 95.5%, context 95.9%.

  AP  every release cites "National Instrument 43-101 Standards of Disclosure for Mineral
      Projects", and that phrase ends in a project noun, so it was being read as the project --
      Patriot's rows came back under "Disclosure for Mineral". Boilerplate words join the list of
      words a name cannot be made of.

Usage: patch_res_v112.py <resources.py>
"""
import hashlib
import sys

EDITS = [
    ('VERSION = "1.0.11"', 'VERSION = "1.0.12"'),
    ('underground surface bulk global regional local""".split())',
     '''underground surface bulk global regional local
disclosure standards standard instrument national report reports technical summary statement
company companies corporation corp inc ltd limited plc holdings resources mining metals gold
exploration development corporate issuer news release filing filings sedar sedarplus""".split())'''),
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
