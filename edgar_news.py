#!/usr/bin/env python3
"""edgar_news.py - MNT_EDGAR_NEWS_V1 (2026-10-30, Justin: "fix the US-wire news gap").

Companies listed in the US must file their news releases with the SEC: US companies as 8-K exhibits (Coeur, McEwen,
Hecla, Vista), Canadian and other foreign filers as 6-K exhibits (Barrick, Agnico, Hudbay, SSR, Aris). Several of them
publish only through wires this server cannot read (GlobeNewswire answers 403, the Q4 investor sites 429 since
2026-10-19), so their releases never reached MNT. EDGAR answers this server when the reader names itself with a
contact address, so this collector reads the releases from there:

  1. map universe companies to SEC filers (MinePortal universe x SEC company_tickers_exchange.json, same name only -
     a same-ticker rule matched Novo Nordisk, Oracle and Arbor Realty; edgar_map.json beside this file adds or blocks
     by hand);
  2. find their new 6-K / 8-K filings: EDGAR's current-filings feed every run, plus a rotating sweep of each filer's
     filing list (a backstop for anything the feed scrolled past);
  3. read each filing's index, take the EX-99 exhibits (or a 6-K's own document when it has none), keep only documents
     that read as a news release (dateline, "news release", exchange tags) and drop statements, MD&A, circulars,
     material change reports and the like;
  4. skip any release MNT already shows (exchange_news.find_match on the headline, then a body-overlap check against
     the company's releases within +/-4 days), and post the rest through MNT's own ingest, classified like every
     other source, as source "companysite:sec.gov" (shown as Company Website, linking to the SEC copy).

Usage: edgar_news.py --dry-run | --apply [--days 10] [--max-ingest 25] [--sweep 30] [--only MUX,CDE] [--stats]
State: /var/lib/mnt-edgar/edgar_news.db (filings seen and what was done with each, runs, sweep cursor, filer map).
"""
import argparse, datetime as dt, html, json, os, re, sqlite3, sys, time, urllib.error, urllib.request

APP = "/opt/mnt/app"
sys.path.insert(0, APP)
import exchange_news as X   # noqa: E402  (find_match, norm, bare, uid_for, PORTAL_DB)

VERSION = "MNT_EDGAR_NEWS_V1"
DB_PATH = os.environ.get("EDGAR_NEWS_DB", "/var/lib/mnt-edgar/edgar_news.db")
SEC_UA = os.environ.get("EDGAR_UA", "MineTerminalPro JustinThring@outlook.com")   # SEC fair access: name + contact
MAP_JSON = os.environ.get("EDGAR_MAP", os.path.join(os.path.dirname(os.path.abspath(__file__)), "edgar_map.json"))
UNIVERSE = "http://127.0.0.1:8090/api/v1/universe"
PAUSE_S = 0.25          # SEC allows 10 requests a second; this stays at 4
SOURCE = "companysite:sec.gov"

SCHEMA = """
CREATE TABLE IF NOT EXISTS filings (
    acc TEXT PRIMARY KEY, cik INTEGER, ticker TEXT, form TEXT, filed TEXT, items TEXT,
    status TEXT NOT NULL,          -- ingested | matched | not_release | error | skipped
    published_date TEXT, title TEXT, doc_url TEXT, event_id TEXT, note TEXT,
    first_seen TEXT DEFAULT CURRENT_TIMESTAMP, acted_at TEXT);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, mode TEXT, filers INTEGER, found INTEGER,
    matched INTEGER, ingested INTEGER, not_release INTEGER, failed INTEGER, note TEXT);
CREATE TABLE IF NOT EXISTS sweep (cik INTEGER PRIMARY KEY, checked_at TEXT);
CREATE TABLE IF NOT EXISTS filers (cik INTEGER PRIMARY KEY, ticker TEXT, symbol TEXT, name TEXT, sec_ticker TEXT,
    sec_exchange TEXT, how TEXT, updated_at TEXT);
"""

_last = [0.0]


def log(msg):
    print(msg, flush=True)


def sec_get(url, accept="*/*"):
    wait = PAUSE_S - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA, "Accept": accept, "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read(8 * 1024 * 1024)
    finally:
        _last[0] = time.time()


def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


# ---------------------------------------------------------------------------------------------------------- filers
_SUFFIX = re.compile(r"\b(inc|corp|corporation|ltd|limited|plc|co|company|the|incorporated|sa|ab|nl|llc|lp|de|ltee)\b")


def nname(s):
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(_SUFFIX.sub(" ", s).split())


