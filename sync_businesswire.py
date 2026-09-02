"""sync_businesswire.py — pull Business Wire mining releases via Google News, dedupe, ingest.

Business Wire's native mining-specific RSS feed is unreliable (subjectcode/9
returns mostly non-mining content). So we use Google News as the discovery
layer with a `site:globenewswire.com` query — same proven pattern as the
Newsfile and Accesswire firehoses.

Business Wire pages fetch cleanly so we get full bodies and extract Canadian
tickers directly. New mining tickers are auto-onboarded into tickers.json.

source_name="businesswire" — same as the per-company adapter, so the
fuzzy_dupe_guard inside db.upsert_event correctly merges across both paths.
"""
from __future__ import annotations
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta

sys.path.insert(0, "/opt/mnt/app")

from sources import businesswire_gnews as bwg  # noqa: E402
from portal import db as pdb  # noqa: E402
from portal.quality import reason_to_skip  # noqa: E402

TICKERS_PATH = "/opt/mnt/app/tickers.json"


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())[:120]


def _slugify(s: str, max_len: int = 80) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return (s[:max_len].rstrip("-") or "release")


def find_fuzzy_dupe(conn: sqlite3.Connection, ticker: str, headline: str,
                    published_at: str, window_hours: int = 48) -> str | None:
    """Return event_id of an existing event matching (ticker, ~headline, ±window)."""
    if not ticker or not headline or not published_at:
        return None
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    lo = (dt - timedelta(hours=window_hours)).strftime("%Y-%m-%dT%H:%M:%S")
    hi = (dt + timedelta(hours=window_hours)).strftime("%Y-%m-%dT%H:%M:%S")
    norm = _normalize(headline)
    rows = conn.execute(
        "SELECT event_id, raw_headline FROM events "
        "WHERE ticker = ? AND published_at >= ? AND published_at <= ?",
        (ticker, lo, hi),
    ).fetchall()
    for eid, rhl in rows:
        rnorm = _normalize(rhl)
        if not rnorm:
            continue
        if len(norm) >= 30 and len(rnorm) >= 30 and norm[:60] == rnorm[:60]:
            return eid
        if rnorm.startswith(norm[:50]) or norm.startswith(rnorm[:50]):
            return eid
    return None


def load_tickers() -> list[dict]:
    return json.load(open(TICKERS_PATH))


def save_tickers(data: list[dict]) -> None:
    tmp = TICKERS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, TICKERS_PATH)


def known_tickers_index(tickers: list[dict]) -> dict[str, dict]:
    return {r["ticker"]: r for r in tickers if isinstance(r, dict) and r.get("ticker")}


def auto_onboard(ticker: str, name: str | None, exchange: str | None,
                 idx: dict[str, dict], tickers: list[dict]) -> bool:
    """Append a new ticker entry. Returns True if added."""
    if ticker in idx:
        return False
    today = datetime.utcnow().strftime("%Y-%m-%d")
    new = {
        "ticker": ticker,
        "name": name or ticker.split(".")[0].title(),
        "source": "businesswire_gnews",
        "source_params": {},
        "discovery_confidence": "businesswire_auto",
        "discovered_at": today,
    }
    if exchange:
        new["exchange"] = exchange
    tickers.append(new)
    idx[ticker] = new
    return True


def main(days: int = 7) -> int:
    started = datetime.utcnow().isoformat()
    print(f"[sync_businesswire] start {started}  days={days}")

    tickers = load_tickers()
    idx = known_tickers_index(tickers)
    print(f"[sync_businesswire] known tickers: {len(idx)}")

    items = list(bwg.list_mining_events(days=days))
    print(f"[sync_businesswire] mining items from GNews: {len(items)}")

    conn = pdb.get_conn()

    ingested = dup_skip = onboarded = qual_skip = err = 0
    for ev in items:
        ticker = ev["ticker"]

        # 1. Auto-onboard if unknown
        if ticker not in idx:
            name = bwg.extract_company_name(ev["raw_headline"], ev["raw_body"])
            if auto_onboard(ticker, name, ev.get("_exchange"), idx, tickers):
                onboarded += 1
                print(f"  + ONBOARD {ticker} — {name or '(name pending)'}")

        # 2. Quality gate (must set _source_name; bare source_name is ignored)
        ev_for_quality = dict(ev)
        ev_for_quality["_cfg_website"] = ev["source_url"]
        ev_for_quality["_source_name"] = ev.get("source_name", "businesswire")
        why = reason_to_skip(ev_for_quality)
        if why and "short body" not in why:
            qual_skip += 1
            continue

        # 3. Fuzzy dedup against existing events (cross-source first-source-wins)
        dupe = find_fuzzy_dupe(conn, ticker, ev["raw_headline"], ev["published_at"])
        if dupe:
            dup_skip += 1
            continue

        # 4. Insert
        try:
            pdb.upsert_event(ev)
            ingested += 1
            print(f"  + {ticker:10s} {ev['raw_headline'][:80]}")
        except Exception as e:
            err += 1
            print(f"  X upsert err for {ticker}: {e}")

    # 5. Persist tickers.json if any onboarded
    if onboarded:
        save_tickers(tickers)
        print(f"[sync_businesswire] tickers.json saved ({len(tickers)} entries)")

    # 6. Backfill slugs for any new events from this source
    n_slug = 0
    for eid, hl in conn.execute(
        "SELECT event_id, raw_headline FROM events "
        "WHERE source_name='businesswire' AND (slug IS NULL OR slug = '')"
    ):
        conn.execute("UPDATE events SET slug = ? WHERE event_id = ?",
                     (_slugify(hl), eid))
        n_slug += 1
    if n_slug:
        conn.commit()

    print(f"[sync_businesswire] DONE  ingested={ingested}  fuzzy_dup_skip={dup_skip}  "
          f"qual_skip={qual_skip}  onboarded={onboarded}  slugs={n_slug}  err={err}")
    return 0


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    sys.exit(main(days=days))
