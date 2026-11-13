"""Cross-tag admission rule: the options reader's finds give a release Partnerships & JV (TAG7 step 3, 2026-10-12).

Owner ruling 2026-10-12: an option to earn or acquire a PARTIAL interest (less than 100%) is an earn-in, so it is
Partnerships & JV as well as Property Options & Staking; an option to buy 100% is not.

admit(headline, text, categories, out) -> (bool, short_reason); categories exclude Partnerships & JV.
  1. A row is an option or earn-in (option_in / option_out) for 10%-99.9% (below 10% is a misread).
  2. The release is the deal's own news: it carries Property Options & Staking, or the options reader's own outside-tag
     rule (admit_options.py) admits it.
  3. Not when the opening text speaks of 100% / full ownership with no JV, farm-in or partnership words (a staged option
     to 100%, read at its first stage); not when the headline names no deal; not when the deal is only the setting of
     drilling, results or an update; not a partner's exploration activity.
Measured: 130/150 before the filter (in-sample), 110/120 (91.7%) on a fresh draw of releases it had not seen.
"""
import importlib.util
import os
import re

I = re.I
JV, OPT = "Partnerships & JV", "Property Options & Staking"
_HUNDRED = re.compile(r"\b(?:up to |an? |the remaining |of |a |undivided )*(?:100\s?%|100 per ?cent|one hundred per ?cent)|"
                      r"\b(?:full|entire|complete|outright) (?:ownership|interest)\b", I)
_JVWORD = re.compile(r"\bjoint[\s-]venture|\bJV\b|\bfarm[\s-]?(?:in|out)\b|\bpartnership\b", I)
_DEAL = re.compile(r"\b(?:option\w*|earn\w*|farm\w*|joint[\s-]venture|JV|agreement|LOI|letter of intent|term sheet|"
                   r"interest|acquir\w+|amend\w+|terminat\w+|vest\w*|exercis\w+)\b", I)
_SETTING = re.compile(r"\b(?:drill\w*|exploration update|production|results|intersect\w*|assay\w*|advances|update[sd]?|"
                      r"survey|sampl\w+)\b", I)
_CHANGE = re.compile(r"\b(?:sign\w*|enter\w*|execut\w+|terminat\w+|amend\w+|agreement|LOI|letter of intent|earns?|"
                     r"earned|vest\w*|exercis\w+|grants?|options?\s+(?:the|its|\w+ (?:project|property))|completes?)\b", I)
_PARTNER = re.compile(r"\b(?:option agreement |JV |earn-in )?partner\w*[,’']?s?\b.{0,40}\b(?:advances|drill\w*|begins|"
                      r"commences|reports|completes? (?:drilling|program))", I)

_AO = None


def _admit_options():
    global _AO
    if _AO is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admit_options.py")
        sp = importlib.util.spec_from_file_location("reader_admit_options_for_jv", path)
        mod = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(mod)
        _AO = mod
    return _AO


def _opening(text):
    """The opening ~1,200 characters as measured (portal.categorize.lede when importable)."""
    try:
        from portal.categorize import lede
        t = lede(text or "", 1200)
    except Exception:  # noqa: BLE001
        t = (text or "")[:1200]
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) < 200:
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()[:1200]
    return t


def _partial(rows):
    out = []
    for r in rows:
        try:
            ip = float(r.get("interest_pct"))
        except (TypeError, ValueError):
            continue
        if r.get("deal_type") in ("option_in", "option_out") and 10 <= ip < 100:
            out.append(r)
    return out


def admit(headline, text, categories, out):
    rows = [r for r in ((out or {}).get("rows") or []) if r and r.get("deal_type")]
    if not _partial(rows):
        return False, "no partial-interest option"
    head = headline or ""
    if OPT not in (categories or []):
        ok, why = _admit_options().admit(head, text, [c for c in (categories or []) if c != OPT], out)
        if not ok:
            return False, "not the deal's news: " + (why or "")[:60]
    t = head + " . " + _opening(text)
    if _HUNDRED.search(t) and not _JVWORD.search(t):
        return False, "100% option"
    if not _DEAL.search(head):
        return False, "headline names no deal"
    if _SETTING.search(head) and not _CHANGE.search(head):
        return False, "deal is the setting"
    if _PARTNER.search(head) and not _CHANGE.search(re.sub(r"(?i)option agreement", "", head)):
        return False, "partner activity"
    return True, "partial-interest option / earn-in"