def build_map(con, apply):
    """{cik: {ticker, symbol, name}} for universe companies that file with the SEC; rebuilt once a day."""
    row = con.execute("SELECT MAX(updated_at) FROM filers").fetchone()[0]
    if row and row > (dt.datetime.utcnow() - dt.timedelta(hours=24)).isoformat():
        return {r["cik"]: dict(r) for r in con.execute("SELECT * FROM filers")}
    with urllib.request.urlopen(UNIVERSE, timeout=60) as r:
        uni = json.loads(r.read())["companies"]
    sec = json.loads(sec_get("https://www.sec.gov/files/company_tickers_exchange.json"))
    F = sec["fields"]
    rows = [dict(zip(F, x)) for x in sec["data"]]
    byname, bytick = {}, {}
    for x in rows:
        byname.setdefault(nname(x["name"]), x)
        bytick.setdefault((x["ticker"] or "").upper(), x)
    try:
        manual = json.load(open(MAP_JSON))
    except (OSError, ValueError):
        manual = {}
    add, block = manual.get("add") or {}, set(manual.get("block") or [])
    bycik = {x["cik"]: x for x in rows}
    out = {}
    for c in uni:
        t = (c.get("ticker") or "").upper()
        if not t or t in block:
            continue
        nm = nname(c.get("name"))
        x, how = byname.get(nm), "name"     # exact name only: ticker matches named Novo Nordisk, Oracle, Arbor Realty
        if t in add:
            x = bycik.get(int(add[t])) or {"cik": int(add[t]), "ticker": "", "exchange": "", "name": c.get("name")}
            how = "manual"
        if not x:
            continue
        out[int(x["cik"])] = {"cik": int(x["cik"]), "ticker": t, "symbol": c.get("symbol") or t, "name": c.get("name"),
                              "sec_ticker": x.get("ticker"), "sec_exchange": x.get("exchange"), "how": how}
    if apply:
        now = dt.datetime.utcnow().isoformat()
        con.execute("DELETE FROM filers")
        con.executemany("INSERT INTO filers VALUES (?,?,?,?,?,?,?,?)",
                        [(v["cik"], v["ticker"], v["symbol"], v["name"], v["sec_ticker"], v["sec_exchange"], v["how"],
                          now) for v in out.values()])
        con.commit()
    return out


# ---------------------------------------------------------------------------------------------------------- filings
def current_feed(form):
    """EDGAR's newest filings of one form (all filers): [(cik, acc, filed, items_text)]."""
    a = sec_get("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=%s&company=&dateb=&owner=include"
                "&start=0&count=100&output=atom" % form, "application/atom+xml").decode("utf-8", "replace")
    out = []
    for e in re.findall(r"(?s)<entry>(.*?)</entry>", a):
        t = re.search(r"<title>\s*([^<]+?)\s*</title>", e)
        if not t or not t.group(1).startswith(form + " "):
            continue                        # 6-K/A and 8-K/A amendments are skipped
        m = re.search(r"\((\d{10})\)\s*\(Filer\)", t.group(1))
        acc = re.search(r"AccNo:&lt;/b&gt;\s*([\d-]{20})", e)
        filed = re.search(r"Filed:&lt;/b&gt;\s*(\d{4}-\d{2}-\d{2})", e)
        if m and acc and filed:
            out.append((int(m.group(1)), acc.group(1), filed.group(1), " ".join(re.findall(r"Item (\d\.\d\d)", e))))
    return out


def filer_list(cik, since):
    j = json.loads(sec_get("https://data.sec.gov/submissions/CIK%010d.json" % cik, "application/json"))
    f = j["filings"]["recent"]
    out = []
    for i in range(len(f["form"])):
        if f["form"][i] in ("6-K", "8-K") and f["filingDate"][i] >= since:
            out.append((cik, f["accessionNumber"][i], f["filingDate"][i], ((f.get("items") or [""] * 99999)[i] or "")
                        .replace(",", " ")))
    return out


RELEASE_ITEMS = re.compile(r"7\.01|8\.01|2\.02|1\.01|2\.01|5\.02")   # 8-K items that carry a news release


def documents(cik, acc):
    """The filing's documents from its index page: [(type, description, url)]."""
    nod = acc.replace("-", "")
    base = "https://www.sec.gov/Archives/edgar/data/%d/%s/" % (cik, nod)
    h = sec_get(base + acc + "-index.htm", "text/html").decode("utf-8", "replace")
    out = []
    for r in re.findall(r"(?s)<tr[^>]*>(.*?)</tr>", h):
        cells = re.findall(r"(?s)<td[^>]*>(.*?)</td>", r)
        if len(cells) < 4:
            continue
        href = re.search(r'href="([^"]+)"', cells[2])
        if not href:
            continue
        url = href.group(1)
        url = "https://www.sec.gov" + url if url.startswith("/") else base + url
        url = re.sub(r"/ix\?doc=", "/", url)          # inline-XBRL viewer link -> the document itself
        typ = re.sub(r"<[^>]+>|&nbsp;", "", cells[3]).strip().upper()
        desc = re.sub(r"<[^>]+>|&nbsp;", "", cells[1]).strip()
        out.append((typ, desc, url))
    return out


