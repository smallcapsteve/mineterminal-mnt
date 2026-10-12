"""DATEDUP_V1 (2026-10-10, Justin): one duplicate rule for every collector.

Two copies of the same news release are the same company's release when:
  * they carry the same ticker,
  * their dates are within MAX_GAP_DAYS of each other,
  * their headlines match once ticker/exchange codes and wire prefixes are removed,
  * every number, ordinal and month word in the shared part of the headline agrees
    ("Third Bi-Weekly Update" is not "Fourth Bi-Weekly Update"; Q2 is not Q3),
  * and, when the dates are more than BODY_CHECK_DAYS apart, the bodies match too.

Corrections and amended releases are never treated as copies of the original.

Which copy stays (Justin, 2026-10-10): the wire copy (real time of day, images,
formatting) over the exchange copy (TMX/CSE); then the visible one; then the one
stored first.

This module only decides. portal/db.py's DATEDUP wrapper applies it at ingest;
datedup_night.py applies it to history. Both write to dup_guard_log, which holds
every removed row in full so it can be put back.
"""
from __future__ import annotations

import datetime as dt
import difflib
import html
import json
import re

EXCHANGE_SOURCES = {"tmx", "cse"}
VISIBLE = ("auto_approved", "approved")
MAX_GAP_DAYS = 3
BODY_CHECK_DAYS = 1
HEADLINE_RATIO = 0.90
BODY_RATIO = 0.80
MIN_HEADLINE = 25
MIN_PREFIX = 40

_CORRECTION = re.compile(r"^\s*(correction|corrected|amended|amendment|revised|clarification|updated|restated)\b", re.I)
_WIRE_PREFIX = re.compile(r"^\s*(retransmission|replacement|update|repeat|press release|news release)\s*[:\-–—]\s*", re.I)
# "(ATMY) (ATMYF) (K8J0)", "(TSXV: ABC)", "[CSE:XYZ]", "(OTCQB: ABCDF)" -- upper-case code groups only,
# so "(Phase 2)" or "(the Company)" are kept.
_CODE_GROUP = re.compile(r"[\(\[]\s*(?:[A-Z][A-Z\-\s]{0,12}:\s*)?[A-Z0-9][A-Z0-9.\-]{0,9}"
                         r"(?:\s*[;,|/]\s*(?:[A-Z][A-Z\-\s]{0,12}:\s*)?[A-Z0-9][A-Z0-9.\-]{0,9})*\s*[\)\]]")
_EXCH_CODE = re.compile(r"\b(?:TSX[\s\-]?V|TSXV|TSX|CSE|OTCQB|OTCQX|OTC|NYSE(?:\s+American)?|NASDAQ|FSE|ASX)"
                        r"\s*:\s*[A-Z0-9.]{1,7}\b")
_ORD = {
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
    "eleventh", "twelfth", "final", "initial", "1st", "2nd", "3rd", "4th", "5th", "6th",
    "q1", "q2", "q3", "q4", "h1", "h2", "fy", "half", "quarter",
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep",
    "sept", "oct", "nov", "dec",
}


def is_exchange(source: str | None) -> bool:
    return (source or "").lower() in EXCHANGE_SOURCES


def is_correction(headline: str | None) -> bool:
    return bool(_CORRECTION.match(html.unescape(headline or "")))


def norm_headline(h: str | None) -> list[str]:
    h = html.unescape(h or "")
    h = _WIRE_PREFIX.sub("", h)
    h = re.sub(r"[\(\[]\s*(amended|corrected|correction|revised|updated|restated)\s*[\)\]]", r" \1 ", h, flags=re.I)  # V1.5: not a code group
    h = _CODE_GROUP.sub(" ", h)
    h = _EXCH_CODE.sub(" ", h)
    h = h.lower().replace("’", "'")
    h = re.sub(r"'s\b", "s", h)
    return re.sub(r"[^a-z0-9]+", " ", h).split()


def _markers(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t in _ORD or any(c.isdigit() for c in t)]


_GENERIC = re.compile(r"\b(form\s*7|form\s*5|monthly progress|quarterly listing|news release|"
                      r"corporate update|press release|bi weekly|weekly update|update)\b")

