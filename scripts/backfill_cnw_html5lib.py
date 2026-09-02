"""Backfill truncated newswire.ca/cnw events using html5lib parser."""
import argparse, sqlite3, sys, time
import requests
from bs4 import BeautifulSoup

DB = "/opt/mnt/app/portal/portal.db"
UA = "Mozilla/5.0 (compatible; MNTBackfill/1.0; +mnt-relay)"
HEAD = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}

def fetch_clean(url, timeout=20):
    try:
        r = requests.get(url, headers=HEAD, timeout=timeout)
    except Exception as e:
        return None, None, "net:%s" % e
    if r.status_code != 200:
        return None, None, "http %d" % r.status_code
    soup = BeautifulSoup(r.text, "html5lib")
    sec = soup.find("section", class_="release-body")
    if sec is None:
        return None, None, "no release-body"
    for im in sec.find_all("img"):
        for k in ("data-getimg", "data-lazy-src", "data-src"):
            v = im.attrs.get(k)
            if v and not im.attrs.get("src"):
                im.attrs["src"] = v
                break
    return str(sec), sec.get_text("\n").strip(), "ok"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--min-ratio", type=float, default=1.5)
    p.add_argument("--min-new-body", type=int, default=1500)
    p.add_argument("--sleep", type=float, default=1.0)
    args = p.parse_args()
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT event_id, ticker, source_url, raw_headline, "
        "       length(coalesce(raw_html,'')) AS h_len, "
        "       length(coalesce(raw_body,'')) AS b_len "
        "FROM events "
        "WHERE (source_url LIKE '%newswire.ca%' OR source_url LIKE '%cnw.ca%') "
        "  AND length(coalesce(raw_body,'')) < 4000 "
        "  AND length(coalesce(raw_body,'')) > 0 "
        "ORDER BY published_at DESC LIMIT ?", (args.limit,)
    ).fetchall()
    print("  candidates:", len(rows))
    upd = 0; short = 0; httperr = 0; neterr = 0
    for i, r in enumerate(rows, 1):
        url = r["source_url"]; ev = r["event_id"]; old_b = r["b_len"]
        nh, nb, status = fetch_clean(url)
        if not nh:
            tag = "SKIP-HTTP" if "http" in status else "SKIP-NET"
            print("  [%3d] %s %-8s ev=%s %s" % (i, tag, r["ticker"], ev[:14], status))
            if "http" in status: httperr += 1
            else: neterr += 1
            time.sleep(args.sleep); continue
        if len(nb) < args.min_new_body:
            print("  [%3d] short      %-8s ev=%s new_b=%5d (true short) %s" % (i, r["ticker"], ev[:14], len(nb), (r["raw_headline"] or "")[:50]))
            short += 1; time.sleep(args.sleep); continue
        ratio = len(nb) / max(old_b, 1)
        if ratio < args.min_ratio:
            print("  [%3d] no-change  %-8s ev=%s old_b=%5d new_b=%5d ratio=%.2f" % (i, r["ticker"], ev[:14], old_b, len(nb), ratio))
            short += 1; time.sleep(args.sleep); continue
        if args.dry_run:
            print("  [%3d] WOULD-UPDATE %-8s ev=%s old_b=%5d -> new_b=%5d (h=%d)" % (i, r["ticker"], ev[:14], old_b, len(nb), len(nh)))
        else:
            con.execute("UPDATE events SET raw_html=?, raw_body=? WHERE event_id=?", (nh, nb, ev))
            con.commit()
            print("  [%3d] UPDATED  %-8s ev=%s old_b=%5d -> new_b=%5d (h=%d)" % (i, r["ticker"], ev[:14], old_b, len(nb), len(nh)))
        upd += 1; time.sleep(args.sleep)
    print()
    print("  SUMMARY: updated=%d short=%d http=%d net=%d (dry_run=%s)" % (upd, short, httperr, neterr, args.dry_run))

if __name__ == "__main__":
    sys.exit(main() or 0)
