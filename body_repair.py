#!/usr/bin/env python3
"""body_repair.py - INGEST_FIX3_V1 (2026-10-12). Justin: "install fix 1 and 2, then start on fix 3"; scope chosen:
"Collectors + repair". Findings: mnt-relay/payloads/drillDF/MNT_DRILL_FIX3_INGESTION_FINDINGS_2026-10-12.md.

Re-fetches release text that was stored incomplete, and replaces it when the new copy is the same release, longer:
  --accesswire  AccessNewswire placeholders ("This release is published on Accesswire. Click 'Original source ...'")
                -> sources.accesswire.fetch_body (the rendered fetch the collector's main path uses)
  --wires       cnw / prnewswire releases stored short (the page markup cut the body at "Continue Reading")
                -> the collectors' own body extraction (html5lib since INGEST_FIX3_V1)
  --pdf         TMX / CSE PDF releases cut at 8 pages -> exchange_news.pdf_text(max_pages=40)
Which releases: --since YYYY-MM-DD (published_at index range) and/or --drill (the releases on /drills, by key).

A new copy is kept only when
  * it is longer than the stored one (by 200+ characters; 1.5x for the wires);
  * it is the same release: it starts like the stored text (whitespace ignored), or, for a placeholder, it contains
    the headline's words;
  * the release is not in an accuracy label set (the gates' labelled releases keep the text they were labelled on;
    they are listed; --include-labelled replaces them too).
For each release replaced:
  * the stored row (raw_body, raw_html, raw_excerpt, categories) is copied first into data/body_repair.db;
  * events.raw_body / raw_html / raw_excerpt are replaced; categories: a placeholder / cut wire copy is categorized
    afresh from the full text; for a PDF only what the added pages change is applied (see apply());
  * the release's runs for each reader's current version (portal.extractors.REGISTRY) are deleted, so the 30-minute
    facts sync reads it again and the publishers update the pages.
--dry-run fetches and compares but writes nothing. --restore TAG puts back every row run TAG replaced.

  body_repair.py --accesswire --since 2025-01-01 --dry-run --limit 20
  body_repair.py --wires --since 2026-01-01 --tag fix3-wires-20261012
  body_repair.py --pdf --drill --tag fix3-pdf-drill-20261013          # long: under systemd-run
  body_repair.py --restore fix3-wires-20261012
"""
import argparse
import json
import re
import sqlite3
import sys
import time

sys.path.insert(0, "/opt/mnt/app")

DB = "/opt/mnt/app/portal/portal.db"
SIDE = "/opt/mnt/app/data/body_repair.db"
SETS = "/opt/mnt/app/accuracy/sets"
PLACEHOLDER = "This release is published on Accesswire."
PDF_PAGES = 40
SIDE_SCHEMA = """
CREATE TABLE IF NOT EXISTS repaired (
  tag         TEXT NOT NULL,
  event_id    TEXT NOT NULL,
  kind        TEXT NOT NULL,
  old_body    TEXT, old_html TEXT, old_excerpt TEXT, old_categories TEXT,
  new_len     INTEGER, old_len INTEGER,
  new_categories TEXT,
  runs_cleared INTEGER,
  at          TEXT NOT NULL DEFAULT (datetime('now')),
  restored_at TEXT,
  PRIMARY KEY (tag, event_id)
);
"""


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def same_start(old, new, n=600):
    a, b = norm(old), norm(new)
    k = min(n, max(0, len(a) - 40))
    return k >= 80 and b[:k] == a[:k]


def headline_in(headline, new):
    words = [w for w in re.findall(r"[a-z0-9]+", (headline or "").lower()) if len(w) > 2]
    if len(words) < 3:
        return False
    low = set(re.findall(r"[a-z0-9]+", (new or "")[:4000].lower()))
    return sum(w in low for w in words) >= 0.8 * len(words)


def labelled_ids():
    import glob
    out = set()
    for f in glob.glob(SETS + "/*.json"):
        try:
            for it in json.load(open(f)).get("items") or []:
                if it.get("event_id"):
                    out.add(it["event_id"])
        except Exception:  # noqa: BLE001
            pass
    return out


