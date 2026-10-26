"""ROYTERMS_V1 (2026-10-12) - royalty & stream terms: match a reader record to a royalty row, and say it in words.

C8 step 3 (Justin 2026-10-10: buyback / buy-down rights, step-downs and sliding scales, stream delivery terms, caps,
minimum or advance payments, area of interest; 2026-10-12: what was paid for each royalty or stream). The records come
from `royalty_terms` (one row per release, written by /opt/mnt/app/royterms_job.py from portal/royterms_reader.py).

Justin chose to show the rules reader as it is (2026-10-12, "The rules reader as-is") after its blind check:
royalties P 92 / R 69, payments P 54 / R 30, terms P 81 / R 44 on 50 fresh releases - so terms can be missing or
incomplete, and the sites say they are read automatically from the release.

Pure functions; no database access. Self-test: python3 royterms_fmt.py
"""
import json
import re

FAM = {"nsr": "NSR", "grr": "GRR", "gmr": "GRR", "gvr": "GRR", "gor": "GRR", "npi": "NPI", "stream": "stream"}
CUR = {"USD": "US$", "CAD": "C$", "AUD": "A$", "GBP": "£", "EUR": "€"}
NOTE = "Terms read automatically from the release; some may be missing."


def fam(t):
    return FAM.get(str(t or "").strip().lower(), "other")


