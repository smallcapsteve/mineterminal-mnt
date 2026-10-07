"""Publish the Debt & Credit Facilities reader into the table /debt-credit reads (DEBT_PUBLISH_V1, 2026-09-24).

The facts store holds what DEBT_V1 (portal/extractors/debt.py) found in every approved release. The page reads
debt_deals, which this module rebuilds from the ACTIVE debt version.

One row per debt instrument an item reports (Justin, 2026-09-24): convertible debentures and notes, loans, credit
facilities, notes and bonds, gold loans and prepayments, at the instrument's stage as of the item: proposed, signed,
closed, drawn, amended, converted, repaid or terminated. The company is the borrower, or the lender where it lends or
buys debt (rule DL as Justin decided: "Row, marked 'company is lender'"); the page shows borrowing by default.
Financings keeps the money raised; this page adds the terms (Justin: "Show on both").

What goes on the page:
  1. every approved item in which the reader found a debt row, tagged Debt & Credit Facilities or not;
  2. a MARKER row (instrument NULL) for every tagged item that reports none, so 'show all' follows the tag;
  3. ONE DEBT, SEVERAL ITEMS: stages chain across releases (Justin: "One row per debt, chained"). Rows of the same
     company, side and instrument family (convertible / notes / loan and credit facility / gold loan and prepayment)
     within 1,825 days share a chain_key, keyed on the lender (or, for a lender row, the borrower) when one is named,
     else on the project, else on the family alone. A row joins a chain unless it names a different lender, the chain
     already ended (repaid or terminated), it is a new offering (proposed or signed) after the chain closed, drew,
     was amended or converted, or it closes again more than 270 days after the chain last closed or drew (a new
     offering, not another tranche). The newest item is the lead row (latest=1); its empty terms are filled from the
     chain, newest first. An amended lead keeps its own maturity blank rather than show the old one.
  4. A row with no stated event date takes the item's date.
  5. (2026-09-25, with reader 1.0.2) A PARTIAL repayment (purpose "Partial repayment") does not end the debt: the
     rest is still owed, so later stages join the same chain. NOTES chain by series: a notes row with a maturity year
     is keyed on it ("FM.TO:B:notes:due=2027"), so a company's 2027, 2029 and 2034 notes are three debts; a notes row
     without a year takes the series of the nearest offering (proposed, signed or closed) notes row of the same company
     within 45 days, the same amount first (an offering announced before its pricing names the year), and a repayment
     without a year the series of the nearest repayment. After a partial repayment the debt stays open for 730 days.

compute() is a pure function of the items so the accuracy gate can score what a candidate version would publish
without writing anything. publish() rebuilds the table in one short transaction.

Timer use (sync_structured.py): python3 -m portal.debt_publish
Self-tests: python3 -m portal.debt_publish --selftest     (in-memory; touches nothing live)
Dry run:    python3 -m portal.debt_publish --dry-run [--version X.Y.Z]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import date

from portal import project_names as PN

EXTRACTOR = "debt"
TAG = "Debt & Credit Facilities"
DB = "/opt/mnt/app/portal/portal.db"
TABLE = "debt_deals"

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS debt_deals (
    dd_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    ordinal           INTEGER NOT NULL DEFAULT 0,
    ticker            TEXT,
    slug              TEXT,
    instrument        TEXT,
    stage             TEXT,
    side              TEXT,
    principal         REAL,
    principal_total   REAL,
    currency          TEXT,
    rate_pct          REAL,
    rate_text         TEXT,
    maturity          TEXT,
    term_months       REAL,
    lender            TEXT,
    borrower          TEXT,
    related_party     INTEGER,
    secured           INTEGER,
    conversion_price  REAL,
    conversion_text   TEXT,
    warrants          REAL,
    warrant_strike    REAL,
    project           TEXT,
    purpose           TEXT,
    date              TEXT,
    filled_from       TEXT,
    chain_key         TEXT,
    chain_items       INTEGER NOT NULL DEFAULT 1,
    first_reported    TEXT,
    stage_rank        INTEGER,
    latest            INTEGER NOT NULL DEFAULT 1,
    n_rows            INTEGER NOT NULL DEFAULT 1,
    tag_confirmed     INTEGER NOT NULL DEFAULT 0,
    raw_headline      TEXT,
    published_at      TEXT,
    extractor_version TEXT
);
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_debt_deals_pub    ON debt_deals(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_debt_deals_ticker ON debt_deals(ticker);
CREATE INDEX IF NOT EXISTS idx_debt_deals_event  ON debt_deals(event_id);
CREATE INDEX IF NOT EXISTS idx_debt_deals_chain  ON debt_deals(chain_key);
"""

