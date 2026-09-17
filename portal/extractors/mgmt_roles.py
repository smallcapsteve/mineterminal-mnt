"""Role vocabulary for the management-changes reader (MGMT_V1, 2026-09-17).

The live v9 reader captured "up to 5 arbitrary words" after a verb and then tried to trim the
result, which is how `VP of Exploration and Completes` and `... AND ESG Vancouver` reached the page.
This module inverts that: a role is recognised only if it matches this vocabulary, so an unknown
word ends the title instead of joining it. The failure mode is a role that is too short, never one
that is wrong.

Every entry gives:
  pattern   what the release may print
  canon     the one spelling the page filters on (Director, Chief Financial Officer, VP Exploration)
  scope     board | management | advisory

`Director of Capital Markets` is management, not a board seat: a bare `Director` is the board, a
`Director` with a department is an officer. That distinction is the reason scope is decided here,
with the role, rather than from a separate keyword list.
"""
from __future__ import annotations

import re

BOARD, MGMT, ADVISORY = "board", "management", "advisory"

# departments that can follow VP / Director of / Head of / Manager of
DEPT = (r"(?:"
        # longest first: regex alternation takes the first branch that matches, so "project development"
        # has to be offered before "projects" or a VP Project Development reads as a VP Project.
        r"exploration\s+and\s+development|exploration\s+and\s+geology|project\s+development|"
        r"corporate\s+development|business\s+development|corporate\s+communications|corporate\s+affairs|"
        r"finance\s+and\s+administration|business\s+strategy|stakeholder\s+relations|capital\s+markets|"
        r"investor\s+relations|community\s+relations|health\s+and\s+safety|technical\s+services|"
        r"human\s+resources|information\s+technology|supply\s+chain|"
        r"exploration|operations?|finance|communications?|sustainability|esg|geology|geoscience|projects?|"
        r"technical|legal|marketing|metallurgy|engineering|mining|environment(?:al)?|safety|strategy|"
        r"land|permitting|administration|it|procurement)")

