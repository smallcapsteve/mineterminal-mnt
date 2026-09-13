#!/usr/bin/env python3
"""JV_TAG_V1 — file a co-issued release under both companies.

Justin, 2026-09-13: *"Can you add a feature that files joint venture news under
both companies tickers?"*

**The problem, as measured.** Riverside Resources (RRI.V) and Questcorp Mining
(QQQ.CN) are partners at La Union and issue their news jointly. The wire path
files each release under whichever company it decided the release belonged to,
and it has consistently chosen Questcorp: **53 events under QQQ.CN, many of them
naming Riverside first in the headline, against 2 under RRI.V.** A Riverside
investor browsing RRI.V does not see them. Nothing was wrong with any individual
decision — the release genuinely is Questcorp news. It is also Riverside news,
and an event row only has one ticker.

**Except it does not.** `events.additional_tickers` already exists, and
`portal/db.py` already reads it everywhere that matters: the company event list,
the per-company counts, and both filtered queries. `portal/app.py` even has an
admin screen for editing it. **One event in the entire database has it set.** So
this is not a feature to build; it is a populated field to start populating.

**How a partner is identified** (Justin's choice, of three offered): the
company's curated MinePortal name, or an explicit exchange-qualified ticker,
appearing **in the headline itself**. Not the body. A release that mentions a
competitor, an acquirer or a royalty holder in paragraph six does not tag them;
a release whose headline reads "Questcorp Mining and Riverside Resources
Complete Geophysics Programs" tags both. Headline-only is the conservative
choice and it is the one that matches the case this was built for — all 53 of
the QQQ.CN events name Riverside in the headline.

**Two guards against the obvious failure mode**, which is a generic company name
matching everything:

  * A name match needs **at least two words** after corporate suffixes are
    stripped. "Riverside Resources" qualifies; a company called "Gold" or
    "Nevada" can only ever be matched by its ticker. This costs real single-word
    matches — Teck by name, for instance — and that is the right trade when the
    alternative is tagging every gold release with a company called Gold.
  * At any position in the headline the **longest** matching name wins, so
    "Riverside Resources" is not also matched as a shorter overlapping name.

**Nothing is applied automatically to history** (Justin's choice). `--propose`
writes candidate pairs to its own store with status `pending` and touches
`portal.db` not at all. `--apply` is a separate, explicit step, and can be
limited to one pair at a time.

Run:
    python3 jv_tag.py --propose --days 400      # scan history, change nothing
    python3 jv_tag.py --review                  # what it proposes, grouped
    python3 jv_tag.py --review --pair QQQ.CN:RRI.V
    python3 jv_tag.py --apply --pair QQQ.CN:RRI.V
    python3 jv_tag.py --reject --pair FOO.V:BAR.V
    python3 jv_tag.py --stats
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sqlite3
import sys

APP_ROOT = "/opt/mnt/app"
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

PORTAL_DB = os.environ.get("PORTAL_DB", f"{APP_ROOT}/portal/portal.db")
STORE = os.environ.get("JV_TAG_DB", f"{APP_ROOT}/data/jv_tags.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    event_id      TEXT NOT NULL,
    primary_tk    TEXT NOT NULL,
    partner_tk    TEXT NOT NULL,
    matched_on    TEXT,            -- the exact text in the headline that matched
    how           TEXT,            -- 'name' | 'ticker'
    headline      TEXT,
    published_at  TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',   -- pending|applied|rejected
    proposed_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    acted_at      TEXT,
    PRIMARY KEY (event_id, partner_tk)
);
CREATE INDEX IF NOT EXISTS idx_jv_pair ON proposals(primary_tk, partner_tk, status);
CREATE INDEX IF NOT EXISTS idx_jv_status ON proposals(status);
"""

# Stripped before deciding whether a name is distinctive enough to match on.
_SUFFIX = re.compile(
    r"\b(inc|inc\.|incorporated|ltd|ltd\.|limited|corp|corp\.|corporation"
    r"|plc|llc|lp|nl|sa|ag|co|company|holdings|group)\b\.?", re.I)
_PUNCT = re.compile(r"[^\w\s&-]+")
_WS = re.compile(r"\s+")

# "(TSXV: RRI)", "TSX-V:RRI", "CSE: QQQ"
_EXCHANGE = r"(?:TSX-?V|TSXV|TSX|CSE|CNSX|NEO|OTCQB|OTCQX|OTC|NYSE|NASDAQ|FSE|ASX)"


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}] {msg}", flush=True)


def store() -> sqlite3.Connection:
    con = sqlite3.connect(STORE)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def core_name(name: str) -> str:
    """The company name with corporate suffixes and punctuation removed."""
    s = _SUFFIX.sub(" ", name or "")
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


