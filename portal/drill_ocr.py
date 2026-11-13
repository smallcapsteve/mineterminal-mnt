"""Drill depths from image tables (DRILL_OCR_V1, 2026-10-13).

Some releases print their drill table as a picture, so the reader has the grade and length of the best interval but no
From-To. This job reads those pictures with tesseract and stores a From-To for the BEST interval only when the
picture proves it (Justin 2026-10-13: strict only). It also marks releases that give no depths anywhere, so the drill
page can say "Not reported" instead of a blank (Justin 2026-10-13).

What it writes: its own small database, /opt/mnt/app/data/drill_ocr.db. portal.db is only read. drill_publish.py
reads drill_ocr.db when it publishes (portal/drill_publish.py, DRILL_OCR_V1) and copies:
  * a fill onto the best interval (from_m, to_m, depth_note='ocr') when the hole, length and grade it was found for
    are still the ones the publisher has;
  * depth_note='not_reported' onto the best interval of a release marked depths='not_reported' (1.1.0: per interval),
    while it still has no From-To.

The strict rule, per text line of the OCR output (hole-id tokens removed before reading numbers):
  two numbers a < b side by side with b - a = the best length (within 2%, at least 0.06 m), and in the same line
  either the best grade (allowing the release to round it) or the best hole id. Exactly one (a, b) must survive
  across all of the release's pictures and passes; two or more different pairs = ambiguous, nothing stored.
  Rules without that arithmetic check (grade + true width, From + Width tables) are NOT used: in the sample one of
  them would have published 19-21 m for a row printed 149 m (an OCR dropped digit).

Pictures: every <img> of the stored HTML except logos, trackers and pictures under 15 KB, at most 12 per release.
The full-size picture is used when there is one: the <a href> around the <img> when it points at a picture, else
Newsfile's own naming (name_550.jpg -> name.jpg). Each picture is read twice: grey and doubled when narrower than
1600 px (pass 1), then the same thresholded at 55% with the table rules removed (pass 2, only when pass 1 found no
match and saw a table: a From/To heading or 4+ decimal numbers; maps and photos are read once). ImageMagick does the image work (no Python imaging packages on the server).

Not reported (1.1.0, per interval, Justin 2026-10-13): the release gives no From-To that fits the best interval -- no
pair of side-by-side numbers in the text whose difference is its length with its grade nearby, no "from <n> m" next
to its grade, no HTML table with From/To or Depth columns, and every picture was read and none shows a From/To or
Depth heading. Anything else is 'unknown' and the page keeps its blank. 1.0.0 was release level and so broad that
almost nothing qualified (any "depth" or "N to M m" anywhere blocked it).
1.1.1 (14 Oct review: 4 of 15 sampled labels were wrong): depth wording next to the grade also blocks the label --
"from 270m", "beginning/starting/commencing at X m", "at X m depth/downhole", "X m downhole", "X m below surface".
--relabel recomputes the labels from stored picture results without reading the pictures again.
1.1.2 (second review: 3-4 of 15 still wrong): the grade inside a row of numbers (a flattened results table -- From +
Width, feet, or depths the reader misread) and "X m from surface" also block the label.
1.1.3 (third review): a reference to a results table that is not in the stored text ("Table 1", "see table below")
blocks the label, and "1,540" is read as 1540 (not 1.54) when matching grades.
1.1.4 (fourth review): depth wording in feet ("starting at 187.0 ft") and "m down- hole" count; a release with less
than 400 characters of stored text is never labelled.
1.1.5 (fifth review): a depth range next to the grade blocks the label even when it is wider than the interval
("over 0.8 m, included in 6.4 m, from 251.5 to 257.9 m", "between 21.3- and 163.1-meters depth"), as does "depth of
480 m"; and an interval whose grade is nowhere in the stored text is never labelled (it came from somewhere we cannot
check).
1.1.6 (sixth review): numbers split by PDF extraction ("from 135 .0 to 142 .3 m") are joined before the checks, and
"at 135 m" next to the grade blocks the label.
1.1.7 (final review): a link to a results table elsewhere ("To view a table of full drill results, please click
here") blocks the label, like "Table 1" does.
Timeouts (1.1.0): identify 180 s, convert 300 s, tesseract 300 s, because mnt-site-guard cuts one-off jobs to 30% CPU
when the site is slow; releases with an unread picture are retried on the next run.

Usage (as mnt, under the one-off queue for long runs):
  python3 -m portal.drill_ocr [--limit N] [--budget SECONDS] [--only EVENT_ID,...] [--dry-run] [--sleep 0.5]
                             [--recent DAYS]   (hourly unit: only releases published in the last DAYS days)
  python3 -m portal.drill_ocr --relabel           (recompute 'not reported' from stored results; no OCR)
  python3 -m portal.drill_ocr --stats
  python3 -m portal.drill_ocr --selftest            (no network, no database)
Switches: /opt/mnt/app/portal/drill_ocr_OFF -> the publisher ignores drill_ocr.db (nothing on the pages changes);
          /opt/mnt/app/portal/drill_ocr_JOB_OFF -> this job does nothing.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request

VERSION = "1.1.0"
DB = "/opt/mnt/app/portal/portal.db"
SIDE = "/opt/mnt/app/data/drill_ocr.db"
JOB_OFF = "/opt/mnt/app/portal/drill_ocr_JOB_OFF"
EXTRACTOR = "drill_results"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
MIN_BYTES = 15000
MAX_BYTES = 12_000_000
MAX_IMAGES = 12
OCR_TIMEOUT = 300

SCHEMA = """
CREATE TABLE IF NOT EXISTS ocr_release (
    event_id    TEXT PRIMARY KEY,
    version     TEXT,
    checked_at  TEXT,
    body_sha1   TEXT,
    best_sig    TEXT,
    status      TEXT,      -- filled | ambiguous | no_match | no_images | error
    depths      TEXT,      -- not_reported | unknown
    n_images    INTEGER,
    n_read      INTEGER,
    seconds     REAL,
    note        TEXT
);
CREATE TABLE IF NOT EXISTS ocr_fill (
    event_id    TEXT PRIMARY KEY,
    hole_id     TEXT,
    length_m    REAL,
    grade       REAL,
    from_m      REAL,
    to_m        REAL,
    rule        TEXT,
    row_text    TEXT,
    image_url   TEXT,
    version     TEXT,
    checked_at  TEXT
);
CREATE TABLE IF NOT EXISTS ocr_image (
    url         TEXT PRIMARY KEY,
    event_id    TEXT,
    fetched_at  TEXT,
    bytes       INTEGER,
    header      INTEGER,
    text        TEXT,
    seconds     REAL,
    error       TEXT
);
"""

# ------------------------------------------------------------------------------------------------ pictures
_IMG = re.compile(r"(?is)(<a\b[^>]*?href=[\"']([^\"']+)[\"'][^>]*>\s*(?:<(?!img\b|/a\b)[^>]+>\s*){0,3})?<img\b([^>]*)>")
_SKIP = re.compile(r"(?i)logo|icon|pixel|tracking|1x1|avatar|badge|spacer|newsinfo/|/api\.|gravatar|share|button")
_PIC = re.compile(r"(?i)\.(?:jpe?g|png|gif|webp|bmp|tiff?)(?:[?#].*)?$")


def _abs(u: str) -> str:
    u = (u or "").strip().replace("&amp;", "&")
    return "https:" + u if u.startswith("//") else u


def pictures(html: str) -> list[tuple[str, str]]:
    """[(url_to_read, src_as_shown)] for the release's pictures, full size when the release links one."""
    out, seen = [], set()
    for m in _IMG.finditer(html or ""):
        s = re.search(r"(?i)\bsrc=[\"']([^\"']+)", m.group(3) or "")
        if not s:
            continue
        src = _abs(s.group(1))
        if not src.startswith("http") or _SKIP.search(src):
            continue
        href = _abs(m.group(2) or "")
        if href.startswith("http") and _PIC.search(href) and not _SKIP.search(href):
            url = href
        else:
            url = re.sub(r"(?i)_550(\.(?:jpe?g|png|gif))$", r"\1", src) if "newsfilecorp.com" in src else src
        if url in seen:
            continue
        seen.add(url)
        out.append((url, src))
        if len(out) >= MAX_IMAGES:
            break
    return out


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        b = r.read(MAX_BYTES + 1)
    if len(b) > MAX_BYTES:
        raise ValueError("too large")
    return b