# ---------------------------------------------------------------------------------------------------------- reading
_TAGS = re.compile(r"(?is)<(script|style|noscript|head)[^>]*>.*?</\1>")
_BLOCK = re.compile(r"(?i)<\s*(br|/p|/div|/li|/h[1-6]|/tr|p|li|tr|div)\b[^>]*>")
_ANY = re.compile(r"(?s)<[^>]+>")
_INLINE = re.compile(r"(?i)</?(?:font|span|b|i|u|em|strong|small|sup|sub|a)\b[^>]*>")   # SECFMT_V1
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATELINE = re.compile(r"(?i)\b(%s|Jan\.?|Feb\.?|Aug\.?|Sept?\.?|Oct\.?|Nov\.?|Dec\.?)\s+(\d{1,2}),?\s+(20\d\d)" % MONTHS)
NOT_RELEASE = re.compile(      # what the document is, read from its first lines (after the SEC header lines)
    r"(?i)management.s discussion|\bmd&a\b|(interim|condensed|unaudited)[a-z ,]{0,40}financial (statements|information)|"
    r"consolidated (financial )?statements|notice and access|information circular|"
    r"form 51-102f3|material change report|annual information form|form 52-109|certification of (interim|annual)|"
    r"form of proxy|voting instruction|report of voting results|technical report|consent of|"
    r"early warning report|form 45-106f1|code of (business )?conduct|shareholder rights plan|"
    r"investor presentation|corporate presentation|report of foreign private issuer|securities commission|"
    r"dealings? in securities|director.{0,3} dealings?|b-?bbee|broad-based black economic|superintendencia del mercado")   # USX_EDGAR_V2
WEAK_NOT = re.compile(r"(?i)agreement|indenture|warrant to purchase|execution (version|copy)|pro forma|notice of|"
                      r"articles of|by-law")   # documents of these kinds, unless the top reads as a news release
IS_RELEASE = re.compile(r"(?i)news release|press release|for immediate release|\((nyse|tsx|nasdaq|otcq)[^)]{0,40}\)|"
                        r"\b(nyse|tsx|tsxv|tsx-v|nasdaq|nyse american)\s*:\s*[a-z.]{1,6}\b|"
                        r"\b(jse|nyse|asx|lse)[a-z ]{0,24}(share code|symbol|code|ticker)\s*:\s*[a-z]{2,6}\b")   # USX_EDGAR_V2
LETTERHEAD = re.compile(   # AUDIT1110_SEC_TITLE (2026-11-10): letterhead lines are not the headline ("8310 S. Valley Highway")
    r"(?i)^\W*(?:\d{2,6} [\w.' -]{2,40}\b(?:street|avenue|ave|road|blvd|boulevard|highway|hwy|parkway)\.?\W*$"
    r"|(?!(?:19|20)\d\d )\d{2,6} [\w.' -]{2,40}\b(?:st|rd|drive|dr|place|way|crescent|lane|court)\.?\W*$"
    r"|suite \d|p\.? ?o\.? box \d|(?:phone|tel|telephone|fax|toll[ -]free|e-?mail|website)\s*[:.]"
    r"|[A-Z][\w.' ]{1,30},\s*[A-Z]{2}\.?,? +\d{5}(?:-\d{4})?\W*$"
    r"|[\w.' ]{2,30},\s*[\w.' ]{2,30},? +[A-Z]\d[A-Z] ?\d[A-Z]\d\W*$"
    r"|[\w ]{0,40}\band\b[\w ]{0,40}stock exchanges\W*$)")
SKIP_LINE = re.compile(r"(?i)^(exhibit|ex-?)\s*99[.\d]*$|^(news|press)?\s*releases?(,? dated .*)?$|^news$|^for immediate release|"
                       r"^\(?(tsx|tsxv|nyse|nasdaq|otc|asx|lse|aim|frankfurt|fse|bvl)[\w &-]*:|^stock symbols?|^trading symbols?|"
                       r"^page \d|^\d+$|^\S+\.(htm|html|txt)$|^(%s)\s+\d{1,2},\s+20\d\d$|^[\w.-]+\.(com|ca)$|^(tel|telephone|fax|email|toll free)\b|^#|"
                       r"\b(telephone|toll free|fax|e-?mail|website|symbols?)\s*:" % MONTHS)
