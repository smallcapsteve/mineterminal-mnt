#!/usr/bin/env python3
"""USX_FMP_NEWS_V3 (2026-11-12, Justin: "Short versions from FMP now", "Check twins, then post",
"Skip them" for items with no summary). --build (root, read-only): builds the MNT event rows for US company news
releases from the FMP press-release feed (short versions linking to the wire). --build never writes to MNT; it saves
the rows to ROWS. --apply (mnt user): posts ROWS through portal.db.upsert_event (duplicate guard included). The FMP key is read in
memory from server.js and never printed."""
import sys, os, re, html, time, json, sqlite3, hashlib, difflib, urllib.request, urllib.parse, inspect, datetime
sys.dont_write_bytecode = True
sys.path.insert(0, "/opt/mnt/app")
CO = {"NEM": ["Newmont"], "FCX": ["Freeport"], "SCCO": ["Southern Copper"], "RGLD": ["Royal Gold"],
      "HL": ["Hecla"], "MP": ["MP Materials"], "ALB": ["Albemarle"], "UEC": ["Uranium Energy", "UEC "],
      "AU": ["AngloGold"], "GFI": ["Gold Fields"], "HMY": ["Harmony"], "SBSW": ["Sibanye"],
      "DRD": ["DRDGOLD"], "BVN": ["Buenaventura", "Compania de Minas Buenaventura"],
      "SQM": ["SQM", "Sociedad Quimica"], "FTCO": ["Fortitude Gold"], "REEMF": ["Rare Element"]}
WIRE = [("businesswire.com", "Business Wire"), ("prnewswire.com", "PR Newswire"),
        ("globenewswire.com", "GlobeNewswire"), ("accessnewswire.com", "Access Newswire"),
        ("accesswire.com", "Access Newswire"), ("newsfilecorp.com", "Newsfile")]
SRC = [("businesswire.com", "businesswire"), ("prnewswire.com", "prnewswire"), ("globenewswire.com", "globenewswire"),
       ("accessnewswire.com", "accessnewswire"), ("accesswire.com", "accessnewswire"), ("newsfilecorp.com", "newsfile")]
WIRE_NAMES = set(n for _, n in SRC)
ADVERT = re.compile(r"(?i)class action|investor alert|shareholder alert|law firm|llp|deadline|investigat|lawsuit|rosen|pomerantz|levi & korsinsky")

def key():
    s = open("/root/minetracker/server.js", encoding="utf-8", errors="replace").read()
    m = re.search(r"""(?i)fmp[_a-z]*(?:api)?[_]?key['" ]*[=:]['" ]*([A-Za-z0-9]{20,})""", s)
    return m.group(1) if m else None

def norm(h):
    return re.sub(r"[^a-z0-9 ]", "", (h or "").lower()).strip()

LIMIT = int(os.environ.get("USX_FMP_LIMIT", "25"))
ROWS = "/var/tmp/usx-sens/hist/fmp_news_rows.json"
STOP = set("the and for its inc corp corporation company ltd limited plc announces announce to of on at in a an".split())

def core_of(text):
    cut = -1
    for mark in ("--", " / "):
        i = text.rfind(mark, 0, 140)
        if i >= 0:
            cut = max(cut, i + len(mark))
    return text[cut:].strip() if cut >= 0 else text

def words(h, names):
    drop = set(norm(" ".join(names)).split()) | STOP
    return set(w for w in norm(h).split() if len(w) > 2 and w not in drop)