_ROW_FIELDS = ("instrument", "stage", "side", "principal", "principal_total", "currency", "rate_pct", "rate_text",
               "maturity", "term_months", "lender", "borrower", "related_party", "secured", "conversion_price",
               "conversion_text", "warrants", "warrant_strike", "project", "purpose", "date")
_COLS = ("event_id", "ordinal", "ticker", "slug") + _ROW_FIELDS + (
    "filled_from", "chain_key", "chain_items", "first_reported", "stage_rank", "latest", "n_rows", "tag_confirmed",
    "raw_headline", "published_at")
_FILLABLE = ("currency", "rate_pct", "rate_text", "maturity", "term_months", "lender", "borrower", "related_party",
             "secured", "conversion_price", "conversion_text", "warrants", "warrant_strike", "project", "purpose")
CHAIN_DAYS = 1825
RECLOSE_DAYS = 270
STAGE_RANK = {"interest_paid": 0, "proposed": 1, "signed": 2, "closed": 3, "drawn": 4, "amended": 4, "converted": 5, "repaid": 5,
              "terminated": 6}
FAMILY = {"convertible_debenture": "conv", "convertible_note": "conv", "notes": "notes", "loan": "loan",
          "credit_facility": "loan", "gold_loan": "metal", "prepayment": "metal", "other": "other"}
_CO_GENERIC = {"inc", "ltd", "corp", "corporation", "limited", "llc", "lp", "l", "p", "ag", "sa", "plc", "pte", "pty",
               "the", "and", "of", "co", "company", "fund", "funds", "capital", "partners", "group", "holdings",
               "investments", "management", "i", "ii", "iii", "resources", "mining", "bank"}

TYPE_LABELS = {"convertible_debenture": "Convertible debenture", "convertible_note": "Convertible note / loan",
               "loan": "Loan", "credit_facility": "Credit facility", "notes": "Notes / bonds",
               "gold_loan": "Gold loan", "prepayment": "Prepayment", "other": "Other debt"}
STAGE_LABELS = {"proposed": "Proposed", "signed": "Signed", "closed": "Closed / funded", "drawn": "Drawdown",
                "amended": "Amended", "converted": "Converted", "repaid": "Repaid / settled",
                "terminated": "Terminated", "interest_paid": "Interest paid"}
SIDE_LABELS = {"borrower": "Company borrowing", "lender": "Company lending"}


def _fold(s):
    s = unicodedata.normalize("NFKD", s or "").lower()
    return "".join(c for c in s if not unicodedata.combining(c))


def _key_words(s, generic):
    return [w for w in re.findall(r"[a-z0-9]+", _fold(s)) if w not in generic]


def _party(r):
    return r.get("borrower") if r.get("side") == "lender" else r.get("lender")


PARTIAL = "Partial repayment"
PARTIAL_OPEN_DAYS = 730
NOTES_ADOPT_DAYS = 45


def _year(m):
    m = re.match(r"((?:19|20)\d\d)", str(m or ""))
    return m.group(1) if m else None


def chain_key(r, ticker, uniq):
    fam = FAMILY.get(r.get("instrument"), "other")
    side = "L" if r.get("side") == "lender" else "B"
    if fam == "notes" and _year(r.get("maturity")):
        return "%s:%s:notes:due=%s" % (ticker or "?", side, _year(r.get("maturity")))
    c = _key_words(_party(r), _CO_GENERIC)
    if c:
        return "%s:%s:%s:cp=%s" % (ticker or "?", side, fam, " ".join(c[:2]))
    w = PN.key(r.get("project")).split()
    if w:
        return "%s:%s:%s:pj=%s" % (ticker or "?", side, fam, " ".join(w[:3]))
    return "%s:%s:%s" % (ticker or "?", side, fam)


