# HLFIX_V1 (2026-10-03): repair stored headlines. Justin: "Headlines should be fixed in MNT's stored data. MTP only
# patches them when it displays them."
#
# The rules are Mine Terminal Pro's display-time repair (MTP_RELFMT_V1.1, live 2026-10-03, checked by hand on 735
# releases) moved to where the headline is stored, so every site gets the same headline and MTP's own repair has
# nothing left to do.
#
#   clean_headline(h)              every source: wire prefixes ("CNW/ -"), "p.1 ", "News Release dated ... - ",
#                                  "( TREO )" spacing, a leading "13:30 ET ", a lowercase first letter.
#   cut_glued_intro(h)             wire headlines that carry the release's first sentence ("... Appointment. Cupani
#                                  Metals Corporation ("Cupani" or the "Company") (CSE: CUPA) is pleased ...").
#   fix_exchange(h, html)          TSX/TSXV/CSE releases, against the release's own converted PDF (release_html):
#                                  a junk headline (an address, a sentence fragment) is replaced by the release's
#                                  title block; a headline cut at the PDF's line wrap is completed from the title
#                                  block; a subtitle glued onto the headline is cut off. Never leaves a title
#                                  hanging ("... Announces", "... for").
#   repair(source, h, html)        -> (new headline, rule) ; rule '' when unchanged.
# Pure functions; BeautifulSoup only to read the converted HTML.
import re

try:
    from bs4 import BeautifulSoup
except Exception:  # noqa: BLE001
    BeautifulSoup = None

_I = re.I


def clean_headline(h):
    if not h:
        return h
    s = str(h)
    s = re.sub(r"^\s*(?:<\s*br\s*/?>\s*)+", "", s, flags=_I)
    s = re.sub(r"^[\s/\\_*•|~=-]+(?=\S)", "", s)
    s = re.sub(r"^(?:CNW|GLOBE NEWSWIRE)\s*/\s*[-–—]\s*", "", s, flags=_I)
    s = re.sub(r"^\s*\d{1,2}:\d{2}\s*ET\s+(?=[A-Z0-9])", "", s)
    s = re.sub(r"^\s*p\.\s?\d+\s+", "", s, flags=_I)
    s = re.sub(r"^\s*(?:news|press)\s+release\s*(?:dated\s+[A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})?\s*[-–—:|]\s*", "", s, flags=_I)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    if re.match(r"^[a-z]+(?:\s|$)", s):                  # "max Power" -> "Max Power"; leaves "enCore", "i-80 Gold"
        s = s[0].upper() + s[1:]
    return s if len(s) >= 12 else str(h).strip()


_GLUED_INTRO = re.compile(
    r"\.\s+(?=[A-Z][^.]{0,140}?(?:\(\s*(?:the\s+)?[\"“]|\(\s*(?:CSE|TSX|TSXV|TSX-V|NYSE|NASDAQ|OTC\w*|NEO)\s*[:\-]|\bis pleased\b))")


def cut_glued_intro(h):
    """A wire headline that runs on into the release's opening sentence: keep the title."""
    if not h or len(h) < 120:
        return h
    m = _GLUED_INTRO.search(h)
    if not m or m.start() < 25:
        return h
    cut = h[:m.start()].strip()
    return cut if len(cut) >= 25 and not CONNECT_END.search(cut) else h


def norm(s):
    s = str(s or "").lower()
    s = re.sub("[‘’“”ʼˮ]", "'", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def caps_ratio(s):
    L = len(re.findall(r"[A-Za-z]", s))
    U = len(re.findall(r"[A-Z]", s))
    return U / L if L else 0


CONNECT_END = re.compile(r"\b(of|and|the|in|to|with|for|at|on|a|an|from|by|as|its|&)$", _I)
SUB_START = re.compile(r"^(\(|this news release|not for (distribution|dissemination)|for immediate release|trading symbol|"
                       r"news release|highlights|\d{1,2}[/.]\d{1,2}[/.]\d{2,4})", _I)
CLUTTER = re.compile(r"(news release|for immediate release|press release|trading symbol|not for (distribution|dissemination)|"
                     r"not intended for|media release|\bsuite\b|\bfloor\b|\bstreet\b|\bavenue\b|\b(St|Ave|Rd|Blvd)\b\.?\s|"
                     r"[A-Z]\d[A-Z]\s?\d[A-Z]\d|www\.|\btel\b|phone|@|\bTSX[-.]?V?\s*:|\bCSE\s*:|^\d{1,2}\s+\w+\s+\d{4}$)", _I)
ADDRESS = re.compile(r"^\d{2,6}\s+[A-Z][A-Za-z]+(\s+[A-Z][A-Za-z]+)*\s+(Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Crescent|Drive|"
                     r"Dr\.?|Boulevard|Blvd\.?|Way|Place|Court|Lane)\b")
DATELINE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|"
                      r"Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+\d{4}\b")
