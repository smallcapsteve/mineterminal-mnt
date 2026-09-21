"""Economic studies extractor, facts-store version (ECON_V1).

The new source of the Economic Studies page once it passes the accuracy gate. Written against the
50-release set Justin confirmed on 2026-09-20 (53 rows).

What this reader does, and why each of them is a rule rather than a preference:

  1. ONE RECORD PER SCENARIO (Justin, 2026-09-18), with pre-tax and after-tax as columns on the
     same record. A study states four to six numbered outcomes -- Canagold names four cases,
     Doubleview states three flowsheets at two price decks -- and the page that shows one of them
     is showing the one the company chose to headline.
  2a. WHERE A RELEASE STATES ITS CAPITAL TWO WAYS, BOTH ARE SHOWN (Justin, 2026-09-20): the
     figure the release states, and the base row of its CAPEX sensitivity table.
  2. A SCENARIO IS A NAMED CASE (Justin, 2026-09-20). Low, Base, High, Spot, A1, A2, B, a price
     deck. A row identified only by a percentage swing is a sensitivity sweep, and Desert Gold's
     three sweeps would otherwise publish twenty-two rows for a study with two cases.
  3. ANNOUNCED OR BACKGROUND. Most releases that state economics are restating an old study while
     announcing something else. A page that does not separate them is a page where a five-year-old
     PEA outranks this morning's feasibility study.
  4. THE STUDY BELONGS TO WHOEVER IT IS ABOUT, not to whoever issued the release. Peloton (PMC.CN)
     relays Surge's webinar and quotes Surge's Nevada North PEA; published under PMC that is a
     nine-billion-dollar project credited to the wrong company. The reader records the company a
     release credits the study to (owner_name); the publisher, which knows the issuer, leaves out a
     study that is plainly someone else's. Surge's own release already carries it.
  5. TAG PLUS DETECTION (Justin, 2026-09-18). The page shows any release stating real economics,
     whether or not the categoriser tagged it.

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    one record per scenario (ordinal 0..n-1)
to_prediction(records) -> dict|None    what the accuracy judge compares

Self-tests: python3 -m portal.extractors.economics
"""
from __future__ import annotations

import re

from portal import facts as F
from portal.extractors import econ_core as C
from portal.extractors import resources as RES

NAME = "economics"
VERSION = "1.0.0"
KIND = "economic_study"
TAG = "Economic Studies"
TEXT_CAP = 20000

# the per-scenario columns, in the order the page shows them
NUM_FIELDS = ("discount_pct", "npv_pre_tax", "npv_after_tax", "irr_pre_tax_pct",
              "irr_after_tax_pct", "payback_years", "initial_capex", "capex_sensitivity",
              "opex", "aisc", "mine_life_years", "throughput_tpd", "annual_production")
TXT_FIELDS = ("scenario", "study_type", "currency", "context", "basis", "project",
              "opex_unit", "aisc_unit", "production_unit")


# Every row the reader can produce hangs off an NPV or an IRR, so a release that never mentions
# either states no economics. The facts runner puts all ~43,600 approved releases through every
# registered reader, and this check is what keeps the other 42,500 cheap.
_RE_ANY_ECON = re.compile(r"(?i)NPV|net\s+present\s+value|\bIRR\b|internal\s+rate\s+of\s+return")