def _png(data: bytes, threshold: bool) -> bytes:
    """grey, doubled when narrow, optionally thresholded, as PNG (ImageMagick)."""
    w = subprocess.run(["identify", "-format", "%w", "-[0]"], input=data, capture_output=True, timeout=180)
    try:
        width = int((w.stdout or b"0").decode().strip() or 0)
    except ValueError:
        width = 0
    args = ["convert", "-[0]", "-colorspace", "Gray"]
    if 0 < width < 1600:
        args += ["-resize", "200%"]
    if threshold:
        # pass 2: black and white, then table rules removed (runs of 100+ px across or down are painted white)
        args += ["-threshold", "55%",
                 "(", "-clone", "0", "-negate", "-morphology", "Open", "rectangle:100x1", ")",
                 "(", "-clone", "0", "-negate", "-morphology", "Open", "rectangle:1x100", ")",
                 "(", "-clone", "1", "-clone", "2", "-compose", "Lighten", "-composite", ")",
                 "-delete", "1,2", "-compose", "Lighten", "-composite", "-median", "3"]
    args += ["png:-"]
    r = subprocess.run(args, input=data, capture_output=True, timeout=300)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("convert failed: " + (r.stderr or b"")[:200].decode("utf-8", "replace"))
    return r.stdout


def tesseract(png: bytes) -> str:
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    r = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "6"], input=png, capture_output=True,
                       timeout=OCR_TIMEOUT, env=env)
    return (r.stdout or b"").decode("utf-8", "replace")


def read_picture(data: bytes, threshold: bool) -> str:
    return tesseract(_png(data, threshold))


# ------------------------------------------------------------------------------------------------ matching
_NUM = re.compile(r"(?<![\d.,])(\d{1,5}(?:[.,]\d{1,3})?)(?!\d)")
_HOLE_TOKEN = re.compile(r"(?i)\b[a-z]+[-_ ]?\d[\w-]*")
_HEADER = re.compile(r"(?i)\bfrom\b.{0,80}\bto\b|\bdepth\b|\binterval\b.{0,40}\bfrom\b")


