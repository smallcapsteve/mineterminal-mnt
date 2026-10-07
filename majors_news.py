#!/usr/bin/env python3
"""majors_news.py - MNT_MAJORS_NEWS_V1.2 (2026-09-29, checklist H22; V1.1 backs off on Q4 429s; V1.2 paces Q4 at 75 s).

Large producers often publish news only on their own investor sites, or through wires Mining News Terminal does not
read (Barrick's newest release on MNT was 11 August; Hudbay, Cameco and First Quantum had none since July). This
collector reads the companies' own newsrooms and fills the gaps, the same way exchange_news.py fills gaps from the
exchanges:

  1. list each company's newest releases from its newsroom feed - Q4 Inc's public PressRelease feed (the platform
     most of these investor sites run on) or, for WordPress sites, the site's RSS feed; one request per company, a
     pause between companies because Q4 answers 429 to rapid requests;
  2. skip any release MNT already shows (exchange_news.find_match: same company, +/-3 days, same headline);
  3. read the release text (the feed's body, else the release page) and post it to MNT's own ingest, classified the
     same way as every other source, with source_name "companysite" ("Company Site" on the sites).

Usage: majors_news.py --dry-run | --apply [--days 45] [--max-ingest 30] [--only ABX,HBM] [--stats]
State: /var/lib/mnt-majors/majors_news.db (what was seen, matched, ingested or failed, and every run).
"""
import argparse, datetime as dt, email.utils, html, json, os, re, sqlite3, sys, time, urllib.error, urllib.request

APP = "/opt/mnt/app"
sys.path.insert(0, APP)
import exchange_news as X   # noqa: E402  (find_match, norm, bare, uid_for, PORTAL_DB)

DB_PATH = os.environ.get("MAJORS_NEWS_DB", "/var/lib/mnt-majors/majors_news.db")
UA = X.UA
PAUSE_S = 12
PAUSE_Q4_S = 75    # Q4 refused a second site 12 s after the first on 2026-09-29 (06:17 run); ~1 request a minute passes
RETRY_429_S = 90   # Q4 rate-limits per caller across all its hosts: back off once, then leave Q4 alone this run
FETCH_TIMEOUT_S = 25

# The companies: majors_news.json beside this file - the largest companies on Mine Terminal Pro whose investor sites
# answer Q4's feed (checked 2026-09-29, one request every 12 s). symbol = MNT's ticker; host = the site.
MAJORS_JSON = os.environ.get("MAJORS_JSON", os.path.join(os.path.dirname(os.path.abspath(__file__)), "majors_news.json"))

FEED = ("/feed/PressRelease.svc/GetPressReleaseList?LanguageId=1&bodyType={body}&pressReleaseDateFilter=3"
        "&categoryId=00000000-0000-0000-0000-000000000000&pageSize={n}&pageNumber=0&tagList=&includeTags=true"
        "&year=-1&excludeSelection=1")

SCHEMA = """
CREATE TABLE IF NOT EXISTS releases (
    uid TEXT PRIMARY KEY, ticker TEXT NOT NULL, host TEXT, published_date TEXT NOT NULL, title TEXT, url TEXT,
    status TEXT NOT NULL,            -- matched | ingested | error | skipped
    matched_event TEXT, note TEXT, first_seen TEXT DEFAULT CURRENT_TIMESTAMP, acted_at TEXT);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, mode TEXT, companies INTEGER, listed INTEGER,
    matched INTEGER, ingested INTEGER, failed INTEGER, note TEXT);
"""


def log(msg):
    print(msg, flush=True)