def analyse(headline: str, body: str) -> dict:
    """Every scenario the release states, with the study's context and whose study it is."""
    if not _RE_ANY_ECON.search(headline or "") and not _RE_ANY_ECON.search(body or ""):
        return {"is_economic_study": False, "reason": "no_figures", "study_type": None,
                "context": None, "project": None, "owner_name": None, "scenarios": []}
    head = headline or ""
    text = C.economics_text(head, body)
    full = head + "\n" + text
    res = {"is_economic_study": False, "reason": None, "study_type": None,
           "context": None, "project": None, "owner_name": None, "scenarios": []}

    context = "announced" if C.release_announces(head, text) else "background"
    # a release announcing a new study may quote the one it replaces; those figures are not its own
    rows = C.scenarios(full, skip_prior=(context == "announced"))
    rows = [r for r in rows
            if r["npv_after_tax"] is not None or r["npv_pre_tax"] is not None
            or r["irr_after_tax_pct"] is not None or r["irr_pre_tax_pct"] is not None]
    if not rows:
        res["reason"] = "no_figures"
        return res

    project = RES.release_project(head, text[:1500])
    study = C.study_type(head, text)
    owner = C.study_owner_name(head, text)
    # What the release SAYS it reports in beats the exchange rate it quotes, which in turn beats
    # what its currency marks happen to add up to -- Westhaven's recaps carry no mark but their
    # own except the US gold price they assume.
    fallback_cur = (C.stated_currency(full) or C.exchange_base(full)
                    or C.dominant_currency(full))
    shared = C.project_economics(full)
    # Justin, 2026-09-20: show both capital figures where a release states two. Desert Gold's
    # highlights say $15 million and the base row of its CAPEX sensitivity table says 20.9.
    shared["capex_sensitivity"] = C.capex_sensitivity_base(full, shared["initial_capex"])

    out = []
    for r in rows:
        row = dict(r)
        row["project"] = project
        row["study_type"] = study
        row["context"] = context
        row["currency"] = row["currency"] or fallback_cur
        for k, v in shared.items():
            if k == "capex_currency":
                continue
            row[k] = v
        out.append(row)

    # A release that states the same scenario in two currencies has stated one scenario. STLLR
    # writes 'Base Case After-Tax NPV5% of C$1.36 billion (US$1.01 billion)' and headlines the
    # US figure; the page carries the currency the release reports in.
    if fallback_cur:
        keep = [r for r in out if (r.get("currency") or fallback_cur) == fallback_cur]
        if keep and len(keep) < len(out):
            names = {C._merge_key(r["scenario"])[:2] for r in keep}
            out = [r for r in out
                   if r in keep or C._merge_key(r["scenario"])[:2] not in names]

    res["is_economic_study"] = True
    res["reason"] = "scenarios"
    res["study_type"] = study
    res["context"] = context
    res["project"] = project
    res["owner_name"] = owner
    res["scenarios"] = out[:12]
    return res


# ------------------------------------------------------------------ facts store adapter
def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    if not a["scenarios"]:
        return [F.Record(KIND, facts=[F.Fact("is_economic_study", value_num=0.0),
                                      F.Fact("reason", value_text=a["reason"])], confidence=0.0)]
    out = []
    for s in a["scenarios"]:
        fs = [F.Fact("is_economic_study", value_num=1.0)]
        if a["owner_name"]:
            fs.append(F.Fact("owner_name", value_text=a["owner_name"][:120]))
        for k in TXT_FIELDS:
            if s.get(k):
                fs.append(F.Fact(k, value_text=str(s[k])))
        for k in NUM_FIELDS:
            if s.get(k) is not None:
                fs.append(F.Fact(k, value_num=float(s[k])))
        out.append(F.Record(KIND, facts=fs, confidence=1.0))
    return out


def parse_records(rows_by_ordinal):
    """{ordinal: [(field, seq, value_num, value_text)]} -> the analyse()-shaped dict."""
    scen, is_es = [], False
    for ordinal in sorted(rows_by_ordinal):
        s = {k: None for k in TXT_FIELDS + NUM_FIELDS}
        for field_, seq, num, text in sorted(rows_by_ordinal[ordinal], key=lambda f: (f[0], f[1])):
            if field_ == "is_economic_study":
                is_es = is_es or num == 1.0
            elif field_ == "owner_name":
                s["owner_name"] = text
            elif field_ in NUM_FIELDS:
                s[field_] = num
            elif field_ in TXT_FIELDS:
                s[field_] = text
        if s["scenario"]:
            scen.append(s)
    return {"is_economic_study": is_es and bool(scen),
            "study_type": scen[0]["study_type"] if scen else None,
            "context": scen[0]["context"] if scen else None,
            "project": scen[0]["project"] if scen else None,
            "owner_name": scen[0].get("owner_name") if scen else None,
            "scenarios": scen}


def to_prediction(records):
    if not records:
        return None
    rows = {i: [(f.field, f.seq, f.value_num, f.value_text) for f in rec.facts]
            for i, rec in enumerate(records)}
    return prediction_from(parse_records(rows))