def _norm_hole(h: str) -> str:
    h = re.sub(r"[^a-z0-9]", "", (h or "").lower())
    return h.replace("o", "0").replace("i", "1").replace("l", "1")


def _grade_tok(g: float) -> str:
    s = ("%.4f" % g).rstrip("0").rstrip(".")
    return s


def _grade_ok(x: float, g: float) -> bool:
    tok = _grade_tok(g)
    d = len(tok.split(".")[1]) if "." in tok else 0
    return abs(x - g) <= 0.5 * 10 ** -d + 1e-9 or abs(x - g) <= 0.005 * g


def match_lines(text: str, best: dict) -> list[tuple[float, float, str, str]]:
    """Strict matches in one OCR text: [(from, to, rule, line)]."""
    L, g, hole = best.get("length_m"), best.get("grade"), best.get("hole_id")
    if not L or L <= 0 or g is None:
        return []
    nh = _norm_hole(hole) if hole else ""
    out = []
    for line in (text or "").splitlines():
        stripped = _HOLE_TOKEN.sub(" ", line)
        vals = []
        for m in _NUM.finditer(stripped):
            try:
                vals.append(float(m.group(1).replace(",", ".")))
            except ValueError:
                pass
        has_hole = bool(nh) and len(nh) >= 3 and nh in _norm_hole(line)
        for i in range(len(vals) - 1):
            a, b = vals[i], vals[i + 1]
            if not (0 <= a < b < 5000) or abs((b - a) - L) > max(0.06, 0.02 * L):
                continue
            if any(_grade_ok(x, g) for x in vals[i + 2:]):
                out.append((a, b, "length+grade", line.strip()[:200]))
            elif has_hole:
                out.append((a, b, "length+hole", line.strip()[:200]))
    return out


def looks_like_table(text: str) -> bool:
    """pass 2 is only worth its time on a picture pass 1 saw as a table: a From/To heading or 4+ decimal numbers."""
    return bool(_HEADER.search(text or "")) or len(re.findall(r"\d\.\d", text or "")) >= 4


def decide(matches: list[tuple[float, float, str, str, str]]):
    """matches: [(from, to, rule, line, url)] over every picture and pass -> ('filled', m) | ('ambiguous', None) |
    ('no_match', None)."""
    pairs = {(round(a, 3), round(b, 3)) for a, b, *_ in matches}
    if not pairs:
        return "no_match", None
    if len(pairs) > 1:
        return "ambiguous", None
    best = sorted(matches, key=lambda m: m[2] != "length+grade")[0]
    return "filled", best


# ------------------------------------------------------------------------------------------------ not reported
# 1.1.0 (Justin 2026-10-13: per interval). The best interval is 'not reported' when the release gives no From-To that
# fits it: no two numbers side by side in the text whose difference is its length with its grade nearby, no
# "from <n> m" next to its grade, no HTML table with From and To (or Depth) columns, and no table picture (a picture
# read without error and without a From/To or Depth heading is a map or a photo). Same idea as the 12 Oct audit's
# 'none' bucket. General wording ("open at depth", "100-150 m below surface") no longer blocks the label.
_TOK = re.compile(r"(?<![\d.,])(\d{1,4}(?:[.,]\d{1,3})?)(?![\d])")
_TABLE_REF = re.compile(r"(?i)\b(?:see\s+)?tables?\s+\d|\bsee\s+(?:the\s+)?(?:attached\s+)?table|\btable\s+(?:below|above)\b"
                        # 1.1.7: results table linked or attached elsewhere
                        r"|\btables?\s+of\s+(?:the\s+)?(?:full|complete|all|significant)?\s*(?:drill(?:ing|\s*hole)?\s+|assay\s+)?"
                        r"(?:results|intercepts|intersections|assays)\b"
                        r"|\b(?:full|complete)\s+(?:drill(?:ing)?\s+|assay\s+)?results\s+(?:table|are|can|may)\b"
                        r"|\bclick\s+here\b[^.]{0,80}\b(?:table|results)\b|\b(?:table|results)\b[^.]{0,80}\bclick\s+here\b")
# depth wording next to the interval's grade (1.1.1, from the 14 Oct review: "from 270m", "beginning 50.9 metres
# downhole", "starting at 33.5 m downhole", "at 161 m depth", "64 metres below surface" all mean the release gives it)
_U = r"(?:metres|meters|m|feet|ft)(?![a-z])"
_N = r"(\d{1,4}(?:\.\d{1,2})?)"
_DEPTH_WORDS = [
    re.compile(r"(?i)\bfrom\s*:?\s*" + _N + r"\s*" + _U),
    re.compile(r"(?i)\b(?:beginning|starting|commencing)\s+(?:at\s+)?(?:a\s+depth\s+of\s+)?" + _N + r"\s*" + _U),
    re.compile(r"(?i)\bat\s+(?:a\s+)?(?:down-?hole\s+)?(?:depth\s+of\s+)?" + _N + r"\s*" + _U
               + r"\s*(?:down-?\s?hole|depth|deep|along\s+hole)"),
    re.compile(r"(?i)" + _N + r"\s*" + _U + r"\s+(?:down-?\s?hole|depth)\b"),
    re.compile(r"(?i)" + _N + r"\s*" + _U + r"\s+(?:vertically\s+)?below\s+(?:the\s+)?surface"),
    re.compile(r"(?i)" + _N + r"\s*" + _U + r"\s+(?:from|of)\s+(?:the\s+)?surface"),
    # 1.1.5: a depth range near the grade, even one wider than the interval (it contains it)
    re.compile(r"(?i)(?<![\d.,])" + _N + r"\s*(?:" + _U + r")?\s*(?:to|-|–|—)\s*" + _N + r"\s*-?\s*" + _U),
    re.compile(r"(?i)\bbetween\s+" + _N + r"\s*-?\s*(?:" + _U + r")?\s*-?\s*and\s+" + _N + r"\s*-?\s*" + _U),
    re.compile(r"(?i)\bat\s+" + _N + r"\s*" + _U + r"(?!\s*(?:wide|long|apart|spacing|intervals?|true|thick))"),
    re.compile(r"(?i)\bdepths?\s+of\s+(?:approximately\s+|about\s+|~\s*)?" + _N + r"\s*" + _U),
]
_TABLE = re.compile(r"(?is)<table\b.*?</table>")