SMALL = re.compile(r"^(of|and|the|in|on|to|for|a|an|at|by|with|from|as|or|vs)$", _I)
HANGING = re.compile(r"\b(announces?|reports?|provides?|receives?|files?|closes?|completes?|appoints?|grants?|signs?|enters?)$", _I)


def title_ratio(s):
    w = [x for x in str(s).split() if re.match(r"^[A-Za-z][A-Za-z'’-]{3,}", x)]
    if not w:
        return 1
    return len([x for x in w if x[0].isupper()]) / len(w)


def looks_prose(t):
    if CLUTTER.search(t) and len(t) < 320 and not re.search(r"\b(is pleased|announces? that|today announced)\b", t, _I):
        return False
    return (len(t) > 150
            or (len(t) > 60 and re.search("[.!?][\"”’)]?$", t) and re.search(
                r"\b(is|are|was|will|has|have|announces?|announced|pleased|today)\b", t, _I))
            or bool(re.search(r"/(CNW|GLOBE NEWSWIRE)/|\((TSX|CSE|NYSE)", t, _I)))


def title_like(t):
    return (len(t) <= 300
            and not re.search(r"/(CNW|GLOBE NEWSWIRE)/|--\(Newsfile|\((TSX|CSE|NYSE|NASDAQ)[^)]{0,40}\)|"
                              r"\b(is pleased|announced today|today announced)\b", t, _I)
            and not (len(t) > 200 and re.search("[.][\"”’)]?$", t)))


def title_case(x):
    out = []
    for i, w in enumerate(re.split(r"(\s+)", x)):
        if re.match(r"^\s+$", w) or re.search(r"\d", w) or re.search(r"[a-z]", w):
            out.append(w)
            continue
        l = w.lower()
        if i > 0 and SMALL.match(l):
            out.append(l)
            continue
        if len(re.sub(r"[^A-Za-z]", "", w)) <= 3:
            out.append(w)
            continue
        out.append(re.sub(r"(^|[^a-z'’])([a-z])", lambda m: m.group(1) + m.group(2).upper(), l))
    return "".join(out)


def case_index(B, S):
    nb = ns = 0
    sb, bb = S.lower(), B.lower()
    while nb < len(bb) and ns < len(sb):
        cb, cs = bb[nb], sb[ns]
        if cb == cs:
            nb += 1
            ns += 1
        elif not re.match(r"[a-z0-9]", cb):
            nb += 1
        elif not re.match(r"[a-z0-9]", cs):
            ns += 1
        else:
            return -1
    return nb if ns >= len(sb) else -1


def _txt(el):
    return re.sub(r"[\s ]+", " ", el.get_text(" ") if el is not None else "").strip()


def blocks_of(html, n=8):
    """[(text, has_img_or_table)] for the first n text blocks outside tables, skipping page numbers and
    letter-spaced banners the way MTP's display pass removes them first."""
    if not html or BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html, "lxml")
    out = []
    for e in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li"]):
        if e.find_parent("table") is not None:
            continue
        t = _txt(e)
        if not t:
            continue
        if len(t) < 140 and (re.match(r"^-\s?\d{1,3}\s?-$", t) or re.match(r"^Page \d{1,3}( of \d{1,3})?$", t, _I)
                             or ("|" in t and re.search(r"\bPage \d{1,3}$", t, _I))):
            continue
        if len(t) < 90:
            tk = t.split(" ")
            one = len([x for x in tk if re.match(r"^[A-Za-z&]$", x)])
            if one >= 6 and one / len(tk) >= 0.6:
                continue
        out.append((t, e.find(["img", "table"]) is not None))
        if len(out) >= n:
            break
    return out


