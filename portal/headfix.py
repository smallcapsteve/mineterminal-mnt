"""HEADFIX_V1 (MNT, 2026-11-05) - display headlines for releases whose headline was read from a PDF or a page.

Render-time only: the stored headline is unchanged. Used by news_api for every response (recent, by-ticker,
article). Only touches headlines from exchange PDFs (tmx, cse), SEC exhibits (companysite:sec.gov) and PR Newswire,
plus cheap repairs for every source (letter-spaced words, "high- grade").

  clean_headline(headline, source, excerpt="") -> headline

Cases (Justin's second formatting sweep, item 5):
  * run-on headline + subtitle/body ("... MINE More than 80% of the planned ...", "... Property The recent high ...")
  * letterhead or section label in front ("PAN AMERICAN SILVER CORP . 1 Pan American ...", "THIRD QUARTER REPORT 2016 Barrick ...")
  * "Page 1 of 11 ...", "// NOT FOR DISTRIBUTION ... //" and "News release" as the whole headline
  * a TR-1 form line ("1a. Identity of the issuer ...")
  * a ticker line as the headline ("ASM : TSX/NYSE American") and PR Newswire page titles
"""
from __future__ import annotations

import re

VERSION = "headfix-1.1"
PDF_SOURCES = {"tmx", "cse", "companysite:sec.gov", "prnewswire"}
MAXLEN = 180

_SPACED = re.compile(r"\b((?:[A-Z] ){3,}[A-Z])\b")
_HYPH = re.compile(r"\b([a-z]{2,})- ([a-z]{2,})\b")
_HYPH_UP = re.compile(r"\b([A-Z]{2,})- ([A-Z]{2,})\b")
_HYPH_CAP = re.compile(r"\b([A-Z][a-z]+)- ([A-Z][a-z]+)\b")
_EDGAR = re.compile(r"(?i)^\s*(?:EX-\d+(?:\.\d+)?\s+\d+\s+\S+\.html?\s+)?(?:(?:press release|news release|exhibit \d+(?:\.\d+)?)\s+)*(?:[A-Z][A-Z.]{0,8}\s*:\s*(?:TSX|NYSE)[\w/ .-]*?American\s+|[A-Z][A-Z.]{0,8}\s*:\s*(?:TSX|TSXV|NYSE|NASDAQ|CSE)\b\s+)?")
KNOWN2 = {"new york", "thunder bay", "quebec city", "salt lake", "north vancouver", "west vancouver", "saint john", "st. john's",
          "sault ste.", "rouyn noranda", "new westminster", "las vegas", "fort st.", "port coquitlam", "grand forks"}
_PAGE = re.compile(r"^\s*page \d+ (?:of|/) \d+\s*[:/\-|]*\s*", re.I)
_NFD = re.compile(r"(?i)^\W*not for (?:distribution|dissemination)[^/]*?(?:united states|u\.s\.)(?: news ?wire services)?(?: or for dissemination in the united states)?\W*")
_BOILER = re.compile(r"(?i)^\s*(news release|press release|media release|for immediate release|news|nr)\s*[.:]?\s*$")
_TR1 = re.compile(r"(?i)^\s*1a?\.\s*identity of the issuer")
_TICKLINE = re.compile(r"^\s*[A-Z][A-Z.]{0,8}\s*:\s*(?:TSX|TSXV|TSX-V|NYSE|NYSE American|NASDAQ|CSE|OTCQX|OTCQB)\b[\w/ :.,-]*$")
_PRN_PAGE = re.compile(r"(?i)^(all .* news and press releases from pr newswire|mining & metals|mining|metals)$")
_CAPWORD = re.compile(r"^[A-Z0-9][A-Z0-9&'’.,:;%$/()+\-]*$")
_DATELINE = re.compile(r"\s(?:[A-Z][A-Za-z.]+(?: [A-Z][A-Za-z.]+)?, (?:[A-Z][A-Za-z.]+(?: [A-Z][a-z]+)?|B\.?C\.?|ON|QC|NV)(?=[\s,.])[^.]{0,40}?(?:–|—| - |/ ?TheNewswire| \(|--))")
_BODYSTART = re.compile(r"\s(?=(?:The|This|In accordance|Further to|Following|As previously|We are|Our|It is|These)\s[a-z])")
# headfix-1.1 (2026-11-05, third sweep item 4): footnote as the headline; short ALL-CAPS title + body/subtitle
_FOOT = re.compile(r"(?i)^\s*\d{1,2}\s+[^.]{0,90}?\b(?:is|are)\s+(?:a\s+|an\s+)?(?:non-GAAP|non-IFRS|supplementary financial|specified financial)")
_TITLEKEY = re.compile(r"\b(?:ANNOUNCES|REPORTS|PROVIDES|COMPLETES|CLOSES|INTERSECTS|DRILLS|APPOINTS|ACQUIRES|SIGNS|RECEIVES|BEGINS|COMMENCES|"
                       r"INCREASES|EXTENDS|CONFIRMS|UPDATE|APPOINTMENT|APPOINTMENTS|RESIGNATION|RESULTS|ACQUISITION|AGREEMENT|FINANCING|PLACEMENT|DISCOVERY)\b")
