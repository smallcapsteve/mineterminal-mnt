"""financing_backfill.py — create schema + extract + match across all events.

Pass 1: extract per-event fields, write financing_events rows.
Pass 2: group events into financing lifecycles (announcement -> closes).
Pass 3: aggregate into financings table.

Match heuristic for grouping:
  - Announcements seed new financing rows (ticker, announcement_date,
    extracted fields).
  - For each non-announcement event with a ref_date, find an announcement
    on the same ticker within ±5 days of any ref_date — attach to that.
  - For non-announcement events without ref_dates, attach to the most
    recent prior announcement on same ticker within 180 days, IF roles
    are compatible AND gross/unit_price are similar (or missing).
  - Orphans (no announcement match) become standalone financing rows.
"""
import sys, sqlite3
from datetime import datetime

sys.path.insert(0, "/opt/mnt/app")
sys.path.insert(0, "/opt/mnt/app/portal")

from financing_extract import extract  # type: ignore

DB = "/opt/mnt/app/portal/portal.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS financings (
    financing_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker            TEXT NOT NULL,
    announced_at      TEXT,
    last_update_at    TEXT,
    kind              TEXT,
    status            TEXT,             -- announced|upsized|tranche_closed|closed|terminated|amended
    gross_announced   REAL,
    gross_closed      REAL,
    unit_price        REAL,
    unit_comp         TEXT,
    warrant_strike    REAL,
    warrant_term_months INTEGER,
    unit_count        INTEGER,
    n_tranches        INTEGER DEFAULT 0,
    n_events          INTEGER DEFAULT 0,
    seed_event_id     TEXT
);
CREATE INDEX IF NOT EXISTS ix_financings_ticker ON financings(ticker);
CREATE INDEX IF NOT EXISTS ix_financings_status ON financings(status);
CREATE INDEX IF NOT EXISTS ix_financings_announced_at ON financings(announced_at);