def fix_exchange(raw_headline, html):
    """(new headline, rule) for a TSX/TSXV/CSE release, from its converted PDF. Same headline when unsure."""
    RAWH = str(raw_headline or "")
    S = clean_headline(RAWH)
    rule = "clean" if S != RAWH.strip() else ""
    blocks = blocks_of(html)
    if not blocks:
        return S, rule
    newH = S
    hn = norm(S)
    pre = hn[:40]
    hi = -1
    junk = bool(not S or re.match("^[\"“”']?\\s*[)\\],.;:]", S)
                or re.match(r"^\s*(announces?|is|are|has|have|that|and|the|will|was)\b", RAWH) or ADDRESS.match(S))
    removed = 0
    if junk:
        for r0 in range(min(len(blocks) - 1, 6)):
            tt, media = blocks[r0]
            if (len(tt) < 20 or len(tt) > 250 or re.search(r"[.;,:]$", tt) or looks_prose(tt) or CLUTTER.search(tt) or media
                    or ADDRESS.match(tt) or norm(tt) == hn):
                continue
            dl = blocks[r0 + 1][0] + " " + (blocks[r0 + 2][0] if r0 + 2 < len(blocks) else "")
            if not DATELINE.search(dl[:300]):
                continue
            newH, rule = tt, "junk"
            removed = r0 + 1
            break
        pre = ""
    if len(pre) >= 15:
        for i, (t, _m) in enumerate(blocks):
            if pre in norm(t):
                hi = i
                break
    for q in range(hi if hi > 0 else 0):
        if looks_prose(blocks[q][0]) or blocks[q][1]:
            hi = -1
            break
    if hi > 6:
        hi = -1
    if hi >= 0:
        B = blocks[hi][0]
        bn = norm(B)
        if (bn.startswith(hn) or hn.startswith(bn)) and title_like(B):
            if hn.startswith(bn) and len(hn) - len(bn) > 12 and not CONNECT_END.search(B):
                tail = B[-12:].lower()
                k = S.lower().rfind(tail)
                if k > 0:
                    R = re.sub("^[\\s:;,\\-–—]+", "", S[k + len(tail):])
                    if SUB_START.match(R) or title_ratio(R) < 0.6:
                        newH = re.sub("[\\s:;,\\-–—]+$", "", S[:k + len(tail)])
                        rule = "subtitle"
            elif bn.startswith(hn) and len(bn) - len(hn) > 5:
                ci = case_index(B, S)
                E = B[ci:].lstrip() if ci > 0 else ""
                is_title = bool(E and len(E) < 160 and title_ratio(E) >= 0.6
                                and not re.match(r"^(download|highlights?|read more|pdf|view|click|jan|feb|mar|apr|may|jun|"
                                                 r"jul|aug|sep|oct|nov|dec)\b", E, _I)
                                and not re.match(r"^\d", E) and not re.search(r":\s*$", B)
                                and "@" not in E and not CLUTTER.search(E))
                if is_title:
                    newH = B if caps_ratio(B) < 0.6 else S.rstrip() + (" " if B[ci].isspace() else "") + title_case(E)
                    rule = "completed"
    if hi < 0 and not junk and newH == S:
        low = S.lower()
        for g in range(removed, min(len(blocks), 3)):
            if newH != S:
                break
            bt = blocks[g][0].lower()
            for k2 in range(20, len(S) - 15):
                if S[k2 - 1] != " ":
                    continue
                if not bt.startswith(low[k2:]):
                    continue
                cut = re.sub(r"[\s:;,\-]+$", "", S[:k2])
                R2 = S[k2:]
                if len(cut) >= 30 and not CONNECT_END.search(cut) and (SUB_START.match(R2) or title_ratio(R2) < 0.6):
                    newH, rule = cut, "subtitle"
                break
    if rule == "subtitle":
        newH = newH.rstrip(" ✓✔•·|:;,-–—")
    if newH != S and (CONNECT_END.search(newH) or HANGING.search(newH)):
        newH = S
        rule = "clean" if S != RAWH.strip() else ""
    return newH, rule


def repair(source, headline, html=None):
    """(new headline, rule). rule is '' when nothing changed."""
    src = (source or "").lower()
    if src in ("tmx", "cse"):
        h, rule = fix_exchange(headline, html)
    else:
        h = clean_headline(headline)
        rule = "clean" if (h or "") != (headline or "").strip() else ""
        h2 = cut_glued_intro(h)
        if h2 != h:
            h, rule = h2, "glued_intro"
    if (h or "").strip() == (headline or "").strip():
        return headline, ""
    return h, rule