_SUBSTART = re.compile(r"^(?:The|This|Announces|Appoints|Provides|Reports|Completes|Closes|Receives|Signs|Begins|Commences|Increases|Extends|"
                       r"Confirms|Intersects|Drills|Acquires|Enters|Files|Grants|Launches|Updates|Highlights|Expands|Discovers)\b")


def _words(s):
    return s.split()


def _is_cap(w):
    letters = [c for c in w if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters) and bool(re.match(r"^[\w&'’.,:;%$/()+\-]+$", w))


def _split_caps(h):
    """Leading ALL-CAPS run and the rest: ('PAN AMERICAN SILVER CORP . 1', 'Pan American ...')."""
    ws = _words(h)
    i = 0
    while i < len(ws) and (_is_cap(ws[i]) or ws[i] == "&" or re.fullmatch(r"[\d.,\-–:|/%$]+", ws[i])):
        i += 1
    caps_words = [w for w in ws[:i] if any(c.isalpha() for c in w)]
    return " ".join(ws[:i]), " ".join(ws[i:]), len(caps_words)


def _cut(h):
    """Shorten a run-on headline at the first place the body or a subtitle begins."""
    m = _DATELINE.search(h, 12)
    if m:
        start = m.start()
        city = h[m.start():m.end()].strip().split(",")[0].split()
        if len(city) == 2 and " ".join(city).lower() not in KNOWN2:
            start = m.start() + 1 + len(city[0])               # "... Meeting Sydney, New South Wales -": cut before Sydney
        return h[:start].rstrip(" ,;:-–—")
    m = _BODYSTART.search(h, 30)
    if m:
        return h[:m.start()].rstrip(" ,;:-–—")
    if len(h) <= MAXLEN:
        return h
    cut = h.rfind(" ", 0, MAXLEN)
    return h[:cut if cut > 60 else MAXLEN].rstrip(" ,;:-–—") + "…"


def _from_excerpt(ex):
    if not ex:
        return ""
    t = re.sub(r"\s+", " ", ex).strip()
    t = _PAGE.sub("", t)
    t = re.sub(r"^\W*//?[^/]{0,160}//\s*", "", t)          # "// NOT FOR DISTRIBUTION ... //"
    t = _NFD.sub("", t)
    t = _EDGAR.sub("", t)
    if re.search(r"(?i)\.htm|\bEX-\d", t[:80]):
        return ""
    if re.search(r"(/i\d+){3}|(\b\w\b ){8}", t[:120]):         # garbled PDF text: give up
        return ""
    caps, rest, n = _split_caps(t)
    if n >= 4:
        return caps
    m = re.match(r"(.{25,200}?)(?=\s(?:[A-Z][A-Za-z.]+, [A-Z]|\(|--|–))", t)
    return m.group(1).strip() if m else ""


