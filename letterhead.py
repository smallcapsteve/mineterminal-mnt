"""LETTERHEAD_V1 / V1b (2026-10-07) - a company's own letterhead, learned from its releases.

H25: many issuers print the same lines above every headline - a tagline ("Advancing precious metal assets in British
Columbia"), a contact block ("Contact: George Sookochoff, President & CEO"), an office address, a law firm's name, a
share count. The document-headline reader (backfill_titles.headline_from_body) knows the generic shapes, but each company
has its own, and when one was read as the headline every release from that company looked like every other one, so the
exchange backfill settled hundreds of different releases as "already on MNT" (one event standing for up to 7 releases).

A line that opens at least MIN_RELEASES of a company's stored releases (and at least SHARE of them) is that company's
letterhead. strip() removes such lines from the top of a document before the headline is read; nothing else changes.
Read-only on the database; fails open (no letterhead) on any error.

    python3 letterhead.py --selftest
    python3 letterhead.py --show GMX           (the lines learned for one company)
"""
from __future__ import annotations

import collections
import re
import sqlite3
import sys

PORTAL_DB = "/opt/mnt/app/portal/portal.db"
SCAN_LINES = 15          # how far down a document letterhead can sit
MIN_RELEASES = 3         # distinct releases a line must open
SHARE = 0.08             # ... and at least this share of the company's releases
MAX_RELEASES = 400       # newest releases looked at per company
# a share count after its label: "Shares Issued and Outstanding: 81,851,494" (the count changes, so it is never learned)
_SHARE_LABEL = re.compile(r"(?i)^\s*(?:common\s+)?shares?\s+(?:issued\s*(?:and|&)\s*)?outstanding\s*:?\s*[\d,.]+\s*$")

# LETTERHEAD_V1b (2026-10-07): a line that reads like news is a recurring headline ("Kinross declares quarterly
# dividend", "Grants Stock Options", "Share Capital and Voting Rights Update"), never letterhead
NEWSY = re.compile(r"(?i)\b(announc(e|es|ed|ing)\b|declar|grant|report|clos(e|es|ed|ing)\b|complet|appoint|issu(e|es|ed|ance)\b|renew|"
                   r"financ|acqui|commenc|receiv|launch|provid|intersect|discover|extend|expand|propos|amend|"
                   r"consolidat|exercis|drill|updat|result)\w*"
                   r"|\b(dividends?|placements?|options?|agm|meetings?|share capital|voting rights|production|"
                   r"discussion and analysis|financial statements|normal course|warrants?|extensions?|signs?|enters?)\b")

_cache: dict[str, frozenset] = {}


def key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _prep(l: str) -> str:
    try:
        from backfill_titles import _prep_line
        return _prep_line(l)
    except Exception:            # noqa: BLE001
        return (l or "").strip()


def learn(bodies) -> frozenset:
    """bodies: the company's stored release texts. -> the normalised lines that are its letterhead."""
    cnt, n = collections.Counter(), 0
    for body in bodies:
        if not body:
            continue
        n += 1
        seen, k = set(), 0
        for raw in body.split("\n"):
            l = _prep(raw)
            if not l:
                continue
            k += 1
            if k > SCAN_LINES:
                break
            t = key(l)
            if len(t) >= 6 and not NEWSY.search(l):     # LETTERHEAD_V1b
                seen.add(t)
        cnt.update(seen)
    if n < MIN_RELEASES:
        return frozenset()
    return frozenset(t for t, c in cnt.items() if c >= MIN_RELEASES and c >= SHARE * n)


def for_company(bare: str, pcon: sqlite3.Connection | None = None) -> frozenset:
    bare = (bare or "").upper().split(".")[0]
    if not bare:
        return frozenset()
    if bare in _cache:
        return _cache[bare]
    lh = frozenset()
    try:
        c = pcon or sqlite3.connect(f"file:{PORTAL_DB}?mode=ro", uri=True, timeout=30)
        rows = c.execute(
            "SELECT raw_body FROM events WHERE (ticker = ? OR ticker LIKE ?) AND raw_body IS NOT NULL "
            "AND review_status IN ('auto_approved', 'duplicate_of_wire') ORDER BY published_at DESC LIMIT ?",
            (bare, bare + ".%", MAX_RELEASES)).fetchall()
        lh = learn(r[0] for r in rows)
        if pcon is None:
            c.close()
    except Exception:            # noqa: BLE001  fail open: no letterhead
        lh = frozenset()
    _cache[bare] = lh
    return lh


def strip(body: str, lh) -> str:
    """The document with the company's letterhead lines (and labelled share counts) removed from its top."""
    if not body:
        return body
    out, k = [], 0
    for raw in body.split("\n"):
        l = _prep(raw)
        if l:
            k += 1
            if k <= SCAN_LINES and ((lh and key(l) in lh) or _SHARE_LABEL.match(l)):
                continue
        out.append(raw)
    return "\n".join(out)


def self_test() -> int:
    fails = []
    def ok(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)
    rel = lambda h: "XIMEN GOLD CORP.\nAdvancing precious metal assets in British Columbia\n%s\nVancouver, BC, May 1, 2026 - Ximen ..." % h
    lh = learn([rel("Ximen Drills 10 m of 5 g/t Au"), rel("Ximen Closes Private Placement"), rel("Ximen Appoints CFO"),
                rel("Ximen Grants Options"), "Other format\nNo letterhead here\nbody"])
    ok("tagline learned", key("Advancing precious metal assets in British Columbia") in lh)
    ok("company name learned", key("XIMEN GOLD CORP.") in lh)
    ok("headlines not learned", key("Ximen Closes Private Placement") not in lh)
    dv = lambda h: "KINROSS GOLD CORPORATION\n%s\nToronto, Ontario - Kinross ..." % h
    lk = learn([dv("Kinross declares quarterly dividend")] * 6 + [dv("Kinross reports Q%d results" % i) for i in range(4)])
    ok("V1b: a recurring headline is not letterhead", key("Kinross declares quarterly dividend") not in lk and key("KINROSS GOLD CORPORATION") in lk)
    s = strip(rel("Ximen Reports Results"), lh)
    ok("strip keeps the headline first", s.split("\n")[0] == "Ximen Reports Results")
    ok("labelled share count stripped", strip("Shares Issued and Outstanding: 81,851,494\nMirasol Announces X", frozenset()).split("\n")[0] == "Mirasol Announces X")
    ok("too few releases: nothing learned", learn([rel("a"), rel("b")]) == frozenset())
    ok("body below the top is untouched", strip("A\n" * 20 + "Advancing precious metal assets in British Columbia", lh).endswith("British Columbia"))
    try:
        import backfill_titles as T
        h = T.headline_from_body(strip(rel("Ximen Intersects 12.4 g/t Gold over 3 m at Brett"), lh), "")
        ok("reader takes the real headline once the letterhead is gone: %r" % h[:50], h.startswith("Ximen Intersects"))
    except ImportError:
        print("skip reader test (backfill_titles not importable here)")
    print("letterhead selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.path.insert(0, "/opt/mnt/app")
        sys.exit(self_test())
    if "--show" in sys.argv:
        sys.path.insert(0, "/opt/mnt/app")
        b = sys.argv[sys.argv.index("--show") + 1]
        for t in sorted(for_company(b)):
            print(t)