def _days(a, b):
    try:
        return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)
    except (TypeError, ValueError):
        return 10 ** 6


def _cp_differ(a, b):
    if not a or not b:
        return False
    wa, wb = set(_key_words(a, _CO_GENERIC)), set(_key_words(b, _CO_GENERIC))
    return bool(wa and wb) and not (wa & wb)


def _marker(ev):
    row = {c: None for c in _COLS}
    row.update(event_id=ev["event_id"], ordinal=0, ticker=ev.get("ticker"), slug=ev.get("slug"), n_rows=0,
               chain_items=1, latest=1, tag_confirmed=1, raw_headline=(ev.get("raw_headline") or "")[:500],
               published_at=ev.get("published_at"))
    return row


def _joinable(group, row):
    last = group[-1]
    if any(g["event_id"] == row["event_id"] for g in group):
        return False
    if _days(last["published_at"], row["published_at"]) > CHAIN_DAYS:
        return False
    if any(_cp_differ(_party(g), _party(row)) for g in group):
        return False
    real = [g for g in group if g["stage"] != "interest_paid"] or [group[-1]]
    stages = [g["stage"] for g in real]
    if stages[-1] == "terminated" or stages[-1] == "repaid" and (real[-1].get("purpose") or "") != PARTIAL:
        return False                          # a repaid or terminated debt is over; the next one is new
    if stages[-1] == "repaid" and _days(real[-1]["published_at"], row["published_at"]) > PARTIAL_OPEN_DAYS:
        return False                          # a partial repayment keeps the debt open for two years, not five
    if row["stage"] in ("proposed", "signed") and set(stages) & {"closed", "drawn", "amended", "converted"}:
        return False                          # a new offering or agreement after the debt was funded
    funded = [g for g in group if g["stage"] in ("closed", "drawn")]
    if row["stage"] == "closed" and funded and _days(funded[-1]["published_at"], row["published_at"]) > RECLOSE_DAYS:
        return False                          # closing again long after: another offering, not another tranche
    return True