def grams(text, n=5):
    w = norm(text).split()
    return set(" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1)))

def twin_by_text(core, body, title=""):
    """True when the feed summary's wording is found in a stored full-text copy (same release, other headline).
    Only full-text copies count (2,000+ characters), and every decimal figure in the feed headline must be in
    that copy, so two different drill releases with the same boilerplate are not paired."""
    g = grams(core)
    if len(g) < 12 or len(body or "") < 2000:
        return False
    if any(x not in body for x in re.findall(r"\d+\.\d+", title or "")):
        return False
    return len(g & grams(body[:60000])) / float(len(g)) >= 0.25

def selftest():
    conn = sqlite3.connect("file:/opt/mnt/app/portal/portal.db?mode=ro", uri=True, timeout=20)
    n = 0
    for row in json.load(open(ROWS)):
        core = core_of(row["raw_body"].split("\n\n")[0]); day = row["published_at"][:10]
        for eid, h, d, b, sn in conn.execute("SELECT event_id, raw_headline, substr(published_at,1,10), COALESCE(raw_body,''), source_name FROM events WHERE ticker = ? AND event_id != ?", (row["ticker"], row["event_id"])):
            try:
                gap = abs((datetime.date.fromisoformat(d) - datetime.date.fromisoformat(day)).days)
            except Exception:
                continue
            if gap <= 4 and twin_by_text(core, b, row["raw_headline"]):
                n += 1; print("TWIN  [%s] %s %s\n        = %s (%s) keep=%s drop=%s" % (row["ticker"], day, row["raw_headline"][:100], (h or "")[:100], sn, eid[:12], row["event_id"][:12])); break
    print("=== SELFTEST twins among posted rows: %d" % n)
    return 0

def build():
    k = key()
    if not k:
        print("no FMP key found"); return 1
    conn = sqlite3.connect("file:/opt/mnt/app/portal/portal.db?mode=ro", uri=True, timeout=20)
    tot = {"feed": 0, "other_co": 0, "advert": 0, "on_mnt": 0, "twin": 0, "empty": 0, "add": 0}
    rows = []
    for sym, names in CO.items():
        url = "https://financialmodelingprep.com/stable/news/press-releases?" + urllib.parse.urlencode({"symbols": sym, "limit": LIMIT, "apikey": k})
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
                items = json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            print("%s: feed error %s" % (sym, type(e).__name__)); continue
        if not isinstance(items, list):
            print("%s: feed answered a non-list" % sym); continue
        tk = sym + ".US"
        have = conn.execute("SELECT raw_headline, substr(published_at,1,10), source_url, COALESCE(raw_body,''), source_name FROM events WHERE ticker = ?", (tk,)).fetchall()
        for it in items:
            tot["feed"] += 1
            title = (it.get("title") or "").strip(); link = it.get("url") or ""
            text = re.sub(r"\s+", " ", it.get("text") or "").strip()
            day = (it.get("publishedDate") or "")[:10]
            if ADVERT.search(title):
                tot["advert"] += 1; continue
            if not any(title.lower().startswith(n.lower()) for n in names):
                tot["other_co"] += 1; continue
            nt = norm(title); core = core_of(text); nc = norm(core); why = None
            wt = words(title, names)
            for h, d, u, b, sn in have:
                if u and link and u.split("?")[0].rstrip("/") == link.split("?")[0].rstrip("/"):
                    why = ("on_mnt", h, sn); break
                try:
                    gap = abs((datetime.date.fromisoformat(d) - datetime.date.fromisoformat(day)).days)
                except Exception:
                    continue
                if gap <= 3 and difflib.SequenceMatcher(None, nt, norm(h)).ratio() >= 0.82:
                    why = ("on_mnt", h, sn); break
                if gap <= 4:
                    wh = words(h, names)
                    nums = lambda x: sorted(re.findall(r"\d+(?:\.\d+)?", x or ""))
                    if (wt and wh and sn not in WIRE_NAMES and nums(title) == nums(h)
                            and len(wt & wh) / float(len(wt | wh)) >= 0.5):
                        why = ("twin", h, sn); break
                    if twin_by_text(core, b, title):
                        why = ("twin", h, sn); break
            if why:
                tot[why[0]] += 1
                if why[0] == "twin":
                    print("TWIN  [%s] %s %s\n        = %s (%s)" % (tk, day, title[:110], (why[1] or "")[:110], why[2]))
                continue
            if len(nc) < 80 or difflib.SequenceMatcher(None, nc, nt).ratio() >= 0.8:
                tot["empty"] += 1
                print("EMPTY [%s] %s %s" % (tk, day, title[:120])); continue
            host = urllib.parse.urlparse(link).netloc.lower()
            sname = next((n for d, n in SRC if d in host), None)
            if not sname or not day or not link:
                print("SKIP  [%s] no known wire in link: %s" % (tk, host)); continue
            label = next(n for d, n in WIRE if d in host)
            tail = "This is a short version. Click 'Original source' to read the full release on %s." % label
            rows.append({"event_id": hashlib.sha256((link + "|" + day).encode()).hexdigest(), "ticker": tk,
                         "event_type": "news_release", "source_name": sname, "source_url": link,
                         "raw_headline": title, "raw_excerpt": text[:1500], "raw_body": text + "\n\n" + tail,
                         "raw_html": "<p>%s</p><p>%s</p>" % (html.escape(text), html.escape(tail)),
                         "published_at": day + "T12:00:00Z", "review_status": "auto_approved"})
            tot["add"] += 1
            print("ADD   [%s] %s %s (%s, %d chars)" % (tk, day, title[:110], sname, len(text)))
    tmp = ROWS + ".tmp"
    json.dump(rows, open(tmp, "w"), indent=1); os.chmod(tmp, 0o644); os.replace(tmp, ROWS)
    print("=== BUILD TOTALS %s" % json.dumps(tot))
    return 0

def apply():
    from portal import db as D
    print("upsert_event%s" % inspect.signature(D.upsert_event))
    rows = json.load(open(ROWS))
    ok = err = 0
    for row in rows:
        for attempt in range(4):
            try:
                res = D.upsert_event(dict(row)); ok += 1
                print("POST  [%s] %s -> %r" % (row["ticker"], row["raw_headline"][:90], res)); break
            except Exception as e:
                if "locked" in str(e).lower() and attempt < 3:
                    time.sleep(8); continue
                err += 1; print("ERR   [%s] %s: %s: %s" % (row["ticker"], row["raw_headline"][:70], type(e).__name__, str(e)[:160])); break
    conn = sqlite3.connect("file:/opt/mnt/app/portal/portal.db?mode=ro", uri=True, timeout=20)
    there = 0
    for row in rows:
        r = conn.execute("SELECT review_status, slug FROM events WHERE event_id = ?", (row["event_id"],)).fetchone()
        there += 1 if r else 0
        print("CHECK [%s] %s" % (row["ticker"], ("%s  /%s" % (r[0], r[1])) if r else "NOT STORED (guard turned it away or error)"))
    print("=== APPLY rows %d, calls ok %d, errors %d, stored %d" % (len(rows), ok, err, there))
    print("US events now: %s" % conn.execute("SELECT COUNT(*) FROM events WHERE ticker LIKE '%.US'").fetchone()[0])
    return 0 if not err else 2

if __name__ == "__main__":
    sys.exit(apply() if "--apply" in sys.argv else selftest() if "--selftest" in sys.argv else build())