def build_index() -> tuple[list, dict]:
    """(patterns, by_symbol).

    patterns is a list of (compiled_regex, symbol, kind, display) ordered so
    that longer names are tried first — at a given position in the headline the
    longest company name should win, not whichever happened to be indexed
    first.
    """
    import universe_client

    pats, by_symbol = [], {}
    for c in universe_client.load():
        sym = (c.get("symbol") or "").strip().upper()
        if not sym:
            continue
        by_symbol[sym] = c
        bare = sym.split(".")[0]

        # A ticker is only ever matched when the exchange is stated next to it.
        # A bare three-letter ticker in prose is far too easy to hit by accident.
        pats.append((
            re.compile(rf"\b{_EXCHANGE}\s*[:\-]\s*{re.escape(bare)}\b", re.I),
            sym, "ticker", f"{_EXCHANGE}: {bare}",
        ))

        core = core_name(c.get("name") or "")
        if len(core.split()) < 2:
            continue                     # too generic to match on by name
        # Tolerate runs of whitespace inside the name.
        body = r"\s+".join(re.escape(w) for w in core.split())
        pats.append((
            re.compile(rf"(?<![\w]){body}(?![\w])", re.I), sym, "name", core,
        ))

    # Longest display string first, so overlapping names resolve to the longest.
    pats.sort(key=lambda p: len(p[3]), reverse=True)
    return pats, by_symbol


def partners_in(headline: str, primary: str, pats: list) -> list[tuple]:
    """(symbol, matched_text, how) for every other universe company named in
    this headline. Overlapping matches are resolved longest-first."""
    if not headline:
        return []
    primary = (primary or "").strip().upper()
    primary_bare = primary.split(".")[0]

    taken: list[tuple[int, int]] = []
    out: dict[str, tuple] = {}
    for rx, sym, how, _disp in pats:
        if sym == primary or sym.split(".")[0] == primary_bare:
            continue                     # the event's own company
        for m in rx.finditer(headline):
            a, b = m.span()
            if any(a < tb and ta < b for ta, tb in taken):
                continue                 # inside a longer name already matched
            taken.append((a, b))
            if sym not in out:
                out[sym] = (sym, m.group(0), how)
    return list(out.values())


# --------------------------------------------------------------------------
# live tagging
# --------------------------------------------------------------------------

_live_pats = None


def tags_for(headline: str, primary: str) -> list[str]:
    """The partner symbols for one headline. Used by portal/jv_gate.py at
    ingest. Never raises — a failure here must not stop an event being stored."""
    global _live_pats
    try:
        if _live_pats is None:
            _live_pats, _ = build_index()
        return [s for s, _t, _h in partners_in(headline, primary, _live_pats)]
    except Exception:                            # noqa: BLE001
        return []


def pipe(tickers: list[str]) -> str | None:
    """The storage form portal/app.py and portal/db.py already use: |A|B|."""
    ts = [t for t in dict.fromkeys(t.strip().upper() for t in tickers) if t]
    return ("|" + "|".join(ts) + "|") if ts else None


# --------------------------------------------------------------------------
# propose / review / apply
# --------------------------------------------------------------------------

def propose(con, days: int, limit: int | None) -> int:
    pats, _ = build_index()
    log(f"{len(pats)} match patterns from the universe")
    p = sqlite3.connect(f"file:{PORTAL_DB}?mode=ro", uri=True)
    p.row_factory = sqlite3.Row
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    q = ("SELECT event_id, ticker, raw_headline, published_at, additional_tickers "
         "FROM events WHERE date(published_at) >= ? ORDER BY published_at DESC")
    rows = p.execute(q, (since,)).fetchall()
    log(f"{len(rows):,} events since {since}")

    n_hit = n_new = 0
    for i, r in enumerate(rows, 1):
        if i % 5000 == 0:
            log(f"  {i:,}/{len(rows):,} scanned, {n_hit} with a partner")
        found = partners_in(r["raw_headline"] or "", r["ticker"] or "", pats)
        if not found:
            continue
        already = set((r["additional_tickers"] or "").strip("|").split("|"))
        n_hit += 1
        for sym, matched, how in found:
            if sym in already:
                continue
            cur = con.execute(
                "SELECT status FROM proposals WHERE event_id=? AND partner_tk=?",
                (r["event_id"], sym)).fetchone()
            if cur:
                continue                 # already proposed, applied or rejected
            con.execute(
                "INSERT INTO proposals (event_id,primary_tk,partner_tk,matched_on,"
                "how,headline,published_at) VALUES (?,?,?,?,?,?,?)",
                (r["event_id"], (r["ticker"] or "").upper(), sym, matched, how,
                 (r["raw_headline"] or "")[:300], r["published_at"]))
            n_new += 1
            if limit and n_new >= limit:
                con.commit()
                log(f"stopped at --limit {limit}")
                return n_new
    con.commit()
    log(f"{n_hit:,} events name another universe company in the headline")
    log(f"{n_new:,} new proposals written (status pending)")
    return n_new


