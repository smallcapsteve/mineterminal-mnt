# -*- coding: utf-8 -*-
"""Turn RES_V1 1.0.10 into 1.0.11 (2026-09-18).

Measured at 1.0.10: detection 25/0/0/25; row 92.4%, deposit 78.9%, category 100.0%, tonnes 100.0%,
grade 95.5%, context 95.9%. Five of the six gated fields pass; deposit is the one left, and almost
all of it is one question Justin settled on 2026-09-18: a row is named project, then zone, then
mining scenario in brackets.

  AM  "0.15% CuEq" is the cut-off a block was reported at, not the name of a place. It was
      reaching the page as XXIX's deposit.
  AN  a table headed "Underground Mining Scenario" or "Pit Constrained" names half of what a
      reader needs. The project goes in front of it and the scenario stays in brackets, so two
      rows for one deposit under two mining assumptions read as the same rock.
  AO  a sentence about "the Rigel and Vega zones" names a zone, not a project. The release project
      goes in front of it. A sentence about "the Feni Island Project" names a different project
      and is left alone -- which is why the noun matters and not just the name.

Usage: patch_res_v111.py <resources.py>
"""
import hashlib
import sys

EDITS = [
    ('VERSION = "1.0.10"', 'VERSION = "1.0.11"'),
    ('''    if _CLASS_WORD.match(s) or metal_of(s):
        return None''',
     '''    if _CLASS_WORD.match(s) or metal_of(s):
        return None
    # "0.15% CuEq" is the cut-off the block was reported at, not the name of a place
    if re.fullmatch(r"(?i)[\\d.,]+\\s*(?:%|g/t|gpt|ppm|c?\\$?\\s*/\\s*t)\\s*[A-Za-z0-9]{0,6}", s):
        return None'''),
    ('def release_announces(headline: str, body_head: str = "") -> bool:',
     '''# a block of one deposit reported under one set of mining assumptions
_RE_SCENARIO = re.compile(r"(?i)\\b(pit[\\s-]?constrained|constrained|open[\\s-]?pit|out[\\s-]?of[\\s-]?pit|"
                          r"in[\\s-]?pit|underground|hybrid|scenario|starter|stockpile|"
                          r"total\\s+resources?)\\b")
_ZONE_NOUNS = ("zone", "zones", "pegmatite", "pegmatites", "vein", "veins", "lens", "lode")


def project_and_kind(text: str):
    """(name, noun) for the first project or zone a passage names, or (None, None)."""
    m = _RE_PROJECT.search(text or "")
    if not m:
        return (None, None)
    name = _WS.sub(" ", m.group(1)).strip(" ,.;:-")
    name = re.sub(r"(?i)^(?:producing|past[\\s-]?producing|former|new|flagship|"
                  r"wholly[\\s-]?owned|100%[\\s-]?owned|its|the|company's)\\s+", "", name)
    name = re.sub(r"(?i)[\\s,]+(?:and|or|de|del|la|el|y)\\s*$", "", name).strip(" ,.;:-")
    name = _named(name)
    if not name or _CLASS_WORD.match(name) or len(name) <= 2:
        return (None, None)
    return (name, (m.group(2) or "").lower())


def qualify(deposit, project, kind=None):
    """Project, then zone, then scenario in brackets (Justin, 2026-09-18).

    A table headed "Underground Mining Scenario" and a sentence about "the Rigel and Vega zones"
    each name half of what a reader needs. Neither is a deposit on its own, and two rows for one
    deposit under two mining assumptions have to be recognisable as the same rock."""
    if not deposit or not project:
        return deposit
    have = set(_norm_dep(deposit).split())
    if have & set(_norm_dep(project).split()):
        return deposit
    if _RE_SCENARIO.search(deposit):
        return "%s (%s)" % (project, deposit)
    if kind in _ZONE_NOUNS:
        return "%s - %s" % (project, deposit)
    return deposit


def release_announces(headline: str, body_head: str = "") -> bool:'''),
    ('                r["_proj"] = release_project(part)',
     '                r["_proj"], r["_proj_kind"] = project_and_kind(part)'),
    ('''        if not r["deposit"]:
            r["deposit"] = r.get("_proj") or project''',
     '''        if not r["deposit"]:
            r["deposit"] = r.get("_proj") or project
            r["deposit"] = qualify(r["deposit"], project, r.get("_proj_kind"))
        else:
            r["deposit"] = qualify(r["deposit"], project)'''),
    ('''        r.pop("_win", None)
        r.pop("_proj", None)''',
     '''        r.pop("_win", None)
        r.pop("_proj", None)
        r.pop("_proj_kind", None)'''),
]


def main(argv):
    path = argv[0] if argv else "resources.py"
    s = open(path, encoding="utf-8").read()
    for i, (old, new) in enumerate(EDITS, 1):
        if s.count(old) != 1:
            print("edit %d: anchor appears %d times, expected 1" % (i, s.count(old)))
            return 1
        s = s.replace(old, new, 1)
    open(path, "w", encoding="utf-8").write(s)
    print("patched", path, len(EDITS), "edits, sha256",
          hashlib.sha256(s.encode("utf-8")).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