# DATEDUP_V1.5 (2026-10-11): the night run removed ~45 releases whose headline differed from another's by one
# word that changes the news ("Announces" vs "Closes" a placement, "Upsize", "Amends", "Pricing" vs "Offering",
# "Correction", "(AMENDED)", a video interview). A difference in any of these words means two releases.
_STAGE = {
    "announce", "announces", "announced", "announcing", "close", "closes", "closed", "closing", "complete", "completes",
    "completed", "completion", "amend", "amends", "amended", "amending", "amendment", "amendments", "upsize", "upsizes",
    "upsized", "upsizing", "increase", "increases", "increased", "pricing", "prices", "priced", "price", "offering",
    "offer", "proposed", "proposes", "clarifies", "clarification", "launch", "launches", "launched", "revision",
    "revised", "revises", "extend", "extends", "extended", "extension", "reprices", "repricing", "subsequent",
    "initial", "final", "pre", "definitive", "correction", "corrected", "corrects", "confirms", "confirming", "dial",
    "host", "hosts", "call", "development", "update", "updated", "restated", "video", "interview", "signs", "signed",
    "agreement", "terminates", "terminated", "termination", "withdraws", "withdrawn", "commences", "results",
    "arranges", "plans", "files", "filing", "tranche", "intends", "intention", "expected", "receives", "approval",
    "approves", "approved", "conditional", "acceptance", "resumes", "halt", "halted", "postpones", "postponement",
    "cancels", "cancelled", "reschedules",
}


def _stage_differs(ta: list[str], tb: list[str]) -> bool:
    return bool((set(ta) ^ set(tb)) & _STAGE)


def headline_match(a: str | None, b: str | None) -> int:
    """2 = same headline; 1 = same but generic, needs the bodies to agree; 0 = different."""
    if is_correction(a) or is_correction(b):
        return 0
    ta, tb = norm_headline(a), norm_headline(b)
    sa, sb = " ".join(ta), " ".join(tb)
    if not sa or not sb:
        return 0
    if _stage_differs(ta, tb):
        return 0
    k = min(len(ta), len(tb))
    if _markers(ta[:k]) != _markers(tb[:k]):
        return 0
    if min(len(sa), len(sb)) < MIN_HEADLINE:
        return 1 if (sa == sb and len(sa) >= 12) else 0
    short, long_ = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
    hit = (len(short) >= MIN_PREFIX and long_.startswith(short)) or \
        difflib.SequenceMatcher(None, sa, sb, autojunk=False).ratio() >= HEADLINE_RATIO
    if not hit:
        return 0
    return 1 if _GENERIC.search(short) and len(short) < 60 else 2


def same_headline(a: str | None, b: str | None) -> bool:
    """True only for a headline match that needs no body check."""
    return headline_match(a, b) == 2


def _body_words(body: str | None, n: int = 300) -> list[str]:
    t = re.sub(r"<[^>]+>", " ", body or "")
    t = html.unescape(t).lower()
    return re.sub(r"[^a-z0-9]+", " ", t).split()[:n]


def same_body(a: str | None, b: str | None) -> bool:
    wa, wb = _body_words(a), _body_words(b)
    if len(wa) < 40 or len(wb) < 40:
        return False
    sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
    if sm.quick_ratio() < BODY_RATIO:
        return False
    return sm.ratio() >= BODY_RATIO


