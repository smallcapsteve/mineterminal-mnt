"""
Pipeline entry point.

Flow:
  1. Load tickers.json - each entry names a `source` and optional `source_params`
  2. For each ticker: pick the source module, fetch recent PR summaries
  3. Dedupe against seen_events.json (per-source event_id)
  4. Fetch body, classify, build envelope, POST to portal /ingest/<event_type>
  5. Log and archive envelopes

Run it:
  /opt/mnt/app/.venv/bin/python -m pipeline.run

--- PIPELINE_ROTATION_V1, 2026-09-13 -----------------------------------------
Two things this file got wrong, both visible only in its own log.

**No rotation.** It iterated the watchlist from the top every run. systemd kills
it at TimeoutStartSec=600 and one company can take 90 seconds, so a run covered
roughly the first half-dozen companies and the rest were never reached - every
30 minutes, for as long as that has been true. A cursor now records when each
company was last attempted and the run takes the most overdue first, stopping
cleanly on a budget below the systemd timeout. Same idea as SediTracker's
pick_batch(), which has worked this way all along.

**A misleading error.** A company whose `source` is `newsfile_gnews`,
`thenewswire`, `cnw_gnews`, `prnewswire_gnews`, `businesswire_gnews` or
`wire_discovery_only` has no per-company adapter and never had one - those names
say which wire the firehose found the company on, and sync_*.py is what collects
it. The old code logged `unknown source` once per company per run, which reads
like 736 companies failing when nothing is wrong. They are counted and reported
in one line instead.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

APP_ROOT = Path("/opt/mnt/app")
sys.path.insert(0, str(APP_ROOT))

import sources
from classify.classifier import classify as classify_event
from portal.quality import reason_to_skip as _quality_skip_reason

# ---- config ---------------------------------------------------------------
load_dotenv(APP_ROOT / ".env")
HMAC_SECRET   = os.environ.get("MNT_HMAC_SECRET", "").strip()
PORTAL_INGEST = os.environ.get("PORTAL_INGEST_URL", "http://127.0.0.1/ingest").rstrip("/")
TICKERS_FILE  = APP_ROOT / "tickers.json"
SEEN_FILE     = APP_ROOT / "data" / "seen_events.json"
LOG_DIR       = APP_ROOT / "data" / "logs"
EVENTS_DIR    = APP_ROOT / "data" / "events"

# PIPELINE_ROTATION_V1
CURSOR_FILE   = APP_ROOT / "data" / "pipeline_cursor.json"
# systemd kills the unit at 600s. Stop before that so the cursor is written and
# the run ends by choice rather than by SIGTERM - a killed run used to lose the
# record of what it had just done.
TIME_BUDGET_S = int(os.environ.get("MNT_PIPELINE_BUDGET_S", "480"))

# Review policy - mirrors blueprint. Keyed by event_type -> threshold for auto.
AUTO_THRESHOLD = {
    "news_item":         0.70,
    "mgmt_change":       0.85,
    "production_update": 0.85,
    "financing":         0.90,
    # Always-review types:
    "drill_result":      0.85,   # THRESH_V1 2026-11-08: was 1.01 (always review, a queue nobody works)
    "resource_estimate": 0.85,   # THRESH_V1
    "econ_study":        0.85,   # THRESH_V1
    "paid_promotion":    1.01,
}

DEFAULT_SOURCE = "globenewswire"

# ---- helpers --------------------------------------------------------------
def log(msg: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.utcnow().isoformat() + "Z"
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_DIR / "pipeline.log", "a") as f:
        f.write(line + "\n")


def load_seen() -> set[str]:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()))
        except Exception:
            return set()
    return set()


def save_seen(seen: set[str]):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)))


def load_tickers() -> list[dict]:
    if not TICKERS_FILE.exists():
        return [{
            "ticker": "CCI.CN",
            "company_id": "CCI",
            "property_id": "MURRAY_BROOK",
            "source": "newsfile",
            "source_params": {"company_id": 9218},
        }]
    return json.loads(TICKERS_FILE.read_text())


# ---- rotation (PIPELINE_ROTATION_V1) --------------------------------------

def load_cursor() -> dict:
    try:
        return json.loads(CURSOR_FILE.read_text())
    except Exception:
        return {}


def save_cursor(cursor: dict) -> None:
    try:
        CURSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CURSOR_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(cursor))
        tmp.replace(CURSOR_FILE)
    except Exception as e:
        log(f"cursor: could not save ({e})")


def plan(tickers: list[dict], cursor: dict) -> tuple[list[dict], dict]:
    """Split the watchlist into what this pipeline can collect and what it
    cannot, then order the workable part most-overdue first.

    A company the pipeline cannot collect is not a failure: its `source` names
    the wire the firehose found it on, and sync_*.py collects it.
    """
    known = set(sources.names())
    workable, deferred = [], {}
    for cfg in tickers:
        name = cfg.get("source", DEFAULT_SOURCE)
        if name in known and name not in SKIP_SOURCES:   # SRVAUDIT_SCRAPERFIX_20261028
            workable.append(cfg)
        else:
            deferred[name] = deferred.get(name, 0) + 1
    # Never attempted sorts first (empty string precedes any timestamp).
    workable.sort(key=lambda c: cursor.get(c.get("ticker", ""), ""))
    return workable, deferred


def build_envelope(candidate: dict, cls: dict, cfg: dict, event_id: str) -> dict:
    conf = cls["classifier_confidence"]
    threshold = AUTO_THRESHOLD.get(cls["event_type"], 1.01)
    review_status = "auto_approved" if conf >= threshold else "pending_review"
    payload = {
        "summary": cls.get("summary", ""),
        "tags":    cls.get("tags", []),
        "ticker":  cfg.get("ticker") or candidate.get("ticker"),
    }
    return {
        "event_id":              event_id,
        "event_type":            cls["event_type"],
        "ticker":                cfg.get("ticker") or candidate.get("ticker"),
        "company_id":            cfg.get("company_id"),
        "property_id":           cfg.get("property_id"),
        "source_url":            candidate["source_url"],
        "source_name":           candidate["source_name"],
        "published_at":          candidate.get("published_at") or dt.datetime.utcnow().isoformat() + "Z",
        "classified_at":         dt.datetime.utcnow().isoformat() + "Z",
        "classifier_model":      cls["classifier_model"],
        "classifier_confidence": conf,
        "review_status":         review_status,
        "raw_headline":          candidate.get("raw_headline", "")[:500],
        "raw_excerpt":           candidate.get("raw_excerpt", "")[:1500],
        "raw_body":              candidate.get("raw_body", "")[:50000],
        "raw_html":              candidate.get("raw_html", "")[:200000],
        "payload":               payload,
    }


def sign_and_post(envelope: dict) -> tuple[int, str]:
    if not HMAC_SECRET:
        return 0, "MNT_HMAC_SECRET not configured"
    body = json.dumps(envelope, separators=(",", ":"))
    ts = str(int(time.time()))
    base = f"{ts}.{body}".encode("utf-8")
    sig = "sha256=" + hmac.new(HMAC_SECRET.encode("utf-8"), base, hashlib.sha256).hexdigest()
    url = f"{PORTAL_INGEST}/{envelope['event_type']}"
    headers = {
        "Content-Type": "application/json",
        "X-MNT-Timestamp": ts,
        "X-MNT-Signature": sig,
    }
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post(url, content=body, headers=headers)
        return r.status_code, r.text[:500]
    except Exception as e:
        return -1, str(e)[:300]


def archive_envelope(envelope: dict):
    sub = "auto" if envelope["review_status"] == "auto_approved" else "pending"
    d = EVENTS_DIR / sub
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{envelope['event_id']}.json").write_text(
        json.dumps(envelope, indent=2, default=str)
    )



# OPSFIX item 9 (2026-10-05): a Google News lookup takes ~110 s per company, every other method about a second.
# Mixed together, a run got through ~9 companies and every company waited ~10 hours between checks. Now the
# fast-method companies not checked in the last FAST_EVERY_S go first (about a minute in total), and the slow
# ones fill the rest of the budget, most overdue first, exactly as before.
FAST_EVERY_S = int(os.environ.get("MNT_PIPELINE_FAST_EVERY_S", "3600"))
SLOW_SOURCES = {x.strip() for x in os.environ.get("MNT_PIPELINE_SLOW_SOURCES", "accesswire").split(",") if x.strip()}

# SRVAUDIT_SCRAPERFIX_20261028 (Justin): globenewswire_gnews re-ran the same Google News discovery for every company
# and GlobeNewswire answers this server with 403, so each lookup took ~135 s and 1,080 of 1,081 items were
# quality-skipped (10-28: 123 lookups, 277 min, 1 post). Runs hit the 600 s systemd limit 12 times that day.
# Those companies are now left to the GlobeNewswire wire collector (sync_globenewswire.py). Set
# MNT_PIPELINE_SKIP_SOURCES="" to bring them back. LOOKUP_CAP_S stops taking items from one lookup after that many
# seconds (checked between items); SLOW_RESERVE_S keeps a slow lookup from starting near the end of the budget.
SKIP_SOURCES = {x.strip() for x in os.environ.get("MNT_PIPELINE_SKIP_SOURCES", "globenewswire_gnews").split(",") if x.strip()}
LOOKUP_CAP_S = int(os.environ.get("MNT_PIPELINE_LOOKUP_CAP_S", "30"))
SLOW_RESERVE_S = int(os.environ.get("MNT_PIPELINE_SLOW_RESERVE_S", "120"))


def _is_slow(cfg: dict) -> bool:
    name = cfg.get("source", DEFAULT_SOURCE) or ""
    return name.endswith("_gnews") or name in SLOW_SOURCES


def _fast_first(workable: list, cursor: dict, now=None) -> tuple:
    now = now or dt.datetime.utcnow()
    def due(c):
        last = cursor.get(c.get("ticker", ""), "")
        if not last:
            return True
        try:
            return (now - dt.datetime.fromisoformat(last.rstrip("Z"))).total_seconds() >= FAST_EVERY_S
        except ValueError:
            return True
    fast = [c for c in workable if not _is_slow(c) and due(c)]
    ids = {id(c) for c in fast}
    return fast + [c for c in workable if id(c) not in ids], len(fast)


# POSTRETRY_V1 (2026-11-08): a post that failed for a passing reason (timeout, 5xx, 429, ...) is not marked seen,
# so the next run posts it again; after POST_MAX_TRIES failed runs it is given up on. Undo: patch_postretry.py --undo
POST_RETRY_FILE = APP_ROOT / "data" / "pipeline_post_retry.json"
POST_MAX_TRIES = int(os.environ.get("MNT_PIPELINE_POST_TRIES", "5"))
POST_FINAL_CODES = {400, 404, 409, 413, 422}       # answers that will not change on a retry


def _post_retry_load() -> dict:
    try:
        d = json.loads(POST_RETRY_FILE.read_text())
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _post_retry_save(d: dict) -> None:
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=30)).isoformat()
    d = {k: v for k, v in d.items() if str(v.get("at", "")) >= cutoff}
    tmp = POST_RETRY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1, sort_keys=True))
    os.replace(tmp, POST_RETRY_FILE)


def _post_settled(eid: str, code: int) -> bool:
    """True when the release should be marked seen (posted, refused for good, or out of tries)."""
    d = _post_retry_load()
    if 200 <= code < 300 or code in POST_FINAL_CODES:
        if d.pop(eid, None) is not None:
            _post_retry_save(d)
        return True
    tries = int((d.get(eid) or {}).get("tries", 0)) + 1
    if tries >= POST_MAX_TRIES:
        d.pop(eid, None)
        _post_retry_save(d)
        log(f"post failed {tries} times (last status {code}); giving up on {eid[:12]}..")
        return True
    d[eid] = {"tries": tries, "last_code": code, "at": dt.datetime.utcnow().isoformat()}
    _post_retry_save(d)
    log(f"post failed (status {code}); {eid[:12]}.. stays unseen and is tried again next run "
        f"(try {tries} of {POST_MAX_TRIES})")
    return False


# ---- main -----------------------------------------------------------------
def main():
    if not HMAC_SECRET:
        log("FATAL: MNT_HMAC_SECRET not set")
        sys.exit(2)

    started = time.monotonic()
    seen = load_seen()
    tickers = load_tickers()
    cursor = load_cursor()
    workable, deferred = plan(tickers, cursor)
    workable, n_fast = _fast_first(workable, cursor)
    log(f"fast tier: {n_fast} companies due (each checked every {FAST_EVERY_S}s); "
        f"slow lookups fill the rest of the budget")

    log(f"starting cycle; watchlist={len(tickers)} collectable_here={len(workable)} "
        f"seen={len(seen)} budget={TIME_BUDGET_S}s")
    if deferred:
        detail = ", ".join(f"{k}={v}" for k, v in sorted(deferred.items()))
        log(f"collected by the wire scrapers, not here: {sum(deferred.values())} "
            f"companies ({detail})")

    new_count = 0
    done = 0
    for cfg in workable:
        if time.monotonic() - started > TIME_BUDGET_S:
            log(f"time budget reached after {done} companies; "
                f"{len(workable) - done} wait for the next run")
            break
        if _is_slow(cfg) and time.monotonic() - started > TIME_BUDGET_S - SLOW_RESERVE_S:   # SRVAUDIT_SCRAPERFIX_20261028
            log(f"less than {SLOW_RESERVE_S}s of budget left; no new slow lookup this run "
                f"({len(workable) - done} wait for the next run)")
            break

        ticker = cfg.get("ticker", "?")
        source_name = cfg.get("source", DEFAULT_SOURCE)
        # Stamp before the work, not after: a company that times out or throws
        # must still rotate to the back, or one bad company blocks the queue
        # for everything behind it.
        cursor[ticker] = dt.datetime.utcnow().isoformat() + "Z"
        done += 1

        try:
            src = sources.get(source_name)
        except KeyError as e:
            log(f"skip {ticker}: {e}")
            continue

        log(f"--- {ticker} via {source_name} ---")
        try:
            candidates = []   # SRVAUDIT_SCRAPERFIX_20261028: soft cap per lookup
            _t0 = time.monotonic()
            for _c in src.list_recent(cfg, limit=50):
                candidates.append(_c)
                if time.monotonic() - _t0 > LOOKUP_CAP_S:
                    log(f"{ticker}: lookup cap {LOOKUP_CAP_S}s reached; using the {len(candidates)} found so far")
                    break
        except Exception as e:
            log(f"list_recent failed for {ticker}: {e}")
            continue
        log(f"{ticker}: {len(candidates)} candidate releases")

        for cand in candidates:
            eid = src.event_id_for(cand["source_url"], cand.get("published_at"))
            if eid in seen:
                continue

            try:
                cand = src.fetch_body(cand)
            except Exception as _fb_err:
                log(f"fetch_body exception {cand.get('source_url')}: {_fb_err}")
                continue
            if cand.get("fetch_error"):
                log(f"fetch fail {cand['source_url']}: {cand['fetch_error']}")
                continue
            if not cand.get("raw_body"):
                log(f"empty body {cand['source_url']}; skipping")
                continue

            cand["_source_name"] = cfg.get("source")
            cand["_cfg_website"] = cfg.get("website") or cfg.get("ir_url") or ""
            _qskip = _quality_skip_reason(cand)
            if _qskip:
                log(f"quality-skip {cand['source_url']}: {_qskip}")
                seen.add(eid)  # don't retry
                continue

            cls = classify_event(cand["raw_headline"], cand["raw_body"])
            env = build_envelope(cand, cls, cfg, eid)
            archive_envelope(env)

            code, text = sign_and_post(env)
            log(
                f"post {env['event_type']} id={env['event_id'][:12]}.. "
                f"status={code} conf={cls.get('classifier_confidence'):.2f} "
                f"review={env['review_status']} {text[:120]}"
            )
            new_count += 1
            if _post_settled(eid, code):   # POSTRETRY_V1: a failed post stays unseen and is tried again next run
                seen.add(eid)
                save_seen(seen)

    save_cursor(cursor)
    never = sum(1 for c in workable if c.get("ticker") not in cursor)
    log(f"cycle complete; companies_done={done}/{len(workable)} "
        f"new_events={new_count} never_attempted_left={never} "
        f"elapsed={time.monotonic() - started:.0f}s")


if __name__ == "__main__":
    main()
