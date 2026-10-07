"""Row checks shared by every MNT family API (MNT_ROW_CHECKS_V1, 2026-09-29; reader review fix 4).

Justin, 2026-09-29 ("Show, marked"): a row whose figures fail a plain sanity test is still published, but it carries a
`check` list saying why, and it is kept out of rankings, screeners and headline numbers. Nothing here changes a stored
value; the checks run on the API's output.

    check(family, item)        -> [reason, ...]   (empty when the row passes)
    annotate(family, payload)  -> payload          adds item["check"] to flagged rows and payload["checked"] (count on the page);
                                                   for a request sorted by size, flagged rows move from `items` to `unranked`
    summary()                  -> {family: {"rows": n, "flagged": n, "reasons": {reason: n}, "examples": [...]}}
                                  every row of every family, read through the local API (python3 -m portal.row_checks summary)

The thresholds are the ones in the 2026-09-29 reader review (MNT Readers x MTP, sections 5 and 6):
  resources     contained metal within 0.6-1.67x of tonnes x grade (one grade and one figure for the metal, 1 Mt or more);
                gold/silver not 'contained' in thousands of tonnes; under 10 billion tonnes
  economics     NPV and initial capital above 5 million (a stated 0 capex passes); IRR under 150%
  technical     the same, on the study figures a technical-report row carries
  debt          principal between 1,000 and 20 billion
  exploration   a program under 300,000 m (larger is a cumulative total); a budget under 1 billion
  drills        a best interval under 1,000 m; gold/silver under 5,000 g/t; a percentage grade under 100%
  financings    gross under 5 billion; a unit price under 1,000
  royalties     a rate under 100%; a price under 5 billion
  production    a quarter's gold under 3 Moz, silver under 150 Moz (the reader's own caps are per period type)
"""
from __future__ import annotations

import json
import sys
import urllib.request

API = "http://127.0.0.1:8001/api/v1/"
OZ_PER_T_GPT = 1 / 31.1034768          # oz per tonne at 1 g/t
LB_PER_T = 2204.62262

SIZE_SORTS = {"drills": {"value", "grade", "length"}, "financings": {"size"}}   # the families whose API sorts by size


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _money(v):
    v = _num(v)
    return "%s" % ("{:,.0f}".format(v) if v is not None else "?")


def _resources(it):
    """Tonnes x grade against the contained figure, for a metal the row states exactly one grade and one contained figure
    for (a row that flattens several columns is not compared), on estimates of 1 Mt or more (a rounded '100 kt' is not
    a mismatch); and gold or silver 'contained' in tonnes by the thousand, which is a tonnage read as metal."""
    out = []
    t = _num(it.get("tonnes"))
    if t is not None and t > 10e9:
        out.append("over 10 billion tonnes")
    grades, cont = {}, {}
    for g in it.get("grades") or []:
        if isinstance(g, dict) and g.get("metal"):
            grades.setdefault(str(g["metal"]).lower(), []).append(g)
    for c in it.get("contained") or []:
        if isinstance(c, dict) and c.get("metal"):
            cont.setdefault(str(c["metal"]).lower(), []).append(c)
    for metal, cs in cont.items():
        for c in cs:
            if metal in ("au", "ag") and str(c.get("unit") or "").lower() == "t" and (_num(c.get("value")) or 0) > 10000:
                out.append("contained %s stated in tonnes (%s t; a tonnage read as metal?)" % (metal.capitalize(), _money(c.get("value"))))
    if not t or t < 1e6:
        return out
    for metal, cs in cont.items():
        gs = grades.get(metal) or []
        if "eq" in metal or len(cs) != 1 or len(gs) != 1:
            continue
        c, g = cs[0], gs[0]
        cv, gv = _num(c.get("value")), _num(g.get("value"))
        if not cv or not gv or cv <= 0 or gv <= 0:
            continue
        gu, cu = str(g.get("unit") or "").lower(), str(c.get("unit") or "").lower()
        exp = None
        if gu in ("g/t", "gpt", "ppm") and cu == "oz":
            exp = t * gv * OZ_PER_T_GPT
        elif gu in ("g/t", "gpt", "ppm") and cu == "t":
            exp = t * gv / 1e6
        elif gu == "%" and cu == "t":
            exp = t * gv / 100
        elif gu == "%" and cu == "lb":
            exp = t * gv / 100 * LB_PER_T
        elif gu == "%" and cu == "kg":
            exp = t * gv / 100 * 1000
        if exp and not (0.6 <= cv / exp <= 1.67):
            out.append("contained %s does not match tonnes x grade (%.2fx)" % (metal.capitalize(), cv / exp))
    return out