def _num(tok: str) -> float:
    """'1,540' is one thousand five hundred and forty (1.1.3); '4,49' stays a decimal comma."""
    if "," in tok and "." not in tok and len(tok.split(",")[1]) == 3:
        return float(tok.replace(",", ""))
    return float(tok.replace(",", "."))


def _nums(text: str) -> list[float]:
    out = []
    for m in _TOK.finditer(text or ""):
        try:
            out.append(_num(m.group(1)))
        except ValueError:
            pass
    return out


def text_has_depths(body: str, html: str, length_m, grade=None) -> bool:
    """True when the release itself gives a From-To that could belong to this interval (the label must not go there)."""
    t = re.sub(r"(\d) +\.(?=\d)", r"\1.", body or "")   # 1.1.6: "135 .0" -> "135.0" (PDF extraction)
    if len(t.strip()) < 400:
        return True   # 1.1.4: no usable release text stored -> we cannot say the release gives no depths
    L = length_m
    if L:
        toks = [(m.start(), m.end(), m.group(1)) for m in _TOK.finditer(t)][:8000]
        for (s1, e1, a), (s2, e2, b) in zip(toks, toks[1:]):
            try:
                av, bv = float(a.replace(",", ".")), float(b.replace(",", "."))
            except ValueError:
                continue
            if av < bv and abs((bv - av) - L) <= max(0.06, 0.02 * L) and s2 - e1 <= 12:
                if grade is None or any(_grade_ok(x, grade) for x in _nums(t[max(0, s1 - 250):e2 + 250])):
                    return True
    # 1.1.3: the release points to a results table ("Table 1", "see table below") that is not in the stored text or
    # HTML -- a picture or an attachment we cannot read -- so its depths may well be there: no label
    if _TABLE_REF.search(t):
        return True
    # 1.1.5: the grade is nowhere in the stored text -> the interval came from something we cannot check: no label
    if grade is not None and not any(_grade_ok(x, grade) for x in _nums(t)):
        return True
    if grade is not None:
        for pat in _DEPTH_WORDS:
            for m in pat.finditer(t):
                if any(_grade_ok(x, grade) for x in _nums(t[max(0, m.start() - 200):m.end() + 200])):
                    return True
        # 1.1.2: the grade sits in a row of numbers (a results table flattened into the text: From/To, From/Width,
        # feet, or a row whose depths the reader misread) -> the release very likely gives the depths
        nums = []
        for m in _TOK.finditer(t):
            try:
                nums.append((m.start(), _num(m.group(1))))
            except ValueError:
                pass
            if len(nums) > 12000:
                break
        for i in range(3, len(nums)):
            if _grade_ok(nums[i][1], grade) and nums[i][0] - nums[i - 3][0] <= 70:
                return True
    for tb in _TABLE.findall(html or ""):
        plain = re.sub(r"(?s)<[^>]+>", " ", tb)
        if (re.search(r"(?i)\bfrom\b", plain) and re.search(r"(?i)\bto\b", plain)) or re.search(r"(?i)\bdepth\b", plain):
            return True
    return False