DL_PARA = re.compile(r"^(([A-Z][\w .'&’-]+,\s*){1,3})?\(?(%s|Jan\.?|Feb\.?|Aug\.?|Sept?\.?|Oct\.?|Nov\.?|Dec\.?)\s+\d{1,2},?\s+20\d\d" % MONTHS)
ACTION = re.compile(r"(?i)\b(announc\w*|today|reports?|reported|is pleased|provides?|files?|closes?|completes?|signs?|enters?)\b")


def html_text(h):
    t = _TAGS.sub(" ", h or "")
    t = _BLOCK.sub("\n", t)
    t = html.unescape(_ANY.sub(" ", _INLINE.sub("", t)))   # SECFMT_V1: "S<font>ã</font>o" stays "São"
    lines = [re.sub(r"[ \t ​]+", " ", l).strip() for l in t.split("\n")]
    out = []
    for l in lines:
        if l or (out and out[-1]):
            out.append(l)
    return "\n".join(out).strip()


# SECFMT_V1 (2026-11-05): keep an exhibit's HTML when it carries a real figures table (3+ rows with 2+ numeric
# cells); the text-only body flattened ASM / ERO / TFPM tables to one number per line.
_LAST_RAW = {}
_ROW = re.compile(r"(?is)<tr\b.*?</tr>")
_NUMCELL = re.compile(r"(?is)<t[dh]\b[^>]*>(?:\s|<[^>]+>)*[$(]?\s*-?[\d][\d,.]*")


def _sec_table_html(url):
    raw = _LAST_RAW.get(url) or ""
    rows = [r for r in _ROW.findall(raw) if len(_NUMCELL.findall(r)) >= 2]
    if len(rows) < 3:
        return ""
    try:
        from portal.html_sanitize import sanitize_release_html
        m = re.search(r"(?is)<body[^>]*>(.*)</body>", raw)
        h = sanitize_release_html(_TAGS.sub("", m.group(1) if m else raw))
        return h if len(_ANY.sub("", h).strip()) > 400 else ""
    except Exception:  # noqa: BLE001
        return ""


# USX_EDGAR_V2 (2026-11-10): a 6-K's own document starts with the SEC cover page and ends with the signature page.
COVER_6K = re.compile(
    r"(?i)form 20-f|form 40-f|indicate by check mark|commission file (number|no)|principal executive offices?|"
    r"rule 13a-16|15d-16|regulation s-t rule|translation of registrant|exact name of registrant|"
    r"report of foreign (private )?issuer|securities exchange act of 1934|^for the month of|^washington, d\.?c\.?|"
    r"^united states$|securities and exchange commission|^form 6-k$|^\(?registrant\)?$|^yes\b.{0,12}\bno\b|^_+$")
USX_SKIP = re.compile(     # lines that are never the headline
    r"(?i)^\S+@\S+\.\w+(\s+[\d(). +-]{7,})?$|^((media|investors?|ir)\s+)?(relations\s+)?contacts?\s*:?$|"
    r"^investor relations\s*:?$|^\(?incorporated in\b|^\(?registration (number|no)\b|^\(?reg\. no|^isin\b|"
    r"share code\s*:|trading symbol\s*:|^\(.{0,80}\b(company|group)\W{0,3}\)$|^free translation")


# USX_EDGAR_V3 (2026-11-10): JSE-listed filers file their SENS announcements as 6-Ks in three shapes the reader turned
# away: a cover written with soft hyphens, a cover with blank lines and an "Enclosure:" title, and documents where every
# page is one long line.
SENS_CO = re.compile(r"(?i)harmony gold|gold fields|anglogold|drdgold|sibanye|^(HMY|GFI|AU-US|AU|DRD|SBSW)(\.US)?$")
SENS_MARK = re.compile(r"(?i)share code\s*:|\b(operational|operating|production|trading) (update|statement|results)\b|"
                       r"earnings release|results for the (quarter|year|three|six|nine)|statement by (the )?ceo")
SENS_NOT = re.compile(r"(?i)operating statistics|dealings? in securities|investor presentation|"
                      r"notice of (the )?(electronic )?(annual )?general meeting|publishes its (suite of )?(annual |integrated )?reports?")
_ENC = [None]      # the "Enclosure: <title>" of the 6-K cover just read


def _n(s):
    return s.replace("\u00ad", "-")