def compute(items):
    """items: iterable of (event, parsed); event = {event_id, ticker, published_at, raw_headline, slug, tagged};
    parsed = debt.parse_records() output. Returns (rows, stats)."""
    items = sorted(items, key=lambda x: ((x[0].get("published_at") or ""), x[0]["event_id"]))
    out = []
    st = {"items": 0, "published": 0, "rows": 0, "markers": 0, "tagged_published": 0, "untagged_published": 0,
          "chains": 0, "repeat_rows": 0, "filled": 0, "lender_rows": 0}
    for ev, p in items:
        st["items"] += 1
        rows = [dict(r) for r in (p.get("rows") or []) if r.get("instrument") and r.get("stage")]
        tagged = bool(ev.get("tagged"))
        if not rows:
            if tagged:
                out.append(_marker(ev))
                st["markers"] += 1
            continue
        st["published"] += 1
        st["tagged_published" if tagged else "untagged_published"] += 1
        for i, r in enumerate(rows):
            row = {c: None for c in _COLS}
            row.update({k: r.get(k) for k in _ROW_FIELDS if k in r})
            for b in ("related_party", "secured"):
                if row[b] is not None:
                    row[b] = 1 if row[b] else 0
            row["side"] = row["side"] or "borrower"
            if not row["date"]:
                row["date"] = (ev.get("published_at") or "")[:10] or None
            row.update(event_id=ev["event_id"], ordinal=i, ticker=ev.get("ticker"), slug=ev.get("slug"), n_rows=len(rows),
                       tag_confirmed=1 if tagged else 0, chain_items=1, latest=1, stage_rank=STAGE_RANK.get(row["stage"]),
                       chain_key=chain_key(row, ev.get("ticker"), "%s/%d" % (ev["event_id"][:12], i)),
                       first_reported=(ev.get("published_at") or "")[:10] or None,
                       raw_headline=(ev.get("raw_headline") or "")[:500], published_at=ev.get("published_at"))
            out.append(row)
            st["rows"] += 1
            st["lender_rows"] += row["side"] == "lender"
            st["stage_" + row["stage"]] = st.get("stage_" + row["stage"], 0) + 1
            st["type_" + row["instrument"]] = st.get("type_" + row["instrument"], 0) + 1
    # notes without a maturity year take the series of the nearest dated notes row of the company (same side)
    dated = [r for r in out if r["instrument"] and FAMILY.get(r["instrument"]) == "notes" and ":due=" in (r["chain_key"] or "")]
    for r in out:
        if not r["instrument"] or FAMILY.get(r["instrument"]) != "notes" or ":due=" in (r["chain_key"] or "") or \
                ":cp=" in (r["chain_key"] or ""):
            continue
        near = [(_days(d["published_at"], r["published_at"]), d["principal"] != r["principal"], d["chain_key"])
                for d in dated if d["ticker"] == r["ticker"] and d["side"] == r["side"] and d["event_id"] != r["event_id"]
                and (d["stage"] == "repaid" if r["stage"] == "repaid" else d["stage"] in ("proposed", "signed", "closed"))]
        near = [x for x in near if x[0] <= NOTES_ADOPT_DAYS]
        if near:
            r["chain_key"] = min(near)[2]
    chains = {}
    for row in out:
        k = row["chain_key"]
        if not k or row["instrument"] is None:
            continue
        groups = chains.setdefault(k, [])
        home = None
        for g in reversed(groups):
            if _joinable(g, row):
                home = g
                break
        if home is not None:
            home.append(row)
        else:
            groups.append([row])
    n = 0
    for k, groups in chains.items():
        for g in groups:
            n += 1
            gid = "%s#%d" % (k, n)
            first = min((r["published_at"] or "")[:10] for r in g) or None
            # an interest payment is a row on the chain but never the debt's latest stage (rule DI, 2026-09-24)
            li = max((j for j, r in enumerate(g) if r["stage"] != "interest_paid"), default=len(g) - 1)
            for j, r in enumerate(g):
                r.update(chain_key=gid, chain_items=len(g), first_reported=first, latest=1 if j == li else 0)
                st["repeat_rows"] += 0 if j == li else 1
            lead = g[li]
            src = []
            for other in reversed(g[:li]):
                if other["stage"] == "interest_paid":
                    continue                      # its amount and shares are the interest's, not the debt's
                for f in _FILLABLE:
                    if lead["stage"] == "amended" and f in ("maturity", "term_months", "rate_pct", "rate_text",
                                                            "conversion_price"):
                        continue                  # the amendment may have changed them; never show the old terms
                    if f == "purpose" and other.get(f) == PARTIAL:
                        continue                  # one repayment's note, not the debt's purpose
                    if lead.get(f) in (None, "") and other.get(f) not in (None, ""):
                        lead[f] = other[f]
                        src.append(other["event_id"][:12])
                        st["filled"] += 1
            lead["filled_from"] = ",".join(dict.fromkeys(src)) or None
    st["chains"] = n
    return out, st


# ------------------------------------------------------------------ reading the facts store
def _has_table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


def active_version(conn):
    if not _has_table(conn, "fx_extractor_versions"):
        return None
    r = conn.execute("SELECT version FROM fx_extractor_versions WHERE extractor=? AND status='active'",
                     (EXTRACTOR,)).fetchone()
    return r[0] if r else None