def review(con, pair: str | None, samples: int) -> None:
    where, args = "status='pending'", []
    if pair:
        a, b = pair.upper().split(":", 1)
        where += " AND primary_tk=? AND partner_tk=?"
        args = [a, b]
    rows = con.execute(
        f"SELECT primary_tk, partner_tk, how, COUNT(*) c, MIN(published_at) f, "
        f"MAX(published_at) l FROM proposals WHERE {where} "
        f"GROUP BY primary_tk, partner_tk, how ORDER BY c DESC", args).fetchall()
    if not rows:
        print("nothing pending")
        return
    print(f"{'primary':<10} {'partner':<10} {'how':<7} {'n':>5}  first       last")
    print("-" * 66)
    for r in rows:
        print(f"{r['primary_tk']:<10} {r['partner_tk']:<10} {r['how']:<7} "
              f"{r['c']:>5}  {(r['f'] or '')[:10]}  {(r['l'] or '')[:10]}")
    print()
    for r in rows[:12]:
        ex = con.execute(
            "SELECT matched_on, headline FROM proposals WHERE status='pending' "
            "AND primary_tk=? AND partner_tk=? LIMIT ?",
            (r["primary_tk"], r["partner_tk"], samples)).fetchall()
        print(f"--- {r['primary_tk']} + {r['partner_tk']}  ({r['c']}) ---")
        for e in ex:
            print(f"    [{e['matched_on'][:28]}] {e['headline'][:88]}")


def apply(con, pair: str | None, dry: bool) -> int:
    where, args = "status='pending'", []
    if pair:
        a, b = pair.upper().split(":", 1)
        where += " AND primary_tk=? AND partner_tk=?"
        args = [a, b]
    rows = con.execute(
        f"SELECT event_id, primary_tk, partner_tk FROM proposals WHERE {where}",
        args).fetchall()
    if not rows:
        print("nothing pending to apply")
        return 0
    if dry:
        print(f"would apply {len(rows)} tags")
        return 0

    p = sqlite3.connect(PORTAL_DB)
    n = 0
    for r in rows:
        cur = p.execute("SELECT additional_tickers FROM events WHERE event_id=?",
                        (r["event_id"],)).fetchone()
        if not cur:
            con.execute("UPDATE proposals SET status='rejected', acted_at=? "
                        "WHERE event_id=? AND partner_tk=?",
                        (dt.datetime.now(dt.UTC).isoformat(), r["event_id"],
                         r["partner_tk"]))
            continue
        have = [t for t in (cur[0] or "").strip("|").split("|") if t]
        if r["partner_tk"] not in have:
            have.append(r["partner_tk"])
        p.execute("UPDATE events SET additional_tickers=? WHERE event_id=?",
                  (pipe(have), r["event_id"]))
        con.execute("UPDATE proposals SET status='applied', acted_at=? "
                    "WHERE event_id=? AND partner_tk=?",
                    (dt.datetime.now(dt.UTC).isoformat(), r["event_id"],
                     r["partner_tk"]))
        n += 1
    p.commit()
    con.commit()
    log(f"applied {n} tags to events.additional_tickers")
    return n


def reject(con, pair: str) -> int:
    a, b = pair.upper().split(":", 1)
    cur = con.execute(
        "UPDATE proposals SET status='rejected', acted_at=? "
        "WHERE status='pending' AND primary_tk=? AND partner_tk=?",
        (dt.datetime.now(dt.UTC).isoformat(), a, b))
    con.commit()
    log(f"rejected {cur.rowcount} proposals for {a} + {b}")
    return cur.rowcount


def stats(con) -> None:
    for r in con.execute("SELECT status, COUNT(*) c FROM proposals GROUP BY 1"):
        print(f"  {r[0]:<10} {r['c']}")
    for r in con.execute("SELECT how, COUNT(*) c FROM proposals GROUP BY 1"):
        print(f"  matched by {r[0]:<8} {r['c']}")
    p = sqlite3.connect(f"file:{PORTAL_DB}?mode=ro", uri=True)
    n = p.execute("SELECT COUNT(*) FROM events WHERE additional_tickers IS NOT NULL "
                  "AND additional_tickers<>''").fetchone()[0]
    print(f"  events currently carrying an extra ticker: {n}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--propose", action="store_true")
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--reject", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--pair", help="PRIMARY:PARTNER, e.g. QQQ.CN:RRI.V")
    args = ap.parse_args()

    con = store()
    if args.propose:
        propose(con, args.days, args.limit)
    if args.review:
        review(con, args.pair, args.samples)
    if args.apply:
        apply(con, args.pair, args.dry_run)
    if args.reject:
        if not args.pair:
            print("--reject needs --pair", file=sys.stderr)
            return 2
        reject(con, args.pair)
    if args.stats:
        stats(con)
    if not any([args.propose, args.review, args.apply, args.reject, args.stats]):
        ap.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