# ------------------------------------------------------------------------------------------------ one release
def analyse(event_id: str, html: str, body: str, best: dict, get=fetch, read=read_picture, sleep=0.5,
            log=lambda s: None) -> dict:
    """Everything for one release. get(url)->bytes and read(bytes, threshold)->text are injectable for tests."""
    t0 = time.time()
    pics = pictures(html)
    res = {"event_id": event_id, "status": None, "depths": "unknown", "n_images": 0, "n_read": 0, "fill": None,
           "images": [], "note": ""}
    text_depths = text_has_depths(body, html, best.get("length_m"), best.get("grade"))
    matches, header_seen, unread = [], False, 0
    for url, src in pics:
        img = {"url": url, "bytes": None, "header": 0, "text": "", "error": None, "seconds": 0.0}
        t1 = time.time()
        try:
            data = get(url)
            if url != src and len(data) < MIN_BYTES:
                data = get(src)
            img["bytes"] = len(data)
            if len(data) < MIN_BYTES:
                img["error"] = "small"
                res["images"].append(img)
                continue
            res["n_images"] += 1
            txt = read(data, False)
            ms = match_lines(txt, best)
            if not ms and looks_like_table(txt):
                txt2 = read(data, True)
                ms = match_lines(txt2, best)
                txt = txt + "\n" + txt2
            img["text"] = txt
            img["header"] = 1 if _HEADER.search(txt) else 0
            header_seen = header_seen or bool(img["header"])
            res["n_read"] += 1
            matches += [m + (url,) for m in ms]
        except Exception as ex:  # noqa: BLE001
            img["error"] = f"{type(ex).__name__}: {str(ex)[:120]}"
            unread += 1
        img["seconds"] = round(time.time() - t1, 2)
        res["images"].append(img)
        if sleep:
            time.sleep(sleep)
    status, m = decide(matches)
    if status == "filled":
        a, b, rule, line, url = m
        res["fill"] = {"from_m": a, "to_m": b, "rule": rule, "row_text": line, "image_url": url}
    if res["n_images"] == 0 and status == "no_match":
        status = "no_images"
    if unread and status != "filled":
        status = "error" if not res["n_read"] else status
    res["status"] = status
    if status != "filled" and not text_depths and not header_seen and unread == 0 and not matches:
        res["depths"] = "not_reported"
    res["seconds"] = round(time.time() - t0, 2)
    res["note"] = f"text_depths={int(text_depths)} header={int(header_seen)} unread={unread} pairs={len({(x[0], x[1]) for x in matches})}"
    return res


# ------------------------------------------------------------------------------------------------ the job
def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def side_connect(path: str = SIDE) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = sqlite3.connect(path, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    return c


def best_sig(best: dict) -> str:
    return json.dumps([best.get("hole_id"), best.get("length_m"), best.get("grade")])


def _best_missing(conn: sqlite3.Connection, recent_days=None):
    """(event_id, hole, length, grade, unit, published_at) of best intervals without From-To. With recent_days only
    releases published in that window are read (index on published_at, then the interval rows by primary key), so the
    hourly run does not scan all of drill_intervals."""
    if not recent_days:
        yield from conn.execute(
            "SELECT i.event_id, i.hole_id, i.length_m, i.grade, i.unit, d.published_at FROM drill_intervals i "
            "JOIN drill_results d ON d.event_id = i.event_id WHERE i.is_best = 1 AND i.from_m IS NULL")
        return
    since = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 86400 * float(recent_days)))
    for eid, pub in conn.execute("SELECT event_id, published_at FROM drill_results WHERE published_at >= ?", (since,)).fetchall():
        for hole, L, g, unit in conn.execute("SELECT hole_id, length_m, grade, unit FROM drill_intervals "
                                             "WHERE event_id = ? AND is_best = 1 AND from_m IS NULL", (eid,)):
            yield eid, hole, L, g, unit, pub


def candidates(conn: sqlite3.Connection, only=None, recent_days=None) -> list[dict]:
    """Best intervals still without From-To, newest first, with the reader's body hash for change detection."""
    ver = conn.execute("SELECT version FROM fx_extractor_versions WHERE extractor=? AND status='active'",
                       (EXTRACTOR,)).fetchone()
    ver = ver[0] if ver else None
    out = []
    for eid, hole, L, g, unit, pub in _best_missing(conn, recent_days):
        if only and eid not in only:
            continue
        r = conn.execute("SELECT body_sha1 FROM fx_runs WHERE extractor=? AND version=? AND event_id=? LIMIT 1",
                         (EXTRACTOR, ver, eid)).fetchone() if ver else None
        out.append({"event_id": eid, "hole_id": hole, "length_m": L, "grade": g, "unit": unit, "published_at": pub,
                    "body_sha1": r[0] if r else None})
    out.sort(key=lambda x: x["published_at"] or "", reverse=True)
    return out


def store(side: sqlite3.Connection, cand: dict, res: dict) -> None:
    now = _now()
    side.execute("INSERT OR REPLACE INTO ocr_release VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (cand["event_id"], VERSION, now, cand.get("body_sha1"), best_sig(cand), res["status"], res["depths"],
                  res["n_images"], res["n_read"], res.get("seconds"), res["note"]))
    side.execute("DELETE FROM ocr_fill WHERE event_id=?", (cand["event_id"],))
    if res["fill"]:
        f = res["fill"]
        side.execute("INSERT INTO ocr_fill VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (cand["event_id"], cand.get("hole_id"), cand.get("length_m"), cand.get("grade"), f["from_m"],
                      f["to_m"], f["rule"], f["row_text"], f["image_url"], VERSION, now))
    for img in res["images"]:
        side.execute("INSERT OR REPLACE INTO ocr_image VALUES (?,?,?,?,?,?,?,?)",
                     (img["url"], cand["event_id"], now, img["bytes"], img["header"], (img["text"] or "")[:20000],
                      img["seconds"], img["error"]))
    side.commit()