def _selftest():
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("FAIL", name, repr(got), "WANTED", repr(want))

    eq("prefix", clean_headline("News Release dated October 1, 2026 - Acme Gold Closes Financing"), "Acme Gold Closes Financing")
    eq("p1", clean_headline("p.1 DPM Metals Reports Third Quarter Results"), "DPM Metals Reports Third Quarter Results")
    eq("paren", clean_headline("Volta Drills 165.3m of 1.36% Total Rare Earth Oxides ( TREO )"),
       "Volta Drills 165.3m of 1.36% Total Rare Earth Oxides (TREO)")
    eq("et", clean_headline("13:30 ET Cupani Accelerates with Senior Geologist Appointment"), "Cupani Accelerates with Senior Geologist Appointment")
    eq("enCore", clean_headline("enCore Energy Reports Results"), "enCore Energy Reports Results")
    eq("i-80", clean_headline("i-80 Gold Reports First Quarter 2026 Results"), "i-80 Gold Reports First Quarter 2026 Results")
    eq("lower", clean_headline("foremost clean energy engages redchip"), "Foremost clean energy engages redchip")
    html = ("<p>Fraser Staltari Listings Compliance Perth Australian Securities Exchange Level 40 PERTH WA 6000 Via email: x@asx.com.au</p>"
            "<p>Dear Fraser, October 1, 2026</p>")
    eq("no contact completion", fix_exchange("Fraser Staltari Listings Compliance Perth Australian Securities Exchange Level 40", html)[1], "")
    html = ("<p>Goliath Reports Up To 9.87 G/T Au Over 5.00 Meters On Surebet, B.C. ✓</p><p>✓ Assay results from multiple holes</p>"
            "<p>Vancouver, BC - October 1, 2026 - Goliath Resources</p>")
    eq("tick", fix_exchange("Goliath Reports Up To 9.87 G/T Au Over 5.00 Meters On Surebet, B.C. ✓ Assay results from multiple gold-", html)[0],
       "Goliath Reports Up To 9.87 G/T Au Over 5.00 Meters On Surebet, B.C.")
    eq("glued", cut_glued_intro('Cupani Accelerates with Senior Geologist Appointment. Cupani Metals Corporation ("Cupani" or the '
                                '"Company") (CSE: CUPA) (OTCQB: CUPIF) is pleased to announce the appointment of Mathieu Mayoux'),
       "Cupani Accelerates with Senior Geologist Appointment")
    eq("not glued", cut_glued_intro("Acme Reports 2.1 g/t Au over 40 m. Drilling Continues at the Main Zone With Four Rigs on Site "
                                    "and More Results Pending From the Fall Program"),
       "Acme Reports 2.1 g/t Au over 40 m. Drilling Continues at the Main Zone With Four Rigs on Site and More Results Pending From the Fall Program")
    html = ("<p>NEWS RELEASE</p><p>NexMetals Reports 72% Increase in Selebi North Indicated Resources</p>"
            "<p>Vancouver, British Columbia - October 1, 2026 - NexMetals Mining Corp. (TSXV: NEXM) is pleased</p>")
    eq("completed", fix_exchange("NexMetals Reports 72% Increase in Selebi", html),
       ("NexMetals Reports 72% Increase in Selebi North Indicated Resources", "completed"))
    html = ("<p>Surge Copper Announces Lithium Carbonate PFS</p><p>PFS improves on 2025 PEA with lower Phase 1 capital, lower costs</p>"
            "<p>Vancouver, BC - October 1, 2026 - Surge Copper Corp. is pleased to announce</p>")
    eq("subtitle", fix_exchange("Surge Copper Announces Lithium Carbonate PFS PFS improves on 2025 PEA with lower Phase 1 capital, lower", html),
       ("Surge Copper Announces Lithium Carbonate PFS", "subtitle"))
    html = ("<p>16142 Morgan Creek Crescent, Surrey, BC</p><p>Acme Metals Closes Second Tranche of Private Placement</p>"
            "<p>Surrey, British Columbia, October 1, 2026 - Acme Metals Corp.</p>")
    eq("junk", fix_exchange("16142 Morgan Creek Crescent, Surrey, BC", html),
       ("Acme Metals Closes Second Tranche of Private Placement", "junk"))
    html = "<p>Gold Co Announces</p><p>Results of AGM</p><p>Toronto, October 1, 2026 - Gold Co.</p>"
    eq("hanging", fix_exchange("Gold Co Announces Results of AGM and more stuff here", html)[0], "Gold Co Announces Results of AGM and more stuff here")
    eq("same", fix_exchange("Acme Gold Closes Financing", "<p>Acme Gold Closes Financing</p><p>Toronto, October 1, 2026</p>"),
       ("Acme Gold Closes Financing", ""))
    eq("repair wire unchanged", repair("globenewswire", "Plato Gold Corp. Closes Initial $55,000 Tranche"), ("Plato Gold Corp. Closes Initial $55,000 Tranche", ""))
    print("headline_fix self-test:", "ok" if not bad else "%d FAILED" % bad)
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if _selftest() else 0)