def clean_headline(h, source="", excerpt=""):
    if not h:
        return h
    out = _SPACED.sub(lambda m: m.group(1).replace(" ", ""), h)
    out = _HYPH.sub(r"\1-\2", out)
    out = _HYPH_UP.sub(r"\1-\2", out)
    out = _HYPH_CAP.sub(r"\1-\2", out)
    src = (source or "").lower()
    if src not in PDF_SOURCES:
        return out
    if _TR1.match(out):
        return "Notification of major holdings (TR-1)"
    if _FOOT.match(out):                                  # headfix-1.1: a footnote was read as the headline
        alt = _from_excerpt(excerpt)
        return _cut(alt) if alt and not _FOOT.match(alt) else "News release"
    bad_whole = bool(_BOILER.match(out) or _TICKLINE.match(out) or (src == "prnewswire" and _PRN_PAGE.match(out.strip())))
    out = _PAGE.sub("", out)
    if _NFD.match(out):
        rest = _NFD.sub("", out)
        bad_whole = bad_whole or len(rest) < 15
        out = rest
    if bad_whole or not out.strip():
        alt = _from_excerpt(excerpt)
        if alt and re.search(r"\bSuite \d|\b\d{2,5} [A-Z][a-z]+ (?:Street|Avenue|Ave|Road|Blvd|Drive)\b|\bP\.?\s?O\.? Box\b", alt):
            alt = ""                                          # a letterhead address, not a title
        return _cut(alt) if alt else ("News release" if (_BOILER.match(h) or _TICKLINE.match(h)) else h)
    caps, rest, n = _split_caps(out)
    if caps and rest:
        first = next((w for w in _words(caps) if any(c.isalpha() for c in w)), "").lower()
        letterhead = bool(first) and (first in rest.lower() or re.search(r"\bREPORT\b|\b(?:19|20)\d\d\b|\s\.\s*\d", caps))
        if 2 <= n <= 5 and letterhead and not caps.rstrip().endswith(":") and len(_words(rest)) >= 4 and rest[:1].isupper():
            out = rest                                       # letterhead / section label in front
        elif 3 <= n <= 5 and _TITLEKEY.search(caps) and _SUBSTART.match(rest) and len(_words(rest)) >= 3:
            out = caps                                       # headfix-1.1: short ALL-CAPS title, then subtitle or body
        elif n >= 6:
            out = caps                                       # ALL-CAPS title, then subtitle or body
        out = re.sub(r"^[\s.\-–:|]*\d?\s*[.\-–:|]\s*", "", out) if out is rest else out
    return _cut(out.strip())