def _num(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def money(v, cur=None):
    v = _num(v)
    if v is None:
        return ""
    p = CUR.get(str(cur or "").upper(), (str(cur).upper() + " ") if cur else "$")
    a = abs(v)
    if a >= 1e9:
        s = ("%.2f" % (v / 1e9)).rstrip("0").rstrip(".") + "B"
    elif a >= 1e6:
        s = ("%.2f" % (v / 1e6)).rstrip("0").rstrip(".") + "M"
    elif a >= 1e3 and v == int(v):
        s = "{:,}".format(int(v))
    else:
        s = ("%.2f" % v).rstrip("0").rstrip(".")
    return p + s


def pct(v):
    v = _num(v)
    if v is None:
        return ""
    return ("%.4f" % v).rstrip("0").rstrip(".") + "%"


def count(v):
    v = _num(v)
    if v is None:
        return ""
    return "{:,}".format(int(round(v)))


def _clip(s, n=140):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _fors(x):
    f = x.get("for")
    return f if isinstance(f, list) else ([f] if f else [])


# ------------------------------------------------------------------ match a reader interest to a royalty row
def _words(s):
    stop = {"the", "of", "and", "property", "project", "projects", "claims", "mine", "gold", "a", "on"}
    return {w for w in re.findall(r"[a-z0-9]+", str(s or "").lower()) if len(w) > 2 and w not in stop}


def pick_interest(doc, row_type, row_rate, row_property=None):
    """-> the reader interest (dict) that is this royalty row, or None. Same type family and rate first; then same
    family alone when it is the only one; then the release's only interest."""
    ints = (doc or {}).get("interests") or []
    if not ints:
        return None
    f, r = fam(row_type), _num(row_rate)
    pw = _words(row_property)

    def score(i):
        s = 0
        if fam(i.get("type")) == f:
            s += 4
        ir = _num(i.get("rate"))
        if r is not None and ir is not None and abs(ir - r) <= 0.011:
            s += 4
        elif r is None and ir is None:
            s += 1
        if pw and (pw & _words(i.get("property"))):
            s += 2
        return s
    best = max(ints, key=score)
    sc = score(best)
    if sc >= 8 or (sc >= 4 and sum(1 for i in ints if fam(i.get("type")) == f) == 1):
        return best
    if len(ints) == 1 and (sc >= 4 or r is None):
        return best
    return None


# ------------------------------------------------------------------ words
def term_line(t):
    k = t.get("kind")
    if k == "buyback":
        part = (pct(t.get("pct")) + (" of the " + pct(t.get("of_rate")) if _num(t.get("of_rate")) is not None else "")).strip()
        price = money(t.get("price"), t.get("currency")) or _clip(t.get("price_text"), 60)
        s = "Buyback" + (": " + part if part else "") + (" for " + price if price else "")
        if t.get("deadline"):
            s += " (" + _clip(t["deadline"], 60) + ")"
        if t.get("who") == "holder":
            s += ", at the holder's option"
        return s
    if k == "stepdown":
        a, b = _num(t.get("from_rate")), _num(t.get("to_rate"))
        unit = str(t.get("unit") or "")
        if a is not None and b is not None and "%" in (unit or "%"):
            s = "Step-down: %s → %s" % (pct(a), pct(b))
            if unit and unit != "%":
                s += " " + _clip(unit.replace("%", "").strip(), 40)
        else:
            s = "Changes automatically"
        if t.get("trigger"):
            s += " when " + _clip(t["trigger"], 90) if a is not None else ": " + _clip(t["trigger"], 110)
        return s
    if k == "stream":
        s = "Delivers"
        if _num(t.get("delivery_pct")) is not None:
            s += " " + pct(t["delivery_pct"]) + " of"
        s += " " + (t.get("metal") or "payable metal")
        if t.get("ongoing_payment"):
            s += "; ongoing payment " + _clip(t["ongoing_payment"], 90)
        if t.get("threshold"):
            s += " (" + _clip(t["threshold"], 60) + ")"
        return s
    if k == "cap":
        if str(t.get("what") or "").lower().startswith("uncapped"):
            return "Uncapped"
        unit = str(t.get("unit") or "")
        amt = (count(t.get("amount")) + " oz") if unit.lower() == "oz" else (money(t.get("amount"), unit) if unit else count(t.get("amount")))
        return "Cap" + (": " + amt if amt else "") + (" (" + _clip(t.get("what"), 50) + ")" if t.get("what") else "")
    if k == "minimum":
        unit = str(t.get("unit") or "")
        amt = (count(t.get("amount")) + " oz") if unit.lower() == "oz" else money(t.get("amount"), unit)
        s = "Advance / minimum payment" + (": " + amt if amt else "")
        if t.get("period"):
            s += " " + _clip(t["period"], 30)
        if t.get("credited") == "yes":
            s += ", credited against the royalty"
        return s
    if k == "aoi":
        return "Area" + (": " + _clip(t.get("extent"), 100) if t.get("extent") else " of interest")
    return ""


def paid_line(c):
    bits = []
    if _num(c.get("cash")) is not None:
        bits.append(money(c["cash"], c.get("currency")) + " cash")
    if _num(c.get("deposit")) is not None:
        bits.append(money(c["deposit"], c.get("currency")) + " deposit")
    if _num(c.get("shares")) is not None:
        bits.append(count(c["shares"]) + " shares")
    if _num(c.get("share_value")) is not None:
        bits.append("shares worth " + money(c["share_value"], c.get("share_currency") or c.get("currency")))
    if _num(c.get("work")) is not None:
        bits.append(money(c["work"], c.get("currency")) + " of work")
    s = ", ".join(bits)
    if c.get("other"):
        s = (s + "; " if s else "") + _clip(c["other"], 90)
    if c.get("schedule") and s:
        s += " (" + _clip(c["schedule"], 90) + ")"
    return s


def summarize(doc, interest):
    """-> {"name", "lines": [...], "paid": [...], "note"} for one interest of a reader record."""
    iid = interest.get("id")
    lines = [term_line(t) for t in (doc.get("terms") or []) if iid in _fors(t)]
    paid = [paid_line(c) for c in (doc.get("considerations") or []) if iid in _fors(c)]
    return {"name": interest.get("type_text") or "", "event": interest.get("event") or "",
            "lines": [x for x in lines if x], "paid": [x for x in paid if x], "note": doc.get("_note") or NOTE,
            "ai_label": interest.get("_label") or ""}   # MNT_ROYOPS_AI_LIVE_V1: agreed | AI-read while switched


def for_row(doc, row_type, row_rate, row_property=None):
    i = pick_interest(doc, row_type, row_rate, row_property)
    if not i:
        return None
    s = summarize(doc, i)
    return s if (s["lines"] or s["paid"] or s["name"]) else None


def all_interests(doc):
    return [dict(summarize(doc, i), type=i.get("type"), family=fam(i.get("type")), rate=_num(i.get("rate")),
                 property=i.get("property") or "") for i in (doc or {}).get("interests") or []]


if __name__ == "__main__":
    doc = {"interests": [{"id": "i1", "type": "NSR", "type_text": "net smelter returns royalty", "rate": 2.0,
                          "property": "Rattlesnake Hills"}],
           "considerations": [{"for": ["i1"], "cash": 150000.0, "currency": "USD"},
                              {"for": ["i1"], "shares": 1400000.0, "schedule": "on closing"}],
           "terms": [{"kind": "buyback", "for": "i1", "pct": 1.0, "of_rate": 2.0, "price": 750000.0, "currency": "USD",
                      "deadline": "on or prior to December 31, 2017", "who": "payor"},
                     {"kind": "stepdown", "for": "i1", "from_rate": 100, "to_rate": 50, "unit": "% of payable gold",
                      "trigger": "150 koz delivered"},
                     {"kind": "cap", "for": "i1", "what": "uncapped"},
                     {"kind": "aoi", "for": "i1", "extent": "2 km area of influence"}]}
    s = for_row(doc, "NSR", 2.0)
    print(json.dumps(s, indent=1, ensure_ascii=False))
    assert s and s["lines"][0] == "Buyback: 1% of the 2% for US$750,000 (on or prior to December 31, 2017)", s["lines"][0]
    assert s["paid"] == ["US$150,000 cash", "1,400,000 shares (on closing)"], s["paid"]
    assert s["lines"][1].startswith("Step-down: 100% → 50% of payable gold when 150 koz"), s["lines"][1]
    assert pick_interest(doc, "GRR", 3.0) is None
    two = {"interests": [{"id": "a", "type": "NSR", "rate": 2.0}, {"id": "b", "type": "NSR", "rate": 0.5}], "terms": [], "considerations": []}
    assert pick_interest(two, "NSR", 0.5)["id"] == "b"
    assert pick_interest(two, "NSR", None) is None
    print("selftest ok")
