"""Exchange bulletins reader (BULL_V1, 2026-10-18). Rules only; no model.

Justin, 2026-10-12: "TSX-V / CSE bulletins as a second source for consolidations, name and symbol changes" (the
calendar reader's corporate actions measured 38-45% on fresh releases and are shown "Unconfirmed"); 2026-10-18 "Can we
do 1-3?". An exchange bulletin is the exchange's own notice of a corporate action, with the trading date it takes
effect, so it confirms (or replaces) what a company's release says.

parse_cse(title, body_html, posted) -> bulletin dict      pure; no network, no clock
  title   "2026-1011 - Name and Symbol Change - Cloud3 Ventures Inc. (CLDV)"
  body    the bulletin's HTML from its page data (bilingual; the English half is read)
  posted  the bulletin's date ("2026-10-07T15:02:11-04:00")

A bulletin dict:
  {"exchange": "CSE", "number": "2026-1011", "types": [...], "company": str, "symbol": str,
   "events": [{"kind", "date", "exact", "detail", "new_symbol", "status"}], "note": str}
kinds: consolidation (detail "10:1" = 10 old for 1 new), name_change (detail = new name), symbol_change (detail = new
symbol), listing (detail "new listing" / "delisting" / "reinstatement"), split (detail "2:1" = 2 new for 1 old).
date = the first trading day under the change; status "scheduled" when the bulletin gives that day, "proposed" when it
says the change waits on something (a fundamental change, shareholder approval), else "completed" with the posted date.

Self-tests: python3 exchange_bulletins.py
"""
from __future__ import annotations

import html as _html
import re
from datetime import date, timedelta

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
     "december"])}
MON3 = {k[:3]: v for k, v in MONTHS.items()}
_MON = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|" \
       r"Nov(?:ember)?|Dec(?:ember)?)"
DATE_EN = re.compile(r"\b(?P<mon>" + _MON + r")\.?\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<y>20\d\d)\b", re.I)
FR_MON = {"janv": 1, "janvier": 1, "f\N{LATIN SMALL LETTER E WITH ACUTE}vr": 2, "fevr": 2, "f\N{LATIN SMALL LETTER E WITH ACUTE}vrier": 2,
          "fevrier": 2, "mars": 3, "avr": 4, "avril": 4, "mai": 5, "juin": 6, "juil": 7, "juillet": 7,
          "ao\N{LATIN SMALL LETTER U WITH CIRCUMFLEX}t": 8, "aout": 8, "sept": 9, "septembre": 9, "oct": 10,
          "octobre": 10, "nov": 11, "novembre": 11, "d\N{LATIN SMALL LETTER E WITH ACUTE}c": 12, "dec": 12,
          "d\N{LATIN SMALL LETTER E WITH ACUTE}cembre": 12, "decembre": 12}
DATE_FR = re.compile(r"\b(?P<d>\d{1,2})(?:er)?\s+(?P<mon>[^\W\d_]{3,9})\.?(?:\s*/\s*[A-Za-z]+\.?)?\s+(?P<y>20\d\d)\b")
DATE_UP = re.compile(r"\b(?P<d>\d{1,2})\s+(?P<mon>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\w*\.?\s+(?P<y>20\d\d)\b")
NUMW = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                   "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}


def _txt(h):
    h = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</tr>|</h\d>", "\n", h or "", flags=re.I)
    t = _html.unescape(re.sub(r"<[^>]+>", " ", h))
    return re.sub(r"[ \t\r\f\v\N{NO-BREAK SPACE}]+", " ", t)


def _english(t):
    """The English half of a bilingual bulletin: from "Month YYYY" to the first long underscore rule, plus the
    bilingual field block at the end ("Effective Date/Date d'entree en vigueur", "Symbol/symbole")."""
    parts = re.split(r"_{8,}", t)
    head = parts[0]
    tail = parts[-1] if len(parts) > 1 else ""
    m = re.search(r"\b(?:Effective Date|Date|Symbol|NEW|OLD|Security Name|Record Date|Listing Date)\s*(?:\(s\))?\s*/", tail)
    fields = tail[m.start():] if m else ""
    return head, fields


