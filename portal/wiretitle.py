"""WIRETITLE_V1 (2026-09-28): drop a trailing wire-service name from a release headline.

Google News titles arrive as "<headline> - <publisher>", and the per-wire collectors only stripped the publisher
names they knew ("PR Newswire", "CNW"). Google now labels them "PR Newswire Canada", "Newswire Canada",
"newswire.ca", "newsfilecorp.com" and so on, so those reached the site as part of the headline.

strip_wire() removes one or more such trailing names. It only acts on a separator (" - ", " – ", " — ", " | ")
followed by a known wire name at the very end, and never leaves a headline shorter than 12 characters.
Called from portal/db.py upsert_event (every collector writes through it) and by the one-off repair script.
"""
import re

_WIRES = (
    r"PR\s*Newswire(?:\s+(?:Canada|UK|US|USA|Asia|APAC|Europe))?",
    r"prnewswire\.(?:com|co\.uk)",
    r"(?:Canada\s+)?News\s*wire(?:\s+Canada)?",
    r"newswire\.ca",
    r"CNW(?:\s+Group)?",
    r"Cision(?:\s+(?:Canada|US|UK|Wire))?",
    r"cision\.com",
    r"(?:TMX\s+)?Newsfile(?:\s+Corp\.?)?",
    r"newsfilecorp\.com",
    r"Globe\s*Newswire(?:\s+by\s+Notified)?",
    r"globenewswire\.com",
    r"ACCESS\s*Newswire",
    r"ACCESSWIRE",
    r"access(?:news)?wire\.com",
    r"Business\s*Wire",
    r"businesswire\.com",
    r"The\s*Newswire",
    r"thenewswire\.com",
)
WIRE_SUFFIX = re.compile(r"\s+[-–—|]\s+(?:" + "|".join(_WIRES) + r")\s*$", re.I)


def strip_wire(headline):
    if not headline:
        return headline
    h = headline
    for _ in range(3):
        m = WIRE_SUFFIX.search(h)
        if not m:
            break
        cut = h[:m.start()].rstrip()
        if len(cut) < 12:
            break
        h = cut
    return h


_TESTS = [
    ("i-80 Gold Publishes its 2025 Sustainability Report - PR Newswire Canada",
     "i-80 Gold Publishes its 2025 Sustainability Report"),
    ("SOMA GOLD Announces Appointment of Sergio Rios as President - Pr Newswire Canada",
     "SOMA GOLD Announces Appointment of Sergio Rios as President"),
    ("A2GOLD COMMENCES RC DRILLING AT TARGET PENTE - newswire.ca", "A2GOLD COMMENCES RC DRILLING AT TARGET PENTE"),
    ("LUCA Mining Announces Binding Equity Commitment - Newswire.ca", "LUCA Mining Announces Binding Equity Commitment"),
    ("Foo Corp Closes Financing - Newswire Canada", "Foo Corp Closes Financing"),
    ("Foo Corp Closes Financing - newsfilecorp.com", "Foo Corp Closes Financing"),
    ("Foo Corp Closes Financing – GlobeNewswire", "Foo Corp Closes Financing"),
    ("Foo Corp Closes Financing | globenewswire.com", "Foo Corp Closes Financing"),
    ("Foo Corp Closes Financing - accessnewswire.com", "Foo Corp Closes Financing"),
    ("Foo Corp Closes Financing - prnewswire.com", "Foo Corp Closes Financing"),
    ("Foo Corp Closes Financing - CNW - PR Newswire Canada", "Foo Corp Closes Financing"),
    ("Foo Corp Closes Financing - Business Wire", "Foo Corp Closes Financing"),
    # left alone
    ("Rock Tech Lithium to Participate in CEM's Muskoka Capital Event", None),
    ("Cascadia Drills 2 m - Central Newfoundland", None),
    ("Newswire Canada", None),
    ("X - PR Newswire", None),
    ("Company Signs Agreement with PR Newswire Canada for Distribution", None),
    ("Stuhini Exploration Ltd. - Corporate Update", None),
    ("Foo Corp Closes Financing -PR Newswire", None),
]


def self_test():
    bad = 0
    for inp, want in _TESTS:
        want = inp if want is None else want
        got = strip_wire(inp)
        if got != want:
            bad += 1
            print("FAIL", repr(inp), "->", repr(got), "want", repr(want))
    print(f"wiretitle self-test {len(_TESTS) - bad}/{len(_TESTS)}")
    return bad == 0


if __name__ == "__main__":
    raise SystemExit(0 if self_test() else 1)