def _study(fig, capex_zero_ok=True):
    out = []
    for k, label in (("npv_after_tax", "NPV"), ("npv_pre_tax", "NPV"), ("npv", "NPV")):
        v = _num(fig.get(k))
        if v is not None and 0 < v < 5e6:
            out.append("%s under 5 million (%s)" % (label, _money(v)))
            break
    cap = _num(fig.get("initial_capex", fig.get("capex")))
    if cap is not None and 0 < cap < 5e6:
        out.append("capital under 5 million (%s)" % _money(cap))
    for k in ("irr_after_tax_pct", "irr_pre_tax_pct", "irr"):
        v = _num(fig.get(k))
        if v is not None and v > 150:
            out.append("IRR over 150%% (%g%%)" % v)
            break
    return out


def _economics(it):
    out = []
    for s in it.get("scenarios") or []:
        if isinstance(s, dict):
            c = _study(s)
            if c:
                s["check"] = c
                out.extend(r for r in c if r not in out)
    return out


def _debt(it):
    p = _num(it.get("principal"))
    if p is None:
        return []
    if p > 20e9:
        return ["principal over 20 billion (%s)" % _money(p)]
    if 0 < p < 1000:
        return ["principal under 1,000 (%s)" % _money(p)]
    return []


def _exploration(it):
    out = []
    m, b = _num(it.get("metres")), _num(it.get("budget"))
    if m is not None and m > 300000:
        out.append("over 300,000 m (%s m; a cumulative total?)" % _money(m))
    if b is not None and b > 1e9:
        out.append("budget over 1 billion (%s)" % _money(b))
    return out


def _drills(it):
    best = it.get("best") or {}
    if not isinstance(best, dict):
        return []
    out = []
    ln, gr, unit, metal = _num(best.get("length_m")), _num(best.get("grade")), str(best.get("unit") or "").lower(), \
        str(best.get("metal") or "").lower()
    if ln is not None and ln > 1000:
        out.append("interval over 1,000 m (%g m)" % ln)
    if gr is not None and unit in ("g/t", "gpt") and metal in ("au", "gold") and gr > 5000:
        out.append("gold grade over 5,000 g/t (%g)" % gr)
    if gr is not None and unit in ("g/t", "gpt") and metal in ("ag", "silver") and gr > 50000:
        out.append("silver grade over 50,000 g/t (%g)" % gr)
    if gr is not None and unit == "%" and gr > 100:
        out.append("grade over 100%% (%g%%)" % gr)
    return out


def _financings(it):
    out = []
    g, up = _num(it.get("gross")), _num(it.get("unit_price"))
    if g is not None and g > 5e9:
        out.append("gross over 5 billion (%s)" % _money(g))
    if up is not None and up > 1000:
        out.append("unit price over 1,000 (%g)" % up)
    return out


def _royalties(it):
    out = []
    r, p = _num(it.get("rate_pct")), _num(it.get("price"))
    if r is not None and r > 100:
        out.append("rate over 100%% (%g%%)" % r)
    if p is not None and p > 5e9:
        out.append("price over 5 billion (%s)" % _money(p))
    return out


def _production(it):
    q = _num(it.get("qty") if it.get("qty") is not None else it.get("high"))
    period, metal, unit = str(it.get("period") or ""), str(it.get("metal") or ""), str(it.get("unit") or "")
    if q is None or unit != "oz" or not period.startswith("Q"):
        return []
    if metal in ("gold", "AuEq", "GEO") and q > 3e6:
        return ["a quarter's gold over 3 Moz (%s oz)" % _money(q)]
    if metal in ("silver", "AgEq") and q > 150e6:
        return ["a quarter's silver over 150 Moz (%s oz)" % _money(q)]
    return []


CHECKS = {"resources": _resources, "economics": _economics, "technical": lambda it: _study(it), "debt": _debt,
          "exploration": _exploration, "drills": _drills, "financings": _financings, "royalties": _royalties,
          "production": _production}


def check(family, item):
    fn = CHECKS.get(family)
    if fn is None or not isinstance(item, dict):
        return []
    try:
        return fn(item)
    except Exception:          # a check never breaks an API response
        return []