CREATE TABLE IF NOT EXISTS financing_events (
    event_id          TEXT PRIMARY KEY,
    financing_id      INTEGER,
    ticker            TEXT NOT NULL,
    role              TEXT,             -- announcement|upsize|tranche_close|final_close|amendment|terminated|mention
    tranche_label     TEXT,
    kind              TEXT,
    gross_total       REAL,
    unit_count        INTEGER,
    unit_price        REAL,
    unit_comp         TEXT,
    warrant_strike    REAL,
    warrant_term_months INTEGER,
    ref_dates         TEXT,             -- pipe-delimited
    event_date        TEXT,             -- copied from events.published_at for fast joins
    raw_headline      TEXT,
    FOREIGN KEY (financing_id) REFERENCES financings(financing_id)
);
CREATE INDEX IF NOT EXISTS ix_finev_ticker ON financing_events(ticker);
CREATE INDEX IF NOT EXISTS ix_finev_event_date ON financing_events(event_date);
CREATE INDEX IF NOT EXISTS ix_finev_role ON financing_events(role);
"""


BF_FLAGS = dict(
    mention_gate=True,   # B1 a number-less or non-financing 'mention' is not a financing row
    dedupe=True,         # B2 wire + exchange copies of one release are one lifecycle / one close
    closed_guard=True,   # B3 a later close with a different amount does not join a lifecycle already closed
    currency=True,       # B4 carry USD/AUD/... next to the amount
    kind_guard=True,     # B5 a loan/bond/stream never joins an equity placement's lifecycle
    rel_price=True,      # B6 "same price" is relative: $0.04 and $0.045 are different deals
    continuation=True,   # B7 a prospectus filing / "previously announced" is not a new deal
)

_DEBT_TOKENS = {"DEBT", "STREAM"}


def _kind_family(kind):
    """'debt' (loan, bond, stream), 'equity' (placements, offerings), or None when
    mixed, convertible or unknown -- None is compatible with anything."""
    toks = {t for t in (kind or "").split("+") if t}
    if not toks or "CD" in toks:
        return None
    if toks <= _DEBT_TOKENS:
        return "debt"
    if not (toks & _DEBT_TOKENS):
        return "equity"
    return None


_DEBT_WORDS = __import__("re").compile(
    r"(?i)\b(?:notes?|debentures?|loans?|bonds?|credit|facility|convertible|prepayment|stream)\b")


def _kinds_compatible(a, b, event_headline=None):
    """a: the lifecycle's kind, b: the joining event's kind. An event the
    extractor labelled as equity may still join a debt lifecycle when its own
    headline is about the debt ("Completes Upsized $115 Million Offering of
    Senior Notes" was read as PP)."""
    fa, fb = _kind_family(a), _kind_family(b)
    if fa is None or fb is None or fa == fb:
        return True
    return fa == "debt" and fb == "equity" and bool(_DEBT_WORDS.search(event_headline or ""))


def _same_price(p, q, rel=0.02):
    if not p or not q:
        return False
    return abs(p - q) <= max(0.0005, rel * max(p, q))


import re as _re_cont
# An announcement that continues an earlier one rather than starting a deal:
# "Files Final Short Form Prospectus in Connection with a Bought Deal",
# "Increases Previously Announced Bought Deal Financing", "Amended Terms".
_CONTINUES = _re_cont.compile(
    r"(?i)\b(?:previously[\s\-]+announced|(?:final|preliminary|amended)\s+(?:base\s+shelf\s+)?"
    r"(?:short[\s\-]+form\s+)?prospectus|prospectus\s+supplement|files?\s+(?:a\s+|the\s+)?"
    r"(?:preliminary|final|amended)|amend(?:s|ed|ment)\s+(?:to\s+)?(?:the\s+)?(?:terms|private|offering|financing)|"
    r"increas(?:es|ed|e)\s+(?:the\s+)?(?:size\s+of\s+)?(?:its\s+)?(?:previously|private|bought|offering|financing|non)|"
    r"upsiz\w*|pricing\s+of|update\s+on\s+(?:its\s+)?(?:previously|private|financing|offering))")


def init_schema(con):
    con.executescript(SCHEMA)
    # unit_count was extracted into financing_events from the start but never
    # had a home here, so the number sat one table away while the financing
    # rendered as empty.
    cols = {r[1] for r in con.execute("PRAGMA table_info(financings)")}
    if "unit_count" not in cols:
        con.execute("ALTER TABLE financings ADD COLUMN unit_count INTEGER")
    # 2026-09-15: nullable additions only -- old readers are unaffected.
    if "currency" not in cols:
        con.execute("ALTER TABLE financings ADD COLUMN currency TEXT")
    ecols = {r[1] for r in con.execute("PRAGMA table_info(financing_events)")}
    if "currency" not in ecols:
        con.execute("ALTER TABLE financing_events ADD COLUMN currency TEXT")
    if "is_deal" not in ecols:
        con.execute("ALTER TABLE financing_events ADD COLUMN is_deal INTEGER")
    con.commit()


def run_pass1(con):
    """Extract per-event into financing_events. Idempotent: re-runs replace existing rows."""
    rows = list(con.execute(
        "SELECT event_id, ticker, raw_headline, raw_body, published_at "
        "FROM events WHERE categories LIKE ? AND review_status='auto_approved'",
        ("%Financings%",),
    ))
    print(f"[pass1] processing {len(rows)} financing events")
    inserted = 0
    out = []
    for r in rows:
        ev = dict(r)
        try:
            x = extract(ev)
        except Exception as e:
            print(f"  extract error {ev['event_id']}: {e}", file=sys.stderr)
            continue
        ref_str = "|".join(x.get("ref_dates") or [])
        out.append(
            (
                ev["event_id"], ev["ticker"], x.get("role"),
                x.get("tranche_label"), x.get("kind"),
                x.get("gross_total"), x.get("unit_count"),
                x.get("unit_price"), x.get("unit_comp"),
                x.get("warrant_strike"), x.get("warrant_term_months"),
                ref_str, (ev.get("published_at") or "")[:10],
                (ev.get("raw_headline") or "")[:500],
                x.get("currency") if BF_FLAGS["currency"] else None,
                x.get("is_deal"),
            ),
        )
        inserted += 1
    # Extract first, then replace the rows. No commit here: pass 2 continues the
    # same transaction and commits once, so the portal (WAL readers) keeps the
    # previous financings until the rebuild is complete, and a failure anywhere
    # leaves both tables untouched. The old order committed an empty table twice.
    con.execute("DELETE FROM financing_events")
    con.executemany(
        "INSERT INTO financing_events("
        " event_id, financing_id, ticker, role, tranche_label, kind,"
        " gross_total, unit_count, unit_price, unit_comp,"
        " warrant_strike, warrant_term_months, ref_dates,"
        " event_date, raw_headline, currency, is_deal"
        ") VALUES (?,NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        out,
    )
    print(f"[pass1] inserted {inserted} financing_events")


_STATUS_OF = {
    "upsize": "upsized",
    "tranche_close": "tranche_closed",
    "final_close": "closed",
    "amendment": "amended",
    "terminated": "terminated",
}


def _norm_head(h):
    import re as _re
    h = (h or "").lower()
    h = _re.sub(r"\(amended\)|/?not for (?:distribution|dissemination).*$|news release\s*-?", " ", h)
    return _re.sub(r"[^a-z0-9]", "", h)[:70]


def _days(a, b):
    try:
        return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days
    except (ValueError, TypeError):
        return None


def _same_amount(x, y):
    return bool(x and y and abs(x - y) <= 0.005 * max(x, y))


def run_pass2_group(con):
    """Group financing_events into financings lifecycles."""
    con.execute("DELETE FROM financings")
    con.execute("UPDATE financing_events SET financing_id=NULL")
    ecols = {r[1] for r in con.execute("PRAGMA table_info(financing_events)")}
    has_cur = BF_FLAGS["currency"] and "currency" in ecols

    def g(row, k):
        return row[k] if k in row.keys() else None

    # Pull announcements first, then attach others
    rows_a = list(con.execute(
        "SELECT * FROM financing_events WHERE role='announcement' ORDER BY ticker, event_date"
    ))
    rows_o = list(con.execute(
        "SELECT * FROM financing_events WHERE role!='announcement' ORDER BY ticker, event_date"
    ))
    print(f"[pass2] {len(rows_a)} announcements, {len(rows_o)} non-announcement events")

    cur = con.cursor()
    ann_ids = {}      # ticker -> [candidate dicts] (announcement-seeded lifecycles)
    life = {}         # financing_id -> state used by the dedupe / closed guards
    orphan_rows = {}  # ticker -> [state] for orphan close rows (dedupe only)
    n_dup_ann = n_dup_close = n_guard = n_gated = 0

    n_cont = 0
    for a in rows_a:
        if BF_FLAGS["continuation"]:
            cont = None
            for c in reversed(ann_ids.get(a["ticker"], [])):
                dd = _days(c["event_date"], a["event_date"])
                if dd is None or dd < 0 or dd > 45:
                    continue
                if BF_FLAGS["kind_guard"] and not _kinds_compatible(c["kind"], a["kind"], a["raw_headline"]):
                    continue
                if _CONTINUES.search(a["raw_headline"] or "") or (
                        dd <= 30 and c["kind"] == a["kind"] and _same_price(c["unit_price"], a["unit_price"], 0.01)):
                    cont = c
                    break
            if cont:
                cur.execute("UPDATE financing_events SET financing_id=? WHERE event_id=?",
                            (cont["financing_id"], a["event_id"]))
                cur.execute("UPDATE financings SET n_events = n_events + 1, last_update_at = ?,"
                            " unit_count = COALESCE(unit_count, ?),"
                            " unit_price = COALESCE(unit_price, ?),"
                            " gross_announced = CASE WHEN ? IS NULL THEN gross_announced"
                            "   WHEN gross_announced IS NULL OR ? > gross_announced THEN ? ELSE gross_announced END"
                            " WHERE financing_id=?",
                            (a["event_date"], a["unit_count"], a["unit_price"], a["gross_total"], a["gross_total"],
                             a["gross_total"], cont["financing_id"]))
                cont["gross"] = max(cont["gross"] or 0, a["gross_total"] or 0) or None
                cont["unit_price"] = cont["unit_price"] or a["unit_price"]
                n_cont += 1
                continue
        if BF_FLAGS["dedupe"]:
            dup = None
            for c in ann_ids.get(a["ticker"], []):
                dd = _days(c["event_date"], a["event_date"])
                if dd is None or abs(dd) > 3:
                    continue
                if ((len(c["head"]) >= 15 and c["head"] == _norm_head(a["raw_headline"]))
                        or (_same_amount(c["gross"], a["gross_total"])
                            and (c["unit_price"] == a["unit_price"]))):
                    dup = c
                    break
            if dup:
                cur.execute("UPDATE financing_events SET financing_id=? WHERE event_id=?",
                            (dup["financing_id"], a["event_id"]))
                cur.execute("UPDATE financings SET n_events = n_events + 1,"
                            " unit_count = COALESCE(unit_count, ?),"
                            " unit_price = COALESCE(unit_price, ?),"
                            " gross_announced = COALESCE(gross_announced, ?)"
                            " WHERE financing_id=?",
                            (a["unit_count"], a["unit_price"], a["gross_total"], dup["financing_id"]))
                dup["gross"] = dup["gross"] or a["gross_total"]
                dup["unit_price"] = dup["unit_price"] or a["unit_price"]
                n_dup_ann += 1
                continue
        cur.execute(
            "INSERT INTO financings("
            " ticker, announced_at, last_update_at, kind, status,"
            " gross_announced, unit_price, unit_comp, warrant_strike,"
            " warrant_term_months, unit_count, n_events, seed_event_id"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                a["ticker"], a["event_date"], a["event_date"], a["kind"],
                "announced",
                a["gross_total"], a["unit_price"], a["unit_comp"],
                a["warrant_strike"], a["warrant_term_months"], a["unit_count"], 1,
                a["event_id"],
            ),
        )
        fid = cur.lastrowid
        if has_cur and g(a, "currency"):
            cur.execute("UPDATE financings SET currency=? WHERE financing_id=?", (a["currency"], fid))
        cur.execute("UPDATE financing_events SET financing_id=? WHERE event_id=?",
                    (fid, a["event_id"]))
        c = {
            "financing_id": fid,
            "event_date": a["event_date"],
            "gross": a["gross_total"],
            "unit_price": a["unit_price"],
            "head": _norm_head(a["raw_headline"]),
            "kind": a["kind"],
        }
        ann_ids.setdefault(a["ticker"], []).append(c)
        life[fid] = {"closes": [], "final": False, "changed_terms": False}

    def _different_deal_after_close(state, c, o):
        if not state["final"] or dup_close_of(state, o):
            return False
        last = max((x[0] for x in state["closes"]), default=None)
        gap = _days(last, o["event_date"]) if last else None
        if gap is not None and gap > 60:
            return True
        prices = [x[3] for x in state["closes"] if x[3]] + ([c["unit_price"]] if c["unit_price"] else [])
        if o["unit_price"] and prices:
            if all(abs(o["unit_price"] - p) > max(0.005, 0.10 * p) for p in prices):
                return True
        return False

    def dup_close_of(state, o):
        """An earlier close in this lifecycle that is a copy of this one: the same
        (informative) headline within 7 days, or the same money at the same price
        and tranche within 7 days. Two tranches often both quote the offering's
        total size, so the amount alone is not enough."""
        h = _norm_head(o["raw_headline"])
        for (d, gross, head, price, label) in state["closes"]:
            dd = _days(d, o["event_date"])
            if dd is None or abs(dd) > 14:
                continue
            if len(h) >= 15 and head == h and abs(dd) <= 7:
                return True
            if (abs(dd) <= 7 and _same_amount(gross, o["gross_total"])
                    and (not price or not o["unit_price"] or abs(price - o["unit_price"]) < 0.0005)
                    and label == o["tranche_label"]):
                return True
        return False

    matched = orphan = 0
    for o in rows_o:
        is_close = o["role"] in ("tranche_close", "final_close")
        candidates = ann_ids.get(o["ticker"], [])
        if BF_FLAGS["closed_guard"] and o["role"] == "final_close":
            # A lifecycle that already has its final close does not take a later
            # close for a DIFFERENT deal: another price, or two months on.
            candidates = [c for c in candidates
                          if not _different_deal_after_close(life[c["financing_id"]], c, o)]
            n_guard += len(ann_ids.get(o["ticker"], [])) - len(candidates) and 1 or 0
        if BF_FLAGS["kind_guard"]:
            candidates = [c for c in candidates if _kinds_compatible(c["kind"], o["kind"], o["raw_headline"])]
        chosen = None
        # 1) ref-date match
        ref_dates = (o["ref_dates"] or "").split("|") if o["ref_dates"] else []
        if ref_dates and candidates:
            for ref in ref_dates:
                for c in candidates:
                    if not c["event_date"] or not ref:
                        continue
                    try:
                        d_ref = datetime.strptime(ref, "%Y-%m-%d")
                        d_ann = datetime.strptime(c["event_date"], "%Y-%m-%d")
                        if abs((d_ref - d_ann).days) <= 5:
                            chosen = c
                            break
                    except ValueError:
                        continue
                if chosen:
                    break
        # 2) Recency + amount match
        if not chosen and candidates:
            try:
                d_ev = datetime.strptime(o["event_date"], "%Y-%m-%d")
            except (ValueError, TypeError):
                d_ev = None
            if d_ev:
                best = None
                for c in candidates:
                    try:
                        d_a = datetime.strptime(c["event_date"], "%Y-%m-%d")
                    except (ValueError, TypeError):
                        continue
                    delta = (d_ev - d_a).days
                    if delta < 0 or delta > 180:
                        continue
                    # gross / unit_price compat
                    score = 0
                    if o["gross_total"] and c["gross"]:
                        ratio = abs(o["gross_total"] - c["gross"]) / max(c["gross"], 1)
                        if ratio < 0.5:
                            score += 2
                    if o["unit_price"] and c["unit_price"]:
                        if (_same_price(o["unit_price"], c["unit_price"]) if BF_FLAGS["rel_price"]
                                else abs(o["unit_price"] - c["unit_price"]) < 0.01):
                            score += 2
                    # Always prefer most recent
                    score += max(0, 10 - delta // 30)
                    if best is None or score > best[1]:
                        best = (c, score)
                if best:
                    chosen = best[0]

        if chosen:
            fid = chosen["financing_id"]
            st = life[fid]
            duplicate = BF_FLAGS["dedupe"] and is_close and dup_close_of(st, o)
            cur.execute("UPDATE financing_events SET financing_id=? WHERE event_id=?",
                        (fid, o["event_id"]))
            # update lifecycle row
            new_status = _STATUS_OF.get(o["role"], None)
            if BF_FLAGS["closed_guard"] and st["final"] and o["role"] == "tranche_close":
                new_status = None   # a late tranche copy does not re-open a closed deal
            patch = ["last_update_at=?", "n_events = n_events + 1"]
            args = [o["event_date"]]
            if o["unit_count"]:
                patch.append("unit_count = COALESCE(unit_count, ?)")
                args.append(o["unit_count"])
            if new_status:
                patch.append("status=?")
                args.append(new_status)
            if is_close and not duplicate:
                patch.append("n_tranches = n_tranches + 1")
                if o["gross_total"]:
                    patch.append("gross_closed = COALESCE(gross_closed, 0) + ?")
                    args.append(o["gross_total"])
            if o["role"] == "upsize" and o["gross_total"]:
                patch.append("gross_announced = ?")
                args.append(o["gross_total"])
            if o["role"] == "upsize" and o["kind"]:
                patch.append("kind = ?")
                args.append(o["kind"])
            if has_cur and g(o, "currency"):
                patch.append("currency = COALESCE(currency, ?)")
                args.append(o["currency"])
            args.append(fid)
            cur.execute(
                f"UPDATE financings SET {', '.join(patch)} WHERE financing_id=?",
                args,
            )
            if is_close:
                st["closes"].append((o["event_date"], o["gross_total"], _norm_head(o["raw_headline"]), o["unit_price"], o["tranche_label"]))
                if o["role"] == "final_close":
                    st["final"] = True
                n_dup_close += bool(duplicate)
            matched += 1
        else:
            if BF_FLAGS["mention_gate"] and o["role"] == "mention":
                has_number = any(o[k] for k in ("gross_total", "unit_price", "unit_count", "warrant_strike"))
                # is_deal is None when an older extractor wrote the row: gate on numbers only
                if not has_number or g(o, "is_deal") == 0:
                    n_gated += 1
                    continue          # stays in financing_events with financing_id NULL
            if BF_FLAGS["dedupe"] and is_close:
                prev = None
                for s in orphan_rows.get(o["ticker"], []):
                    if dup_close_of(s, o):
                        prev = s
                        break
                if prev:
                    cur.execute("UPDATE financing_events SET financing_id=? WHERE event_id=?",
                                (prev["financing_id"], o["event_id"]))
                    cur.execute("UPDATE financings SET n_events = n_events + 1,"
                                " unit_count = COALESCE(unit_count, ?) WHERE financing_id=?",
                                (o["unit_count"], prev["financing_id"]))
                    prev["closes"].append((o["event_date"], o["gross_total"], _norm_head(o["raw_headline"]), o["unit_price"], o["tranche_label"]))
                    n_dup_close += 1
                    matched += 1
                    continue
            # Orphan: create standalone financing row
            new_status = _STATUS_OF.get(o["role"], "mention")
            cur.execute(
                "INSERT INTO financings("
                " ticker, announced_at, last_update_at, kind, status,"
                " gross_announced, gross_closed, unit_price, unit_comp, warrant_strike,"
                " warrant_term_months, unit_count, n_tranches, n_events, seed_event_id"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    o["ticker"], o["event_date"], o["event_date"], o["kind"],
                    new_status,
                    # An orphan that is not a close still knows the size of the
                    # deal it is describing. Storing it only for 'upsize' threw
                    # away 94 real amounts, including a $295M termination.
                    None if is_close else o["gross_total"],
                    o["gross_total"] if is_close else None,
                    o["unit_price"], o["unit_comp"],
                    o["warrant_strike"], o["warrant_term_months"],
                    o["unit_count"],
                    1 if is_close else 0,
                    1, o["event_id"],
                ),
            )
            fid = cur.lastrowid
            if has_cur and g(o, "currency"):
                cur.execute("UPDATE financings SET currency=? WHERE financing_id=?", (o["currency"], fid))
            cur.execute("UPDATE financing_events SET financing_id=? WHERE event_id=?",
                        (fid, o["event_id"]))
            if is_close:
                orphan_rows.setdefault(o["ticker"], []).append(
                    {"financing_id": fid,
                     "closes": [(o["event_date"], o["gross_total"], _norm_head(o["raw_headline"]), o["unit_price"], o["tranche_label"])]})
            orphan += 1
    con.commit()
    print(f"[pass2] matched={matched} orphan={orphan} dup_announcements={n_dup_ann} "
          f"dup_closes={n_dup_close} mentions_not_promoted={n_gated} continuations={n_cont}")


