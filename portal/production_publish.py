"""Publish the Production Results reader into the table /production-results reads (PROD_PUBLISH_V1,
2026-09-21).

The facts store holds what PROD_V1 (portal/extractors/production.py) found in every approved release. The
page reads production_results, which this module rebuilds from the ACTIVE production version. Like
/economic-studies it replaces nothing: the URL showed a plain list of tagged releases, so there is no legacy
table and no legacy backfill.

One row per metal per period (Justin, 2026-09-21), of three kinds -- actual, guidance, milestone -- and since
PROD13 (2026-09-28) a fourth, recovered: ounces a release says were recovered, shown apart from production. A
year-to-date nine months is period '9M 2025' (period_end 2025-09-30).

What goes on the page:
  1. every approved release in which the reader found a row, tagged Production Results or not (the tag
     misses real production releases -- Energy Fuels, Sierra Madre, Equinox guidance -- and leaks oil and
     gas, royalty payments and developers);
  2. a MARKER row (kind NULL) for every tagged release that states none, so the page follows the tag;
  3. GUIDANCE FOR A PERIOD THAT HAD ENDED by the release date is not a row of its own: it goes on the
     actual row for that period and metal as guided_low / guided_high (Justin, 2026-09-21), so the page can
     say whether guidance was met. Torex's January release shows FY2024 452,523 oz, guided 450,000-470,000.
     With no actual row to carry it, it is dropped -- it is a comparison, not news. The reader cannot do
     this: it never sees the release date.
  4. a restatement of figures already published (Torex's Q3 in its production release and again in its
     results) is shown both times (Justin, 2026-09-21).
  5. (2026-10-01, fiscal fix) an actual whose calendar period would end after the release date is normally a plan
     or a year-to-date figure and is dropped -- unless the HEADLINE names that very period ('First Quarter 2025
     Results' in January, 'Fourth Quarter and Fiscal 2022 Results' in September) and the period would end within
     eleven months of the release, the headline is a results or production one, the year named is not followed
     by 'guidance' or 'outlook', a headline without 'results' is not a plan ('expansion', 'expects', 'guidance'),
     and the release reports no calendar period that has just ended (a calendar
     reporter's '2018 annual results and 2019 guidance'): then it is the company's own fiscal period, which has
     ended. It is kept with
     period_end None (the reader's other fiscal periods, 'Q1 FY2026', have none either), so the page dates it by the
     release.

compute() is a pure function of the items so the accuracy gate can score what a candidate version would
publish without writing anything. publish() rebuilds the table in one short transaction.

Timer use (sync_structured.py): python3 -m portal.production_publish
Self-tests: python3 -m portal.production_publish --selftest     (in-memory; touches nothing live)
Dry run:    python3 -m portal.production_publish --dry-run [--version X.Y.Z]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time

EXTRACTOR = "production"
TAG = "Production Results"
DB = "/opt/mnt/app/portal/portal.db"

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS production_results (
    pr_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    ordinal           INTEGER NOT NULL DEFAULT 0,
    ticker            TEXT,
    slug              TEXT,
    kind              TEXT,
    period            TEXT,
    period_end        TEXT,
    metal             TEXT,
    unit              TEXT,
    qty               REAL,
    low               REAL,
    high              REAL,
    sold              REAL,
    aisc              REAL,
    guided_low        REAL,
    guided_high       REAL,
    milestone         TEXT,
    asset             TEXT,
    basis             TEXT,
    approx            INTEGER NOT NULL DEFAULT 0,
    n_rows            INTEGER NOT NULL DEFAULT 1,
    tag_confirmed     INTEGER NOT NULL DEFAULT 0,
    raw_headline      TEXT,
    published_at      TEXT,
    extractor_version TEXT
);
"""
INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_prod_pub    ON production_results(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_prod_ticker ON production_results(ticker);
CREATE INDEX IF NOT EXISTS idx_prod_event  ON production_results(event_id);
"""

_COLS = ("event_id", "ordinal", "ticker", "slug", "kind", "period", "period_end", "metal", "unit", "qty", "low",
         "high", "sold", "aisc", "guided_low", "guided_high", "milestone", "asset", "basis", "approx", "n_rows",
         "tag_confirmed", "raw_headline", "published_at")
_ROW_FIELDS = ("kind", "period", "metal", "unit", "qty", "low", "high", "sold", "aisc", "milestone", "asset",
               "basis", "approx")

_QEND = {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}


def period_end(period):
    """'Q3 2025' -> '2025-09-30'; 'H1 2025' -> '2025-06-30'; 'FY 2025' -> '2025-12-31'; '2025-03' -> '2025-03-31'.
    A fiscal period ('Q1 FY2026') has no calendar end the reader knows: None."""
    p = (period or "").strip()
    m = re.fullmatch(r"Q([1-4]) (20\d\d)", p)
    if m:
        return "%s-%s" % (m.group(2), _QEND[m.group(1)])
    m = re.fullmatch(r"H([12]) (20\d\d)", p)
    if m:
        return "%s-%s" % (m.group(2), "06-30" if m.group(1) == "1" else "12-31")
    m = re.fullmatch(r"9M (20\d\d)", p)
    if m:
        return "%s-09-30" % m.group(1)      # 1.3: nine months (year to date)
    m = re.fullmatch(r"FY (20\d\d)", p)
    if m:
        return "%s-12-31" % m.group(1)
    m = re.fullmatch(r"(20\d\d)-(\d\d)", p)
    if m:
        import calendar
        return "%s-%s-%02d" % (m.group(1), m.group(2), calendar.monthrange(int(m.group(1)), int(m.group(2)))[1])
    return None


_HEADLINE_PROD = re.compile(r"(?i)(?<![\w-])produc|\boperat\w*\s+(?:results|update|highlights)|\bquarter|\bQ[1-4]\b|\b[1-4]Q\d\d|"
                            r"\bH[12]\b|guidance|\bresults\b|first\s+(?:gold\s+)?pour|\bgeos?\b|year[\s\-]+end|"
                            r"\bfull[\s\-]+year|\bannual\b|resum|restart")


_HEADLINE_NOT = re.compile(r"(?i)\b(?:mineral\s+)?(?:reserves?|resources?)\s+(?:and\s+(?:mineral\s+)?(?:reserves?|resources?)\s+)?"
                           r"(?:update|estimate|statement)|\bmeeting\b|\bAGM\b|webinar|conference\s+call\s+details")


_ORDW = {"1": "first|1st", "2": "second|2nd", "3": "third|3rd", "4": "fourth|4th"}
_NOT_PLAN = r"(?![\s\-]+(?:full[\s\-]+year\s+)?(?:production\s+)?(?:guidance|outlook|forecast|target|budget|plan)\b)"


def _fiscal_named(period, hl, day):
    """True when the headline names this calendar-labelled period and the period would end within eleven months
    after the release: a company reporting its own non-calendar fiscal quarter or year (2026-10-01)."""
    end = period_end(period)
    if not end or not day or end <= day or not hl:
        return False
    if not re.search(r"(?i)\bresults\b|produc|\boperat|\bfinancial", hl):
        return False          # a results or production release only ('Q1 2023 Shareholder Update' is not)
    if not re.search(r"(?i)\bresults\b", hl) and re.search(
            r"(?i)expan|expect|\btarget|\bplans?\b|guidance|on\s+track|doubl|\bwill\b|\bto\s+be\b", hl):
        return False          # a plan headline ('expansion doubling production by Q2 2022', 'guidance revision')
    if (int(end[:4]) * 12 + int(end[5:7])) - (int(day[:4]) * 12 + int(day[5:7])) > 11:
        return False
    p = period.strip()
    m = re.fullmatch(r"([QH])([1-4]) (20(\d\d))", p)
    if m:
        kind, n, year, yy = m.groups()
        if kind == "Q":
            q = r"(?:\bQ%s\b|\b(?:%s)[\s\-]+quarter\b)" % (n, _ORDW[n])
            if re.search(r"(?i)\b%sQ%s\b" % (n, yy), hl):
                return True
        else:
            q = r"(?:\bH%s\b|\b%s[\s\-]+half\b)" % (n, "first" if n == "1" else "second")
        return bool(re.search(r"(?i)" + q, hl)) and bool(re.search(r"(?i)(?<!\d)%s(?!\d)%s" % (year, _NOT_PLAN), hl))
    m = re.fullmatch(r"FY (20\d\d)", p)
    if m:
        return bool(re.search(r"(?i)(?:\bfiscal|\bFY|year[\s\-]+end|\bfull[\s\-]+year|\bannual)\D{0,20}%s(?!\d)%s|"
                              r"(?<!\d)%s\s+(?:fiscal|full[\s\-]+year|annual|year[\s\-]+end)%s" % (m.group(1), _NOT_PLAN, m.group(1), _NOT_PLAN), hl))
    return False


def _ptype(period):
    p = period or ""
    if p.startswith("9M"):
        return "9M"       # 1.3: a year-to-date nine months is its own kind of period
    return "FQ" if "FY20" in p else p[:1] if p[:1] in "QHF" else "M"


def _pkey(period):
    """A sortable key within one kind of period: 'Q3 2025' -> '2025-3', 'FY 2024' -> '2024', '2025-03' -> '2025-03'."""
    p = period or ""
    m = re.match(r"([QH])([1-4]) (?:FY)?(20\d\d)", p)
    if m:
        return "%s-%s" % (m.group(3), m.group(2))
    m = re.search(r"20\d\d(?:-\d\d)?", p)
    return m.group(0) if m else p


def _stale(r, day):
    """A quarter, half or month that ended more than seven months before the release, or a year more than fifteen,
    is a comparison or history: quarterly results come out within three months of the quarter's end."""
    end = period_end(r.get("period"))
    if not end or not day:
        return False
    y, mth = int(day[:4]), int(day[5:7])
    back = 15 if (r.get("period") or "").startswith("FY") else 7
    tot = y * 12 + (mth - 1) - back
    return end < "%04d-%02d-01" % (tot // 12, tot % 12 + 1)


def fold_past_guidance(rows, published_at):
    """Guidance for a period that ended on or before the release date goes on the actual row."""
    day = (published_at or "")[:10]
    out = []
    actual = {(r["period"], r["metal"]): r for r in rows if r.get("kind") == "actual"}
    for r in rows:
        if r.get("kind") == "guidance":
            end = period_end(r.get("period"))
            if end and day and end <= day:
                a = actual.get((r["period"], r["metal"]))
                vals = [v for v in (r.get("low"), r.get("high")) if v is not None]
                mid = sum(vals) / len(vals) if vals else None
                # guidance far from the actual (a third below it or half again above it) is some other asset's (1.1)
                fits = bool(mid) and a is not None and bool(a.get("qty")) and 0.67 <= a["qty"] / mid <= 1.5
                if fits and a.get("guided_low") is None and a.get("guided_high") is None:
                    a["guided_low"], a["guided_high"] = r.get("low"), r.get("high")
                continue
        out.append(r)
    return out


# ------------------------------------------------------------------ formatting (the page uses these)
def fmt_qty(v, unit=None):
    if v is None:
        return None
    a = abs(v)
    if unit == "lb" and a >= 1e6:
        s = ("%.3f" % (a / 1e6)).rstrip("0").rstrip(".") + "M lb"
    elif a >= 1e6:
        s = ("%.3f" % (a / 1e6)).rstrip("0").rstrip(".") + "M" + (" " + unit if unit else "")
    elif a >= 100:
        s = "{:,.0f}".format(a) + (" " + unit if unit else "")
    else:
        s = ("%.1f" % a).rstrip("0").rstrip(".") + (" " + unit if unit else "")
    return ("-" if v < 0 else "") + s


def fmt_range(low, high, unit=None):
    if low is None and high is None:
        return None
    if high is None:
        return "≥ " + fmt_qty(low, unit)
    if low is None:
        return "≤ " + fmt_qty(high, unit)
    if low == high:
        return fmt_qty(low, unit)
    return fmt_qty(low).replace(" ", "") + " – " + fmt_qty(high, unit)


MILESTONE_LABELS = {"commercial_production": "Commercial production", "first_pour": "First pour",
                    "resumption": "Operations resumed", "first_production": "First production",
                    "first_shipment": "First shipment", "restart": "Restart", "suspension": "Suspension"}


# ------------------------------------------------------------------ compute (pure)
def _marker(ev):
    row = {c: None for c in _COLS}
    row.update(event_id=ev["event_id"], ordinal=0, ticker=ev.get("ticker"), slug=ev.get("slug"), n_rows=0,
               approx=0, tag_confirmed=1, raw_headline=(ev.get("raw_headline") or "")[:500],
               published_at=ev.get("published_at"))
    return row


def compute(items):
    """items: iterable of (event, parsed); event = {event_id, ticker, published_at, raw_headline, slug, tagged};
    parsed = production.parse_records() output. Returns (rows, stats)."""
    items = sorted(items, key=lambda x: ((x[0].get("published_at") or ""), x[0]["event_id"]))
    out = []
    st = {"releases": 0, "published": 0, "rows": 0, "markers": 0, "tagged_published": 0, "untagged_published": 0,
          "actual": 0, "guidance": 0, "milestone": 0, "folded": 0}
    for ev, p in items:
        st["releases"] += 1
        rows = [dict(r) for r in (p.get("rows") or []) if r.get("kind")]
        n0 = sum(1 for r in rows if r["kind"] == "guidance")
        rows = fold_past_guidance(rows, ev.get("published_at"))
        # an 'actual' for a period that had not ended when the release came out is a plan or a year-to-date
        # figure read as a period ('250,000 ounces in 2026' in an October 2025 release): never a row
        day = (ev.get("published_at") or "")[:10]
        hl = ev.get("raw_headline") or ""
        # 2026-10-01: the company's own fiscal period, named in the headline, has ended (module note 5) -- unless the
        # release also reports a calendar period that has just ended: then it is a calendar reporter and the later
        # period is a plan ('2018 annual results and 2019 guidance')
        if day and not any(r["kind"] in ("actual", "recovered") and period_end(r.get("period"))
                           and period_end(r.get("period")) <= day and not _stale(r, day) for r in rows):
            for r in rows:
                if r["kind"] in ("actual", "recovered") and _fiscal_named(r.get("period"), hl, day):
                    r["_fiscal"] = True
        keep = [r for r in rows if r.get("_fiscal") or
                not (r["kind"] in ("actual", "recovered") and day and (period_end(r.get("period")) or "0") > day)]
        st["fiscal_kept"] = st.get("fiscal_kept", 0) + sum(1 for r in keep if r.get("_fiscal"))
        st["future_actuals"] = st.get("future_actuals", 0) + len(rows) - len(keep)
        rows = keep
        # of two actuals for one metal and one kind of period (Q1 2026 and Q1 2025, FY 2025 and FY 2024) the
        # earlier is the comparison the release draws, not its news; and a figure for a period that ended more
        # than fifteen months before the release is history ('the mine produced 5.47 Moz to 2016')
        latest = {}
        for r in rows:
            if r["kind"] in ("actual", "recovered"):
                k = (r["kind"], r["metal"], _ptype(r["period"]))
                latest[k] = max(latest.get(k, ""), _pkey(r["period"]))
        n1 = len(rows)
        rows = [r for r in rows if r["kind"] not in ("actual", "recovered") or
                (_pkey(r["period"]) == latest[(r["kind"], r["metal"], _ptype(r["period"]))] and (r.get("_fiscal") or not _stale(r, day)))]
        # guidance more than two years out is a study's plan, not guidance
        rows = [r for r in rows if r["kind"] != "guidance" or not day or not period_end(r.get("period"))
                or period_end(r["period"])[:4] <= str(int(day[:4]) + 2)]
        st["history"] = st.get("history", 0) + n1 - len(rows)
        st["folded"] += n0 - sum(1 for r in rows if r["kind"] == "guidance")
        tagged = bool(ev.get("tagged"))
        hl = ev.get("raw_headline") or ""
        if _HEADLINE_NOT.search(hl):
            # a reserve and resource update, a meeting notice: the figures in it are not this period's production
            st["headline_skipped"] = st.get("headline_skipped", 0) + (1 if rows else 0)
            rows = [r for r in rows if r["kind"] == "milestone"]
        if re.search(r"(?i)royalt", hl) and not any(r.get("metal") == "GEO" for r in rows):
            # a royalty company quoting its operators' ounces: not its own production
            rows = [r for r in rows if r["kind"] not in ("actual", "recovered")]
        if not tagged and not _HEADLINE_PROD.search(hl):
            # outside the tag, only a release whose headline is about production or results is read: the rest
            # quote production in passing -- a property's history, an acquisition target, a market article
            st["untagged_skipped"] = st.get("untagged_skipped", 0) + (1 if rows else 0)
            rows = []
        if not rows:
            if tagged:
                out.append(_marker(ev))
                st["markers"] += 1
            continue
        st["published"] += 1
        st["tagged_published" if tagged else "untagged_published"] += 1
        for i, r in enumerate(rows):
            row = {c: None for c in _COLS}
            row.update({k: r.get(k) for k in _ROW_FIELDS})
            row.update(guided_low=r.get("guided_low"), guided_high=r.get("guided_high"),
                       approx=1 if r.get("approx") else 0, period_end=None if r.get("_fiscal") else period_end(r.get("period")),
                       event_id=ev["event_id"], ordinal=i, ticker=ev.get("ticker"), slug=ev.get("slug"),
                       n_rows=len(rows), tag_confirmed=1 if tagged else 0,
                       raw_headline=(ev.get("raw_headline") or "")[:500], published_at=ev.get("published_at"))
            out.append(row)
            st["rows"] += 1
            st[r["kind"]] = st.get(r["kind"], 0) + 1
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
    """(event, parsed) for every approved release this version found rows in, and every approved release
    carrying the tag today (those with none become marker rows)."""
    from portal.extractors import production as X
    found = {r[0] for r in conn.execute(
        "SELECT DISTINCT r.event_id FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
        "WHERE r.extractor=? AND r.version=? AND f.field='is_production' AND f.value_num=1",
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
                " WHERE r2.extractor=? AND r2.version=? AND f2.field='is_production' AND f2.value_num=1)",
                (EXTRACTOR, version, EXTRACTOR, version)):
            facts.setdefault(eid, {}).setdefault(ordinal, []).append((field_, seq, num, text))
    return [(evs[e], X.parse_records(facts.get(e, {}))) for e in evs]


def _ensure_schema(conn):
    conn.executescript(TABLE_SQL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(production_results)")}
    for line in TABLE_SQL.splitlines():
        m = re.match(r"\s+([a-z_]+)\s+(TEXT|REAL|INTEGER)", line)
        if m and m.group(1) not in have and m.group(1) != "pr_id":
            conn.execute("ALTER TABLE production_results ADD COLUMN %s %s" % (m.group(1), m.group(2)))
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
        st["rowsync"] = rowsync.sync_rows(conn, "production_results", "pr_id", _COLS, rows, {"extractor_version": version})
    conn.execute("BEGIN IMMEDIATE")
    try:
        # OPSFIX item 1 (2026-10-05): write only the rows that changed; same table contents (portal/rowsync.py)
        from portal import rowsync
        st["rowsync"] = rowsync.sync_rows(conn, "production_results", "pr_id", _COLS, rows, {"extractor_version": version})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[production_publish] " + json.dumps(st))
    return st


# ------------------------------------------------------------------ self-tests
def _selftest():
    sys.path.insert(0, "/opt/mnt/app")
    from portal import facts as F
    from portal.extractors import production as X
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
    evs = [
        # a finished year's guidance printed beside its actual: folded onto the actual row
        ("e1", "TXG.TO", "2025-01-08", "Torex Gold Delivers on Full-Year Production Guidance 2024",
         "Torex reports fourth quarter gold production of 103,795 ounces and full-year gold production of 452,523 oz, "
         "within the Company's revised guidance range of 450,000 to 470,000 oz.", "Production Results"),
        # this year's guidance stays a row of its own
        ("e2", "ARTG.V", "2026-04-09", "Artemis Gold Announces Q1 2026 Production Results",
         "Blackwater produced 61,923 ounces of gold in Q1 2026. The Company is maintaining its full year production "
         "guidance of 265,000 to 290,000 ounces of gold.", "Production Results"),
        # tagged, no figures -> one marker
        ("e3", "FF.TO", "2026-03-31", "First Mining Announces Year-End 2025 Financial Results",
         "The Company advanced its Springpole project.", "Production Results|Financials"),
        # untagged with figures -> published, marked untagged
        ("e4", "SM.V", "2026-05-19", "Sierra Madre Reports Q1 2026 Results",
         "Sierra Madre produced 58,506 ounces of silver and 932 ounces of gold in Q1 2026.", "Financials"),
        # untagged, no figures -> nothing
        ("e5", "XYZ.V", "2026-01-05", "XYZ Drills 12 m of 3 g/t Gold", "Drilling continues.", "Drill Results"),
    ]
    for eid, tk, pub, hl, body, cats in evs:
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?, 'auto_approved')",
                     (eid, tk, pub, None, hl, body, eid + "-slug", cats))
    F.run_batch(conn, spec, [dict(r) for r in conn.execute("SELECT * FROM events")])
    rows, st = compute(load_items(conn, "9.9.9"))
    by = {}
    for r in rows:
        by.setdefault(r["event_id"], []).append(r)
    eq("past guidance folded", [(r["kind"], r["period"], r["qty"], r["guided_low"], r["guided_high"]) for r in by["e1"]],
       [("actual", "Q4 2024", 103795.0, None, None), ("actual", "FY 2024", 452523.0, 450000.0, 470000.0)])
    eq("current guidance kept", [(r["kind"], r["period"]) for r in by["e2"]], [("actual", "Q1 2026"), ("guidance", "FY 2026")])
    eq("marker", [(r["kind"], r["n_rows"]) for r in by["e3"]], [(None, 0)])
    eq("untagged published", [r["tag_confirmed"] for r in by["e4"]], [0, 0])
    eq("untagged, nothing -> absent", by.get("e5"), None)
    # production 1.3.2 folds a finished period's guidance onto its actual row itself, so the publisher has none left to fold
    eq("stats", (st["published"], st["markers"], st["folded"]), (3, 1, 0))
    publish(conn, "9.9.9", log=lambda *_: None)
    publish(conn, "9.9.9", log=lambda *_: None)
    eq("idempotent", conn.execute("SELECT COUNT(*) FROM production_results").fetchone()[0], len(rows))
    eq("1.3 period_end 9M", period_end("9M 2025"), "2025-09-30")
    # 2026-10-01 fiscal fix: a non-calendar company's own quarter / year, named in the headline, is kept
    fx = lambda hl, day, rws: compute([({"event_id": "f", "published_at": day, "raw_headline": hl, "tagged": True},
                                        {"rows": [dict(kind=k, metal="gold", period=p, qty=q) for k, p, q in rws]})])[0]
    got = fx("TRX Reports First Quarter 2025 Results", "2025-01-15", [("actual", "Q1 2025", 4841.0)])
    eq("fiscal quarter kept", [(r["kind"], r["period"], r["period_end"]) for r in got], [("actual", "Q1 2025", None)])
    got = fx("Monument Reports Fourth Quarter and Fiscal 2022 Results", "2022-09-23",
             [("actual", "FY 2022", 7091.0), ("actual", "Q4 2022", 1942.0)])
    eq("fiscal year and quarter kept", sorted(r["period"] for r in got), ["FY 2022", "Q4 2022"])
    got = fx("Company Reports Year-End 2024 Results", "2024-12-02", [("actual", "FY 2024", 19389.0)])
    eq("fiscal year-end kept", [r["period"] for r in got], ["FY 2024"])
    got = fx("Company Provides Corporate Update", "2025-10-01", [("actual", "FY 2025", 250000.0)])
    eq("unnamed future year still dropped", [r["kind"] for r in got], [None])
    got = fx("Company Reports Fourth Quarter Results", "2023-01-19", [("actual", "Q4 2023", 34090.0)])
    eq("headline without the year: dropped", [r["kind"] for r in got], [None])
    got = fx("Company Targets First Quarter 2026 Restart", "2024-11-01", [("actual", "Q1 2026", 1000.0)])
    eq("more than eleven months ahead: dropped", [r["kind"] for r in got], [None])
    got = fx("Miner Announces 2018 Fourth Quarter and Annual Results and 2019 Guidance", "2019-02-12",
             [("actual", "FY 2018", 201095.0), ("actual", "FY 2019", 187000.0)])
    eq("calendar reporter: next year's figure stays out", [r["period"] for r in got], ["FY 2018"])
    got = fx("Miner Reports Fourth Quarter Production Results and 2022 Guidance", "2022-01-10",
             [("actual", "Q4 2021", 22903.0), ("actual", "Q4 2022", 10000.0)])
    eq("calendar quarter just ended wins", [r["period"] for r in got], ["Q4 2021"])
    got = fx("Miner Q1 2023 Shareholder Update", "2023-01-25", [("actual", "Q1 2023", 1500000.0)])
    eq("not a results headline: dropped", [r["kind"] for r in got], [None])
    got = fx("Mine Expansion Doubling Production by the Second Quarter of 2022", "2021-10-12", [("actual", "Q2 2022", 721.0)])
    eq("plan headline: dropped", [r["kind"] for r in got], [None])
    got = fx("Guidance Revision - Increase FY2026 Production Range", "2026-04-16", [("actual", "FY 2026", 3600000.0)])
    eq("guidance headline: dropped", [r["kind"] for r in got], [None])
    eq("fiscal helper", (_fiscal_named("Q2 2025", "2Q25 results", "2025-03-01"), _fiscal_named("H1 2025", "First Half 2025 results", "2025-02-01"),
                         _fiscal_named("Q3 2025", "First Quarter 2025 Results", "2025-03-01"),
                         _fiscal_named("Q1 2025", "FIRST QUARTER RESULTS AND 2025 GUIDANCE", "2025-01-20")), (True, True, False, False))
    eq("1.3 9M is its own kind of period", (_ptype("9M 2025"), _ptype("2025-09")), ("9M", "M"))
    eq("period_end", (period_end("Q3 2025"), period_end("H1 2025"), period_end("FY 2024"), period_end("2025-02"),
                      period_end("Q1 FY2026")), ("2025-09-30", "2025-06-30", "2024-12-31", "2025-02-28", None))
    eq("formats", (fmt_qty(452523, "oz"), fmt_qty(14e6, "lb"), fmt_range(265000, 290000, "oz"), fmt_range(375000, None, "oz")),
       ("452,523 oz", "14M lb", "265,000 – 290,000 oz", "≥ 375,000 oz"))
    print("production_publish: %s" % ("ok" if not bad else "%d FAILURES" % bad))
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
            print("[production_publish] dry run: no version given and none active")
            return 2
        rows, st = compute(load_items(conn, v))
        st.update(version=v)
        print("[production_publish] dry run " + json.dumps(st))
        return 0
    if version is None:
        print("[production_publish] no active production version; nothing to publish")
        return 0
    try:
        publish(conn, version)
        return 0
    except Exception as exc:  # noqa: BLE001
        print("[production_publish] FAILED publishing %s: %s: %s" % (version, type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