JUDGED = ("scenario", "study_type", "currency", "context", "basis", "discount_pct",
          "npv_pre_tax", "npv_after_tax", "irr_pre_tax_pct", "irr_after_tax_pct",
          "payback_years", "initial_capex", "capex_sensitivity", "mine_life_years")


def prediction_from(a):
    if not a.get("is_economic_study") or not a.get("scenarios"):
        return None
    return {"project": a.get("project"), "owner_name": a.get("owner_name"),
            "scenarios": [{k: s.get(k) for k in JUDGED} for s in a["scenarios"]]}


def _code_sha():
    import hashlib
    import os
    h = hashlib.sha1()
    for p in (__file__, C.__file__, RES.__file__):
        with open(p, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest() + "-" + os.path.basename(C.__file__)


SPEC = F.ExtractorSpec(NAME, VERSION, KIND, TAG, extract, _code_sha())


# ------------------------------------------------------------------ self-test
def self_test(verbose=False):
    """Cases the set forced. Every figure here is from a release Justin labelled on 2026-09-20;
    the full-body run on the box is what measures the reader, this is what stops a regression."""
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))
        elif verbose:
            print("  ok   %s" % name)

    # NILI.V 4629ef10f3a4 -- a four-cell flat table with the tax basis in a bare cell above it
    a = analyse("Surge Battery Metals Announces PEA for its Nevada North Lithium Project",
                "Surge Battery Metals Inc. (TSXV: NILI) announces the Preliminary Economic "
                "Assessment for its Nevada North Lithium Project. Project Economics | Pre-Tax | "
                "Net Present Value (NPV) | (8%) | $ M | 11,395 | Internal Rate of Return (IRR) | "
                "% | 25.5% | Post-Tax | Net Present Value (NPV) | 8%) | $ M | 9,214 | "
                "Internal Rate of Return (IRR) | % | 22.8%. The base case uses a lithium price "
                "of US$24,000/t LCE.")
    s = a["scenarios"]
    eq("NILI one row", len(s), 1)
    eq("NILI pre-tax NPV is not filed as after-tax",
       (s[0]["npv_pre_tax"], s[0]["npv_after_tax"]), (11395e6, 9214e6))
    eq("NILI IRRs", (s[0]["irr_pre_tax_pct"], s[0]["irr_after_tax_pct"]), (25.5, 22.8))
    eq("NILI rate from its own cell", s[0]["discount_pct"], 8.0)
    eq("NILI scenario carries its price deck", s[0]["scenario"], "base case US$24,000/t LCE")
    eq("NILI study type", a["study_type"], "PEA")
    eq("NILI project", a["project"], "Nevada North Lithium")

    # SLI.V f6a9a23a4d8f -- three-cell table, rate stated only in prose
    a = analyse("Standard Lithium Announces PEA for the Smackover Project",
                "The PEA uses a discount rate of 8%. NPV (Pre-Tax) | $ million | 5,924 | "
                "NPV (After-Tax) | $ million | 4,992 | IRR (Pre-Tax) | % | 25.7% | "
                "IRR (After-Tax) | % | 24.0%")
    s = a["scenarios"][0]
    eq("SLI tax label after the token", (s["npv_pre_tax"], s["npv_after_tax"]), (5924e6, 4992e6))
    eq("SLI rate from prose", s["discount_pct"], 8.0)

    # LMR.V 345847f40783 -- both bases in consecutive sentences; the nearest marker wins
    a = analyse("Lomiko Metals Announces PFS for the La Loutre Graphite Project",
                "Pre-tax NPV (8%) of CA$797.5 M and a pre-tax IRR of 30.3%. After-tax NPV (8%) "
                "of CA$617.4 M and an after-tax IRR of 24.7%.")
    s = a["scenarios"][0]
    eq("LMR both bases on one row",
       (s["npv_pre_tax"], s["npv_after_tax"], s["irr_pre_tax_pct"], s["irr_after_tax_pct"]),
       (797.5e6, 617.4e6, 30.3, 24.7))
    eq("LMR currency", s["currency"], "CAD")

    # DBG.V eb87d75595b9 -- three flowsheets tagged inline in one sentence
    a = analyse("Doubleview Gold Announces PEA for the Hat Project",
                "Using consensus prices the Hat deposit returns an After-Tax NPV(5%) of "
                "C$4.96 billion (A1), C$6.73 billion (A2), or C$7.27 billion (B), with an "
                "After-Tax IRR of 19% (A1), 23% (A2), or 19% (B).")
    eq("DBG three rows", [x["npv_after_tax"] for x in a["scenarios"]], [4.96e9, 6.73e9, 7.27e9])
    eq("DBG IRRs follow their tags", [x["irr_after_tax_pct"] for x in a["scenarios"]],
       [19.0, 23.0, 19.0])

    # DAU.V a32e12a20c53 -- two named cases above three sensitivity sweeps
    a = analyse("Desert Gold Announces PEA on the SMSZ Project",
                "At a base case gold price of US$2,500/oz the SMSZ project returns an after-tax "
                "NPV (10%) of US$24 million and an after-tax IRR of 34%. At US$3,000/oz gold the "
                "after-tax NPV (10%) is US$41 million and the after-tax IRR is 51%. "
                "Gold price sensitivity | -20% | NPV | US$9 million | -10% | NPV | "
                "US$16 million | +10% | NPV | US$32 million | +20% | NPV | US$40 million")
    eq("DAU sweeps are not scenarios", len(a["scenarios"]), 2)

    # detection: the vocabulary without the figures is not an economic study
    a = analyse("Century Lithium Receives Final Permit",
                "The PEA reports net present value, internal rate of return, capital costs and "
                "operating costs for the project.")
    eq("no figures, no study", a["is_economic_study"], False)
    eq("no figures, reason", a["reason"], "no_figures")

    # attribution: the reader records whose study the release says it is; the publisher decides.
    # PMC.CN 90d629ca3ed3, as Peloton actually wrote it -- no exchange symbol anywhere in it
    a = analyse("Surge Battery Metals Presents Their Preliminary Economic Assessment",
                "In June, 2025, Surge Battery Metals (Surge) released a Preliminary Economic Assessment "
                "(PEA) on their Nevada North Lithium Project, which is located immediately beside "
                "Peloton's North Elko Lithium Project. Key highlights from the Surge PEA include: "
                "After-tax NPV8%: US$9.21 Billion. After-tax IRR: 22.8% at US$24,000/t LCE.")
    eq("owner named in the headline", a["owner_name"], "Surge Battery Metals")
    eq("not Peloton's", C.same_company(a["owner_name"], "Peloton Minerals Corporation"), False)
    eq("is Surge's", C.same_company(a["owner_name"], "Surge Battery Metals Inc."), True)
    eq("the issuer's own headline", C.study_owner_name("Radisson Announces Its Positive PEA", ""), "Radisson")
    eq("a short name is the same company", C.same_company("Radisson", "Radisson Mining Resources Inc."), True)
    eq("a project name is not an owner", C.study_owner_name("West Red Lake Delivers Madsen PFS", ""), None)
    eq("no named owner", analyse("Standard Lithium Announces PEA for the Smackover Project",
                                 "NPV (After-Tax) | $ million | 4,992")["owner_name"], None)

    # background: a release restating a study it already published
    a = analyse("Frontier Lithium Initiates Update to the PAK Feasibility Study",
                "The Company is initiating an update. The 2025 FS, disclosed in a press release "
                "dated May 28, 2025, reported an after-tax NPV (8%) of C$932 million and an "
                "after-tax IRR of 17.9%.")
    eq("background is not announced", a["context"], "background")

    # the facts-store round trip has to come back the same
    recs = extract("Standard Lithium Announces PEA for the Smackover Project",
                   "The PEA uses a discount rate of 8%. NPV (After-Tax) | $ million | 4,992")
    back = to_prediction(recs)
    eq("round trip keeps the figure", back["scenarios"][0]["npv_after_tax"], 4992e6)
    eq("round trip keeps the rate", back["scenarios"][0]["discount_pct"], 8.0)

    print("economics %s: %s" % (VERSION, "ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if self_test(verbose=True) else 0)