def report(con):
    print()
    print("=== FINANCINGS SUMMARY ===")
    n = con.execute("SELECT COUNT(*) FROM financings").fetchone()[0]
    print(f"financings rows: {n}")
    print("by status:")
    for r in con.execute(
        "SELECT status, COUNT(*) FROM financings GROUP BY status ORDER BY 2 DESC"
    ):
        print(f"  {r[0]:<20s} {r[1]}")
    print("\nby kind:")
    for r in con.execute(
        "SELECT kind, COUNT(*) FROM financings GROUP BY kind ORDER BY 2 DESC LIMIT 10"
    ):
        print(f"  {r[0]:<25s} {r[1]}")
    print("\ntop 5 most-recently-updated:")
    for r in con.execute(
        "SELECT ticker, status, gross_announced, gross_closed, unit_price, "
        " unit_comp, warrant_strike, warrant_term_months, last_update_at "
        "FROM financings ORDER BY last_update_at DESC LIMIT 5"
    ):
        print(" ", dict(r) if hasattr(r, "keys") else r)


def main():
    con = sqlite3.connect(DB); con.execute("PRAGMA busy_timeout = 30000")
    con.row_factory = sqlite3.Row
    init_schema(con)
    run_pass1(con)
    run_pass2_group(con)
    report(con)
    con.close()