def _d(m):
    mon = m.group("mon").lower()
    mm = FR_MON.get(mon) or MON3.get(mon[:3])
    try:
        return date(int(m.group("y")), mm, int(m.group("d")))
    except (ValueError, KeyError, TypeError):
        return None


def _field_date(t, at):
    """The date written just after a field label: "le 13 OCT 2026", "Le 20 ao\N{LATIN SMALL LETTER U WITH CIRCUMFLEX}t 2026", "October 13, 2026"."""
    w = t[at:at + 40]
    for rx in (DATE_UP, DATE_FR, DATE_EN):
        dm = rx.search(w)
        if dm and _d(dm):
            return _d(dm)
    return None


def _num(x):
    x = x.strip().lower()
    if x in NUMW:
        return float(NUMW[x])
    try:
        return float(x.replace(",", ""))
    except ValueError:
        return None


def _fmt(x):
    return ("%g" % x) if x is not None else None


def _next_trading_day(d):
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _consol_ratio(t):
    """'one (1) post-consolidated share for every ten (10) pre-consolidated' -> '10:1' (old:new)."""
    m = re.search(r"basis of\s+(?:one|1)\s*(?:\(\s*1\s*\))?\s+post[\s-]consolidat\w*\s+(?:common\s+)?shares?\s+for\s+"
                  r"(?:(?:each|every)\s+)?(?:[a-z-]+\s+){0,4}\(\s*([\d.,]+)\s*\)\s+pre[\s-]consolidat", t, re.I)
    if m:
        return "%s:1" % _fmt(_num(m.group(1))) if _num(m.group(1)) else None
    m = re.search(r"basis of\s+(?:one|1)\s*(?:\(\s*1\s*\))?\s+post[\s-]consolidat\w*\s+(?:common\s+)?shares?\s+for\s+"
                  r"(?:(?:each|every)\s+)?(?:(\w[\w.,]*)\s*\(\s*([\d.,]+)\s*\)|([\d.,]+|\w+))\s+pre[\s-]consolidat", t, re.I)
    if m:
        old = _num(m.group(2) or m.group(1) or m.group(3))
        return "%s:1" % _fmt(old) if old else None
    m = re.search(r"\b(\w+)\s*(?:\(\s*([\d.,]+)\s*\))?\s+(?:old|pre[\s-]consolidat\w*)\s+(?:common\s+)?(?:shares?\s+)?"
                  r"for\s+(?:one|1)\s*(?:\(\s*1\s*\))?\s+new", t, re.I)
    if m:
        old = _num(m.group(2) or m.group(1))
        return "%s:1" % _fmt(old) if old else None
    return None


def _split_ratio(t):
    m = re.search(r"\b(\w+)\s*(?:\(\s*(\d+)\s*\))?\s+for\s+(\w+)\s*(?:\(\s*(\d+)\s*\))?\s+(?:stock|share|forward)\s+split",
                  t, re.I)
    if m:
        a, b = _num(m.group(2) or m.group(1)), _num(m.group(4) or m.group(3))
        if a and b:
            return "%s:%s" % (_fmt(a), _fmt(b))
    return None


