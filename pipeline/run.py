"""
Pipeline entry point.

Flow:
  1. Load tickers.json — each entry names a `source` and optional `source_params`
  2. For each ticker: pick the source module, fetch recent PR summaries
  3. Dedupe against seen_events.json (per-source event_id)
  4. Fetch body, classify, build envelope, POST to portal /ingest/<event_type>
  5. Log and archive envelopes

Run it:
  /opt/mnt/app/.venv/bin/python -m pipeline.run
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
PORTAL_INGEST = os.environ.get("PORTAL_INGEST_URL", "http://104.131.123.144/ingest").rstrip("/")
TICKERS_FILE  = APP_ROOT / "tickers.json"
SEEN_FILE     = APP_ROOT / "data" / "seen_events.json"
LOG_DIR       = APP_ROOT / "data" / "logs"
EVENTS_DIR    = APP_ROOT / "data" / "events"

# Review policy — mirrors blueprint. Keyed by event_type -> threshold for auto.
AUTO_THRESHOLD = {
    "news_item":         0.70,
    "mgmt_change":       0.85,
    "production_update": 0.85,
    "financing":         0.90,
    # Always-review types:
    "drill_result":      1.01,
    "resource_estimate": 1.01,
    "econ_study":        1.01,
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


# ---- main -----------------------------------------------------------------
def main():
    if not HMAC_SECRET:
        log("FATAL: MNT_HMAC_SECRET not set")
        sys.exit(2)

    seen = load_seen()
    tickers = load_tickers()
    log(f"starting cycle; tickers={[t['ticker'] for t in tickers]} seen={len(seen)}")

    new_count = 0
    for cfg in tickers:
        ticker = cfg.get("ticker", "?")
        source_name = cfg.get("source", DEFAULT_SOURCE)
        try:
            src = sources.get(source_name)
        except KeyError as e:
            log(f"skip {ticker}: {e}")
            continue

        log(f"--- {ticker} via {source_name} ---")
        try:
            candidates = list(src.list_recent(cfg, limit=50))
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
            seen.add(eid)
            new_count += 1
            save_seen(seen)

    log(f"cycle complete; new_events={new_count}")


if __name__ == "__main__":
    main()