_VERSIONS = None


def registry_versions():
    """(reader, current version) for every reader; imported only when a release is actually replaced or restored."""
    global _VERSIONS
    if _VERSIONS is None:
        from portal.extractors import REGISTRY
        _VERSIONS = [(s.name, s.version) for s in REGISTRY]
    return _VERSIONS


# ------------------------------------------------------------------ candidates
def candidates(ro, kind, since, drill, limit):
    where = {
        "accesswire": "source_name='accessnewswire' AND raw_body LIKE 'This release is published on Accesswire.%'",
        "wires": "source_name IN ('cnw','prnewswire') AND length(raw_body) < 2500 AND raw_html LIKE '%release-body%'",
        "pdf": "source_name IN ('tmx','cse') AND (raw_html IS NULL OR raw_html='') AND source_url IS NOT NULL",
    }[kind]
    ids = []
    if since:
        ids += [r[0] for r in ro.execute(
            "SELECT event_id FROM events INDEXED BY idx_events_published_at WHERE published_at >= ? AND " + where +
            " ORDER BY published_at DESC", (since,))]
    if drill:
        seen = set(ids)
        for (eid,) in ro.execute("SELECT event_id FROM drill_results"):
            if eid in seen:
                continue
            if ro.execute("SELECT 1 FROM events WHERE event_id=? AND " + where, (eid,)).fetchone():
                ids.append(eid)
                seen.add(eid)
    return ids


# ------------------------------------------------------------------ fetchers
class Fetch:
    def __init__(self):
        self._client = None
        self._aw = None

    def accesswire(self, row):
        if self._aw is None:
            from sources import accesswire as aw
            self._aw = aw
        got = self._aw.fetch_body({"source_url": row["source_url"], "raw_headline": row["raw_headline"],
                                   "published_at": row["published_at"]})
        if got.get("fetch_error"):
            return None, "fetch: " + str(got["fetch_error"])[:80]
        return {"raw_body": got.get("raw_body") or "", "raw_html": got.get("raw_html") or "",
                "raw_excerpt": got.get("raw_excerpt") or ""}, ""

    def wires(self, row):
        """The cnw / prnewswire collectors' own extraction (same selectors, same tags removed), parsed with html5lib
        as they do since INGEST_FIX3_V1 (kept here so a repair does not depend on which collector file is live)."""
        import httpx
        from bs4 import BeautifulSoup
        if self._client is None:
            self._client = httpx.Client(headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 "
                                                       "(KHTML, like Gecko) Version/17.2 Safari/605.1.15"},
                                        timeout=25, follow_redirects=True)
        r = self._client.get(row["source_url"])
        if r.status_code != 200:
            return None, f"http {r.status_code}"
        soup = BeautifulSoup(r.text, "html5lib")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript", "iframe"]):
            tag.decompose()
        for sel in ("section.release-body", "div.release-body", "div#release-body", "div.release-body-text",
                    "section[data-module='release-body']", "article", "main article", "main"):
            for el in soup.select(sel):
                txt = el.get_text("\n\n", strip=True)
                if len(txt) > 400:
                    return {"raw_body": txt, "raw_html": str(el), "raw_excerpt": None}, ""
        return None, "no body on the page"

    def pdf(self, row):
        import exchange_news as X
        data = X.http_get(row["source_url"])
        if X.is_docx(data):
            return None, "docx"
        if not data[:5].startswith(b"%PDF"):
            return None, "not a pdf"
        from pypdf import PdfReader
        import io
        n = len(PdfReader(io.BytesIO(data)).pages)
        if n <= 8:
            return None, f"{n} pages (not cut)"
        return {"raw_body": X.pdf_text(data, max_pages=PDF_PAGES), "raw_html": None, "raw_excerpt": None}, f"{n} pages"

    def close(self):
        if self._client is not None:
            self._client.close()
        if self._aw is not None:
            try:
                self._aw.close_browser()
            except Exception:  # noqa: BLE001
                pass