# (regex source, canonical spelling, scope). Order matters: the first match wins, so the longest and
# most specific phrasings come first.
ROLE_TABLE = [
    # ---- board
    (r"co[\s\-]?chair(?:man|woman|person)?(?:\s+of\s+the\s+board(?:\s+of\s+directors)?)?", "Co-Chair", BOARD),
    (r"member\s+of\s+the\s+audit\s+committee", "Member of the Audit Committee", BOARD),
    (r"chair(?:man|woman|person)?\s+(?:and\s+\w+\s+)?of\s+the\s+board(?:\s+of\s+directors)?", "Chair of the Board", BOARD),
    (r"(?:executive\s+|non[\s\-]executive\s+|independent\s+|interim\s+|acting\s+)?chair(?:man|woman|person)\b", "Chair", BOARD),
    (r"(?:executive\s+|non[\s\-]executive\s+|independent\s+|interim\s+|acting\s+)?chair\b(?!\s+of\s+(?!the\s+board))", "Chair", BOARD),
    (r"lead\s+(?:independent\s+)?director", "Lead Director", BOARD),
    (r"board\s+observer", "Board Observer", BOARD),
    (r"(?:independent\s+|non[\s\-]executive\s+|executive\s+|outside\s+)?directors?\b(?!\s*(?:,|\s)?\s*(?:of|,)\s+" + DEPT + r")",
     "Director", BOARD),
    (r"board\s+of\s+directors", "Director", BOARD),
    (r"(?:the\s+)?board\b", "Director", BOARD),
    # ---- management: the C-suite spelled out and abbreviated
    (r"(?:president\s+and\s+)?chief\s+executive\s+officer|\bCEO\b", "Chief Executive Officer", MGMT),
    (r"chief\s+financial\s+officer|\bCFO\b", "Chief Financial Officer", MGMT),
    (r"chief\s+operating\s+officer|\bCOO\b", "Chief Operating Officer", MGMT),
    (r"chief\s+technolog(?:y|ical)\s+officer|\bCTO\b", "Chief Technology Officer", MGMT),
    (r"chief\s+geologist|chief\s+geoscientist", "Chief Geologist", MGMT),
    (r"chief\s+legal\s+officer|general\s+counsel", "General Counsel", MGMT),
    (r"chief\s+sustainability\s+officer", "Chief Sustainability Officer", MGMT),
    (r"chief\s+development\s+officer", "Chief Development Officer", MGMT),
    (r"chief\s+exploration\s+officer", "Chief Exploration Officer", MGMT),
    (r"chief\s+commercial\s+officer", "Chief Commercial Officer", MGMT),
    (r"chief\s+operating\s+and\s+financial\s+officer", "Chief Operating Officer", MGMT),
    (r"chief\s+accounting\s+officer", "Chief Accounting Officer", MGMT),
    (r"chief\s+(?:\w+\s+){0,2}officer", None, MGMT),          # canon filled from the printed text
    # ---- management: president, VPs, managers
    (r"(?:interim\s+|acting\s+)?president(?:\s+and\s+chief\s+executive\s+officer)?", "President", MGMT),
    (r"(?:senior\s+|executive\s+)?vice[\s\-]president,?\s+(?:and\s+\w+\s+)?(?:of\s+)?" + DEPT, None, MGMT),
    (r"(?:senior\s+|executive\s+)?vice[\s\-]president", "Vice President", MGMT),
    (r"\b(?:S|E)?VP,?\s+(?:of\s+)?" + DEPT, None, MGMT),
    (r"\b(?:S|E)?VP\b", "Vice President", MGMT),
    (r"managing\s+director", "Managing Director", MGMT),
    (r"general\s+manager", "General Manager", MGMT),
    (r"(?:corporate\s+|company\s+)secretary", "Corporate Secretary", MGMT),
    (r"treasurer", "Treasurer", MGMT),
    (r"controller", "Controller", MGMT),
    (r"directors?\s*(?:,|\s+of)\s+" + DEPT, None, MGMT),      # Director of Capital Markets: an officer, not a seat
    (r"head\s+of\s+" + DEPT, None, MGMT),
    (r"(?:country|project|mine|site|exploration)\s+manager", None, MGMT),
    (r"principal\s+(?:\w+(?:ist|er|or))\b", None, MGMT),      # Principal Metallurgist, Principal Engineer
    (r"(?:senior\s+|lead\s+|chief\s+)?(?:geologist|metallurgist|engineer|geophysicist)", None, MGMT),
    # ---- advisory
    (r"(?:technical|scientific|strategic|special|senior|geological|advisory)\s+advisory\s+(?:board|committee)", None, ADVISORY),
    (r"member\s+of\s+the\s+advisory\s+(?:board|committee)", "Advisory Board", ADVISORY),
    (r"advisory\s+(?:board|committee)", "Advisory Board", ADVISORY),
    (r"(?:technical|scientific|strategic|special|senior|geological|corporate|financial)\s+advisor?s?e?r?\b", None, ADVISORY),
    (r"advis[oe]rs?\b", "Advisor", ADVISORY),
]

_COMPILED = [(re.compile(r"(?i)\b(?:" + src + r")"), canon, scope) for src, canon, scope in ROLE_TABLE]

# words that may sit inside a printed role but never start one
_TITLECASE_FIX = {"of": "of", "and": "and", "the": "the", "for": "for"}


def tidy(printed: str) -> str:
    """The role as the release printed it, with spacing and case cleaned up but the words kept."""
    s = re.sub(r"\s+", " ", (printed or "").strip(" ,.;:-\\u2013\\u2014"))
    if not s:
        return s
    if s.isupper() and len(s) > 4:                            # ALL-CAPS headlines: title-case, keeping CEO/CFO/VP/ESG
        out = []
        for w in s.split(" "):
            lw = w.lower()
            if lw in _TITLECASE_FIX and out:
                out.append(_TITLECASE_FIX[lw])
            elif len(w) <= 4 and w.isalpha() and w in ("CEO", "CFO", "COO", "CTO", "VP", "SVP", "EVP", "ESG", "IR", "CLO"):
                out.append(w)
            else:
                out.append(w.capitalize())
        s = " ".join(out)
    return s