def _date(s: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def is_copy(a: dict, b: dict) -> bool:
    """a and b: dicts with ticker, published_at, raw_headline, raw_body."""
    if not a.get("ticker") or a.get("ticker") != b.get("ticker"):
        return False
    da, db_ = _date(a.get("published_at")), _date(b.get("published_at"))
    if not da or not db_:
        return False
    gap = abs((da - db_).days)
    if gap > MAX_GAP_DAYS:
        return False
    m = headline_match(a.get("raw_headline"), b.get("raw_headline"))
    if m == 0:
        return False
    if m == 1 or gap > BODY_CHECK_DAYS:
        return same_body(a.get("raw_body"), b.get("raw_body"))
    return True


def keep_rank(e: dict) -> tuple:
    """Lower sorts first = the copy to keep, among copies dated within a day of each other."""
    return (
        1 if is_exchange(e.get("source_name")) else 0,
        0 if (e.get("review_status") in VISIBLE) else 1,
        e.get("ingested_at") or "9999",
        e.get("event_id") or "",
    )


def choose_keeper(members: list[dict]) -> dict:
    """The copy to keep. The announcement date wins first: only copies dated within a day of the
    earliest copy are eligible (a wire re-send days later must not carry the release's date). Among
    those, keep_rank: wire over exchange, visible, first stored."""
    dates = [d for d in (_date(m.get("published_at")) for m in members) if d]
    if dates:
        first = min(dates)
        eligible = [m for m in members
                    if _date(m.get("published_at")) and (_date(m.get("published_at")) - first).days <= BODY_CHECK_DAYS]
        if eligible:
            return min(eligible, key=keep_rank)
    return min(members, key=keep_rank)


# ---------------------------------------------------------------- storage

LOG_DDL = """CREATE TABLE IF NOT EXISTS dup_guard_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL,
  action TEXT NOT NULL,          -- skipped_new | replaced_exchange | deleted_history | restored
  event_id TEXT NOT NULL,        -- the copy that was skipped or removed
  kept_id TEXT,                  -- the copy that stays
  ticker TEXT, source_name TEXT, kept_source TEXT,
  published_at TEXT, headline TEXT,
  row_json TEXT                  -- the removed row in full, for undo
);
CREATE INDEX IF NOT EXISTS ix_dup_guard_log_eid ON dup_guard_log(event_id);"""

EVENT_COLS = ("event_id", "event_type", "ticker", "company_id", "property_id", "source_url",
              "source_name", "published_at", "classified_at", "classifier_model",
              "classifier_confidence", "review_status", "raw_headline", "raw_excerpt",
              "raw_body", "raw_html", "payload_json", "ingested_at", "categories", "slug",
              "additional_tickers")


def ensure_log(conn) -> None:
    conn.executescript(LOG_DDL)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(conn, action: str, removed: dict, kept: dict | None, full_row: bool) -> None:
    conn.execute(
        "INSERT INTO dup_guard_log (at, action, event_id, kept_id, ticker, source_name, kept_source,"
        " published_at, headline, row_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (now(), action, removed.get("event_id"), (kept or {}).get("event_id"), removed.get("ticker"),
         removed.get("source_name"), (kept or {}).get("source_name"), removed.get("published_at"),
         (removed.get("raw_headline") or "")[:300],
         json.dumps({k: removed.get(k) for k in EVENT_COLS}) if full_row else None))


def was_removed(conn, event_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM dup_guard_log WHERE event_id = ? AND action IN "
        "('replaced_exchange','deleted_history','skipped_new') LIMIT 1", (event_id,)).fetchone() is not None


def load_row(conn, event_id: str) -> dict | None:
    r = conn.execute(f"SELECT {','.join(EVENT_COLS)} FROM events WHERE event_id = ?", (event_id,)).fetchone()
    return dict(zip(EVENT_COLS, tuple(r))) if r else None