def strip_6k_cover(body):
    _ENC[0] = None
    ls = body.split("\n")
    head = _n(" ".join(ls[:40])).lower()
    if "form 6-k" not in head or "securities and exchange commission" not in head:
        return body
    if max(len(l) for l in ls[:40]) > 1500:           # V3: every page is one long line
        out = []
        for l in ls:
            n = _n(l).lower()
            if len(out) < 12 and "securities and exchange commission" in n and "form 6-k" in n:
                continue
            m = re.search(r"SIGNATURES?\s+Pursuant to the requirements", l)
            if m:
                if l[:m.start()].strip():
                    out.append(l[:m.start()])
                break
            out.append(l)
        return "\n".join(out).strip()
    last, gap = -1, 0
    for i, l in enumerate(ls[:260]):
        t = _n(l.strip())
        if not t:
            continue                                  # V3: blank lines do not count toward the gap
        if COVER_6K.search(t):
            last, gap = i, 0
        elif last >= 0:
            gap += 1
            if gap > 12:
                break
    rest = ls[last + 1:]
    for i, l in enumerate(rest[:80]):     # cover, exhibit list, signature page, then "Exhibit 99.1" and the release
        if re.match(r"(?i)^exhibit\s+99(\.\d+)?$", l.strip()):
            rest = rest[i + 1:]
            break
    nb = [i for i, l in enumerate(rest[:30]) if l.strip()][:6]        # V3: "Enclosure: <title of what follows>"
    for a, i in enumerate(nb):
        m = re.match(r"(?i)^enclosures?\s*:\s*(.{12,})$", rest[i].strip())
        if m:
            t, end = m.group(1).strip(), i
            if not re.search(r"20\d\d$", t) and a + 1 < len(nb) and len(rest[nb[a + 1]].strip()) < 40:
                t, end = t + " " + rest[nb[a + 1]].strip(), nb[a + 1]
            _ENC[0] = re.sub(r"\s+", " ", t)[:250]
            rest = rest[end + 1:]
            break
    for i, l in enumerate(rest):
        if i > 3 and re.match(r"(?i)^signatures?$", l.strip()):
            rest = rest[:i]
            break
    return "\n".join(rest).strip()


def sens_reflow(body):
    """USX_EDGAR_V3: SEC wrapper lines off; a page-per-line document becomes headline + paragraphs, table pages dropped."""
    ls = body.split("\n")
    k = 0
    while k < len(ls) and k < 10 and (not ls[k].strip() or re.match(r"(?i)^(6-k|ex-99(\.\d+)?|\d{1,2}|\S+\.html?)$", ls[k].strip())):
        k += 1
    ls = ls[k:]
    if max([len(l) for l in ls] or [0]) <= 1500:
        return "\n".join(ls)
    out = []
    for l in ls:
        l = re.sub(r"\s+", " ", l).strip()
        if not l:
            continue
        if len(l) > 800 and sum(c.isdigit() for c in l) > 0.20 * len(l):
            continue                                  # a page of tables read as one line
        if not out:                                   # first page: SENS preamble, then the headline
            l = re.sub(r"(?i)^.{0,500}?\(\s*[\u201c\"][^)]{0,90}\b(company|group)\b[\u201d\"]?\s*\)\s*", "", l)
            m = re.match(r"((?:[A-Z0-9][A-Z0-9&'\u2019,:;%$/().\u2013-]*\s+){3,18}?[A-Z0-9][A-Z0-9&'\u2019,:;%$/().\u2013-]*)"
                         r"(?=\s+(?:[A-Z][a-z]|[a-z(\u2022\uf0b7]))", l)
            if m:
                hd, tail = m.group(1), l[m.end():].strip()
            else:
                c = re.search(r"\s+\(|\s+vs\.?\s|\s[\u2022\uf0b7]\s", l[:260])
                cut = c.start() if c and c.start() >= 20 else len(l[:110].rsplit(" ", 1)[0])
                hd, tail = l[:cut].strip(), l[cut:].strip()
            if re.match(r"(?i)^(statement by|message from|highlights|overview)\b", hd):
                m2 = re.search(r"(?i)\b((?:operational|operating|production|trading) (?:update|results|statement)|results) for the "
                               r"(?:quarter|three months|six months|nine months|year) ended \d{1,2} [A-Za-z]+ 20\d\d", " ".join(ls))
                if m2:
                    hd, tail = m2.group(0)[0].upper() + m2.group(0)[1:], hd + " " + tail
            out += [hd, ""]
            l = tail
        l = re.sub(r"\s*[\u2022\uf0b7]\s+", "\n\u2022 ", l)
        for para in l.split("\n"):
            para = para.strip()
            if not para:
                continue
            if len(para) <= 700:
                out += [para, ""]
                continue
            cur = ""
            for s_ in re.split(r"(?<=[a-z0-9)%\u201d])\.\s+(?=[A-Z])", para):
                s_ = s_.strip()
                if not s_:
                    continue
                if not s_.endswith("."):
                    s_ += "."
                if cur and len(cur) + len(s_) > 600:
                    out += [cur, ""]
                    cur = s_
                else:
                    cur = (cur + " " + s_).strip()
            if cur:
                out += [cur, ""]
    return "\n".join(out).strip()