def annotate(family, payload, sort=None):
    if family not in CHECKS or not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return payload
    n, keep, moved = 0, [], []
    for it in payload["items"]:
        c = check(family, it)
        if c:
            it["check"] = c
            n += 1
        (moved if c and sort and str(sort).lower() in SIZE_SORTS.get(family, ()) else keep).append(it)
    payload["checked"] = n
    if moved:
        payload["items"] = keep
        payload["unranked"] = moved
        payload["unranked_note"] = "Rows flagged for checking are listed here rather than ranked by size."
    return payload


def summary(limit=500):
    out = {}
    for fam in sorted(CHECKS):
        rows = flagged = 0
        reasons, examples, page = {}, [], 1
        while page <= 200:
            try:
                with urllib.request.urlopen(f"{API}{fam}?limit={limit}&page={page}", timeout=120) as r:
                    d = json.loads(r.read().decode())
            except Exception as e:     # a family whose API is down is reported, not fatal
                out[fam] = {"error": repr(e)[:200]}
                break
            items = d.get("items") or []
            for it in items:
                rows += 1
                c = it.get("check") if "check" in it else check(fam, it)
                if c:
                    flagged += 1
                    for x in c:
                        k = x.split(" (")[0]
                        reasons[k] = reasons.get(k, 0) + 1
                    if len(examples) < 12:
                        examples.append({"ticker": it.get("ticker"), "date": it.get("date"), "check": c,
                                         "headline": str(it.get("headline") or "")[:90]})
            pages = d.get("pages") or 1
            if page >= pages or not items:
                break
            page += 1
        else:
            pass
        if "error" not in out.get(fam, {}):
            out[fam] = {"rows": rows, "flagged": flagged, "reasons": reasons, "examples": examples}
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        import datetime
        import os
        res = {"at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "families": summary()}
        path = sys.argv[2] if len(sys.argv) > 2 else "/var/lib/mnt-portal/row_checks.json"
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(res, fh, indent=1)
        os.replace(tmp, path)
        for f, v in res["families"].items():
            print(f, {k: v[k] for k in v if k != "examples"})
    else:
        # self-test
        bad = 0

        def eq(name, got, want):
            global bad
            if got != want:
                bad += 1
                print("FAIL", name, got, want)
        eq("resources ok", check("resources", {"tonnes": 110.9e6, "grades": [{"metal": "Au", "value": 1.34, "unit": "g/t"}],
                                               "contained": [{"metal": "Au", "value": 4.8e6, "unit": "oz"}]}), [])
        eq("resources bad", len(check("resources", {"tonnes": 110.9e6, "grades": [{"metal": "Au", "value": 1.34, "unit": "g/t"}],
                                                    "contained": [{"metal": "Au", "value": 48e6, "unit": "oz"}]})), 1)
        eq("resources, a tonnage read as gold", len(check("resources", {"tonnes": 176e6, "grades": [{"metal": "Au", "value": 1.22, "unit": "g/t"}],
                                                                        "contained": [{"metal": "Au", "value": 6.9e6, "unit": "oz"}, {"metal": "Au", "value": 87.8e6, "unit": "t"}]})), 1)
        eq("resources, small and rounded", check("resources", {"tonnes": 1e5, "grades": [{"metal": "Ag", "value": 174, "unit": "g/t"}],
                                                               "contained": [{"metal": "Ag", "value": 4e5, "unit": "oz"}]}), [])
        eq("debt", check("debt", {"principal": 17.5e12}), ["principal over 20 billion (17,500,000,000,000)"])
        eq("econ", check("economics", {"scenarios": [{"npv_after_tax": 24000.0, "irr_after_tax_pct": 60}]}), ["NPV under 5 million (24,000)"])
        eq("econ zero capex", check("economics", {"scenarios": [{"npv_after_tax": 2e8, "initial_capex": 0}]}), [])
        p = annotate("financings", {"items": [{"gross": 1e6}, {"gross": 18e9}]}, sort="size")
        eq("unranked", (len(p["items"]), len(p["unranked"]), p["checked"]), (1, 1, 1))
        p = annotate("financings", {"items": [{"gross": 1e6}, {"gross": 18e9}]}, sort="date")
        eq("date sort keeps", (len(p["items"]), p["checked"]), (2, 1))
        print("row_checks:", "ok" if not bad else "%d FAILURES" % bad)
        sys.exit(1 if bad else 0)