def restore_row(conn, row: dict) -> None:
    cols = [c for c in EVENT_COLS if c in row]
    conn.execute(f"INSERT OR IGNORE INTO events ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                 [row[c] for c in cols])


def find_visible_twin(conn, row: dict) -> dict | None:
    """The best visible stored copy of `row`, if any."""
    d = _date(row.get("published_at"))
    if not row.get("ticker") or not d or not row.get("raw_headline"):
        return None
    lo = (d - dt.timedelta(days=MAX_GAP_DAYS)).isoformat()
    hi = (d + dt.timedelta(days=MAX_GAP_DAYS + 1)).isoformat()
    cands = conn.execute(
        "SELECT event_id, ticker, published_at, raw_headline, raw_body, source_name, review_status, ingested_at"
        " FROM events WHERE ticker = ? AND published_at >= ? AND published_at < ?"
        " AND review_status IN ('auto_approved','approved') AND event_id != ?",
        (row["ticker"], lo, hi, row.get("event_id") or "")).fetchall()
    keys = ("event_id", "ticker", "published_at", "raw_headline", "raw_body", "source_name",
            "review_status", "ingested_at")
    twins = [dict(zip(keys, tuple(c))) for c in cands]
    twins = [t for t in twins if is_copy(row, t)]
    return min(twins, key=keep_rank) if twins else None


def new_copy_replaces(row: dict, twin: dict) -> bool:
    """At ingest: does the arriving copy replace the stored twin? Only a wire copy replacing an
    exchange copy, and only when it is not dated more than a day later (choose_keeper's rule)."""
    if is_exchange(row.get("source_name")) or not is_exchange(twin.get("source_name")):
        return False
    d_new, d_old = _date(row.get("published_at")), _date(twin.get("published_at"))
    if not d_new or not d_old:
        return False
    return (d_new - d_old).days <= BODY_CHECK_DAYS


# ---------------------------------------------------------------- DATEDUP_V1.5: strict dateline (2026-10-11)
# The general date reader took the first plausible date in the text, which is often a date the release only
# mentions ("further to its June 12 news release", "see news August 31", a warrant expiry, "since August 23,
# 2025"). A date counts here only when it sits in a dateline: right after "News Release" / "(Newsfile Corp. -"
# style wording, or directly followed by the dash, bracket or colon that ends a dateline, and never after words
# like "further to", "dated", "since", "until", "announced on". Otherwise the exchange date stays.
_MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_D = r"(\d\s?\d|\d)"
_Y = r"(2\s?0\s?\d\s?\d)"
_MON = r"(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.?"
_PAT_MDY = re.compile(_MON + r"\s+" + _D + r"(?:st|nd|rd|th)?,?\s+" + _Y)
_PAT_DMY = re.compile(_D + r"(?:st|nd|rd|th)?\s+" + _MON + r",?\s+" + _Y)
_BAD_BEFORE = re.compile(r"\b(see|further|dated|since|until|announced|on|of|from|to|before|after|effective|expir\w*|"
                         r"by|between|and|until|through|ended|ending|as at|as of|filed|released|prior|previous\w*)\W*$", re.I)
_BAD_NEAR = re.compile(r"\b(see|further to|dated|since|until|announced|news of|reported|refer)\b", re.I)
_GOOD_BEFORE = re.compile(r"(news release|press release|for immediate release|newsfile corp\.?\s*-|/cnw/|"
                          r"globe newswire\)?|accesswire|thenewswire|\bnr\b)\W*$", re.I)
_GOOD_AFTER = re.compile(r"^\s*[–—─\-\)\:/|]")


def _year_typo(d: dt.date, upload: dt.date) -> bool:
    """DATEDUP_V1.6 (2026-10-12): a dateline one year before the exchange date, within 3 days of the same
    month and day, is the company typing last year (SYG.V and SAE.V in two weeks), not a year-old release."""
    if d.year != upload.year - 1:
        return False
    try:
        same = d.replace(year=upload.year)
    except ValueError:                    # February 29
        return False
    return abs((same - upload).days) <= 3


def strict_release_date(body: str | None, upload: dt.date, max_back_days: int = 400):
    """(date, 'dateline') when the release states its own date in a dateline, else (upload, 'upload')."""
    t = re.sub(r"<[^>]+>", " ", body or "")
    t = re.sub(r"\s+", " ", html.unescape(t))[:2500]
    found = []
    for pat, order in ((_PAT_MDY, "mdy"), (_PAT_DMY, "dmy")):
        for m in pat.finditer(t):
            g = m.groups()
            mon, day, yr = (g[0], g[1], g[2]) if order == "mdy" else (g[1], g[0], g[2])
            try:
                d = dt.date(int(yr.replace(" ", "")), _MONTHS[mon[:3].lower()], int(day.replace(" ", "")))
            except (ValueError, KeyError):
                continue
            found.append((m.start(), m.end(), d))
    for start, end, d in sorted(found):
        if not (upload - dt.timedelta(days=max_back_days) <= d <= upload):
            continue
        if _year_typo(d, upload):
            continue                      # V1.6: "October 7, 2025" on a release the exchange got on Oct 7, 2026
        before = t[max(0, start - 40):start]
        after = t[end:end + 4]
        if _BAD_BEFORE.search(before) or _BAD_NEAR.search(before[-28:]):
            continue
        if _GOOD_BEFORE.search(before) or _GOOD_AFTER.search(after):
            return d, "dateline"
    return upload, "upload"