def accept(kind, row, new):
    old = row["raw_body"] or ""
    nb = new["raw_body"] or ""
    if len(nb) < len(old) + 200:
        return False, f"not longer ({len(old)} -> {len(nb)})"
    if kind == "wires" and len(nb) < 1.5 * len(old):
        return False, f"not 1.5x ({len(old)} -> {len(nb)})"
    if kind == "accesswire":
        if not headline_in(row["raw_headline"], nb):
            return False, "headline not in the fetched text"
    elif not same_start(old, nb):
        return False, "does not start like the stored text"
    return True, ""


# ------------------------------------------------------------------ apply / restore
def apply(rw, side, tag, kind, row, new, dry):
    from portal.categorize import categorize, format_categories
    body = new["raw_body"]
    html = row["raw_html"] if new["raw_html"] is None else new["raw_html"]
    excerpt = row["raw_excerpt"] if new["raw_excerpt"] is None else new["raw_excerpt"]
    try:
        from portal.cfemail import decode_row
        h2, b2, x2, n = decode_row(html, body, excerpt)
        if n:
            html, body, excerpt = h2, b2, x2
    except Exception:  # noqa: BLE001
        pass
    # categories. A placeholder or a cut wire copy was categorized from a fragment (often the headline alone): the
    # full text is categorized as ingestion would do now. A PDF's first 8 pages were real text: only what the added
    # pages change is applied (tags the categorizer adds for the new text are added, tags it drops are dropped, every
    # other stored tag stays, so a newer categorizer or a hand edit does not move other tags).
    try:
        now = categorize(row["raw_headline"], body, row["ticker"])
        if kind != "pdf":
            cats = format_categories(now) or None
        else:
            was = categorize(row["raw_headline"], row["raw_body"] or "", row["ticker"])
            stored = [x for x in (row["categories"] or "").split("|") if x]
            keep = [x for x in stored if not (x in was and x not in now)]
            cats = format_categories(keep + [x for x in now if x not in was and x not in keep]) or None
    except Exception:  # noqa: BLE001
        cats = row["categories"]
    if dry:
        return cats, 0
    side.execute("INSERT OR REPLACE INTO repaired(tag, event_id, kind, old_body, old_html, old_excerpt, old_categories, "
                 "new_len, old_len, new_categories, runs_cleared) VALUES (?,?,?,?,?,?,?,?,?,?,0)",
                 (tag, row["event_id"], kind, row["raw_body"], row["raw_html"], row["raw_excerpt"], row["categories"],
                  len(body), len(row["raw_body"] or ""), cats))
    side.commit()
    rw.execute("BEGIN IMMEDIATE")
    try:
        rw.execute("UPDATE events SET raw_body=?, raw_html=?, raw_excerpt=?, categories=? WHERE event_id=?",
                   (body, html, excerpt, cats, row["event_id"]))
        n = 0
        for name, ver in registry_versions():
            n += rw.execute("DELETE FROM fx_runs WHERE extractor=? AND version=? AND event_id=?",
                            (name, ver, row["event_id"])).rowcount
        rw.execute("COMMIT")
    except Exception:
        rw.execute("ROLLBACK")
        raise
    side.execute("UPDATE repaired SET runs_cleared=? WHERE tag=? AND event_id=?", (n, tag, row["event_id"]))
    side.commit()
    return cats, n