def _trading_date(t, posted):
    """The first trading day under the change, and whether the bulletin states it."""
    pats = [r"(?:delisted|retir\w+)[^.]{0,80}?(?:at (?:the )?market close|at the close of (?:business|trading))"
            r",?\s+(?:today,?\s+|on\s+)?(?:\w+day,?\s+)?",
            r"(?:begin|commence|start)\s+trading[^.]{0,160}?\bon\s+(?:\w+day,?\s+)?",
            r"(?:will\s+)?(?:begin|commence|start)\s+(?:to\s+)?trad\w*[^.]{0,120}?(?:effective|as of|at the open(?:ing)? (?:of|on))\s+(?:\w+day,?\s+)?",
            r"effective at the (?:open(?:ing)?|market open)[^.]{0,20}?(?:on|of)?\s+(?:\w+day,?\s+)?",
            r"reinstated for trading[^.]{0,40}?\bon\s+(?:\w+day,?\s+)?",
            r"trading will resume[^.]{0,40}?\bon\s+(?:\w+day,?\s+)?"]
    for p in pats:
        m = re.search(p, t, re.I)
        if m:
            dm = DATE_EN.match(t, m.end()) or DATE_EN.search(t[m.end():m.end() + 40])
            if dm:
                d = _d(dm)
                if d:
                    return d, True
    m = re.search(r"(?:Effective Date|Listing Date|Trading Date|Date of Listing)\s*/[^:]{0,40}:\s*"
                  r"(?:Le\s+|Market (?:Open|Close)[^\d]{0,40})?", t, re.I)
    if m and _field_date(t, m.end()):
        return _field_date(t, m.end()), True
    # a consolidation's or split's own record date field (the first day on the new basis); ahead of the open-orders
    # rule, which cannot know holidays (Thanksgiving 2025-10-13)
    m = re.search(r"Record Date\s*/[^:]{0,40}:\s*", t, re.I)
    if m and re.search(r"consolidat|split", t, re.I) and _field_date(t, m.end()):
        return _field_date(t, m.end()), True
    m = re.search(r"open orders will be (?:cancel+ed|purged)[^.]{0,60}?(?:(?:close|end) of (?:business|trading|the day)|"
                  r"market close)(?:\s+on)?,?\s+(?:\w+day,?\s+)?", t, re.I)
    if m:
        dm = DATE_EN.match(t, m.end()) or DATE_EN.search(t[m.end():m.end() + 30])
        if dm and _d(dm):
            return _next_trading_day(_d(dm)), True
    if re.search(r"\b(?:effective immediately|today)\b", t, re.I) and posted:
        return posted, True
    return None, False


def _name(t, m):
    """The new name; keeps the period of a closing "Corp." / "Inc." / "Ltd." that the sentence end swallowed."""
    if not m:
        return None
    nm = m.group(1).strip()
    if re.search(r"\b(?:Corp|Inc|Ltd|Co|Corpn|Limitee|Ltee|S\.A|N\.V|plc)$", nm) and t[m.end(1):m.end(1) + 1] == ".":
        nm += "."
    return nm


TYPE_KINDS = [("consolidation", r"consolidation"), ("name_change", r"\bname\b"), ("symbol_change", r"\bsymbol\b"),
              ("split", r"stock split|forward split|subdivision"), ("new listing", r"new listing"),
              ("delisting", r"\bdelist"), ("reinstatement", r"reinstatement")]