def read_release(url, filed, coname):
    """(headline, body, published_date, why_not) for one exhibit."""
    if not re.search(r"(?i)\.(htm|html|txt)$", url):
        return None, None, None, "not a text document"
    raw = sec_get(url, "text/html").decode("utf-8", "replace")
    _LAST_RAW[url] = raw   # SECFMT_V1
    body = html_text(raw) if re.search(r"(?i)\.htm", url) else raw
    body = strip_6k_cover(body)   # USX_EDGAR_V2
    sens = bool(SENS_CO.search((coname or "").strip()))   # USX_EDGAR_V3
    sens_head = body[:1500]
    if sens:
        body = sens_reflow(body)
    if len(body) < 600:
        return None, None, None, "too short (%d chars)" % len(body)
    head = body[:1500]
    ls = [l.strip() for l in body.split("\n") if l.strip()]
    while ls and (SKIP_LINE.search(ls[0]) or USX_SKIP.search(ls[0]) or len(ls[0]) < 4):   # USX_EDGAR_V2
        ls.pop(0)
    top = re.sub(r"\s+", " ", " ".join(ls)[:300])
    m0 = NOT_RELEASE.search(top) or (WEAK_NOT.search(top) if not (IS_RELEASE.search(head) or (sens and SENS_MARK.search(sens_head))) else None)   # USX_EDGAR_V3
    if sens and not m0:
        m0 = SENS_NOT.search(_n(top + " " + (_ENC[0] or "")))
    if m0:
        return None, None, None, "not a release: " + m0.group(0)[:40]
    dl = DATELINE.search(head)
    if not (IS_RELEASE.search(head) or (dl and ACTION.search(head))
            or (sens and SENS_MARK.search(sens_head + " " + head + " " + (_ENC[0] or "")))):   # USX_EDGAR_V3
        return None, None, None, "no release markers"
    fd = dt.date.fromisoformat(filed)
    pub = filed
    for m in DATELINE.finditer(head):          # the first date on or up to 30 days before the filing (a headline
        try:                                    # may name a later date: "to announce Q3 results on October 28")
            d = dt.datetime.strptime("%s %s %s" % (m.group(1)[:3].title(), m.group(2), m.group(3)), "%b %d %Y").date()
        except ValueError:
            continue
        if fd - dt.timedelta(days=30) <= d <= fd:
            pub = d.isoformat()
            break
    title = None
    cn = nname(coname)
    lines = body.split("\n")[:60]
    for i, l in enumerate(lines):
        l = l.strip(" -–—*·")
        if len(l) < 12 or SKIP_LINE.search(l) or LETTERHEAD.search(l) or USX_SKIP.search(l):   # USX_EDGAR_V2
            continue
        if nname(l) == cn or (len(l) < 60 and IS_RELEASE.search(l)) or DL_PARA.search(l):
            continue
        parts = [l]                     # a headline wraps over several lines until the first blank one
        for nxt in lines[i + 1:i + 5]:
            nxt = nxt.strip()
            if not nxt or DL_PARA.search(nxt) or len(" ".join(parts)) > 200:
                break
            parts.append(nxt)
        title = re.sub(r"\s+", " ", " ".join(parts))[:250]
        k = i + len(parts)              # USX_EDGAR_V2: a headline broken by blank lines ("Buenaventura Announces" / "Third Quarter ...")
        for _ in range(2):
            if not re.search(r"(?i)\b(announces?|reports?|and|of|for|the|to|its)$|quarter 20\d\d$", title):
                break
            nx = [(j, x.strip()) for j, x in enumerate(lines[k:k + 3], k) if x.strip()][:1]
            if not nx or DL_PARA.search(nx[0][1]) or SKIP_LINE.search(nx[0][1]) or len(nx[0][1]) > 120:
                break
            title, k = (title + " " + nx[0][1])[:250], nx[0][0] + 1
        title = re.split(r"\s[\uf0b7\u2022\u25cf]\s", title)[0]   # USX_EDGAR_V2: stop at a bullet mark; drop page numbers
        title = re.sub(r"(?<=\d{4}) \d{1,2}$", "", re.sub(r"^\d{1,2}\s+(?=[A-Z][a-z])", "", title)).strip()
        if len(title) < 20:
            title = None
            continue
        break
    if sens and _ENC[0] and len(_ENC[0]) >= 20:       # USX_EDGAR_V3: the cover names what it encloses
        title = _ENC[0]
    if not title:
        return None, None, None, "no headline found"
    return title, body, pub, None


# ---------------------------------------------------------------------------------------------------------- matching
WORD = re.compile(r"[a-z0-9]{3,}")


