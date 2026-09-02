"""
5-year historical backfill runner.

Iterates tickers.json, calls source_module.list_historical(cfg, cutoff) per
ticker, enriches each release via fetch_body, and POSTs to the portal /ingest
endpoint (same path as the live pipeline).

Usage:
  python -m pipeline.backfill                     # all tickers
  python -m pipeline.backfill --source newsfile   # only newsfile tickers
  python -m pipeline.backfill --ticker AFF.CN     # single ticker
  python -m pipeline.backfill --years 5 --dry-run # preview
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

APP_DIR = Path("/opt/mnt/app")
sys.path.insert(0, str(APP_DIR))

from sources import get as get_source  # noqa: E402
from pipeline.run import build_envelope, archive_envelope, sign_and_post, classify_event  # noqa: E402
from portal.quality import reason_to_skip  # noqa: E402
import random  # noqa: E402

PORTAL_URL = os.environ.get("PORTAL_URL", "http://104.131.123.144")
INGEST_ENDPOINT = f"{PORTAL_URL}/ingest"
TICKERS_PATH = APP_DIR / "tickers.json"


def _load_tickers():
    with TICKERS_PATH.open() as f:
        return json.load(f)


def _post_event(client: httpx.Client, event: dict, cfg: dict) -> tuple[bool, str]:
    """Sign via live-dispatch contract, archive, and POST to /ingest/<event_type>."""
    try:
        cls = classify_event(event.get("raw_headline", ""), event.get("raw_body", ""))
        eid = event.get("event_id") or f"backfill-{int(time.time()*1000)}"
        env = build_envelope(event, cls, cfg, eid)
        archive_envelope(env)
        code, text = sign_and_post(env)
        if 200 <= code < 300:
            return True, ""
        return False, f"HTTP {code}: {text[:200]}"
    except Exception as e:
        return False, str(e)


def backfill_ticker(cfg: dict, cutoff: datetime, dry_run: bool = False) -> dict:
    source_name = cfg.get("source")
    ticker = cfg.get("ticker")
    source = get_source(source_name) if source_name else None
    if source is None:
        return {"ticker": ticker, "error": f"no source module for {source_name}"}
    if not hasattr(source, "list_historical"):
        return {"ticker": ticker, "error": f"{source_name} has no list_historical yet"}

    stats = {
        "ticker": ticker,
        "source": source_name,
        "listed": 0,
        "fetched": 0,
        "ingested": 0,
        "skipped": 0,
        "gated": 0,
        "errors": 0,
    }

    with httpx.Client() as client:
        for summary in source.list_historical(cfg, cutoff_date=cutoff):
            stats["listed"] += 1
            try:
                enriched = source.fetch_body(summary)
                stats["fetched"] += 1
            except Exception as e:
                stats["errors"] += 1
                print(f"[backfill] {ticker} fetch_body error: {e}")
                continue

            # Attach event_id so portal can dedup deterministically
            try:
                enriched["event_id"] = source.event_id_for(
                    enriched.get("source_url", ""),
                    enriched.get("published_at"),
                )
            except Exception:
                pass


            # Quality gate — same checks the live pipeline applies in run.py.
            # Skips French versions, empty/short bodies, external URLs, generic articles.
            enriched["_source_name"] = cfg.get("source")
            enriched["_cfg_website"] = cfg.get("website") or cfg.get("ir_url") or ""
            try:
                why = reason_to_skip(enriched)
            except Exception as _e:
                why = None
                print(f"[backfill] {ticker} gate error: {_e}")
            if why:
                stats["gated"] += 1
                print(f"[backfill] {ticker} gated: {why} | {(enriched.get('raw_headline') or '')[:80]}")
                continue

            if dry_run:
                stats["skipped"] += 1
                continue

            ok, err = _post_event(client, enriched, cfg)
            if ok:
                stats["ingested"] += 1
            else:
                stats["errors"] += 1
                print(f"[backfill] {ticker} ingest error: {err}")

            # Gentle rate limit for the portal + source
            time.sleep(random.uniform(2, 5))

    # 45s +/- 15s per-ticker cool-off to dodge newsfile 403 rate-limit
    time.sleep(random.uniform(30, 60))
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="restrict to a single source (e.g. newsfile)")
    ap.add_argument("--ticker", help="restrict to a single ticker")
    ap.add_argument("--years", type=int, default=5, help="cutoff in years (default 5)")
    ap.add_argument("--dry-run", action="store_true", help="don't POST to portal")
    ap.add_argument("--limit", type=int, help="stop after N tickers (for testing)")
    args = ap.parse_args()

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=365 * args.years)
    tickers = _load_tickers()

    if args.source:
        tickers = [t for t in tickers if t.get("source") == args.source]
    if args.ticker:
        tickers = [t for t in tickers if t.get("ticker") == args.ticker]
    if args.limit:
        tickers = tickers[: args.limit]

    print(f"[backfill] starting: {len(tickers)} ticker(s), cutoff={cutoff.date()}, dry_run={args.dry_run}")
    totals = {"listed": 0, "fetched": 0, "ingested": 0, "errors": 0}
    for i, cfg in enumerate(tickers, 1):
        print(f"\n[backfill] ({i}/{len(tickers)}) {cfg.get('ticker')} via {cfg.get('source')}")
        try:
            r = backfill_ticker(cfg, cutoff, dry_run=args.dry_run)
        except Exception as e:
            print(f"[backfill] {cfg.get('ticker')} fatal: {e}")
            traceback.print_exc()
            r = {"ticker": cfg.get("ticker"), "error": str(e)}
        print(f"[backfill] {cfg.get('ticker')} result: {r}")
        for k in totals:
            totals[k] += int(r.get(k) or 0)

    print(f"\n[backfill] DONE totals: {totals}")


if __name__ == "__main__":
    main()
