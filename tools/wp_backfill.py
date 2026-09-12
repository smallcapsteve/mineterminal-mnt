#!/usr/bin/env python3
"""Backfill N years of WP REST history for a letter-range of tickers.

Reuses pipeline.run helpers (build_envelope, sign_and_post, archive_envelope,
classify_event) so events arrive in the portal the same way live ones do.

Usage:
    /opt/mnt/app/.venv/bin/python -m tools.wp_backfill \
        --letters A-F --years 5 [--dry] [--limit-tickers N] [--max-per-ticker N]
"""
from __future__ import annotations
import argparse
import json
import sys
import time
import sqlite3
from pathlib import Path

APP = Path("/opt/mnt/app")
sys.path.insert(0, str(APP))

import sources  # noqa
from pipeline.run import (
    build_envelope, sign_and_post, archive_envelope,
    load_seen, save_seen, HMAC_SECRET,
)
from classify.classifier import classify as classify_event
from portal.quality import reason_to_skip as _quality_skip_reason

TICKERS_JSON = APP / "tickers.json"
PROBE_JSON   = APP / "data" / "wp_rest_probe.json"
DB           = APP / "portal" / "portal.db"


def _load_rest_enabled() -> set:
    """Probe JSON is a list of {ticker, ok, total, pages, ...}."""
    try:
        data = json.loads(PROBE_JSON.read_text())
    except Exception as e:
        print(f"[backfill] can't read probe results: {e}", flush=True)
        return set()
    rows = data.get("results", data) if isinstance(data, dict) else data
    out = set()
    for row in (rows or []):
        if not isinstance(row, dict):
            continue
        # Accept 'ok' or 'rest_enabled' flag
        if row.get("ok") or row.get("rest_enabled"):
            tk = row.get("ticker")
            if tk:
                out.add(tk)
    return out


def _existing_urls(ticker: str) -> set:
    try:
        con = sqlite3.connect(str(DB))
        try:
            rows = con.execute(
                "SELECT source_url FROM events WHERE ticker=?", (ticker,),
            ).fetchall()
        finally:
            con.close()
        return {r[0] for r in rows if r[0]}
    except Exception as e:
        print(f"  [{ticker}] db read err: {e}", flush=True)
        return set()


def _letter_of(t: str) -> str:
    return (t[:1] or "#").upper()


def main():
    if not HMAC_SECRET:
        print("FATAL: MNT_HMAC_SECRET not set", flush=True)
        sys.exit(2)

    ap = argparse.ArgumentParser()
    ap.add_argument("--letters", default="A-Z",
                    help="Letter range like A-F or J-Q (inclusive).")
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--max-per-ticker", type=int, default=2000)
    ap.add_argument("--limit-tickers", type=int, default=0)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--one-ticker", default="",
                    help="Only process this exact ticker (overrides letters)")
    args = ap.parse_args()

    lo, _, hi = args.letters.partition("-")
    lo = (lo or "A").upper()[:1]
    hi = (hi or lo).upper()[:1]

    rest_ok = _load_rest_enabled()
    tickers = json.loads(TICKERS_JSON.read_text())

    todo = []
    for cfg in tickers:
        # tickers.json uses "source" (not "source_name")
        if cfg.get("source") != "company_ir_wp":
            continue
        if not ((cfg.get("source_params") or {}).get("website")):
            continue
        t = cfg.get("ticker", "")
        if args.one_ticker:
            if t != args.one_ticker:
                continue
        else:
            if t not in rest_ok:
                continue
            if not (lo <= _letter_of(t) <= hi):
                continue
        todo.append(cfg)
    todo.sort(key=lambda c: c.get("ticker", ""))
    if args.limit_tickers:
        todo = todo[: args.limit_tickers]

    print(f"[backfill] letters={lo}-{hi} tickers={len(todo)} "
          f"years={args.years} dry={args.dry}", flush=True)

    seen = load_seen()
    co = sources.get("company_ir_wp")

    grand_new = 0
    grand_seen = 0
    grand_skip = 0
    grand_err  = 0
    t0 = time.time()

    for i, cfg in enumerate(todo, 1):
        t = cfg.get("ticker", "")
        website = cfg["source_params"]["website"]
        existing = _existing_urls(t)
        new_count = 0
        tried = 0
        skipped = 0
        errored = 0
        t_start = time.time()
        try:
            for summary in co.list_via_rest(
                cfg, years=args.years, max_posts=args.max_per_ticker,
            ):
                tried += 1
                url = summary.get("source_url") or ""
                if not url or url in existing:
                    skipped += 1
                    continue
                eid = co.event_id_for(url, summary.get("published_at"))
                if eid in seen:
                    skipped += 1
                    continue
                try:
                    summary = co.fetch_body(summary)
                except Exception as e:
                    errored += 1
                    continue
                if not summary.get("raw_body"):
                    skipped += 1
                    continue

                _qr = _quality_skip_reason(summary)
                if _qr:
                    skipped += 1
                    seen.add(eid)  # do not retry
                    continue

                if args.dry:
                    new_count += 1
                    existing.add(url)
                    seen.add(eid)
                    continue

                try:
                    cls = classify_event(
                        summary["raw_headline"], summary["raw_body"]
                    )
                except Exception as e:
                    errored += 1
                    continue
                env = build_envelope(summary, cls, cfg, eid)
                archive_envelope(env)
                code, _text = sign_and_post(env)
                if code == 200 or code == 201:
                    new_count += 1
                    existing.add(url)
                    seen.add(eid)
                elif code == 409:
                    # dedupe hit at portal — fine
                    existing.add(url)
                    seen.add(eid)
                    skipped += 1
                else:
                    errored += 1
        except Exception as e:
            print(f"  [{t}] outer err: {e}", flush=True)
            errored += 1

        grand_new += new_count
        grand_seen += tried
        grand_skip += skipped
        grand_err += errored
        dt_s = time.time() - t_start
        print(
            f"  [{i:3d}/{len(todo)}] {t:6s} {website[:50]:50s} "
            f"posts={tried:4d} new={new_count:4d} skip={skipped:4d} "
            f"err={errored:2d} {dt_s:5.1f}s",
            flush=True,
        )
        if i % 5 == 0 and not args.dry:
            save_seen(seen)

    if not args.dry:
        save_seen(seen)
    wall = time.time() - t0
    print(
        f"[backfill] DONE letters={lo}-{hi} tickers={len(todo)} "
        f"posts_seen={grand_seen} new={grand_new} skip={grand_skip} "
        f"err={grand_err} wall={wall:.0f}s",
        flush=True,
    )


if __name__ == "__main__":
    main()
