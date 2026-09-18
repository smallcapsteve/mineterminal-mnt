#!/usr/bin/env python3
"""Turn RES_V1 1.0.0 into 1.0.1 in place (2026-09-18).

Eight edits, each anchored on an exact string so a miss fails loudly rather than half-applying.
What they fix, measured on the 50-release set at 1.0.0 (row 86.2%, deposit 54.4%, category
100.0%, tonnes 91.0%, grade 60.3%, context 87.0%):

  1 + 4  a sentence wrapped across lines by a PDF was never assembled, so the prose reader never
         saw it -- two of the three releases the reader missed entirely were that one bug
  2      deposit names were compared with their accents on, so Trojarova from the headline and
         Trojarova from the table were two deposits and the release published both
  3      a disqualifying word anywhere in the headline made the release "not an announcement";
         Imagine Lithium's "... and Upcoming Drill Program" put its own maiden estimate in
         background. Only the first 70 characters decide it now.
  5 + 6  units rows, date fragments and unbalanced parentheses were reaching the page as deposit
         names -- "M g/t g/t g/t % % % koz C$/t" was one of them
  7 + 8  a units-only header mapped the columns but left every grade with no metal against it

Usage: patch_res_v101.py <path to resources.py>
"""
import hashlib
import sys

EDITS = []


def edit(old, new, once=True):
    EDITS.append((old, new, once))


edit('''def lines_of(text: str) -> list:
    return [ln for ln in clean(text).split("\\n")]
''',
     '''def lines_of(text: str) -> list:
    return [ln for ln in clean(text).split("\\n")]


def reflow(text: str, min_len: int = 55) -> str:
    """Rejoin lines that a PDF wrapped mid-sentence, leaving table cells alone.

    Patriot's resource statement runs across three lines, and splitting on newlines before reading
    it meant the sentence never existed -- two of the three releases this reader missed were that
    one bug. A wrapped line is long and ends without punctuation; a table cell is short, so only
    lines of at least min_len characters absorb the line below them."""
    out = []
    for ln in text.split("\\n"):
        if (out and out[-1] and ln and len(out[-1]) >= min_len
                and not re.search(r"[.;:!?]$", out[-1]) and not _RE_BARE_UNIT.match(ln)):
            out[-1] = out[-1] + " " + ln
        else:
            out.append(ln)
    return "\\n".join(out)
''')

edit('''def _norm_dep(d):
    if not d:
        return ""
    s = re.sub(r"(?i)\\b(project|deposit|mine|property|zone|prospect|the)\\b", " ", d)''',
     '''def _fold(s):
    """Accents off, so Trojarova read from the headline and Trojarova read from the table are the
    same deposit. They were not, and the release published two rows instead of one."""
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _norm_dep(d):
    if not d:
        return ""
    s = re.sub(r"(?i)\\b(project|deposit|mine|property|zone|prospect|the)\\b", " ", _fold(d))''')

edit('''    h = headline or ""
    if _RE_NOT_ANNOUNCING.search(h):
        return False''',
     '''    h = headline or ""
    # "Highlights Robust Initial Mineral Resource ... and Upcoming Drill Program" is an
    # announcement with a trailing aside; "Outstanding drilling results ..." is not an
    # announcement at all. What the headline leads with is what decides it.
    if _RE_NOT_ANNOUNCING.search(h[:70]):
        return False''')

edit('''    rows = read_tables(text.split("\\n"))
    rows += read_prose(text)''',
     '''    rows = read_tables(text.split("\\n"))
    rows += read_prose(reflow(text))''')

edit('''    s = _RE_DEP_NOISE.sub(" ", s)''',
     '''    s = re.sub(r"(?i)[,\\-\\s]*(?:and\\s+)?(?:as\\s+)?(?:at|of)\\s+(?:jan|feb|mar|apr|may|jun|jul|'''
     '''aug|sep|oct|nov|dec)[a-z]*\\.?\\s*\\d{0,2},?\\s*\\d{4}\\S*\\s*$", " ", s)
    s = re.sub(r"\\s*@.*$", " ", s)
    s = re.sub(r"(?i)\\([^)]*\\b(?:table|subset|inclusive|see)\\b[^)]*\\)", " ", s)
    s = _RE_DEP_NOISE.sub(" ", s)''')

edit('''    if _CLASS_WORD.match(s) or metal_of(s):
        return None
    return s''',
     '''    if _CLASS_WORD.match(s) or metal_of(s):
        return None
    if s.count("(") != s.count(")"):
        return None
    # a stray units row is not a deposit: "M g/t g/t g/t % % % koz C$/t" reached the page as one
    toks = [t for t in re.split(r"[\\s,;|]+", s) if t]
    if not toks:
        return None
    unitish = sum(1 for t in toks
                  if _RE_BARE_UNIT.match(t.strip(".,")) or t.strip(".,").isdigit())
    if unitish * 2 >= len(toks):
        return None
    return s''')

edit('''            cols = wide_columns([x for x in ls[max(0, i - 8):i] if x], len(vals)) \\
                or build_columns(header, len(vals)) \\
                or (last_cols if len(vals) == last_n else [])''',
     '''            cols = _best_columns([
                wide_columns([x for x in ls[max(0, i - 8):i] if x], len(vals)),
                build_columns(header, len(vals)),
                last_cols if len(vals) == last_n else []])''')

edit('''                cols = build_columns(header, len(vals)) or (last_cols if len(vals) == last_n else [])''',
     '''                cols = _best_columns([build_columns(header, len(vals)),
                                      last_cols if len(vals) == last_n else []])''')

edit('''def _one_tonnage(cols):''',
     '''def _best_columns(cands):
    """Of the mappings that fit, take the one that names the most metals.

    A units-only header maps the columns but leaves every grade unlabelled, and an unlabelled
    grade is a figure with no metal against it -- true, and useless on the page."""
    best, score = [], -1
    for c in cands:
        if not c:
            continue
        sc = sum(1 for x in c if x["metal"])
        if sc > score:
            best, score = c, sc
    return _borrow_metals(best)


def _borrow_metals(cols):
    """A table lists its grades and its contained metal in the same order. Where the grade columns
    lost their labels and the contained columns kept theirs, read the metals across."""
    g = [c for c in cols if c["kind"] == "grade"]
    cm = [c for c in cols if c["kind"] == "contained"]
    if g and cm and len(g) == len(cm):
        for a, b in zip(g, cm):
            if a["metal"] is None and b["metal"]:
                a["metal"], a["eq"] = b["metal"], b["eq"]
    return cols


def _one_tonnage(cols):''')

edit('VERSION = "1.0.0"', 'VERSION = "1.0.1"')


def main(argv):
    path = argv[0] if argv else "resources.py"
    s = open(path, encoding="utf-8").read()
    for i, (old, new, once) in enumerate(EDITS, 1):
        if s.count(old) != 1:
            print("edit %d: anchor appears %d times, expected 1" % (i, s.count(old)))
            return 1
        s = s.replace(old, new, 1)
    open(path, "w", encoding="utf-8").write(s)
    print("patched", path, len(EDITS), "edits")
    print("sha256", hashlib.sha256(s.encode("utf-8")).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