def run(limit=None, budget=None, only=None, dry=False, sleep=0.5, db=DB, side_path=SIDE, log=print, recent_days=None) -> dict:
    if os.path.exists(JOB_OFF):
        log("[drill_ocr] job switch present (drill_ocr_JOB_OFF); nothing done")
        return {"off": True}
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)
    side = side_connect(side_path)
    # a release whose pictures could not be read (status 'error') is tried again on the next run
    done = {r[0]: (r[1], r[2], r[3]) for r in side.execute(
        "SELECT event_id, version, body_sha1, best_sig FROM ocr_release WHERE status <> 'error'")}
    cands = candidates(conn, only, recent_days)
    todo = [c for c in cands if only or done.get(c["event_id"]) != (VERSION, c.get("body_sha1"), best_sig(c))]
    st = {"candidates": len(cands), "todo": len(todo), "checked": 0, "filled": 0, "ambiguous": 0, "no_match": 0,
          "no_images": 0, "error": 0, "not_reported": 0, "images_read": 0, "dry_run": dry}
    t0 = time.time()
    for c in todo:
        if limit is not None and st["checked"] >= limit:
            break
        if budget is not None and time.time() - t0 > budget:
            st["stopped_on_budget"] = True
            break
        row = conn.execute("SELECT raw_html, raw_body FROM events WHERE event_id=?", (c["event_id"],)).fetchone()
        if not row:
            continue
        html, body = row
        try:
            res = analyse(c["event_id"], html or "", body or "", c, sleep=sleep if pictures(html or "") else 0)
        except Exception as ex:  # noqa: BLE001
            res = {"status": "error", "depths": "unknown", "n_images": 0, "n_read": 0, "fill": None, "images": [],
                   "note": f"{type(ex).__name__}: {ex}"[:300], "seconds": 0}
        st["checked"] += 1
        st[res["status"]] = st.get(res["status"], 0) + 1
        st["not_reported"] += res["depths"] == "not_reported"
        st["images_read"] += res["n_read"]
        if res["fill"] or res["status"] in ("ambiguous",) or (only and res["n_images"]):
            f = res["fill"] or {}
            log(f"  {c['event_id'][:12]} {res['status']} best {c.get('hole_id')} {c.get('grade')} / {c.get('length_m')}m "
                f"-> {f.get('from_m')}-{f.get('to_m')} [{f.get('rule')}] {res['note']} :: {f.get('row_text', '')[:120]}")
        if not dry:
            store(side, c, res)
    st["seconds"] = round(time.time() - t0, 1)
    log("[drill_ocr] " + json.dumps(st))
    return st