def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def get(url, accept="*/*"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as r:
        return r.read(6 * 1024 * 1024)


_TAGS = re.compile(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>")
_BLOCK = re.compile(r"(?i)<\s*(br|/p|/div|/li|/h[1-6]|/tr|p|li|tr)\b[^>]*>")
_ANY = re.compile(r"(?s)<[^>]+>")


def html_text(h):
    t = _TAGS.sub(" ", h or "")
    t = _BLOCK.sub("\n", t)
    t = html.unescape(_ANY.sub(" ", t))
    lines = [re.sub(r"[ \t ]+", " ", l).strip() for l in t.split("\n")]
    out, blank = [], 0
    for l in lines:
        if not l:
            blank += 1
            if blank == 1 and out:
                out.append("")
            continue
        blank = 0
        out.append(l)
    return "\n".join(out).strip()


_MENU_WORDS = ("home", "about", "about us", "who we are", "overview", "leadership", "governance", "investors",
               "careers", "contact", "contact us", "sustainability", "operations", "news", "media", "menu")


def looks_like_menu(text):
    """MNT_FIX_20261003: the site's navigation, not a release (AEM 2026-09-28 was stored as "Home / Who We Are /
    Overview / Leadership ..."). Short lines dominate the top and several are menu words."""
    lines = [l.strip() for l in (text or "").split("\n") if l.strip()][:30]
    if len(lines) < 8:
        return False
    short = sum(1 for l in lines if len(l) <= 32)
    menu = sum(1 for l in lines if l.lower().rstrip(" >/|") in _MENU_WORDS)
    return short >= 0.7 * len(lines) and menu >= 3


def page_text(url):
    """The release page's text, when the feed carries no body. Q4 release pages keep the release in
    .module_body / .module-details_body, WordPress pages in <article> or .entry-content; else the whole page."""
    raw = get(url, "text/html").decode("utf-8", "replace")
    m = re.search(r'(?is)<div[^>]+class="[^"]*(module_body|module-details_body|q4default)[^"]*"[^>]*>(.*)', raw)
    if m:
        return html_text(m.group(2))
    m = re.search(r"(?is)<article\b[^>]*>(.*?)</article>", raw) or \
        re.search(r'(?is)<div[^>]+class="[^"]*entry-content[^"]*"[^>]*>(.*)', raw)
    t = html_text(m.group(1) if m else raw)
    return "" if looks_like_menu(t) else t        # MNT_FIX_20261003: unreadable, retried later, never stored


def _tag(x, name):
    m = re.search(r"(?is)<" + re.escape(name) + r"\b[^>]*>(.*?)</" + re.escape(name) + ">", x)
    if not m:
        return ""
    v = m.group(1).strip()
    if v.startswith("<![CDATA["):
        v = v[9:]
        v = v[:-3] if v.endswith("]]>") else v
    return v.strip()


def rss_list(co, n):
    """A WordPress (or any RSS 2.0) news feed: title, link, pubDate, and content:encoded when the site includes it."""
    raw = get(co["feed"], "application/rss+xml, application/xml").decode("utf-8", "replace")
    out = []
    for it in re.findall(r"(?is)<item\b.*?</item>", raw)[:n]:
        try:
            day = email.utils.parsedate_to_datetime(_tag(it, "pubDate")).date().isoformat()
        except (TypeError, ValueError):
            continue
        out.append({"published_date": day, "title": html.unescape(re.sub(r"<[^>]+>", "", _tag(it, "title"))).strip(),
                    "url": _tag(it, "link"), "body_html": _tag(it, "content:encoded")})
    return out


def q4_list(co, n, with_body):
    url = "https://" + co["host"] + co.get("path", FEED).format(body=3 if with_body else 0, n=n)
    d = json.loads(get(url, "application/json").decode("utf-8", "replace"))
    out = []
    for x in d.get("GetPressReleaseListResult") or []:
        when = x.get("PressReleaseDate") or ""
        try:
            day = dt.datetime.strptime(when[:10], "%m/%d/%Y").date().isoformat()
        except ValueError:
            continue
        link = x.get("LinkToDetailPage") or ""
        if re.search(r"(?i)blog|stories", link):
            continue    # Q4 sites list their feature stories and blog posts in the same feed; news releases only
        if link.startswith("/"):
            link = "https://" + co["host"] + link
        out.append({"published_date": day, "title": (x.get("Headline") or "").strip(),
                    "url": link, "body_html": x.get("Body") or ""})
    return out


def publish(rel, body, headline):
    """Classify and post to MNT's ingest - exchange_news.publish, with this source's name."""
    from pipeline.run import build_envelope, sign_and_post, archive_envelope
    from classify.classifier import classify as classify_event
    try:
        cls = classify_event(headline, body)
    except Exception as e:  # noqa: BLE001
        return False, f"classify: {type(e).__name__} {str(e)[:60]}"
    cand = {"source_url": rel["url"], "source_name": "companysite",
            "published_at": rel["published_date"] + "T12:00:00Z", "raw_headline": headline,
            "raw_excerpt": body[:1500], "raw_body": body, "raw_html": "", "ticker": rel["ticker"]}
    cfg = {"ticker": rel["ticker"], "company_id": rel["bare"], "property_id": None}
    env = build_envelope(cand, cls, cfg, X.uid_for("companysite", rel["ticker"], rel["published_date"], headline))
    archive_envelope(env)
    code, text = sign_and_post(env)
    if 200 <= code < 300:
        return True, f"{env['event_type']} {env['review_status']}"
    return False, f"post {code}: {text[:80]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--max-ingest", type=int, default=30)
    ap.add_argument("--per-company", type=int, default=12)
    ap.add_argument("--only")
    a = ap.parse_args()
    con = db()
    if a.stats:
        for r in con.execute("SELECT ticker, status, count(*) c, max(published_date) m FROM releases GROUP BY 1,2 ORDER BY 1,2"):
            print(dict(r))
        for r in con.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 5"):
            print(dict(r))
        return 0
    if a.apply == a.dry_run:
        print("pass exactly one of --apply or --dry-run", file=sys.stderr)
        return 2
    majors = json.load(open(MAJORS_JSON))
    only = {t.strip().upper() for t in a.only.split(",")} if a.only else None
    cutoff = (dt.date.today() - dt.timedelta(days=a.days)).isoformat()
    started = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat()
    log(f"MNT_MAJORS_NEWS_V1.2 ({'APPLY' if a.apply else 'DRY RUN'}) window={a.days}d since {cutoff}, "
        f"{len(majors)} companies")
    pcon = sqlite3.connect(f"file:{X.PORTAL_DB}?mode=ro", uri=True)
    settled = {r[0] for r in con.execute("SELECT uid FROM releases WHERE status IN ('matched','ingested','skipped') "
                                         "OR (status='error' AND acted_at > datetime('now','-1 day'))")}
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat()

    def record(rel, status, event=None, note=None):
        if not a.apply:
            return
        con.execute("INSERT INTO releases (uid,ticker,host,published_date,title,url,status,matched_event,note,acted_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET status=excluded.status, "
                    "matched_event=excluded.matched_event, note=excluded.note, acted_at=excluded.acted_at",
                    (rel["uid"], rel["ticker"], rel["host"], rel["published_date"], rel["title"], rel["url"],
                     status, event, note, now))
        con.commit()

    n_co = n_list = n_match = n_ing = n_fail = 0
    budget = a.max_ingest
    q4_blocked = False
    for i, co in enumerate(majors):
        if only and co["bare"] not in only:
            continue
        is_q4 = co.get("kind") != "rss"
        if i and n_co:
            time.sleep(PAUSE_Q4_S if (is_q4 and not q4_blocked) else PAUSE_S)
        n_co += 1
        if is_q4 and q4_blocked:
            log(f"  {co['bare']:<6} SKIPPED  Q4 is rate-limiting this run; the next run picks it up")
            n_fail += 1
            continue
        try:
            try:
                items = (q4_list(co, a.per_company, with_body=True) if is_q4 else rss_list(co, a.per_company))
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    raise
                log(f"  {co['bare']:<6} 429, waiting {RETRY_429_S}s and trying once more")
                time.sleep(RETRY_429_S)
                try:
                    items = (q4_list(co, a.per_company, with_body=True) if is_q4 else rss_list(co, a.per_company))
                except urllib.error.HTTPError as e2:
                    if e2.code == 429 and is_q4:
                        q4_blocked = True
                    raise
        except Exception as e:  # noqa: BLE001
            log(f"  {co['bare']:<6} LIST FAILED {type(e).__name__} {str(e)[:70]}")
            n_fail += 1
            continue
        items = [x for x in items if x["published_date"] >= cutoff and x["title"]]
        n_list += len(items)
        newest = max((x["published_date"] for x in items), default="-")
        got = 0
        for x in items:
            rel = dict(x, ticker=co["symbol"], bare=co["bare"], exchange=co.get("exchange", "TSX"),
                       host=co.get("host") or re.sub(r"^https?://([^/]+).*", r"\1", co.get("feed", "")),
                       source="companysite")
            if not rel["url"]:
                continue
            rel["uid"] = X.uid_for("companysite", co["symbol"], x["published_date"], x["title"])
            if rel["uid"] in settled:
                continue
            eid, _wrong = X.find_match(pcon, rel, title=x["title"])
            if eid:
                n_match += 1
                record(rel, "matched", event=eid)
                continue
            if budget <= 0:
                continue
            body = html_text(x["body_html"]) if x["body_html"] else ""
            note = None
            if len(body) < 200:
                try:
                    time.sleep(PAUSE_Q4_S if is_q4 else 3)
                    body = page_text(x["url"])
                except Exception as e:  # noqa: BLE001
                    body = ""
                    note = f"fetch: {type(e).__name__} {str(e)[:60]}"
            if len(body) < 200:
                n_fail += 1
                record(rel, "error", note=note or f"text too short ({len(body)} chars)")
                log(f"  {co['bare']:<6} UNREADABLE {x['published_date']} {x['title'][:60]}")
                continue
            budget -= 1
            got += 1
            if a.apply:
                ok, note = publish(rel, body, x["title"])
                if ok:
                    n_ing += 1
                    record(rel, "ingested", note=note)
                else:
                    n_fail += 1
                    record(rel, "error", note=note)
                log(f"  {co['bare']:<6} {'INGESTED' if ok else 'FAILED  '} {x['published_date']} {x['title'][:60]} - {note[:40]}")
            else:
                log(f"  {co['bare']:<6} GAP      {x['published_date']} {x['title'][:70]} ({len(body)} chars)")
        log(f"  {co['bare']:<6} {len(items)} listed since {cutoff}, newest {newest}, {got} new")
    if a.apply:
        con.execute("INSERT INTO runs (started_at,finished_at,mode,companies,listed,matched,ingested,failed,note) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", (started, dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(), "apply", n_co, n_list,
                                                   n_match, n_ing, n_fail, f"window={a.days}d"))
        con.commit()
    log(f"done: {n_co} companies, {n_list} releases listed, {n_match} already on MNT, {n_ing} ingested, "
        f"{n_fail} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