def load_items(conn, version):
    """(event, parsed) for every approved item this version found debt in, and every approved item carrying the tag
    today (those with none become marker rows)."""
    from portal.extractors import debt as X
    found = {r[0] for r in conn.execute(
        "SELECT DISTINCT r.event_id FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
        "WHERE r.extractor=? AND r.version=? AND f.field='is_debt' AND f.value_num=1",
        (EXTRACTOR, version))}
    evs = {}
    for eid, tk, pub, hl, slug, cats in conn.execute(
            "SELECT e.event_id, e.ticker, COALESCE(e.published_at, e.classified_at), e.raw_headline, e.slug, "
            "e.categories FROM events e JOIN fx_runs u ON u.event_id=e.event_id AND u.extractor=? "
            "AND u.version=? WHERE e.review_status='auto_approved'", (EXTRACTOR, version)):
        tagged = ("|" + (cats or "") + "|").find("|" + TAG + "|") >= 0
        if eid in found or tagged:
            evs[eid] = {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl, "slug": slug,
                        "tagged": tagged}
    facts = {}
    if found:
        for eid, ordinal, field_, seq, num, text in conn.execute(
                "SELECT r.event_id, r.ordinal, f.field, f.seq, f.value_num, f.value_text "
                "FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
                "WHERE r.extractor=? AND r.version=? AND r.event_id IN "
                "(SELECT r2.event_id FROM fx_records r2 JOIN fx_facts f2 ON f2.record_id=r2.record_id "
                " WHERE r2.extractor=? AND r2.version=? AND f2.field='is_debt' AND f2.value_num=1)",
                (EXTRACTOR, version, EXTRACTOR, version)):
            facts.setdefault(eid, {}).setdefault(ordinal, []).append((field_, seq, num, text))
    return [(evs[e], X.parse_records(facts.get(e, {}))) for e in evs]


