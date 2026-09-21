#!/usr/bin/env python3
"""ECON_V1 diagnostics (read-only): the text around the figures repro_econ.py flagged as implausible,
and around the owner names it read. Run from the candidate tree."""
import re
import sqlite3
import sys

sys.path.insert(0, ".")
from portal.extractors import econ_core as C  # noqa: E402

conn = sqlite3.connect("file:/opt/mnt/app/portal/portal.db?mode=ro", uri=True)
CASES = [  # (ticker, date prefix, needles)
    ("FL.V", "2025-02-28", ["1.74"]), ("CAM.V", "2025-09-17", ["3.75"]), ("WHN.V", "2025-05-01", ["NPV"]),
    ("USCU.V", "2025-04-28", ["1.07"]), ("VZLA.TO", "2025-11-12", ["1.8"]), ("GENM.TO", "2025-03-27", ["992"]),
    ("BRVO.V", "2025-07-07", ["496", "1,271"]), ("DML.TO", "2025-08-06", ["701"]), ("CCM.TO", "2025-09-03", ["3,300"]),
    ("PMET.TO", "2025-10-20", ["1,594", "1.594", "1,221", "1.221"]), ("XXIX.V", "2025-10-21", ["67.7", "108.5"]),
    ("RPX.V", "2026-02-18", ["523", "51"]), ("TALA.V", "2026-02-22", ["47.8", "4.78", "4,78"]),
    ("DBG.V", "2026-03-02", ["900"]), ("ACM.CN", "2026-03-02", ["500"]), ("BUFF.V", "2026-04-27", ["NPV"]),
    ("AMC.TO", "2026-04-30", ["IRR"]), ("SRL.V", "2026-07-15", ["248"]), ("TRX.TO", "2026-01-15", ["4,000"]),
    ("FMAN.V", "2026-09-08", ["696"]), ("USGD.CN", "2023-04-24", ["266"]), ("AGMR.TO", "2025-01-21", ["85"]),
    ("CUU.V", "2025-06-23", ["0.25"]), ("OMG.V", "2025-05-01", ["Eastern Flats"]),
]
for tk, day, needles in CASES:
    rows = conn.execute("SELECT event_id, raw_headline, raw_body FROM events WHERE ticker=? AND "
                        "COALESCE(published_at, classified_at) LIKE ? AND review_status='auto_approved'",
                        (tk, day + "%")).fetchall()
    for eid, hl, body in rows[:2]:
        flat = C.unwrap((hl or "") + "\n" + (body or ""))
        if not re.search(r"NPV|net present value|IRR", flat, re.I):
            continue
        print("\n#### %s %s %s | %s" % (tk, day, eid[:12], (hl or "")[:90]))
        shown = 0
        for nd in needles:
            for m in re.finditer(re.escape(nd), flat):
                s = flat[max(0, m.start() - 170):m.end() + 110].replace("\n", " / ")
                print("  [%s] ...%s..." % (nd, s))
                shown += 1
                if shown >= 3:
                    break
            if shown >= 3:
                break
print("DIAG_DONE")
