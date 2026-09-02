"""sync_accesswire.py — pull Accesswire mining releases via Google News, dedupe, ingest."""
from __future__ import annotations
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta

sys.path.insert(0, "/opt/mnt/app")

from sources import accesswire_gnews as anw  # noqa: E402
from portal import db as pdb  # noqa: E402

TICKERS_PATH = "/opt/mnt/app/tickers.json"


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())[:120]


def find_fuzzy_dupe(conn: sqlite3.Connection, ticker: str, headline: str,
                    published_at: str, window_hours: int = 48) -> str | None:
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


def main(days: int = 14) -> int:
    print(f"[sync_accesswire] start days={days}")
    tickers = json.load(open(TICKERS_PATH))
    name_index = anw.build_company_index(tickers)
    print(f"[sync_accesswire] company-name index: {len(name_index)} entries")

    items = list(anw.list_mining_events(name_index, days=days))
    print(f"[sync_accesswire] mining items resolved to known tickers: {len(items)}")

    conn = pdb.get_conn()
    ingested = dup_skip = 0
    for ev in items:
        if find_fuzzy_dupe(conn, ev["ticker"], ev["raw_headline"], ev["published_at"]):
            dup_skip += 1
            continue
        try:
            pdb.upsert_event(ev)
            ingested += 1
            print(f"  + {ev['ticker']:10s} {ev['raw_headline'][:80]}")
        except Exception as e:
            print(f"  X {ev['ticker']}: {e}")

    print(f"[sync_accesswire] DONE  ingested={ingested}  fuzzy_dup_skip={dup_skip}")
    return 0


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    sys.exit(main(days=days))