def parse_cse(title, body_html, posted=None):
    pd = None
    if posted:
        try:
            pd = date.fromisoformat(str(posted)[:10])
        except ValueError:
            pd = None
    tm = re.match(r"\s*(\d{4}\s*-\s*\d{2,4})\s*[-\N{EN DASH}]\s*(.*)$", title or "")
    number = re.sub(r"\s", "", tm.group(1)) if tm else None
    rest = tm.group(2) if tm else (title or "")
    sm = re.search(r"\(([A-Z0-9.]+)\)\s*$", rest)
    symbol = sm.group(1) if sm else None
    # "<type> - <company> (SYM)"; the type itself can contain " - " (Symbol Change - Inactive Designation)
    pieces = [p.strip() for p in re.split(r"\s+[-\N{EN DASH}]\s+", re.sub(r"\s*\([A-Z0-9.]+\)\s*$", "", rest))]
    company = pieces[-1] if len(pieces) > 1 else None
    typ = " - ".join(pieces[:-1]) if len(pieces) > 1 else rest
    head, fields = _english(_txt(body_html))
    t = re.sub(r"\s+", " ", head + " " + fields)
    out = {"exchange": "CSE", "number": number, "type": typ, "company": company, "symbol": symbol, "posted": str(pd or ""),
           "events": [], "note": ""}
    tl = typ.lower()
    if re.search(r"inactive designation|\.x\b|nv issuer|dealer|holiday|schedule|index|cusip", tl):
        out["note"] = "not a company corporate action"
        return out
    d, exact = _trading_date(t, pd)
    waits = re.search(r"(?:will not resume until|pending (?:a |the )?fundamental change|subject to (?:shareholder|the "
                      r"Exchange|CSE) approval|has not yet been|is expected to)", t, re.I)
    status = "scheduled" if d and pd and d > pd else "completed" if d else ("proposed" if waits else "completed")
    if not d and not waits and pd:
        d, exact = pd, False
    if waits and not (d and exact):
        d, exact, status = None, False, "proposed"

    def ev(kind, detail=None, **kw):
        e = {"kind": kind, "date": d.isoformat() if d else None, "exact": bool(exact and d), "detail": detail,
             "status": status}
        e.update(kw)
        out["events"].append(e)

    if "consolidation" in tl:
        ev("consolidation", _consol_ratio(t))
    if re.search(r"\bname\b", tl) and not re.search(r"dealer name", tl):
        nm = re.search(r"name (?:and symbol )?change (?:to|for)\s+(.+?)(?:\s*\(([A-Z0-9.]+)\))?(?:\s+and\s+a\s+|\.\s|,\s)", t)
        ev("name_change", _name(t, nm))
    if re.search(r"\bsymbol\b", tl) or (re.search(r"change of business", tl) and re.search(r"symbol change", t, re.I)):
        ns = re.search(r"(?:symbol change to|change to)\s+[^()]{0,120}?\(([A-Z0-9.]{1,10})\)", t) or \
            re.search(r"NEW\s+(?:Symbol|Trading Symbol)[^:]{0,40}:\s*([A-Z0-9.]{1,10})\b", t) or \
            re.search(r"new (?:trading )?symbol[^A-Z]{0,30}\b([A-Z][A-Z0-9.]{0,9})\b", t)
        ev("symbol_change", ns.group(1) if ns else None)
    if re.search(r"change of business", tl) and not any(e["kind"] == "name_change" for e in out["events"]) and \
            re.search(r"name (?:and symbol )?change", t, re.I):
        nm = re.search(r"name (?:and symbol )?change to\s+(.+?)(?:\s*\(([A-Z0-9.]+)\))?(?:\s+and\s+a\s+|\.\s|,\s|\s+The\s)", t)
        ev("name_change", _name(t, nm))
    if re.search(r"stock split|forward split|subdivision", tl):
        ev("split", _split_ratio(t))
    if "new listing" in tl:
        ev("listing", "new listing", venue="CSE")
    if re.search(r"\bdelist", tl):
        ev("listing", "delisting", venue="CSE")
    if "reinstatement" in tl:
        ev("listing", "reinstatement", venue="CSE")
    return out


# ------------------------------------------------------------------ store, collector, calendar rows
PARSER_VERSION = "1.0.3"
DB = "/opt/mnt/app/portal/portal.db"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
CSE_LIST = "https://website-data-api-v2.thecse.com/api/bulletins?locale=en"
CSE_PAGE = "https://thecse.com/bulletin/%s/"
# the bulletin types worth fetching: the corporate actions the calendar shows, and listing changes
CSE_WANT = re.compile(r"consolidation|\bname\b|symbol change|new listing|delist|stock split|reinstatement|change of business",
                      re.I)
CSE_SKIP = re.compile(r"inactive designation|dealer|holiday|schedule|index|nv issuer|cusip", re.I)
CAL_KINDS = ("consolidation", "name_change", "symbol_change", "listing")
TABLE_SQL = """
CREATE TABLE IF NOT EXISTS exchange_bulletins (
    bulletin_id     TEXT PRIMARY KEY,
    exchange        TEXT NOT NULL,
    number          TEXT,
    posted          TEXT,
    title           TEXT,
    type            TEXT,
    company         TEXT,
    symbol          TEXT,
    symbols         TEXT,
    url             TEXT,
    body_text       TEXT,
    parsed          TEXT,
    parser_version  TEXT,
    fetched_at      TEXT
);
CREATE INDEX IF NOT EXISTS ix_exchange_bulletins_symbol ON exchange_bulletins(exchange, symbol);
CREATE INDEX IF NOT EXISTS ix_exchange_bulletins_posted ON exchange_bulletins(posted);
"""