def relabel(db=DB, side_path=SIDE, log=print) -> dict:
    """1.1.1: recompute depths ('not_reported' | 'unknown') for every release already read by this VERSION with the
    current text rule and the stored picture results (headings, errors) -- no downloads, no OCR."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)
    side = side_connect(side_path)
    st = {"rows": 0, "not_reported": 0, "unknown": 0, "to_unknown": 0, "to_not_reported": 0}
    rows = side.execute("SELECT event_id, best_sig, status, depths FROM ocr_release WHERE version=?", (VERSION,)).fetchall()
    for eid, sig, status, old in rows:
        try:
            hole, L, g = json.loads(sig or "[null, null, null]")
        except ValueError:
            continue
        row = conn.execute("SELECT raw_html, raw_body FROM events WHERE event_id=?", (eid,)).fetchone()
        if not row:
            continue
        header, errs = side.execute("SELECT MAX(header), SUM(error IS NOT NULL AND error <> 'small') FROM ocr_image "
                                    "WHERE event_id=?", (eid,)).fetchone()
        td = text_has_depths(row[1] or "", row[0] or "", L, g)
        new = ("not_reported" if status in ("no_match", "no_images") and not td and not (header or 0) and not (errs or 0)
               else "unknown")
        st["rows"] += 1
        st[new] += 1
        if new != old:
            st["to_" + new] += 1
            side.execute("UPDATE ocr_release SET depths=? WHERE event_id=?", (new, eid))
    side.commit()
    log("[drill_ocr] relabel " + json.dumps(st))
    return st


def stats(side_path=SIDE) -> dict:
    side = side_connect(side_path)
    out = {"releases": dict(side.execute("SELECT status, COUNT(*) FROM ocr_release GROUP BY status").fetchall()),
           "depths": dict(side.execute("SELECT depths, COUNT(*) FROM ocr_release GROUP BY depths").fetchall()),
           "fills": side.execute("SELECT COUNT(*) FROM ocr_fill").fetchone()[0],
           "images": side.execute("SELECT COUNT(*), SUM(error IS NOT NULL) FROM ocr_image").fetchone()}
    print(json.dumps(out))
    return out


# ------------------------------------------------------------------------------------------------ self-tests
def _selftest() -> int:
    bad = 0

    def ok(name, cond):
        nonlocal bad
        bad += not cond
        print(("  ok    " if cond else "  FAIL  ") + name)

    html = ('<p>x</p><a href="https://images.newsfilecorp.com/files/1/1_tbl.jpg"><img src="https://images.newsfilecorp.com/files/1/1_tbl_550.jpg"></a>'
            '<img src="https://images.newsfilecorp.com/files/1/1_002.jpg"><img src="https://images.newsfilecorp.com/files/1/1_logo.jpg">'
            '<img src="https://api.newsfilecorp.com/newsinfo/1/157/">')
    p = pictures(html)
    ok("full-size picture from the link", p[0][0].endswith("1_tbl.jpg"))
    ok("logos and trackers skipped", len(p) == 2)
    ok("newsfile _550 rule", pictures('<img src="https://images.newsfilecorp.com/files/1/x_550.jpg">')[0][0].endswith("/x.jpg"))
    best = {"hole_id": "RM26-213", "length_m": 33.5, "grade": 0.92}
    ok("length+grade", match_lines("RM26-213 Main Mercur 151 -59 30.5 64.0 33.5 0.92 81", best)[0][:3] == (30.5, 64.0, "length+grade"))
    ok("hole id digits are not read as depths", not match_lines("RM26-213 RM26-246 0.92", {"hole_id": None, "length_m": 33.0, "grade": 0.92}))
    ok("release rounding 3.1 vs 3.12", match_lines("GC26-166 1000 233.2 295.7 62.5 30 3.12", {"hole_id": "GC26-166", "length_m": 62.5, "grade": 3.1})[0][2] == "length+grade")
    ok("OCR misread grade, hole saves it", match_lines("GC26-166 1000 233.2 295.7 62.5 30 4.12", {"hole_id": "GC26-166", "length_m": 62.5, "grade": 3.1})[0][2] == "length+hole")
    ok("no arithmetic, no match (From + Width table)", not match_lines("LMD-148 19 2 80.54 44.5", {"hole_id": "LMD-148", "length_m": 2.0, "grade": 80.54}))
    ok("no arithmetic, no match (true width)", not match_lines("AGR W1 143.45 146.40 2.95 2.55 1.66 1,695 25.85", {"hole_id": "426014", "length_m": 2.55, "grade": 25.85}))
    ok("two different pairs is ambiguous", decide([(1, 3, "length+grade", "", "u"), (5, 7, "length+grade", "", "u")])[0] == "ambiguous")
    ok("same pair twice is one fill", decide([(1, 3, "length+grade", "", "u"), (1.0, 3.0, "length+hole", "", "v")])[0] == "filled")
    ok("text with from-depth is not 'not reported'", text_has_depths("intersected 2.0 g/t over 3.0 m from 120 m", "", 3.0, 2.0))
    ok("pair in text is not 'not reported'", text_has_depths("hole A 120.0 123.0 3.0 2.0", "", 3.0, 2.0))
    ok("pair with the range dash", text_has_depths("15.0 meters grading 61.5 g/t Au (402.7 to 417.7 m)", "", 15.0, 61.5))
    ok("plain summary is 'not reported'", not text_has_depths("Hole A intersected 2.0 g/t Au over 3.0 metres. " + "x" * 400, "", 3.0, 2.0))
    ok("general depth wording does not block the label", not text_has_depths(
        "remains open at depth and the zone extends to depth. 3.0 g/t over 21.3 m " + "x" * 400, "", 21.3, 3.0))
    ok("a pair for another interval does not block the label", not text_has_depths("hole A 5.0 g/t over 2.0 m. " + "y" * 300 + " hole B 10.0 12.0 2.0 9.9 g/t " + "x" * 400, "", 2.0, 5.0))
    ok("depth wording: from 270m", text_has_depths("7m at 223 g/t gold  from 270m26EGN013 within", "", 7.0, 223.0))
    ok("depth wording: beginning .. downhole", text_has_depths("15.00 g/t Gold over 0.4 metres beginning 50.9 metres downhole", "", 0.4, 15.0))
    ok("depth wording: starting at .. downhole", text_has_depths("starting at 33.5 m downhole with 36 m at 0.59% Nb", "", 36.0, 0.59))
    ok("depth wording: at .. m depth", text_has_depths("147.5 gpt gold over 1.0 m from a vein with visible gold at 161 m  depth.", "", 1.0, 147.5))
    ok("depth wording: below surface", text_has_depths("8.4 m at 0.3% U3O8 encountered only 64 metres below surface", "", 8.4, 0.3))
    ok("table row: From + Width (ASTR)", text_has_depths("LMD-121 224.4 3.1 9.04 1286.0 26.72 1602.92", "", 3.1, 1286.0))
    ok("table row: feet (BRC)", text_has_depths("GAB-005 251.4 345.6 94.2 541 250 345 95 374.0", "", 28.7122, 541.0))
    ok("table row: reader length error (FINX)", text_has_depths("RUO25D008 125.15 126.25 1.10 4.92  RUO25D009 18.50", "", 126.25, 4.92))
    ok("depth wording: from surface", text_has_depths("Intersection is within 33 metres from surface and 3.32 g/t over 22.35 metres", "", 22.35, 3.32))
    ok("thousands comma (1,540)", text_has_depths("UCM-120 210.5 212.7 2.2 3.43 1,265 1,540", "", 2.2, 1540.0))
    ok("a table referred to but not stored", text_has_depths("returned 1.13% Li2O over 27.98 m (Table 1)", "", 27.98, 1.13))
    ok("decimal comma kept", _num("4,49") == 4.49 and _num("1,540") == 1540.0)
    ok("1.1.5: wider range contains the interval", text_has_depths("CH24-305: 105.21 g/t Au over 0.8 m, included in 14.16 g/t Au over 6.4 m, from 251.5 to 257.9 m " + "x" * 400, "", 0.8, 105.21))
    ok("1.1.5: between .. and .. depth", text_has_depths("TG2606: 51.8 meters @ 2.34 g/t Au, all in five zones between 21.3-  and 163.1-meters  depth; " + "x" * 400, "", 51.8, 2.34))
    ok("1.1.5: vertical depth of", text_has_depths("Hole 7 at a vertical depth of 480 m returning 8.22 g/t Au over 8.5 m " + "x" * 400, "", 8.5, 8.22))
    ok("1.1.5: grade not in text", text_has_depths("Reports assays over 2,400 g/t Ag. " + "x" * 400, "", 0.3, 15.5))
    ok("1.1.6: split decimals", text_has_depths("returned 4.12 g/t Au over 7.3 m  from 135 .0 to 142 .3 m . " + "x" * 400, "", 7.3, 4.12))
    ok("1.1.6: at 135M", text_has_depths("4.12 G/T GOLD OVER 7.3 M AT 135M; INCLUDING " + "x" * 400, "", 7.3, 4.12))
    ok("1.1.6: 'at 2 m spacing' does not block", not text_has_depths("3.1 g/t over 2.0 m, samples at 2 m spacing " + "x" * 400, "", 2.0, 3.1))
    ok("1.1.7: linked results table", text_has_depths("10.7 metres grading 4.32 g/t. To view a table of full drill results, please click here: http://x/y.pdf " + "x" * 400, "", 10.7, 4.32))
    ok("1.1.5: plain summary still labelled", not text_has_depths("Hole A intersected 2.0 g/t Au over 3.0 metres. " + "x" * 400, "", 3.0, 2.0))
    ok("depth wording in feet", text_has_depths("38.2 m with an average grade of 938.1 ppm Li, starting at 187.0 ft (57.0 m). " + "x" * 400, "", 38.2, 938.0))
    ok("no stored text, no label", text_has_depths("", "", 6.35, 313.0))
    ok("no depth wording: true width only", not text_has_depths("14.13% zinc over 2.2 metres true width " + "x" * 400, "", 2.2, 14.13))
    ok("no depth wording: from <year>, million", not text_has_depths("from 2025 drilling 3.0 g/t over 2 m and 270 million tonnes " + "x" * 400, "", 2.0, 3.0))
    ok("html table with From and To", text_has_depths("", "<table><tr><td>From</td><td>To</td></tr></table>", 3.0, 2.0))
    ok("pass 2 gate: table-ish text", looks_like_table("| 231.6 | 2515 | 4.40 | 257.6 | 295.7 |") and looks_like_table("Hole From To Au"))
    ok("pass 2 gate: map text", not looks_like_table("NORTH 500 m Mercur Main zone 0.92 g/t"))

    pics = {"https://images.newsfilecorp.com/files/1/1_tbl.jpg": b"T" * 20000,
            "https://images.newsfilecorp.com/files/1/1_002.jpg": b"M" * 20000}
    texts = {b"T" * 20000: "Hole From To Length Au\nRM26-213 30.5 64.0 33.5 0.92", b"M" * 20000: "map NORTH 500m"}
    r = analyse("e1", html, "Hole RM26-213 cut 0.92 g/t over 33.5 m.", best, get=lambda u: pics[u],
                read=lambda d, t: texts[d], sleep=0)
    ok("analyse fills from the table picture", r["status"] == "filled" and r["fill"]["from_m"] == 30.5)
    r2 = analyse("e2", '<img src="https://x/y_map.jpg">', "Hole A cut 2.0 g/t over 3.0 m. " + "x" * 400, {"hole_id": "A", "length_m": 3.0, "grade": 2.0},
                 get=lambda u: b"M" * 20000, read=lambda d, t: "map NORTH 500m", sleep=0)
    ok("map only, no depths anywhere -> not reported", r2["status"] == "no_match" and r2["depths"] == "not_reported")
    r3 = analyse("e3", '<img src="https://x/y_t.jpg">', "Hole A cut 2.0 g/t over 3.0 m.", {"hole_id": "A", "length_m": 3.0, "grade": 2.0},
                 get=lambda u: b"M" * 20000, read=lambda d, t: "Hole From To Width\nB 1 2 1 5", sleep=0)
    ok("table picture without a match stays unknown", r3["depths"] == "unknown")
    r4 = analyse("e4", '<img src="https://x/y_t.jpg">', "Hole A cut 2.0 g/t over 3.0 m.", {"hole_id": "A", "length_m": 3.0, "grade": 2.0},
                 get=lambda u: (_ for _ in ()).throw(OSError("down")), read=lambda d, t: "", sleep=0)
    ok("unreadable picture stays unknown", r4["depths"] == "unknown" and r4["status"] == "error")
    r5 = analyse("e5", "", "Hole A cut 2.0 g/t over 3.0 m. " + "x" * 400, {"hole_id": "A", "length_m": 3.0, "grade": 2.0}, sleep=0)
    ok("no pictures, no depths -> not reported", r5["status"] == "no_images" and r5["depths"] == "not_reported")
    print(f"failures: {bad}")
    return 1 if bad else 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv:
        return _selftest()
    if "--stats" in argv:
        stats()
        return 0
    if "--relabel" in argv:
        relabel()
        return 0

    def opt(name, cast=str, default=None):
        return cast(argv[argv.index(name) + 1]) if name in argv else default
    only = set(opt("--only", str, "").split(",")) - {""} or None
    run(limit=opt("--limit", int), budget=opt("--budget", float), only=only, dry="--dry-run" in argv,
        sleep=opt("--sleep", float, 0.5), db=opt("--db", str, DB), side_path=opt("--side", str, SIDE),
        recent_days=opt("--recent", float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
