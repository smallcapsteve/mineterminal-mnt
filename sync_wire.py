"""sync_wire.py — pull thenewswire.com /rss, ingest mining items, auto-onboard new tickers.

Runs once per invocation. Designed to be called by a systemd timer every 30 min.

Behavior:
- Strict mining classification (see thenewswire_wire.is_mining)
- First-source wins fuzzy dedup over (ticker, normalized_headline, ±48h window)
- Auto-add unknown mining tickers to tickers.json (active immediately)
- Backfills slug + idempotent upsert
"""
from __future__ import annotations
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta

sys.path.insert(0, "/opt/mnt/app")

from sources import thenewswire_wire as wire  # noqa: E402
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
    # Match if normalized prefixes overlap heavily.
    for eid, rhl in rows:
        rnorm = _normalize(rhl)
        if not rnorm:
            continue
        # Same prefix 60+ chars
        if len(norm) >= 30 and len(rnorm) >= 30 and norm[:60] == rnorm[:60]:
            return eid
        # Or: longest is a prefix of the other (handles "A Closes Tranche" vs "A Closes First Tranche of...")
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
        "source": "thenewswire",
        "source_params": {},
        "discovery_confidence": "wire_auto",
        "discovered_at": today,
    }
    if exchange:
        new["exchange"] = exchange
    tickers.append(new)
    idx[ticker] = new
    return True


def main() -> int:
    started = datetime.utcnow().isoformat()
    print(f"[sync_wire] start {started}")

    tickers = load_tickers()
    idx = known_tickers_index(tickers)
    # Known mining tickers: those whose source IS a mining wire/ir adapter
    mining_sources = {"newsfile", "company_ir_wp", "cnw", "globenewswire",
                      "accesswire", "thenewswire", "wp_feed"}
    known_mining = {
        t for t, cfg in idx.items()
        if (cfg.get("source") or "") in mining_sources
    }
    print(f"[sync_wire] known tickers: {len(idx)}, mining-tagged: {len(known_mining)}")

    items = list(wire.list_mining_events(known_mining_tickers=known_mining))
    print(f"[sync_wire] mining items from RSS: {len(items)}")

    conn = pdb.get_conn()

    ingested = dup_skip = onboarded = qual_skip = 0
    for ev in items:
        ticker = ev["ticker"]
        # 1. Auto-onboard if unknown
        if ticker not in idx:
            name = wire.extract_company_name(ev["raw_headline"], ev["raw_body"])
            if auto_onboard(ticker, name, ev.get("_exchange"), idx, tickers):
                onboarded += 1
                print(f"  + ONBOARD {ticker} — {name or '(name pending)'}")

        # 2. Quality gate
        ev_for_quality = dict(ev)
        ev_for_quality["_cfg_website"] = ev["source_url"]
        why = reason_to_skip(ev_for_quality)
        if why and "short body" not in why:
            qual_skip += 1
            continue

        # 3. Fuzzy dedup against existing events
        dupe = find_fuzzy_dupe(conn, ticker, ev["raw_headline"], ev["published_at"])
        if dupe:
            dup_skip += 1
            continue

        # 4. Insert
        try:
            pdb.upsert_event(ev)
            ingested += 1
        except Exception as e:
            print(f"  X upsert err for {ticker}: {e}")

    # 5. Persist tickers.json if any onboarded
    if onboarded:
        save_tickers(tickers)
        print(f"[sync_wire] tickers.json saved ({len(tickers)} entries)")

    # 6. Backfill slugs for any new events
    n_slug = 0
    for eid, hl in conn.execute(
        "SELECT event_id, raw_headline FROM events "
        "WHERE source_name='thenewswire' AND (slug IS NULL OR slug = '')"
    ):
        conn.execute("UPDATE events SET slug = ? WHERE event_id = ?",
                     (_slugify(hl), eid))
        n_slug += 1
    if n_slug:
        conn.commit()

    print(f"[sync_wire] DONE  ingested={ingested}  fuzzy_dup_skip={dup_skip}  "
          f"qual_skip={qual_skip}  onboarded={onboarded}  slugs={n_slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