def ensure_schema(conn):
    conn.executescript(TABLE_SQL)


def _get(url, timeout=30):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _cse_body(page_html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_html, re.S)
    if not m:
        return None
    import json
    return (json.loads(m.group(1)).get("props", {}).get("pageProps", {}).get("bulletin") or {}).get("body")


def collect_cse(conn, days=30, max_fetch=60, sleep=1.0, log=print, fetch=None, now=None):
    """New CSE bulletins of the wanted types posted in the last `days` days -> rows in exchange_bulletins. One list
    request, then one page per new bulletin, `sleep` seconds apart, at most `max_fetch` pages a run. Returns stats."""
    import json
    import time as _t
    from datetime import datetime, timezone
    fetch = fetch or _get
    ensure_schema(conn)
    since = ((now or datetime.now(timezone.utc)).date() - timedelta(days=days)).isoformat()
    lst = json.loads(fetch(CSE_LIST))["list"]
    have = {r[0] for r in conn.execute("SELECT bulletin_id FROM exchange_bulletins WHERE exchange='CSE'")}
    todo = [x for x in lst if str(x.get("date") or "")[:10] >= since and CSE_WANT.search(x.get("title") or "")
            and not CSE_SKIP.search(x.get("title") or "") and "CSE:%s" % x["id"] not in have]
    todo.sort(key=lambda x: x.get("date") or "", reverse=True)
    st = {"listed": len(lst), "in_window": sum(1 for x in lst if str(x.get("date") or "")[:10] >= since),
          "new": len(todo), "fetched": 0, "errors": 0, "events": 0}
    for x in todo[:max_fetch]:
        url = CSE_PAGE % x["slug"]
        try:
            body = _cse_body(fetch(url))
        except Exception as exc:  # noqa: BLE001 - one bad page must not stop the run
            st["errors"] += 1
            log("[exchange_bulletins] CSE %s: %s" % (x.get("slug"), str(exc)[:160]))
            continue
        if body is None:
            st["errors"] += 1
            continue
        b = parse_cse(x["title"], body, x.get("date"))
        st["fetched"] += 1
        st["events"] += len(b["events"])
        conn.execute("INSERT OR REPLACE INTO exchange_bulletins(bulletin_id, exchange, number, posted, title, type, "
                     "company, symbol, symbols, url, body_text, parsed, parser_version, fetched_at) VALUES "
                     "(?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
                     ("CSE:%s" % x["id"], "CSE", b["number"], x.get("date"), x["title"], b["type"], b["company"],
                      b["symbol"], json.dumps(x.get("symbols") or []), url, _txt(body)[:20000], json.dumps(b),
                      PARSER_VERSION))
        if sleep:
            _t.sleep(sleep)
    st["left"] = max(0, len(todo) - max_fetch)
    return st


def reparse(conn):
    """Re-read stored bulletins whose parser version is older than this one (no fetching)."""
    import json
    n = 0
    for bid, ex, title, body, posted in conn.execute(
            "SELECT bulletin_id, exchange, title, body_text, posted FROM exchange_bulletins WHERE "
            "COALESCE(parser_version, '') <> ?", (PARSER_VERSION,)).fetchall():
        if ex != "CSE":
            continue
        b = parse_cse(title, "<p>" + _html.escape(body or "") + "</p>", posted)
        conn.execute("UPDATE exchange_bulletins SET parsed=?, parser_version=? WHERE bulletin_id=?",
                     (json.dumps(b), PARSER_VERSION, bid))
        n += 1
    return n


def mnt_ticker(exchange, symbol):
    """CSE 'CRUZ' / 'UAV.X' -> MNT's 'CRUZ.CN' / 'UAV.CN'; None for warrants, preferreds, debentures, units."""
    s = (symbol or "").strip().upper()
    if not s or re.search(r"\.(?:WT|PR|DB|U|UN|RT|NT)\b|\.[A-Z]\.[A-Z]", s):
        return None
    s = re.sub(r"\.X$", "", s)
    if exchange == "CSE":
        return s + ".CN"
    if exchange == "TSXV":
        return re.sub(r"\.H$", "", s) + ".V"
    return None


