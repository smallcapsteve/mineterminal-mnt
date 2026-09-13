#!/usr/bin/env python3
"""UNIVERSE_SYNC_V1 — regenerate MNT's tickers.json from the shared universe.

tickers.json stops being a source and becomes a build artefact.

Before this, the file was authoritative and self-editing: six wire scrapers
appended to it whenever they saw an unfamiliar ticker, "active immediately",
naming the company from the press-release headline. That is where names like
'Axl', 'Bmo' and "We caught up with Barry O'Shea, CEO of Highland Copper" came
from — `auto_onboard()` falls back to `ticker.split('.')[0].title()`.

Now MinePortal decides who exists and this job writes the file to match. Two
consequences worth being explicit about:

  * Anything a scraper has appended since the last run is NOT kept. It is sent
    to MinePortal's candidate queue first, with whatever name the scraper
    scraped, and then dropped from the file. Discovery is preserved; silent
    publication is not.
  * The six scrapers need no edit. They can go on appending; this job keeps
    undoing it and funnelling the result into review. That is deliberate —
    rewriting six near-identical live scrapers to achieve the same guarantee
    would be a much larger change for the same outcome.

Run:
    python3 universe_sync.py --dry-run
    python3 universe_sync.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, "/opt/mnt/app")
import universe_client

TICKERS_PATH = "/opt/mnt/app/tickers.json"
BACKUP_DIR = "/opt/mnt/app/data/tickers-backups"

# Never shrink the watchlist by more than this in one run. A universe that
# comes back short — a half-finished import, a bad query — would otherwise
# silently switch off news collection for hundreds of companies.
MIN_KEEP_RATIO = 0.80


def load_current() -> list[dict]:
    try:
        with open(TICKERS_PATH) as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def build(universe_rows: list[dict]) -> list[dict]:
    """The universe in tickers.json's own shape, so every existing reader —
    pipeline/run.py, the portal's name lookups, text_helpers — keeps working
    unchanged while reading MinePortal's data."""
    out = []
    for c in universe_rows:
        sym = c.get("symbol")
        if not sym:
            continue
        entry = {
            "ticker": sym,
            "company_id": c.get("ticker"),
            "name": c.get("name"),
            "source": c.get("news_source") or "wire_discovery_only",
            "source_params": c.get("news_source_params") or {},
            "discovery_confidence": "universe",
        }
        if c.get("exchange"):
            entry["exchange"] = c["exchange"]
        out.append(entry)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-propose", action="store_true",
                    help="skip sending unknown tickers to the candidate queue")
    args = ap.parse_args()
    if args.apply == args.dry_run:
        print("pass exactly one of --apply or --dry-run", file=sys.stderr)
        return 2

    rows = universe_client.load(force=True)
    if not rows:
        print("ABORT: universe empty and no cache — tickers.json left alone")
        return 1
    if universe_client.is_stale():
        print("ABORT: universe served from cache, MinePortal unreachable — "
              "refusing to rewrite tickers.json from stale data")
        return 1

    current = load_current()
    new = build(rows)
    cur_syms = {(e.get("ticker") or "").upper() for e in current if isinstance(e, dict)}
    new_syms = {e["ticker"].upper() for e in new}

    dropped = sorted(cur_syms - new_syms)
    added = sorted(new_syms - cur_syms)

    print(f"UNIVERSE_SYNC_V1  ({'APPLY' if args.apply else 'DRY RUN'})")
    print(f"  universe:  {len(rows):,} companies -> {len(new):,} entries")
    print(f"  current:   {len(current):,} entries")
    print(f"  added:     {len(added)}")
    print(f"  dropped:   {len(dropped)}")

    if current and len(new) < len(current) * MIN_KEEP_RATIO:
        print(f"ABORT: new file would be {len(new)} entries against "
              f"{len(current)} now — below the {MIN_KEEP_RATIO:.0%} floor. "
              f"Not writing.")
        return 1

    # Anything the scrapers added that the universe does not know about goes to
    # review rather than to the bin.
    if dropped and not args.no_propose:
        by_sym = {(e.get("ticker") or "").upper(): e
                  for e in current if isinstance(e, dict)}
        queued = 0
        for sym in dropped:
            e = by_sym.get(sym, {})
            if args.apply:
                status = universe_client.propose(
                    ticker=sym,
                    name=e.get("name"),
                    exchange=e.get("exchange"),
                    source=e.get("source"),
                    source_params=e.get("source_params"),
                    discovered_by="mnt-tickers-json",
                )
                if status in ("queued", "exists"):
                    queued += 1
            else:
                queued += 1
        print(f"  proposed:  {queued} of the dropped entries sent to the "
              f"candidate queue{'' if args.apply else ' (would be)'}")

    if dropped:
        print(f"  dropping:  {', '.join(dropped[:25])}"
              + (f" ... +{len(dropped) - 25} more" if len(dropped) > 25 else ""))

    if not args.apply:
        print("  done (nothing written).")
        return 0

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(BACKUP_DIR, f"tickers-{stamp}.json")
    if os.path.exists(TICKERS_PATH):
        shutil.copy2(TICKERS_PATH, backup)
        print(f"  backup:    {backup}")

    d = os.path.dirname(TICKERS_PATH)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tickers.", suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        json.dump(new, fh, indent=2)
    os.replace(tmp, TICKERS_PATH)
    try:
        shutil.chown(TICKERS_PATH, user="mnt", group="mnt")
    except (OSError, LookupError):
        pass
    print(f"  wrote:     {TICKERS_PATH}  ({len(new):,} entries)")
    print("  done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