def body_match(pcon, symbol, day, body):
    """An MNT release of this company within +/-4 days whose text is mostly the same words."""
    d = dt.date.fromisoformat(day)
    lo, hi = (d - dt.timedelta(days=4)).isoformat(), (d + dt.timedelta(days=5)).isoformat()
    a = set(WORD.findall(body[:2500].lower()))
    if len(a) < 40:
        return None
    b_ = X.bare(symbol)
    for eid, rb in pcon.execute(
            "SELECT event_id, substr(raw_body,1,3000) FROM events WHERE (ticker = ? OR ticker = ? OR ticker LIKE ?) "
            "AND published_at >= ? AND published_at < ? "
            "AND +review_status IN ('auto_approved','approved','duplicate_of_wire')",
            (symbol, b_, b_ + ".%", lo, hi)):
        b = set(WORD.findall((rb or "").lower()))
        if b and len(a & b) / float(len(a | b)) >= 0.5:
            return eid
    return None


def publish(rel, body, headline):
    """Classify and post to MNT's ingest (as majors_news / exchange_news do), under this source's name."""
    from pipeline.run import build_envelope, sign_and_post, archive_envelope
    from classify.classifier import classify as classify_event
    try:
        cls = classify_event(headline, body)
    except Exception as e:  # noqa: BLE001
        return False, f"classify: {type(e).__name__} {str(e)[:60]}", None
    cand = {"source_url": rel["url"], "source_name": SOURCE, "published_at": rel["published_at"],
            "raw_headline": headline, "raw_excerpt": body[:1500], "raw_body": body, "raw_html": _sec_table_html(rel["url"]),   # SECFMT_V1
            "ticker": rel["ticker"]}
    cfg = {"ticker": rel["ticker"], "company_id": rel["bare"], "property_id": None}
    uid = X.uid_for("edgar", rel["ticker"], rel["published_date"], headline)
    env = build_envelope(cand, cls, cfg, uid)
    archive_envelope(env)
    code, text = sign_and_post(env)
    if 200 <= code < 300:
        return True, f"{env['event_type']} {env['review_status']}", env.get("event_id")
    return False, f"post {code}: {text[:80]}", None