def calendar_items(conn):
    """Stored bulletins -> [(event, {"rows": [...]})] in the form calendar_publish.compute() takes: confirmed rows of
    the corporate kinds the calendar shows, attached to the company's MNT ticker before the change."""
    import json
    out = []
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='exchange_bulletins'").fetchone():
        return out
    for bid, ex, posted, title, sym, url, parsed in conn.execute(
            "SELECT bulletin_id, exchange, posted, title, symbol, url, parsed FROM exchange_bulletins"):
        tk = mnt_ticker(ex, sym)
        try:
            b = json.loads(parsed or "{}")
        except ValueError:
            continue
        rows = []
        for e in b.get("events") or []:
            if e.get("kind") not in CAL_KINDS:
                continue
            rows.append({"kind": e["kind"], "status": e.get("status") or "scheduled", "date": e.get("date"),
                         "exact": bool(e.get("exact")), "detail": e.get("detail"), "venue": ex, "show": True})
        if tk and rows:
            out.append(({"event_id": "bulletin:%s" % bid, "ticker": tk, "published_at": posted,
                         "raw_headline": title, "slug": url, "tagged": True, "bulletin": True}, {"rows": rows}))
    return out


def main(argv=None):
    import json
    import sqlite3
    import sys
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    db = argv[argv.index("--db") + 1] if "--db" in argv else DB
    if argv[0] == "collect":
        days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 30
        mx = int(argv[argv.index("--max-fetch") + 1]) if "--max-fetch" in argv else 60
        conn = sqlite3.connect(db, timeout=30, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=30000")
        st = collect_cse(conn, days=days, max_fetch=mx)
        st["reparsed"] = reparse(conn)
        print("[exchange_bulletins] " + json.dumps(st, sort_keys=True))
        return 0 if not st["errors"] or st["fetched"] else 1
    if argv[0] == "show":
        conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=30)
        for ev, p in calendar_items(conn)[-int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else -30:]:
            for r in p["rows"]:
                print("%-10s %-9s %-14s %-10s %-9s %s" % (ev["published_at"][:10], ev["ticker"], r["kind"], r["date"],
                                                         r["status"], (r["detail"] or "")[:50]))
        return 0
    print("usage: exchange_bulletins.py collect [--days N] [--max-fetch N] | show [N] | selftest")
    return 2


