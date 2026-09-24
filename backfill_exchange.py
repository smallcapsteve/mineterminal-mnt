#!/usr/bin/env python3
"""BACKFILL_EXCHANGE — fill MNT's historical gaps from the exchanges.

Justin, 2026-09-14: *"is there a way we can start to backfill MNT news
releases? Can we start by getting all of 2026 onto MNT?"*

**Why this is a separate script.** `exchange_news.py` is the four-hourly
collector: small windows, small caps, and the site's normal review policy. A
backfill is a different job with different risks — thousands of releases in one
run, real money spent on classification, and a decision about the review gate
that must not leak into the live path. Keeping it separate means the timer job
stays exactly as reviewed. Everything that *reconciles* is imported from
`exchange_news`, so there is one implementation of "is this already on the
site", not two.

**What it measured before it was written** (2026-09-14, read-only):

  * The CSE whole-market feed lists **3,856 releases for our 346 CSE companies
    in 2026**. MNT already holds 1,861. **1,995 are missing**, and of 40 opened
    and checked, 40 were genuine gaps — a 100% hit rate, not a matching bug.
  * The TMX filings store holds **9,159 news releases** for our 697 TSX/TSXV
    companies in 2026. Stage 1 covers 2,838 of them by count; **6,152 are
    candidates**.
  * The gap is **year-round** on CSE, and heavily front-loaded on TMX: 1,077,
    1,139, 1,002 and 911 candidates for Jan–Apr against 475, 450, 383, 429 for
    May–Aug. MNT's own volume triples in May, which is when the collectors came
    up.

**The review-gate decision, and why it is not a policy change.**
`AUTO_THRESHOLD` gives `drill_result`, `resource_estimate`, `econ_study` and
`paid_promotion` a threshold of **1.01**, which no confidence can reach: they
are always held for review, and `pending_review` is excluded from the news API,
so such an event appears on no site. With the classifier *off* — how the 9,231
`disabled` events were ingested — every release is `news_item` at confidence
1.0 and publishes. So switching classification on would take the most valuable
third of the backfill *off* the site.

Justin's call: classify for the event types, and auto-approve backfilled items
regardless of type, tagged `backfill_exchange`. Deferred on the same day, so the
2026 run went out unclassified; `raw_body` is stored, so a later pass can
classify these rows without re-fetching anything, and the tag is written whether
or not the classifier ran. **`pipeline/run.py` is untouched.**

**Titles are not headlines** — `backfill_titles.py`. 12% of the CSE feed's own
titles are boilerplate or placeholders, and TMX has no titles at all: `name` is
the literal string "News release" on 9,095 of 9,198 rows, so every TSX/TSXV
headline is read out of the document.

**Feed dates are not release dates** — `backfill_dates.py`. This one cost us:
the first full run published 203 duplicates because the duplicate check ran
against the date the *exchange received* the document rather than the date the
company issued it. Etruscus uploaded five releases in one batch dated
2026-08-13 that had been issued across 2025, so each landed months from the
wire's copy and no ±3-day window could pair them.

The fix is an ordering, and it is the shape of the whole script: **stage 2 opens
the document, takes the real date out of it, matches on that date, and only then
publishes.** Matching before opening the document is precisely the bug, and it
is why stage 1 cannot be made to catch these — stage 1 exists to decide whether
a fetch is worth paying for, not whether to publish.

**A correct date is necessary but not sufficient**, which the regression test
against those 203 duplicates showed plainly: 155 fall out from the date alone,
36 more need a similarity comparison because the wire reworded slightly, and a
further set need a wider window because *the wire itself* is days late. Hence
the two tiers in `find_twin`. The thresholds are not guesses; each was chosen
against the near-misses that would break it.

**Preconditions gate the run, they do not merely precede it.** Twice this system
has produced a confident, wrong, zero-exit summary because a missing dependency
looked like an empty result. So every precondition is checked *before the first
fetch*:

    extractor · title rules · date rules · HMAC · portal · disk · classifier

and mid-run, three consecutive classifier errors abort rather than quietly
filling the site with confidence-0.0 guesses.

Run:
    python3 backfill_exchange.py --source cse --since 2026-01-01 --dry-run --no-classify
    python3 backfill_exchange.py --source cse --since 2026-01-01 --apply --no-classify
    python3 backfill_exchange.py --source tmx --since 2026-01-01 --apply --no-classify
    python3 backfill_exchange.py --self-test
    python3 backfill_exchange.py --stats
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import os
import shutil
import sys
import time

APP_ROOT = "/opt/mnt/app"
sys.path.insert(0, APP_ROOT)

import backfill_dates as D          # noqa: E402  document -> real release date
import backfill_titles as T         # noqa: E402  title and headline rules
import exchange_news as X           # noqa: E402  the reconcile lives there

BACKFILL_TAG = "backfill_exchange"

# Two tiers, because two different things go wrong. Close in time, the headline
# may be reworded by the wire, so 0.90 is right. Further out, only a
# near-identical headline is safe, because "Upsize of Bought Deal Equity
# Offering" and "Closing of Bought Deal Equity Offering" are 13 days apart and
# genuinely different releases — they score below 0.97 and must stay separate.
TWIN_WINDOW_DAYS, TWIN_SIMILARITY = 3, 0.90
TWIN_WIDE_DAYS, TWIN_WIDE_SIMILARITY = 21, 0.97

SAMPLE_HEADLINE = "Example Gold Corp. Reports Drill Results from the Example Project"
SAMPLE_BODY = (
    "VANCOUVER, BC - Example Gold Corp. today reported assay results from its "
    "2026 drill program, including 12.4 metres grading 3.1 g/t gold from 84 "
    "metres in hole EX-26-001. The program comprised 14 holes totalling 3,200 "
    "metres. Drilling is ongoing and further results are expected."
)


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}] {msg}", flush=True)


def headline_for(rel: dict, body: str) -> tuple[str, str]:
    """(headline, where it came from).

    The feed title when it says something, the document when it does not, and
    the cleaned title as a last resort — because a thin headline still beats
    the words "News release", and a PDF that will not parse should not cost us
    the release entirely.

    For TMX there is never a usable title, so this is always the document.
    """
    t = T.clean_title(rel.get("title", ""))
    if not T.title_is_hollow(t):
        return t, ("feed" if t == (rel.get("title") or "").strip() else "feed_cleaned")
    from_pdf = D.trim_at_dateline(T.headline_from_body(body, "")) if body else ""
    if from_pdf and not T.title_is_hollow(from_pdf):
        return from_pdf[:300], "pdf"
    return (t or (rel.get("title") or "").strip() or "News release"), "fallback"


def dated(rel: dict, body: str) -> tuple[dt.date, str]:
    """The date the company issued this release, not the date the exchange
    received it. See backfill_dates for why that distinction matters."""
    upload = dt.date.fromisoformat(rel["published_date"][:10])
    return D.release_date(body, upload)


def find_twin(pcon, rel: dict, headline: str, published: dt.date):
    """(event_id, wrong_ticker) — is this release already on the site?

    `X.find_match` first, which compares headline prefixes against the date the
    document gives. Then two similarity tiers, because a correct date turned out
    to be necessary and not sufficient:

      **±3 days at 0.90.** The wire rewords. 36 of the 203 duplicates the first
      run created differed only as "Norsemont Appoints Ariel Tepperman to Its
      Board" differs from "Norsemont Mining Appoints Ariel Tepperman to Its
      Board" — one extra word at the front, and a prefix comparison is defeated.

      **±21 days at 0.97.** The wire is late, or our own date is off. Appia's
      appointment is dated 2026-08-18 in the document and 2026-09-01 by the
      wire. Prismo's release announces a webinar *on* February 26th and says so
      in the headline, so the date extractor took the webinar date rather than
      the release date; the wire has it right at the 18th.

    The tighter threshold is what makes the wider window safe. Annual
    recurrences — an AGM, a repeated placement — sit 180+ days out and are
    untouched by either tier.
    """
    match_rel = dict(rel, published_date=published.isoformat())
    eid, wrong = X.find_match(pcon, match_rel, title=headline)
    if eid:
        return eid, wrong

    n1 = X.norm(headline)
    if len(n1) < 25:
        return None, None
    iso = published.isoformat()
    rows = pcon.execute(
        "SELECT event_id, raw_headline, date(published_at) FROM events "
        "WHERE (ticker = ? OR ticker LIKE ?) AND date(published_at) BETWEEN date(?,?) AND date(?,?)",  # SHORTFIX_V1
        (rel["bare"], rel["bare"] + ".%", iso, f"-{TWIN_WIDE_DAYS} day", iso, f"+{TWIN_WIDE_DAYS} day"),
    ).fetchall()
    for eid2, hl, other_day in rows:
        n2 = X.norm(hl)
        if len(n2) < 25:
            continue
        try:
            gap = abs((dt.date.fromisoformat(other_day) - published).days)
        except (TypeError, ValueError):
            continue
        sim = difflib.SequenceMatcher(None, n1[:90], n2[:90]).ratio()
        if gap <= TWIN_WINDOW_DAYS and sim >= TWIN_SIMILARITY:
            return eid2, None
        if sim >= TWIN_WIDE_SIMILARITY:
            return eid2, None
    return None, None


# --------------------------------------------------------------------------
# preconditions
# --------------------------------------------------------------------------

# The ledger mnt-exchange.service runs with. Only used to tell the operator
# when this process resolved a different one.
SERVICE_LEDGER = "/var/lib/mnt-exchange/exchange_news.db"


def preflight(want_classifier: bool, need_free_mb: int = 2048) -> dict:
    """Prove every dependency before a single PDF is fetched."""
    log("preflight:")

    # The ledger is the dependency that silently forked the bookkeeping on
    # 2026-09-15. DB_PATH is env-or-default, and a transient systemd-run unit
    # inherits no environment, so a 272-minute run wrote its record of what it
    # had settled to a file the live service never reads. Nothing was lost and
    # nothing was duplicated -- stage 1 checks the portal, not this table --
    # but the run could not skip work an earlier run had already done, and the
    # next one would not have skipped this run's. Name the file, and say where
    # the name came from, so a split is visible in the first ten lines of the
    # log instead of four hours later.
    _from_env = "EXCHANGE_NEWS_DB" in os.environ
    _rows = "new file"
    if os.path.exists(X.DB_PATH):
        try:
            _c = X.sqlite3.connect(f"file:{X.DB_PATH}?mode=ro", uri=True)
            _n = _c.execute("SELECT count(*) FROM releases").fetchone()[0]
            _c.close()
            _rows = f"{_n} rows"
        except Exception as _e:                      # noqa: BLE001
            _rows = f"unreadable ({type(_e).__name__})"
    log(f"  ledger               {X.DB_PATH} ({_rows}, from "
        f"{'EXCHANGE_NEWS_DB' if _from_env else 'the APP_ROOT default'})")
    if not _from_env and X.DB_PATH != SERVICE_LEDGER:
        log(f"  ledger               WARNING: mnt-exchange.service uses "
            f"{SERVICE_LEDGER}. This run will not see what that ledger has "
            f"settled, and that service will not see what this run settles. "
            f"Set EXCHANGE_NEWS_DB to share one ledger.")

    X._pdf_reader()
    log(f"  PDF extractor        ok ({sys.executable})")

    if X.docx_self_test(verbose=True) != 0:
        raise SystemExit("ABORT: the .docx reader failed its own self-test.")
    log("  DOCX extractor       ok")

    if T.self_test(verbose=False) != 0:
        raise SystemExit("ABORT: the title rules failed their own self-test — run "
                         "`python3 backfill_titles.py` to see which cases.")
    log(f"  title rules          ok ({len(T.SELF_TEST) + len(T.DOC_TEST)} cases)")

    if D.self_test(verbose=False) != 0:
        raise SystemExit("ABORT: the date rules failed their own self-test — run "
                         "`python3 backfill_dates.py` to see which cases.")
    log(f"  date rules           ok ({len(D.SELF_TEST) + len(D.TRIM_TEST)} cases)")

    from pipeline.run import HMAC_SECRET, PORTAL_INGEST
    if not HMAC_SECRET:
        raise SystemExit("ABORT: MNT_HMAC_SECRET is not configured — every post "
                         "would be rejected. Check /opt/mnt/app/.env is readable "
                         "by this user.")
    log(f"  HMAC secret          ok (configured, {len(HMAC_SECRET)} chars, not shown)")

    # Reachability is "did something answer", not "did it answer 200". The
    # first version of this check derived a /health URL and treated its 404 as
    # the portal being down — nginx routes by Host header and simply has no
    # such path on 127.0.0.1.
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(PORTAL_INGEST, timeout=10) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:                       # noqa: BLE001
        raise SystemExit(f"ABORT: portal not reachable at {PORTAL_INGEST} "
                         f"({type(e).__name__} {str(e)[:60]})")
    log(f"  portal               ok ({PORTAL_INGEST} answered {code})")

    free_mb = shutil.disk_usage("/opt").free // (1024 * 1024)
    if free_mb < need_free_mb:
        raise SystemExit(f"ABORT: only {free_mb} MB free on /opt, want {need_free_mb} MB.")
    log(f"  disk                 ok ({free_mb} MB free)")

    from classify.classifier import classify as classify_event
    t0 = time.monotonic()
    probe = classify_event(SAMPLE_HEADLINE, SAMPLE_BODY)
    dtm = time.monotonic() - t0
    model = probe.get("classifier_model")
    tags = probe.get("tags") or []

    if want_classifier:
        if model == "disabled":
            raise SystemExit(
                "ABORT: classification was requested but the classifier is off. "
                "It needs BOTH of these in /opt/mnt/app/.env:\n"
                "    MNT_CLASSIFIER_MODE=on\n"
                "    ANTHROPIC_API_KEY=<key>\n"
                "Set them over SSH, never through the relay — every relay "
                "command and its output is committed to git permanently.")
        if "classifier_error" in tags:
            raise SystemExit(f"ABORT: the classifier errored on the probe: "
                             f"{str(probe.get('error'))[:200]}")
        log(f"  classifier           ok ({model}, probe {dtm:.1f}s, "
            f"returned {probe.get('event_type')} @ {probe.get('classifier_confidence')})")
    else:
        log(f"  classifier           off by request (model would be '{model}') — "
            f"rows are still tagged '{BACKFILL_TAG}' for a later pass")

    return probe


# --------------------------------------------------------------------------
# publish
# --------------------------------------------------------------------------

def publish_backfill(rel: dict, body: str, headline: str,
                     published: dt.date) -> tuple[bool, str, bool]:
    """(ok, note, billed). The only publish path this script has.

    There is deliberately no separate unclassified branch: `classify()` already
    returns a `disabled` result when the classifier is off, so the same code
    covers both, and the `backfill_exchange` tag is applied either way. A second
    branch would have been the obvious way to write this and would have quietly
    dropped the tag from every row of the unclassified run — the rows a future
    classification pass has to find.
    """
    from pipeline.run import build_envelope, sign_and_post, archive_envelope
    from classify.classifier import classify as classify_event

    cls = classify_event(headline, body)
    billed = cls.get("classifier_model") not in (None, "", "disabled")
    if "classifier_error" in (cls.get("tags") or []):
        # Confidence 0.0 with the real model name attached: publishing that
        # would put an unclassified guess on three sites and bill for it.
        return False, f"classifier_error: {str(cls.get('error'))[:70]}", billed

    cand = {
        "source_url": rel["url"],
        "source_name": rel["source"],
        "published_at": published.isoformat() + "T12:00:00Z",
        "raw_headline": headline,
        "raw_excerpt": body[:1500],
        "raw_body": body,
        "raw_html": "",
        "ticker": rel["ticker"],
    }
    cfg = {"ticker": rel["ticker"], "company_id": rel["bare"], "property_id": None}
    eid = X.uid_for(rel["source"], rel["ticker"], rel["published_date"], headline)
    env = build_envelope(cand, cls, cfg, eid)

    was = env["review_status"]
    env["review_status"] = "auto_approved"
    tags = list(env["payload"].get("tags") or [])
    if BACKFILL_TAG not in tags:
        tags.append(BACKFILL_TAG)
    env["payload"]["tags"] = tags

    archive_envelope(env)
    code, text = sign_and_post(env)
    if 200 <= code < 300:
        held = " [gate lifted]" if was != "auto_approved" else ""
        return True, (f"{env['event_type']} conf="
                      f"{cls.get('classifier_confidence')}{held}"), billed
    return False, f"post {code}: {text[:70]}", billed


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--self-test", action="store_true",
                    help="run the title and date rules against their cases and exit")
    ap.add_argument("--since", default="2026-01-01")
    ap.add_argument("--source", choices=("cse", "tmx"), default="cse")
    ap.add_argument("--only", help="comma-separated bare tickers")
    ap.add_argument("--max-ingest", type=int, default=250_000,
                    help="safety brake against a mistyped --since; a run that hits it says so, loudly, at both ends")
    ap.add_argument("--max-classify", type=int, default=10_000)
    ap.add_argument("--sleep", type=float, default=0.4)
    ap.add_argument("--no-classify", action="store_true",
                    help="do not require the classifier; releases land as news_item "
                         "and are still tagged for a later classification pass")
    args = ap.parse_args()

    if args.self_test:
        return T.self_test() | D.self_test()

    con = X.db()

    if args.stats:
        print("backfill state, from the shared releases table:")
        for r in con.execute("SELECT source, status, COUNT(*) FROM releases "
                             "GROUP BY 1,2 ORDER BY 1,3 DESC"):
            print(f"  {r[0]:<5} {r[1]:<10} {r[2]:6d}")
        return 0

    if args.apply == args.dry_run:
        print("pass exactly one of --apply or --dry-run", file=sys.stderr)
        return 2

    if not args.apply:
        log("dry run — preflight still runs, so a missing dependency is found now "
            "rather than at the start of a three-hour job")
    preflight(want_classifier=not args.no_classify)

    only = {X.bare(x) for x in args.only.split(",")} if args.only else None
    cse_u, tsx_u = X.universe_by_exchange()
    log(f"BACKFILL_EXCHANGE ({'APPLY' if args.apply else 'DRY RUN'}) "
        f"source={args.source} since={args.since}")
    log(f"universe: {len(cse_u)} CSE, {len(tsx_u)} TSX/TSXV")

    t0 = time.monotonic()
    if args.source == "cse":
        X.CSE_HEAD_BYTES = int(os.environ.get("CSE_HEAD_BYTES", 80_000_000))
        X.FETCH_TIMEOUT_S = max(X.FETCH_TIMEOUT_S, 300)
        releases = X.pull_cse_fast(cse_u, args.since, only)
    else:
        releases = X.pull_tmx(tsx_u, args.since, only)
    log(f"the exchange lists {len(releases)} releases since {args.since} "
        f"({time.monotonic() - t0:.0f}s)")
    if not releases:
        log("nothing to do")
        return 0

    # The cleaned title rides alongside the raw one. uid_for() keeps hashing the
    # raw title, so cleaning can never orphan an already-settled release and
    # cause it to be fetched and published a second time.
    n_cleaned = n_hollow = 0
    for rel in releases:
        ct = T.clean_title(rel.get("title", ""))
        rel["clean_title"] = ct
        if ct != (rel.get("title") or "").strip():
            n_cleaned += 1
        if T.title_is_hollow(ct):
            n_hollow += 1
    log(f"titles: {n_cleaned} had boilerplate stripped, {n_hollow} say nothing and "
        f"will take their headline from the document")

    pcon = X.sqlite3.connect(f"file:{X.PORTAL_DB}?mode=ro", uri=True)
    now = dt.datetime.now(dt.UTC).isoformat()

    settled = {r[0] for r in con.execute(
        "SELECT uid FROM releases WHERE status IN "
        "('covered','matched','ingested','skipped')")}
    fresh = [r for r in releases
             if X.uid_for(r["source"], r["ticker"], r["published_date"], r["title"])
             not in settled]
    log(f"{len(releases) - len(fresh)} settled by an earlier run; {len(fresh)} to look at")

    def record(rel, status, **kw):
        if not args.apply:
            return
        uid = X.uid_for(rel["source"], rel["ticker"], rel["published_date"], rel["title"])
        con.execute(
            "INSERT INTO releases (uid,ticker,bare,exchange,source,published_date,"
            "title,url,status,matched_event,wrong_ticker,note,acted_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(uid) DO UPDATE SET status=excluded.status, "
            "matched_event=excluded.matched_event, note=excluded.note, "
            "acted_at=excluded.acted_at",
            (uid, rel["ticker"], rel["bare"], rel["exchange"], rel["source"],
             rel["published_date"], rel["title"], rel["url"], status,
             kw.get("event"), kw.get("wrong"), kw.get("note"), now))

    # ---- stage 1: cheap elimination ----------------------------------------
    # Matched on the CLEANED title, and against the FEED date, which is the only
    # date available before the document is opened. That is a real limitation:
    # a release the issuer filed late sits far from its wire twin here and will
    # survive to stage 2. That is the intended division of labour — stage 1 only
    # decides whether a fetch is worth paying for, never whether to publish.
    cov = X.covered_by_count(pcon, [r for r in fresh if r["source"] == "tmx"])
    candidates, n_covered, n_matched = [], 0, 0
    for rel in fresh:
        uid = X.uid_for(rel["source"], rel["ticker"], rel["published_date"], rel["title"])
        if rel["source"] == "tmx":
            if uid in cov:
                n_covered += 1
                record(rel, "covered", note="MNT already had that day's events")
            else:
                candidates.append(rel)
            continue
        eid, wrong = X.find_match(pcon, rel, title=rel.get("clean_title") or rel["title"])
        if eid:
            n_matched += 1
            record(rel, "matched", event=eid, wrong=wrong)
        else:
            candidates.append(rel)
    log(f"stage 1 — {n_covered} covered by count, {n_matched} matched by headline; "
        f"{len(candidates)} candidates remain")

    if args.dry_run:
        by_m: dict = {}
        for r in candidates:
            by_m[r["published_date"][:7]] = by_m.get(r["published_date"][:7], 0) + 1
        for m in sorted(by_m):
            log(f"    {m}  {by_m[m]:5d} to backfill")
        est_s = len(candidates) * (1.0 + (0.0 if args.no_classify else 3.0))
        log(f"estimated run time {est_s/3600:.1f}h at {args.sleep}s spacing, "
            f"{0 if args.no_classify else len(candidates)} billed classifier calls")
        log("dry run — nothing fetched, nothing published")
        return 0

    # ---- stage 2: open, date, match, publish — in that order ----------------
    # The ordering is the fix for the 203 duplicates the first run created.
    n_ing = n_fail = n_late = n_classified = n_moved = 0
    prov_counts: dict = {}
    date_prov: dict = {}
    consecutive_cls_errors = 0
    t1 = time.monotonic()
    n_capped = max(0, len(candidates) - args.max_ingest)
    if n_capped:
        log(f"WARNING: {len(candidates)} candidates but --max-ingest is "
            f"{args.max_ingest} - {n_capped} will NOT be attempted in this "
            f"run. Re-run to pick them up, or raise --max-ingest.")
    for i, rel in enumerate(candidates[:args.max_ingest], 1):
        if not args.no_classify and n_classified >= args.max_classify:
            log(f"stopping: hit --max-classify {args.max_classify}")
            break

        ct = rel.get("clean_title", "")
        probe_rel = dict(rel, title=("" if T.title_is_hollow(ct) else ct))
        body, _pdf_headline, err = X.fetch_release(probe_rel)
        if err:
            n_fail += 1
            record(rel, "error", note=err)
        else:
            headline, prov = headline_for(rel, body)
            prov_counts[prov] = prov_counts.get(prov, 0) + 1

            published, dprov = dated(rel, body)
            date_prov[dprov] = date_prov.get(dprov, 0) + 1
            if published.isoformat() != rel["published_date"][:10]:
                n_moved += 1

            eid, wrong = find_twin(pcon, rel, headline, published)
            if eid:
                n_late += 1
                record(rel, "matched", event=eid, wrong=wrong,
                       note=f"already on site under {published} [{dprov}]")
            else:
                ok, note, billed = publish_backfill(rel, body, headline, published)
                if billed:
                    n_classified += 1
                if ok:
                    n_ing += 1
                    consecutive_cls_errors = 0
                    record(rel, "ingested", note=f"{note} [{prov}/{dprov}]")
                else:
                    n_fail += 1
                    record(rel, "error", note=note)
                    if note.startswith("classifier_error"):
                        consecutive_cls_errors += 1
                        if consecutive_cls_errors >= 3:
                            con.commit()
                            raise SystemExit(
                                "ABORT: three classifier errors in a row — stopping "
                                "rather than filling the site with unclassified "
                                f"guesses. Last error: {note[:160]}")

        if i % 25 == 0:
            con.commit()
            rate = (time.monotonic() - t1) / i
            left = (min(len(candidates), args.max_ingest) - i) * rate
            log(f"  {i}/{min(len(candidates), args.max_ingest)}  "
                f"ingested={n_ing} already_on_site={n_late} failed={n_fail}  "
                f"{rate:.1f}s/release, ~{left/3600:.1f}h left")
        time.sleep(args.sleep)

    con.commit()
    log(f"done in {(time.monotonic()-t1)/60:.0f}m — ingested={n_ing} "
        f"already_on_site={n_late} failed={n_fail} billed_classifier_calls={n_classified}")
    if n_capped:
        log(f"NOTE: this run STOPPED AT THE --max-ingest CAP of "
            f"{args.max_ingest}; {n_capped} candidates were never "
            f"attempted. This is not a finished backfill - re-run it.")
    log(f"headline provenance: {prov_counts}")
    log(f"date provenance: {date_prov}  ({n_moved} releases dated earlier than the "
        f"exchange's own date)")
    log("note: the portal's fuzzy-duplicate guard silently drops a release that "
        "already exists under a near-identical headline, so 'ingested' is an "
        "upper bound on rows actually added.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