def restore(rw, side, tag):
    rows = side.execute("SELECT event_id, old_body, old_html, old_excerpt, old_categories FROM repaired "
                        "WHERE tag=? AND restored_at IS NULL", (tag,)).fetchall()
    for eid, b, h, x, c in rows:
        rw.execute("BEGIN IMMEDIATE")
        rw.execute("UPDATE events SET raw_body=?, raw_html=?, raw_excerpt=?, categories=? WHERE event_id=?", (b, h, x, c, eid))
        for name, ver in registry_versions():
            rw.execute("DELETE FROM fx_runs WHERE extractor=? AND version=? AND event_id=?", (name, ver, eid))
        rw.execute("COMMIT")
        side.execute("UPDATE repaired SET restored_at=datetime('now') WHERE tag=? AND event_id=?", (tag, eid))
        side.commit()
    print(f"RESTORED {len(rows)} releases of {tag}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--accesswire", action="store_const", dest="kind", const="accesswire")
    g.add_argument("--wires", action="store_const", dest="kind", const="wires")
    g.add_argument("--pdf", action="store_const", dest="kind", const="pdf")
    g.add_argument("--restore", metavar="TAG")
    ap.add_argument("--since")
    ap.add_argument("--drill", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-labelled", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.5)
    ap.add_argument("--show", type=int, default=25)
    a = ap.parse_args(argv)

    side = sqlite3.connect(SIDE, timeout=60)
    side.executescript(SIDE_SCHEMA)
    rw = sqlite3.connect(DB, timeout=60, isolation_level=None)
    rw.execute("PRAGMA busy_timeout=60000")
    if a.restore:
        restore(rw, side, a.restore)
        return 0
    if not a.since and not a.drill:
        ap.error("give --since and/or --drill")
    if not a.dry_run and not a.tag:
        ap.error("a run that writes needs --tag")
    ro = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=60)
    ro.row_factory = sqlite3.Row
    ids = candidates(ro, a.kind, a.since, a.drill, a.limit)
    n_all = len(ids)
    ids = ids[:a.limit] if a.limit else ids
    lab = labelled_ids()
    print(f"[body_repair] {a.kind} candidates {n_all}, taking {len(ids)}; dry_run={a.dry_run} tag={a.tag or '-'} "
          f"labelled-set releases {len(lab)}", flush=True)
    if not ids:
        return 0
    f = Fetch()
    tally = {}
    shown = 0
    cat_changes = 0
    t0 = time.time()
    try:
        for i, eid in enumerate(ids):
            if i and i % 100 == 0:
                print(f"[body_repair] {i}/{len(ids)} {json.dumps(tally)} {time.time() - t0:.0f}s", flush=True)
            row = ro.execute("SELECT event_id, ticker, source_name, source_url, published_at, raw_headline, raw_body, "
                             "raw_html, raw_excerpt, categories FROM events WHERE event_id=?", (eid,)).fetchone()
            if row is None:
                tally["gone"] = tally.get("gone", 0) + 1
                continue
            if eid in lab and not a.include_labelled:
                tally["labelled (left as is)"] = tally.get("labelled (left as is)", 0) + 1
                print(f"  labelled, left as is: {row['ticker']} {(row['published_at'] or '')[:10]} {eid[:12]}")
                continue
            try:
                new, why = getattr(f, a.kind)(row)
            except Exception as ex:  # noqa: BLE001
                new, why = None, f"error {type(ex).__name__}: {str(ex)[:80]}"
            if new is None:
                k = re.sub(r"\d+", "#", why)[:40]
                tally[k] = tally.get(k, 0) + 1
                time.sleep(a.sleep)
                continue
            ok, why2 = accept(a.kind, row, new)
            if not ok:
                k = re.sub(r"\(.*\)", "", why2).strip()
                tally[k] = tally.get(k, 0) + 1
                if shown < a.show:
                    shown += 1
                    print(f"  skip {row['ticker']} {(row['published_at'] or '')[:10]} {why} {why2}")
                time.sleep(a.sleep)
                continue
            cats, n = apply(rw, side, a.tag, a.kind, row, new, a.dry_run)
            cat_changes += (cats or "") != (row["categories"] or "")
            tally["replaced" if not a.dry_run else "would replace"] = tally.get("replaced" if not a.dry_run else "would replace", 0) + 1
            if shown < a.show:
                shown += 1
                print(f"  {'REPLACED' if not a.dry_run else 'would replace'} {row['ticker']} {(row['published_at'] or '')[:10]} "
                      f"{row['source_name']} {len(row['raw_body'] or '')} -> {len(new['raw_body'])} chars {why} "
                      f"runs cleared {n}; categories {row['categories']!r} -> {cats!r}", flush=True)
            time.sleep(a.sleep)
    finally:
        f.close()
    print(f"[body_repair] DONE {a.kind} {json.dumps(tally)} categories changed {cat_changes} {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