def _selftest():
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("  FAIL %s: got %r want %r" % (name, got, want))
    b = parse_cse("2026-1011 - Name and Symbol Change - Cloud3 Ventures Inc. (CLDV)",
                  "<p>Le 7 octobre/October 2026</p><p>Cloud3 Ventures Inc. (CLDV) has announced a name and symbol change "
                  "to Aeon Strategies Ltd. (AEON). Shares will begin trading under the new name and symbol and with a "
                  "new CUSIP number on October 9, 2026. Please note that all open orders will be canceled at the end of "
                  "business on October 8, 2026.</p><p>_________________________</p><p>Cloud3 ... francais</p>",
                  "2026-10-07T15:00:00-04:00")
    eq("cldv kinds", [(e["kind"], e["date"], e["detail"], e["status"]) for e in b["events"]],
       [("name_change", "2026-10-09", "Aeon Strategies Ltd.", "scheduled"), ("symbol_change", "2026-10-09", "AEON", "scheduled")])
    b = parse_cse("2026-1012 - Name Change and Consolidation - Cruz Battery Metals Corp. (CRUZ)",
                  "<p>Le 8 octobre/October 2026</p><p>Cruz Battery Metals Corp. has announced a name change to Cruz Mining "
                  "Corp. and a consolidation of its issued and outstanding common shares on the basis of one (1) "
                  "post-consolidated common share for every ten (10) pre-consolidated common shares. Please note that all "
                  "open orders will be canceled at the close of business on October 13, 2026.</p><p>________</p>",
                  "2026-10-08T12:00:00-04:00")
    eq("cruz", [(e["kind"], e["date"], e["detail"]) for e in b["events"]],
       [("consolidation", "2026-10-14", "10:1"), ("name_change", "2026-10-14", "Cruz Mining Corp.")])
    b = parse_cse("2026-1018 - Consolidation - Global UAV Technologies Ltd.  (UAV.X)",
                  "<p>Global UAV Technologies Ltd. has announced a consolidation of its issued and outstanding common "
                  "shares on the basis of one (1) post-consolidated share for each 1.324206 pre-consolidated shares. "
                  "Trading will not resume until the Fundamental Change has been approved.</p>", "2026-10-14T16:10:33-04:00")
    eq("uav", [(e["kind"], e["date"], e["detail"], e["status"]) for e in b["events"]],
       [("consolidation", None, "1.32421:1", "proposed")])
    b = parse_cse("2026-1009 - Delist - Lords & Company Worldwide Holdings Inc. (LRDS)",
                  "<p>The common shares of Lords will be delisted from the CSE at market close today, October 7, 2026.</p>",
                  "2026-10-07T10:00:00-04:00")
    eq("delist", [(e["kind"], e["date"], e["detail"], e["status"]) for e in b["events"]],
       [("listing", "2026-10-07", "delisting", "completed")])
    b = parse_cse("2026-1001 - Consolidation - Armory Mining Corp. (ARMY)",
                  "<p>Armory Mining Corp. has announced a consolidation of its issued and outstanding common shares on the "
                  "basis of one (1) post-consolidated share for five (5) pre-consolidated shares. Please note that all open "
                  "orders will be canceled at the close of business on October 5, 2026.</p>", "2026-10-02T10:00:00-04:00")
    eq("army", [(e["kind"], e["date"], e["detail"]) for e in b["events"]], [("consolidation", "2026-10-06", "5:1")])
    b = parse_cse("2026-0924 - Stock Split - Bighorn Metals Corp. (HRNY)",
                  "<p>Bighorn Metals Corp. has announced a two (2) for one (1) stock split of its issued and outstanding "
                  "common shares. All open orders will be purged from the book at the market close on September 22, "
                  "2026.</p>", "2026-09-18T10:00:00-04:00")
    eq("split", [(e["kind"], e["date"], e["detail"]) for e in b["events"]], [("split", "2026-09-23", "2:1")])
    b = parse_cse("2026-1015 - New Listing - Alpha Gold Corp. (ALP)",
                  "<p>Le 8 octobre/October 2026</p><p>The common shares of Alpha Gold Corp. have been approved for listing "
                  "on the CSE. Listing and disclosure documents will be available at www.thecse.com on the listing "
                  "date.</p><p>__________________________</p><p>Symbol(s)/Symbole(s) : ALP Listing Date/Date de "
                  "l'inscription : le 13 OCT 2026</p>", "2026-10-08T15:00:00-04:00")
    eq("listing date field", [(e["kind"], e["date"], e["status"]) for e in b["events"]],
       [("listing", "2026-10-13", "scheduled")])
    eq("bilingual month in a field", _field_date("Listing Date/Date de l'inscription : Le 20 ao\N{LATIN SMALL LETTER U WITH CIRCUMFLEX}t/August 2026 Other", 37),
       date(2026, 8, 20))
    b = parse_cse("2026-0702 - Delist - Two Hands Corporation (TWOH.X)",
                  "<p>The common shares of Two Hands Corporation will be delisted from the CSE at market close, July 7, "
                  "2026. Two Hands continues to trade elsewhere.</p>", "2026-07-02T12:00:00-04:00")
    eq("delisting date after a comma", [(e["kind"], e["date"], e["status"]) for e in b["events"]],
       [("listing", "2026-07-07", "scheduled")])
    print("exchange_bulletins self-tests: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) > 1 and _sys.argv[1] != "selftest":
        raise SystemExit(main())
    raise SystemExit(1 if _selftest() else 0)