# ---------------------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--max-ingest", type=int, default=25)
    ap.add_argument("--sweep", type=int, default=30, help="filers whose filing list is read this run (backstop)")
    ap.add_argument("--only")
    a = ap.parse_args()
    con = db()
    if a.stats:
        for r in con.execute("SELECT status, count(*) c, max(filed) m FROM filings GROUP BY 1"):
            print(dict(r))
        for r in con.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 6"):
            print(dict(r))
        print("filers", con.execute("SELECT how, count(*) FROM filers GROUP BY 1").fetchall())
        return 0
    if a.apply == a.dry_run:
        print("pass exactly one of --apply or --dry-run", file=sys.stderr)
        return 2
    started = dt.datetime.utcnow().isoformat()
    since = (dt.date.today() - dt.timedelta(days=a.days)).isoformat()
    filers = build_map(con, a.apply)
    only = {t.strip().upper() for t in a.only.split(",")} if a.only else None
    if only:
        filers = {k: v for k, v in filers.items() if v["ticker"] in only}
    log(f"{VERSION} ({'APPLY' if a.apply else 'DRY RUN'}) {len(filers)} SEC filers in the universe, window {a.days}d "
        f"since {since}")
    found = {}
    for form in ("6-K", "8-K"):
        try:
            for cik, acc, filed, items in current_feed(form):
                if cik in filers and filed >= since:
                    found[acc] = (cik, form, filed, items)
        except Exception as e:  # noqa: BLE001
            log(f"  current feed {form} failed: {type(e).__name__} {str(e)[:60]}")
    n_feed = len(found)
    if only:
        sweep = list(filers)
    else:
        seen = {r[0]: r[1] for r in con.execute("SELECT cik, checked_at FROM sweep")}
        sweep = sorted(filers, key=lambda c: seen.get(c, ""))[:a.sweep]
    for cik in sweep:
        try:
            for c, acc, filed, items in filer_list(cik, since):
                found.setdefault(acc, (c, None, filed, items))
            if a.apply:
                con.execute("INSERT INTO sweep (cik, checked_at) VALUES (?, ?) ON CONFLICT(cik) DO UPDATE SET "
                            "checked_at=excluded.checked_at", (cik, dt.datetime.utcnow().isoformat()))
        except Exception as e:  # noqa: BLE001
            log(f"  filing list {filers[cik]['ticker']} failed: {type(e).__name__} {str(e)[:60]}")
    con.commit()
    settled = {r[0] for r in con.execute("SELECT acc FROM filings WHERE status IN ('ingested','matched','not_release',"
                                         "'skipped') OR (status='error' AND acted_at > datetime('now','-1 day'))")}
    todo = sorted(((acc, v) for acc, v in found.items() if acc not in settled), key=lambda x: x[1][2])
    log(f"  filings: {n_feed} from the current feed, {len(found)} with the sweep of {len(sweep)} filers, "
        f"{len(todo)} not yet settled")
    pcon = sqlite3.connect(f"file:{X.PORTAL_DB}?mode=ro", uri=True)
    now = dt.datetime.utcnow().isoformat()

    def record(acc, f, status, **kw):
        if not a.apply:
            return
        con.execute("INSERT INTO filings (acc,cik,ticker,form,filed,items,status,published_date,title,doc_url,event_id,"
                    "note,acted_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(acc) DO UPDATE SET "
                    "status=excluded.status, published_date=excluded.published_date, title=excluded.title, "
                    "doc_url=excluded.doc_url, event_id=excluded.event_id, note=excluded.note, acted_at=excluded.acted_at",
                    (acc, f["cik"], f["ticker"], kw.get("form"), kw.get("filed"), kw.get("items"), status,
                     kw.get("pub"), kw.get("title"), kw.get("url"), kw.get("eid"), kw.get("note"), now))
        con.commit()

    n_match = n_ing = n_not = n_fail = 0
    budget = a.max_ingest
    for acc, (cik, form, filed, items) in todo:
        f = filers[cik]
        form = form or ("8-K" if items else "6-K")
        meta = dict(form=form, filed=filed, items=items)
        if form == "8-K" and items and not RELEASE_ITEMS.search(items):
            n_not += 1
            record(acc, f, "not_release", note="8-K items " + items, **meta)
            continue
        try:
            docs = documents(cik, acc)
        except Exception as e:  # noqa: BLE001
            n_fail += 1
            record(acc, f, "error", note=f"index: {type(e).__name__} {str(e)[:60]}", **meta)
            continue
        cands = [d for d in docs if d[0].startswith("EX-99")] or \
                ([d for d in docs if d[0] == "6-K"] if form == "6-K" else [])
        rels, whys = [], []
        for typ, desc, url in cands[:3]:
            try:
                title, body, pub, why = read_release(url, filed, f["name"])
            except Exception as e:  # noqa: BLE001
                title, why = None, f"fetch: {type(e).__name__} {str(e)[:50]}"
            if title:
                rels.append((title, body, pub, url))
            else:
                whys.append(f"{typ} {why}")
        if not rels:
            n_not += 1
            record(acc, f, "not_release", note="; ".join(whys)[:300] or "no EX-99 exhibit", **meta)
            log(f"  {f['ticker']:<6} {form} {filed} not a release ({'; '.join(whys)[:90] or 'no EX-99 exhibit'})")
            continue
        for k, (title, body, pub, url) in enumerate(rels):
            key = acc if k == 0 else f"{acc}#{k}"
            rel = {"published_date": pub, "title": title, "ticker": f["symbol"], "bare": X.bare(f["symbol"]),
                   "exchange": "", "url": url}
            eid, _tk = X.find_match(pcon, rel, title=title, body=body)
            eid = eid or body_match(pcon, f["symbol"], pub, body)
            m2 = dict(meta, pub=pub, title=title, url=url)
            if eid:
                n_match += 1
                record(key, f, "matched", eid=eid, **m2)
                log(f"  {f['ticker']:<6} {form} {pub} on MNT already  {title[:70]}")
                continue
            if budget <= 0:
                continue
            budget -= 1
            rel["published_at"] = pub + "T12:00:00Z"
            if a.apply:
                ok, note, new_eid = publish(rel, body, title)
                if ok:
                    n_ing += 1
                    record(key, f, "ingested", eid=new_eid, note=note, **m2)
                else:
                    n_fail += 1
                    record(key, f, "error", note=note, **m2)
                log(f"  {f['ticker']:<6} {'INGESTED' if ok else 'FAILED  '} {form} {pub} {title[:70]} - {note[:40]}")
            else:
                log(f"  {f['ticker']:<6} GAP      {form} {pub} {title[:90]} ({len(body)} chars) {url}")
                log(f"           | {re.sub(chr(10), ' / ', body[:300])}")
    if a.apply:
        con.execute("INSERT INTO runs (started_at,finished_at,mode,filers,found,matched,ingested,not_release,failed,note) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)", (started, dt.datetime.utcnow().isoformat(), "apply", len(filers),
                                                     len(found), n_match, n_ing, n_not, n_fail, f"window={a.days}d"))
        con.commit()
    log(f"done: {len(filers)} filers, {len(found)} filings in window, {n_match} already on MNT, {n_ing} ingested, "
        f"{n_not} not releases, {n_fail} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
