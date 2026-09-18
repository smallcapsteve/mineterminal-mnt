# -*- coding: utf-8 -*-
"""Turn RES_V1 1.0.7 into 1.0.8, and fix one thing in the scorer (2026-09-18).

Measured at 1.0.7: detection 25/0/0/25; row 92.3%, deposit 81.9%, category 100.0%, tonnes 95.7%,
grade 83.3%, context 93.1%. Traced the three releases where the reader was at fault; all four
defects below came out of that trace.

  reader
    AC  "1.0 million tonnes grading 1.00 g/t Au for an indicated resource of 33 koz Au and 12.7
        million tonnes grading 0.97 g/t Au for an inferred resource of 393 koz" -- the tonnage and
        the grade sit in front of the category and only the contained metal follows it. Reading
        forward gave Adyton's indicated row the inferred figures.
    AD  "ir@adytonresources.com" was being read as iridium, and a release whose only metal is
        iridium then labels every unlabelled grade with it.
    AE  "at Camp and Los Cuyes deposits" names a deposit. The project pattern allowed no "and" and
        no plural, so Silvercorp's two deposits both fell back to the project name and the second
        pair was then marked an alternative cut-off of the first.
    AF  the units test for deposit names counted whole numbers and not decimals, so the row
        "Cuyes 0.72 4.04 3.82 22.9 0.09 0.6" reached the page as a deposit.

  scorer
    AG  a field the label does not state cannot be judged. Adyton's 1.0 Mt is right and my label
        has no tonnage for it, because the excerpt I labelled from was cut before it -- counting
        that as a precision miss measures the label, not the reader. Those claims are now reported
        separately instead.

Usage: patch_res_v108.py <resources.py> [score_res.py]
"""
import hashlib
import sys

READER = [
    ('VERSION = "1.0.7"', 'VERSION = "1.0.8"'),
    ('''# "... for 128,000 indicated tonnes of LCE" labels the tonnes; the estimate is in front of it
_RE_TRAILING = re.compile(r"(?i)^\\s*(?:[,;.)]|and\\b|category\\b|classification\\b|"
                          r"tonnes?\\b|ounces\\b|oz\\b|pounds\\b|lbs?\\b|t\\b|$)")''',
     '''# "... for 128,000 indicated tonnes of LCE" labels the tonnes; the estimate is in front of it
_RE_TRAILING = re.compile(r"(?i)^\\s*(?:[,;.)]|and\\b|category\\b|classification\\b|"
                          r"tonnes?\\b|ounces\\b|oz\\b|pounds\\b|lbs?\\b|t\\b|$)")
# "1.0 million tonnes grading 1.00 g/t Au for an indicated resource of 33 koz Au" -- the tonnage
# and the grade are in front of the category and only the contained metal follows it
_RE_TRAILING_BEFORE = re.compile(r"(?i)\\b(?:for|as)\\s+(?:an?\\s+)?$")'''),
    ('                trailing = bool(_RE_TRAILING.match(part[h.end():h.end() + 6]))',
     '''                trailing = bool(_RE_TRAILING.match(part[h.end():h.end() + 6])) \\
                    or bool(_RE_TRAILING_BEFORE.search(part[max(0, h.start() - 10):h.start()]))'''),
    ('''    found = set()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9]{0,8}", (headline or "") + " " + (body_head or "")[:300]):
        got = metal_of(w)
        if got and not got[1]:
            found.add(got[0])
    return next(iter(found)) if len(found) == 1 else None''',
     '''    found = set()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9]{0,8}", (headline or "") + " " + (body_head or "")[:300]):
        if len(w) <= 2 and w not in _SYMBOLS:
            continue          # "ir@adytonresources.com" is not iridium
        got = metal_of(w)
        if got and not got[1] and got[0] not in _NEVER_INFERRED:
            found.add(got[0])
    return next(iter(found)) if len(found) == 1 else None'''),
    ('def release_metal(headline: str, body_head: str = "") -> str | None:',
     '''# symbols too easily struck by an ordinary word to carry a release on their own
_NEVER_INFERRED = {"Ir", "Os", "Ru", "Y", "W", "V", "U", "C", "S", "P", "Be", "Sr", "La", "Ce"}


def release_metal(headline: str, body_head: str = "") -> str | None:'''),
    ('''    r"((?:[A-Z][\\w'’\\-\\.]*|\\d+)(?:\\s+(?:[A-Z][\\w'’\\-\\.]*|de|del|la|el))??"
    r"(?:\\s+[A-Z][\\w'’\\-\\.]*)??)\\s+"
    r"(project|deposit|mine|property|zone|prospect|royalty|vein|pit|target|district|complex|claims?)\\b")''',
     '''    r"((?:[A-Z][\\w'’\\-\\.]*|\\d+)"
    r"(?:\\s+(?:[A-Z][\\w'’\\-\\.]*|\\d+|and|de|del|la|el|y)){0,3})\\s+"
    r"(projects?|deposits?|mines?|properties|property|zones?|prospects?|royalty|veins?|pits?|"
    r"targets?|districts?|complex|claims?)\\b")'''),
    ('''            name = re.sub(r"(?i)^(?:producing|past[\\s-]?producing|former|new|flagship|"
                          r"wholly[\\s-]?owned|100%[\\s-]?owned|its|the|company's)\\s+", "", name)''',
     '''            name = re.sub(r"(?i)^(?:producing|past[\\s-]?producing|former|new|flagship|"
                          r"wholly[\\s-]?owned|100%[\\s-]?owned|its|the|company's)\\s+", "", name)
            name = re.sub(r"(?i)[\\s,]+(?:and|or|de|del|la|el|y)\\s*$", "", name).strip(" ,.;:-")'''),
    ('''    unitish = sum(1 for t in toks
                  if _RE_BARE_UNIT.match(t.strip(".,")) or t.strip(".,").isdigit())''',
     '''    unitish = sum(1 for t in toks
                  if _RE_BARE_UNIT.match(t.strip(".,")) or re.fullmatch(r"[\\d.,]+", t))'''),
]

SCORER = [
    ('''                if has_pred:
                    claimed[f] += 1
                    hit[f] += 1 if ok else 0''',
     '''                if has_pred and has_label:
                    claimed[f] += 1
                    hit[f] += 1 if ok else 0
                elif has_pred:
                    # the label does not state this field, so the claim cannot be judged --
                    # counting it wrong would measure the label rather than the reader
                    unstated[f] += 1'''),
    ('''    unjudged = 0
    det = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}''',
     '''    unjudged = 0
    unstated = {k: 0 for k in KEY_FIELDS}
    det = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}'''),
    ('''    print("unjudgeable rows on partial items:", unjudged)''',
     '''    print("unjudgeable rows on partial items:", unjudged,
          " field claims the labels do not state:", {k: v for k, v in unstated.items() if v})'''),
]


def apply(path, edits):
    s = open(path, encoding="utf-8").read()
    for i, (old, new) in enumerate(edits, 1):
        if s.count(old) != 1:
            print("%s edit %d: anchor appears %d times, expected 1" % (path, i, s.count(old)))
            return None
        s = s.replace(old, new, 1)
    open(path, "w", encoding="utf-8").write(s)
    print("patched", path, len(edits), "edits, sha256",
          hashlib.sha256(s.encode("utf-8")).hexdigest())
    return s


def main(argv):
    if apply(argv[0] if argv else "resources.py", READER) is None:
        return 1
    if len(argv) > 1 and apply(argv[1], SCORER) is None:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