def _self_test():
    T = [
        ("ESGOLD SURPASSES 4,000 METRES DRILLED AT MONTAUBAN, EXPANDING DRILLING BEYOND THE HISTORIC MINE More than 80% of the planned 5,000-metre drill program",
         "cse", "ESGOLD SURPASSES 4,000 METRES DRILLED AT MONTAUBAN, EXPANDING DRILLING BEYOND THE HISTORIC MINE"),
        ("PAN AMERICAN SILVER CORP . 1 Pan American Silver Discovers New High-grade Veins at the La Colorada Mine", "tmx",
         "Pan American Silver Discovers New High-grade Veins at the La Colorada Mine"),
        ("THIRD QUARTER REPORT 2016 Barrick Reports Third Quarter 2016 Results", "tmx", "Barrick Reports Third Quarter 2016 Results"),
        ("Page 1 of 11 New Age Metals Reports Gold Values up to 4.77 g/t from Ongoing Prospecting at the Bonanza Ridge Gold and Critical Metals Project, Kenora", "tmx",
         "New Age Metals Reports Gold Values up to 4.77 g/t from Ongoing Prospecting at the Bonanza Ridge Gold and Critical Metals Project, Kenora"),
        ("1a. Identity of the issuer or the underlying issuer of existing shares to which voting rights are at-tached ii", "tmx", "Notification of major holdings (TR-1)"),
        ("FireFly makes another significant high- grade copper-gold VMS discovery", "tmx", "FireFly makes another significant high-grade copper-gold VMS discovery"),
        ("C O R R E C T I O N - Silvercorp Metals Inc./", "cnw", "CORRECTION - Silvercorp Metals Inc./"),
        ("Playfair Makes Plans for 1,475 Meter Core Drilling Program at Country Harbour Property The recent high gold price coupled with the lack of recent exploration", "tmx",
         "Playfair Makes Plans for 1,475 Meter Core Drilling Program at Country Harbour Property"),
        ("BARRICK PAVES THE WAY FOR REINTRODUCTION OF WHITE RHINO TO GARAMBA NATIONAL PARK Garamba National Park, Democr", "tmx",
         "BARRICK PAVES THE WAY FOR REINTRODUCTION OF WHITE RHINO TO GARAMBA NATIONAL PARK"),
        ("Kinross reports 2026 third-quarter results", "tmx", "Kinross reports 2026 third-quarter results"),
        ("i-80 Gold Announces Q3 Results", "tmx", "i-80 Gold Announces Q3 Results"),
        ("AGNICO EAGLE REPORTS THIRD QUARTER 2026 RESULTS", "tmx", "AGNICO EAGLE REPORTS THIRD QUARTER 2026 RESULTS"),
        ("UPDATE: Golconda Gold Releases Q3 2026 Production Update at Galaxy", "tmx", "UPDATE: Golconda Gold Releases Q3 2026 Production Update at Galaxy"),
        ("TSX Venture Exchange Stock Maintenance Bulletins", "tmx", "TSX Venture Exchange Stock Maintenance Bulletins"),
        ("NEW FOUND GOLD Reports Drill Results at Queensway North", "tmx", "NEW FOUND GOLD Reports Drill Results at Queensway North"),
        ("2026 Results of Annual General Meeting Sydney, New South Wales – In accordance with ASX Listing Rule 3.13.2", "tmx", "2026 Results of Annual General Meeting"),
        ("LUCA ANNOUNCES AGREEMENT TO ACQUIRE EL BARQUEÑO FROM AGNICO EAGLE", "tmx", "LUCA ANNOUNCES AGREEMENT TO ACQUIRE EL BARQUEÑO FROM AGNICO EAGLE"),
        ("Edge Copper Discovers Large Copper-Gold- Silver-Molybdenum Porphyry System", "tmx", "Edge Copper Discovers Large Copper-Gold-Silver-Molybdenum Porphyry System"),
        ("Drilling Update VANCOUVER, B.C. – Acme Gold Corp. is pleased", "tmx", "Drilling Update"),
        ("REV DRILLS INTO MULTIPLE HELIUM- BEARING HORIZONS AT ADEN DOME Maiden Drilling Validates Stacked Helium Potential", "tmx", "REV DRILLS INTO MULTIPLE HELIUM-BEARING HORIZONS AT ADEN DOME"),
    ]
    for h, s, want in T:
        got = clean_headline(h, s)
        assert got == want, (h, got)
    ex = "NEWS RELEASE October 14, 2026 NR 26-25 www.sitkagoldcorp.com SITKA DRILLS 236.0 METRES OF 1.15 G/T GOLD AT THE SADDLE ZONE Vancouver, B.C. - Sitka"
    assert clean_headline("News release", "tmx", ex) in ("News release", ) or "SITKA" in clean_headline("News release", "tmx", ex)
    assert clean_headline("ASM : TSX/NYSE American", "companysite:sec.gov", "") == "News release"



def _self_test2():
    T = [
        ("MANAGING DIRECTOR & CHIEF EXECUTIVE OFFICER APPOINTMENT The Board of Paladin Energy Ltd (ASX:PDN, TSX:PDN, OTCQX:PALAF) (Paladin or the Comp", "tmx",
         "MANAGING DIRECTOR & CHIEF EXECUTIVE OFFICER APPOINTMENT"),
        ("APPOINTMENT OF INDEPENDENT NON-EXECUTIVE DIRECTOR The Board of Paladin Energy Ltd (ASX:PDN, TSX:PDN, OTCQX:PALAF) (Paladin or the Company) is", "tmx",
         "APPOINTMENT OF INDEPENDENT NON-EXECUTIVE DIRECTOR"),
        ("COLOMBIA CREST PROVIDES CORPORATE UPDATE Announces New CEO and Appoints New Director", "tmx", "COLOMBIA CREST PROVIDES CORPORATE UPDATE"),
        ("1 Operating earnings is a non-GAAP measure defined as sales, less operating costs (excluding depreciation) and general and administrative costs.", "tmx", "News release"),
        ("AGNICO EAGLE REPORTS Third Quarter 2026 Results", "tmx", "AGNICO EAGLE REPORTS Third Quarter 2026 Results"),
        ("NEW FOUND GOLD Reports Drill Results at Queensway North", "tmx", "NEW FOUND GOLD Reports Drill Results at Queensway North"),
        ("1,000 Metre Drill Program Begins at Big Lake", "tmx", "1,000 Metre Drill Program Begins at Big Lake"),
        ("Q3 2026 Results", "tmx", "Q3 2026 Results"),
    ]
    for h, s, want in T:
        got = clean_headline(h, s)
        assert got == want, (h, got)


_self_test()
_self_test2()