def match(text: str, start: int = 0):
    """The first role in `text` at or after `start`: (printed, canon, scope, span) or None.

    Earliest start wins, and among the matches overlapping it the longest does, so
    "to the Board of Directors" reads as the whole phrase and not as "the Board"."""
    hits = []
    for rx, canon, scope in _COMPILED:
        m = rx.search(text, start)
        if m:
            hits.append((m.start(), m.end(), canon, scope, m.group(0)))
    if not hits:
        return None
    first = min(h[0] for h in hits)
    over = [h for h in hits if h[0] <= first + 4]
    a, b, canon, scope, raw = max(over, key=lambda h: h[1])
    printed = tidy(re.sub(r"(?i)^the\s+", "", raw))
    return (printed, canon or _derive_canon(printed), scope, (a, b))


_RE_VP_DEPT = re.compile(r"(?i)^(?:senior\s+|executive\s+)?(?:vice[\s\-]president|S?E?VP)[,]?\s+(?:of\s+)?(.+)$")
_RE_DIR_DEPT = re.compile(r"(?i)^directors?[,]?\s+(?:of\s+)?(.+)$")
_RE_HEAD_DEPT = re.compile(r"(?i)^head\s+of\s+(.+)$")


def _derive_canon(printed: str) -> str:
    """One spelling for the roles the table cannot name in advance, so the page can filter on them:
    VP / SVP / Vice President of a department all become "VP <Department>"."""
    def title(x):
        out = []
        for i, w in enumerate(x.split()):
            if w.isupper() and len(w) <= 4:
                out.append(w)
            elif i and w.lower() in ("and", "of", "the", "for"):
                out.append(w.lower())
            else:
                out.append(w.capitalize())
        return " ".join(out)
    m = _RE_VP_DEPT.match(printed or "")
    if m:
        return _singular("VP " + title(m.group(1)))
    m = _RE_DIR_DEPT.match(printed or "")
    if m:
        return _singular("Director, " + title(m.group(1)))
    m = _RE_HEAD_DEPT.match(printed or "")
    if m:
        return _singular("Head of " + title(m.group(1)))
    return _singular(tidy(printed))


_RE_PLURAL = re.compile(r"(?i)\b(advisor|adviser|officer|director|president|manager|chair|geologist|engineer|"
                        r"metallurgist|geophysicist|secretary|treasurer|controller|observer)s\b")


def _singular(s: str) -> str:
    return _RE_PLURAL.sub(lambda m: m.group(1), s or "")


def rank(canon: str) -> int:
    """How senior a role is, so one row per person can carry the senior title when a release names two."""
    c = (canon or "").lower()
    if "chair" in c and "board" in c:
        return 96
    if c.startswith("co-chair"):
        return 94
    if "chair" in c:
        return 92
    if "chief executive" in c:
        return 88
    if c.startswith("president"):
        return 86
    if "chief" in c or "general counsel" in c:
        return 80
    if "vice president" in c or c.startswith("vp"):
        return 70
    if "managing director" in c:
        return 68
    if "head of" in c or "general manager" in c:
        return 60
    if c.startswith("director,"):
        return 56
    if "lead director" in c:
        return 40
    if c == "director":
        return 32
    if "observer" in c:
        return 22
    if "advisor" in c or "advisory" in c:
        return 18
    return 50


def match_at(text: str):
    """The role this whole phrase names, or None. Used when the phrase is already isolated."""
    got = match(text)
    if got is None:
        return None
    printed, canon, scope, (a, b) = got
    # the phrase must be mostly the role, not a role buried in a sentence
    return got if (b - a) >= 0.5 * len(text.strip()) else got


def canonical(printed: str):
    """(canon, scope) for a printed role, or (printed, None) when the vocabulary does not know it."""
    got = match(printed or "")
    if got is None:
        return tidy(printed), None
    return got[1], got[2]


def same_role(a: str, b: str) -> bool:
    """True when two printed roles name the same position."""
    ca, sa = canonical(a)
    cb, sb = canonical(b)
    na, nb = re.sub(r"[^a-z]", "", (ca or "").lower()), re.sub(r"[^a-z]", "", (cb or "").lower())
    if na and na == nb:
        return True
    pa, pb = re.sub(r"[^a-z]", "", (a or "").lower()), re.sub(r"[^a-z]", "", (b or "").lower())
    return bool(pa) and pa == pb