def self_test():
    """Pass 2 on a handful of real headlines, in memory."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    init_schema(con)
    rows = [
        # (event_id, ticker, role, tranche, gross, price, date, headline, is_deal)
        ("a1", "HRT", "announcement", None, 1150000, 0.04, "2026-03-04", "Heritage Mining Announces Non-Brokered Private Placement of Flow-Through Shares and Units", 1),
        ("a2", "HRT", "announcement", None, 1150000, 0.04, "2026-03-04", "Heritage Mining Announces Non-Brokered Private Placement of Flow-Through Shares and Units", 1),
        ("c1", "HRT", "tranche_close", "first", 665000, 0.04, "2026-03-17", "Heritage Mining Announce Closing of First Tranche of Non-Brokered Private Placement", 1),
        ("b1", "ASH", "final_close", None, 300000, 0.072, "2023-10-04", "ASHLEY CLOSES $300,000 PRIVATE PLACEMENT WITH INSTITUTIONAL INVESTOR", 1),
        ("b2", "ASH", "final_close", None, 300000, 0.072, "2023-10-04", "Press Release", 1),
        ("e1", "EXP", "announcement", None, 4000000, 0.45, "2021-02-25", "EXPLOITS ANNOUNCES $4 MILLION NON-BROKERED PRIVATE PLACEMENT", 1),
        ("e2", "EXP", "final_close", "final", 1850350, 0.49, "2021-03-30", "EXPLOITS CLOSES FINAL TRANCHE OF IT'S $4 MILLION PRIVATE PLACEMENT", 1),
        ("e3", "EXP", "final_close", None, 8000000, 0.60, "2021-05-14", "Exploits Discovery Announces Closing Of $8 Million Investment By Eric Sprott", 1),
        ("m1", "APP", "mention", None, None, None, "2026-05-01", "Austral Gold Files Q1 2026 Quarterly Activities Report", 0),
        ("m2", "CAS", "mention", None, 432777, None, "2026-05-01", "Casa Minerals Inc. Receives Proceeds of $432,777 from Warrant Exercises", 0),
        ("m3", "IRV", "mention", None, 2000000, 0.25, "2026-05-01", "Irving Resources Reports Non-Brokered Private Placement", 1),
    ]
    for r in rows:
        con.execute("INSERT INTO financing_events(event_id, ticker, role, tranche_label, gross_total, unit_price,"
                    " event_date, raw_headline, is_deal, kind) VALUES (?,?,?,?,?,?,?,?,?, 'PP')", r)
    # 2026-09-16 grouping pass: (event_id, ticker, role, gross, price, date, headline, kind)
    for r in [
        ("gk1", "ABI", "announcement", 3000000, 0.05, "2025-03-24", "Abcourt Announces a Non-Brokered Private Placement for up to $3.0 Million", "FT+NON_BROKERED"),
        ("gk2", "ABI", "final_close", 4613004, 0.05, "2025-05-06", "Abcourt Closes Private Placement", "FT+NON_BROKERED"),
        ("gk3", "ABI", "final_close", 8000000, None, "2025-07-03", "Abcourt Closes US$ 8M Loan Facility to Start Sleeping Giant Mine", "DEBT"),
        ("gp1", "AMQ", "announcement", 10000000, 0.35, "2025-11-25", "Announce C$10 Million Bought Deal Financing", "FT+BOUGHT_DEAL"),
        ("gp2", "AMQ", "announcement", 4000500, 0.57, "2025-12-09", "Abitibi Files Final Short Form Prospectus in Connection with a Bought Deal Public Offering", "FT+BOUGHT_DEAL"),
        ("gp3", "AMQ", "final_close", 16104600, 0.57, "2025-12-16", "Abitibi Metals Closes Bought Deal Public Offering", "FT+BOUGHT_DEAL"),
        ("gb1", "BGF", "announcement", None, 0.04, "2025-09-17", "Beauce Gold Fields: Non-Brokered Private Placement Offering", "NON_BROKERED"),
        ("gb2", "BGF", "announcement", 450000, 0.045, "2025-09-30", "Beauce Gold Fields to Proceed with a $450,000 Flow-Through Private Placement", "FT+NON_BROKERED"),
        ("gb3", "BGF", "final_close", 765304, 0.04, "2025-10-24", "Beauce Gold Fields Closing a Non-Brokered Private Placement", "NON_BROKERED"),
        ("gn1", "EU", "announcement", 75000000, None, "2025-08-19", "enCore Announces Proposed Offering of $75 Million of Convertible Senior Notes", "DEBT"),
        ("gn2", "EU", "final_close", 115000000, 2.58, "2025-08-22", "enCore Completes Upsized $115 Million Offering of Senior Notes", "PP"),
    ]:
        con.execute("INSERT INTO financing_events(event_id, ticker, role, gross_total, unit_price, event_date,"
                    " raw_headline, kind, is_deal) VALUES (?,?,?,?,?,?,?,?,1)", r)
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        run_pass2_group(con)
    fid = {r["event_id"]: r["financing_id"] for r in con.execute("SELECT event_id, financing_id FROM financing_events")}
    bad = 0
    checks = [
        ("wire copy of an announcement is one lifecycle", fid["a1"] == fid["a2"]),
        ("two copies of one close are one row", fid["b1"] == fid["b2"]),
        ("a later $8M deal at another price is not the closed $4M deal", fid["e3"] != fid["e1"]),
        ("the $4M close joins its announcement", fid["e2"] == fid["e1"]),
        ("number-less mention is not a financing", fid["m1"] is None),
        ("warrant-exercise mention is not a financing", fid["m2"] is None),
        ("a mention about a placement with figures is kept", fid["m3"] is not None),
    ]
    checks += [
        ("a loan close does not join an equity placement", fid["gk3"] != fid["gk1"] and fid["gk2"] == fid["gk1"]),
        ("a final prospectus filing continues its bought deal, and the close follows", fid["gp2"] == fid["gp1"] == fid["gp3"]),
        ("a $0.04 close joins the $0.04 placement, not the $0.045 one", fid["gb3"] == fid["gb1"] != fid["gb2"]),
        ("a senior-notes close labelled PP still joins its notes offering", fid["gn2"] == fid["gn1"]),
    ]
    g = con.execute("SELECT gross_closed, n_tranches FROM financings WHERE financing_id=?", (fid["b1"],)).fetchone()
    checks.append(("a duplicate close is not counted twice", g["gross_closed"] == 300000 and g["n_tranches"] == 1))
    for name, ok in checks:
        if not ok:
            bad += 1
            print("FAIL:", name)
    print(f"backfill self_test: {len(checks) - bad}/{len(checks)} passed")
    return bad


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(1 if self_test() else 0)
    main()