def _ensure_schema(conn):
    conn.executescript(TABLE_SQL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(debt_deals)")}
    for line in TABLE_SQL.splitlines():
        m = re.match(r"\s+([a-z_]+)\s+(TEXT|REAL|INTEGER)", line)
        if m and m.group(1) not in have and m.group(1) != "dd_id":
            conn.execute("ALTER TABLE debt_deals ADD COLUMN %s %s" % (m.group(1), m.group(2)))
    conn.executescript(INDEX_SQL)


def publish(conn, version, log=print):
    if not re.match(r"^[0-9]+[.][0-9]+[.][0-9]+$", version or ""):
        raise ValueError("bad version %r" % (version,))
    t0 = time.time()
    rows, st = compute(load_items(conn, version))
    _ensure_schema(conn)
    # OPTD step A (2026-10-06): the same rowsync calls, run once before the write lock to work out the
    # differences; the locked pass below then only applies them (portal/rowsync.py, planning). Kill switch:
    # /opt/mnt/app/portal/rowsync_plan_OFF.
    from portal import rowsync as _rowsync_plan
    with _rowsync_plan.planning(conn):
        # OPSFIX item 1 (2026-10-05): write only the rows that changed; same table contents (portal/rowsync.py)
        from portal import rowsync
        st["rowsync"] = rowsync.sync_rows(conn, "debt_deals", "dd_id", _COLS, rows, {"extractor_version": version})
    conn.execute("BEGIN IMMEDIATE")
    try:
        # OPSFIX item 1 (2026-10-05): write only the rows that changed; same table contents (portal/rowsync.py)
        from portal import rowsync
        st["rowsync"] = rowsync.sync_rows(conn, "debt_deals", "dd_id", _COLS, rows, {"extractor_version": version})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[debt_publish] " + json.dumps(st))
    return st


# ------------------------------------------------------------------ self-tests
def _selftest():
    sys.path.insert(0, "/opt/mnt/app")
    from portal import facts as F
    from portal.extractors import debt as X
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))

    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE events (event_id TEXT PRIMARY KEY, ticker TEXT, published_at TEXT, "
                       "classified_at TEXT, raw_headline TEXT, raw_body TEXT, slug TEXT, categories TEXT, "
                       "review_status TEXT)")
    F.ensure_schema(conn)
    spec = F.ExtractorSpec(EXTRACTOR, "9.9.9", X.KIND, TAG, X.extract, "selftest")
    fill = " The Company is advancing its gold projects in Ontario and continues to review exploration targets." * 4
    lead = "Toronto, %s -- ABC Gold Corp. (TSXV: ABC) (\"ABC\" or the \"Company\") "
    evs = [
        ("e1", "ABC.V", "2026-03-02", "ABC Gold Signs US$20 Million Term Loan with Delta Capital",
         lead % "March 2, 2026" + "has entered into a binding loan agreement with Delta Capital LLC (\"Delta\") for a "
                                  "US$20 million secured term loan bearing interest at 11% per annum and maturing on "
                                  "December 31, 2029. Closing is expected later this month." + fill, TAG),
        ("e2", "ABC.V", "2026-04-15", "ABC Gold Closes Term Loan with Delta Capital",
         lead % "April 15, 2026" + "has closed its previously announced US$20 million term loan with Delta Capital LLC "
                                   "and has drawn the full amount." + fill, TAG),
        ("e3", "ABC.V", "2026-06-01", "ABC Gold Announces Drill Results at Alpha",
         lead % "June 1, 2026" + "reports drill results from the Alpha Project, including 12.3 g/t gold over 4.0 metres."
         + fill, TAG),
        ("e4", "XYZ.V", "2026-01-05", "XYZ Closes Private Placement",
         lead % "January 5, 2026" + "has closed a private placement of units." + fill, "Financings"),
    ]
    for eid, tk, pub, hl, body, cats in evs:
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?, 'auto_approved')",
                     (eid, tk, pub, None, hl, body, eid + "-slug", cats))
    F.run_batch(conn, spec, [dict(r) for r in conn.execute("SELECT * FROM events")])
    rows, st = compute(load_items(conn, "9.9.9"))
    by = {}
    for r in rows:
        by.setdefault(r["event_id"], []).append(r)
    eq("signed row", [(r["instrument"], r["stage"], r["latest"], r["principal"], r["currency"]) for r in by["e1"]],
       [("loan", "signed", 0, 20000000.0, "USD")])
    eq("closing is the lead, terms filled from the chain",
       [(r["stage"], r["latest"], r["chain_items"], r["first_reported"], r["rate_pct"], r["maturity"], r["lender"])
        for r in by["e2"]],
       [("closed", 1, 2, "2026-03-02", 11.0, "2029-12-31", "Delta Capital")])
    eq("same debt", by["e1"][0]["chain_key"] == by["e2"][0]["chain_key"], True)
    eq("marker for a tagged item with no debt", [(r["instrument"], r["n_rows"]) for r in by["e3"]], [(None, 0)])
    eq("untagged, nothing -> absent", by.get("e4"), None)
    # chain rules on synthetic rows
    E = lambda eid, pub: {"event_id": eid, "ticker": "Q.V", "published_at": pub, "raw_headline": "", "slug": "",
                          "tagged": True}
    R = lambda ins, stage, lender=None, side="borrower", **kw: {"rows": [dict({"instrument": ins, "stage": stage,
                                                                              "lender": lender, "side": side}, **kw)]}
    rs, _ = compute([(E("a", "2024-01-01"), R("convertible_debenture", "closed", principal=1e6)),
                     (E("b", "2024-02-01"), R("convertible_debenture", "closed", principal=5e5)),
                     (E("c", "2025-03-01"), R("convertible_debenture", "closed", principal=2e6)),
                     (E("d", "2025-06-01"), R("convertible_debenture", "proposed", principal=3e6))])
    ck = [r["chain_key"] for r in rs]
    eq("tranches chain; a closing a year on and a new offering do not",
       [ck[0] == ck[1], ck[1] == ck[2], ck[2] == ck[3]], [True, False, False])
    rs, _ = compute([(E("a", "2024-01-01"), R("loan", "closed", "Omega Bank")),
                     (E("b", "2024-05-01"), R("loan", "amended", "Omega Bank", maturity="2027-01-01")),
                     (E("c", "2024-09-01"), R("loan", "repaid", "Omega Bank")),
                     (E("d", "2024-10-01"), R("loan", "closed", "Omega Bank"))])
    ck = [r["chain_key"] for r in rs]
    eq("repaid ends the chain", [ck[0] == ck[1], ck[1] == ck[2], ck[2] == ck[3]], [True, True, False])
    rs, _ = compute([(E("a", "2024-01-01"), R("loan", "signed", "Omega Bank")),
                     (E("b", "2024-02-01"), R("credit_facility", "closed", "Sigma Credit Fund"))])
    eq("another lender is another debt", rs[0]["chain_key"] == rs[1]["chain_key"], False)
    rs, _ = compute([(E("a", "2024-01-01"), R("loan", "closed", None, side="lender", borrower="Target Co")),
                     (E("b", "2024-02-01"), R("loan", "closed", "Omega Bank"))])
    eq("lending never chains with borrowing", rs[0]["chain_key"] == rs[1]["chain_key"], False)
    rs, _ = compute([(E("a", "2024-01-01"), R("loan", "closed", "Omega Bank", maturity="2026-01-01", rate_pct=10.0)),
                     (E("b", "2024-06-01"), R("loan", "amended", "Omega Bank"))])
    eq("an amended lead keeps its maturity and rate blank", (rs[1]["maturity"], rs[1]["rate_pct"], rs[1]["lender"]),
       (None, None, "Omega Bank"))
    rs, _ = compute([(E("a", "2024-01-01"), R("convertible_debenture", "closed", principal=1e6, conversion_price=0.1)),
                     (E("b", "2024-12-31"), R("convertible_debenture", "interest_paid", principal=5e4,
                                              conversion_text="interest paid in 500,000 common shares")),
                     (E("c", "2025-06-01"), R("convertible_debenture", "converted", principal=2e5))])
    eq("interest paid chains but is never the latest stage, and fills nothing",
       ([r["chain_key"] == rs[0]["chain_key"] for r in rs], [r["latest"] for r in rs], rs[2]["conversion_text"],
        rs[2]["conversion_price"]), ([True, True, True], [0, 0, 1], None, 0.1))
    rs, _ = compute([(E("a", "2024-12-31"), R("convertible_debenture", "interest_paid", principal=5e4))])
    eq("an interest payment alone is its chain's latest row", rs[0]["latest"], 1)
    rs, _ = compute([(E("a", "2024-01-01"), R("convertible_debenture", "closed", "EBRD")),
                     (E("b", "2024-06-01"), R("convertible_debenture", "repaid", "EBRD", purpose=PARTIAL)),
                     (E("c", "2024-09-01"), R("convertible_debenture", "amended", "EBRD")),
                     (E("d", "2025-01-01"), R("convertible_debenture", "repaid", "EBRD"))])
    ck = [r["chain_key"] for r in rs]
    eq("a partial repayment does not end the debt; a full one does, and its purpose is not filled",
       ([ck[0] == c for c in ck], rs[3]["purpose"]), ([True, True, True, True], None))
    rs, _ = compute([(E("a", "2020-09-01"), R("notes", "closed", maturity="2027")),
                     (E("b", "2025-02-01"), R("notes", "proposed")),
                     (E("c", "2025-02-02"), R("notes", "signed", maturity="2033", rate_pct=8.0)),
                     (E("d", "2025-02-20"), R("notes", "closed", maturity="2033")),
                     (E("e", "2025-03-01"), R("notes", "repaid", maturity="2027", purpose=PARTIAL)),
                     (E("f", "2025-09-01"), R("notes", "repaid", maturity="2027"))])
    ck = [r["chain_key"] for r in rs]
    eq("notes chain by series; an undated offering takes the series priced next",
       (ck[0] == ck[4] == ck[5], ck[1] == ck[2] == ck[3], ck[0] == ck[1], [r["latest"] for r in rs]),
       (True, True, False, [0, 0, 0, 1, 0, 1]))
    publish(conn, "9.9.9", log=lambda *_: None)
    publish(conn, "9.9.9", log=lambda *_: None)
    eq("idempotent", conn.execute("SELECT COUNT(*) FROM debt_deals").fetchone()[0], len(rows))
    print("debt_publish: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return 1 if bad else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv:
        return _selftest()
    db = argv[argv.index("--db") + 1] if "--db" in argv else DB
    conn = sqlite3.connect(db, timeout=30, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=30000")
    version = active_version(conn)
    if "--dry-run" in argv:
        v = argv[argv.index("--version") + 1] if "--version" in argv else version
        if not v:
            print("[debt_publish] dry run: no version given and none active")
            return 2
        rows, st = compute(load_items(conn, v))
        st.update(version=v)
        print("[debt_publish] dry run " + json.dumps(st))
        return 0
    if version is None:
        print("[debt_publish] no active debt version; nothing to publish")
        return 0
    try:
        publish(conn, version)
        return 0
    except Exception as exc:  # noqa: BLE001
        print("[debt_publish] FAILED publishing %s: %s: %s" % (version, type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
