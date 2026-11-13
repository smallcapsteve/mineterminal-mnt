"""How the corporate calendar is scored (CAL_SPEC_V1, 2026-10-12).

The Calendar reader (portal/extractors/corp_calendar.py) reads the dated corporate events a release reports: meetings,
results dates, calls, dividends, NCIBs, presentations and the corporate actions (consolidations, name and symbol
changes, arrangements, spin-outs, listings, take-over bids, rights offerings). Mine Terminal Pro shows the future ones
(claude/MNT_EVENTS_READERS_2026-10-07.md section 8; rule calls CA-CH, CD1, CO1, CP1, CN1).

A release is judged event by event. The answer key keeps the release's published_at beside its events, so the reader's
rows are finished (year, "today", status) exactly as the publisher finishes them. Events pair within a release, first
same kind and date, then same kind and the same start of the detail, then same kind, then same date. Leftover
predictions are false rows, leftover labels missed rows.

Key fields (gate at 90% precision on 10+ claims): row, kind, date, status.
- date: both undated is set aside; a date where the label has none, or a different date, is a false claim;
- status: scheduled, proposed, completed, cancelled or postponed, as the release reads on its own date.
Reported only: record_date (dividends), role (presentations), show (OTC / Frankfurt symbols are stored, not shown).

Registered by portal/accuracy.py, which imports this module at the end of its own definitions.
"""
from __future__ import annotations

try:
    from portal.accuracy import TagSpec, register_spec
except Exception:  # pragma: no cover - standalone use of the judge
    TagSpec = register_spec = None

CAL_KEY_FIELDS = ("row", "kind", "date", "status")
CAL_REPORT_FIELDS = ("record_date", "role", "show")


def pair(pred, exp):
    """-> ([(pi, li)], unpaired pred indexes, unpaired label indexes)"""
    pairs, P, E = [], list(range(len(pred))), list(range(len(exp)))
    tests = (lambda p, e: p.get("kind") == e.get("kind") and p.get("date") == e.get("date"),
             lambda p, e: p.get("kind") == e.get("kind") and (p.get("detail") or "")[:4].lower() == (e.get("detail") or "")[:4].lower(),
             lambda p, e: p.get("kind") == e.get("kind"),
             lambda p, e: bool(p.get("date")) and p.get("date") == e.get("date"))
    for test in tests:
        for i in list(P):
            for j in list(E):
                if test(pred[i], exp[j]):
                    pairs.append((i, j))
                    P.remove(i)
                    E.remove(j)
                    break
    return pairs, P, E


def _cmp(out, f, pv, lv):
    pv, lv = pv or None, lv or None
    if pv is None and lv is None:
        return
    if pv == lv:
        out[f].append("tp")
    elif pv is None:
        out[f].append("fn")
    elif lv is None:
        out[f].append("fp")
    else:
        out[f].extend(["fp", "fn"])


def finished_rows(pred, published_at):
    """pred: None, {"rows": [finished rows]} (the publisher's table) or {"dl", "events"} (the reader's records)."""
    if not pred:
        return []
    if "rows" in pred:
        return list(pred["rows"])
    from portal.extractors import corp_calendar as X
    return X.rows_from(pred, published_at)


def judge_calendar(pred, expect):
    out = {f: [] for f in CAL_KEY_FIELDS + CAL_REPORT_FIELDS}
    rows = finished_rows(pred, expect.get("published_at"))
    gold = list(expect.get("events") or [])
    pairs, extra, missed = pair(rows, gold)
    for pi, li in pairs:
        P, L = rows[pi], gold[li]
        out["row"].append("tp")
        _cmp(out, "kind", P.get("kind"), L.get("kind"))
        _cmp(out, "date", P.get("date"), L.get("date"))
        _cmp(out, "status", P.get("status"), L.get("status"))
        if L.get("kind") == "dividend" or P.get("kind") == "dividend":
            _cmp(out, "record_date", P.get("record_date"), L.get("record_date"))
        if L.get("kind") == "presentation" or P.get("kind") == "presentation":
            _cmp(out, "role", P.get("role"), L.get("role"))
        out["show"].extend(["tp"] if (P.get("show") is not False) == (L.get("show") is not False) else ["fp", "fn"])
    out["row"].extend(["fp"] * len(extra))
    out["row"].extend(["fn"] * len(missed))
    return out


def stored_calendar(conn, event_id):
    """What calendar_events holds for one release (the publisher's table)."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='calendar_events'").fetchone():
        return None
    rows = []
    for r in conn.execute("SELECT kind, status, event_date, exact, end_date, record_date, time, detail, venue, role, "
                          "show FROM calendar_events WHERE event_id=? ORDER BY ordinal", (event_id,)):
        rows.append({"kind": r[0], "status": r[1], "date": r[2], "exact": bool(r[3]), "end_date": r[4],
                     "record_date": r[5], "time": r[6], "detail": r[7], "venue": r[8], "role": r[9],
                     "show": bool(r[10])})
    return {"rows": rows} if rows else None


def _calendar_from_records(records):
    from portal.extractors import corp_calendar as X
    return X.to_prediction(records)


def self_test():
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))

    gold = {"published_at": "2026-04-02T12:00:00Z", "events": [
        {"kind": "dividend", "status": "scheduled", "date": "2026-05-15", "exact": True, "record_date": "2026-04-30"},
        {"kind": "meeting", "status": "scheduled", "date": "2026-06-18", "exact": True, "detail": "annual"},
        {"kind": "consolidation", "status": "proposed", "date": None, "detail": "10:1"}]}
    pred = {"rows": [
        {"kind": "dividend", "status": "scheduled", "date": "2026-05-15", "record_date": "2026-04-30"},
        {"kind": "meeting", "status": "completed", "date": "2026-06-19", "detail": "annual"},
        {"kind": "conference_call", "status": "scheduled", "date": "2026-05-01"}]}
    r = judge_calendar(pred, gold)
    eq("rows", r["row"], ["tp", "tp", "fp", "fn"])
    eq("dates", r["date"], ["tp", "fp", "fn"])
    eq("status", r["status"], ["tp", "fp", "fn"])
    eq("record date", r["record_date"], ["tp"])
    r = judge_calendar(None, gold)
    eq("nothing read", r["row"], ["fn"] * 3)
    r = judge_calendar(pred, {"events": []})
    eq("a release with no events: every row is false", r["row"], ["fp"] * 3)
    r = judge_calendar({"rows": [{"kind": "consolidation", "status": "proposed", "date": None, "detail": "10:1"}]},
                       {"events": [gold["events"][2]]})
    eq("both undated: date set aside", (r["row"], r["date"], r["status"]), (["tp"], [], ["tp"]))
    print("accuracy_calendar: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


if register_spec is not None:
    register_spec(TagSpec(
        name="calendar", tag="Corporate Actions", key_fields=CAL_KEY_FIELDS, report_fields=CAL_REPORT_FIELDS,
        judge=judge_calendar, stored=stored_calendar, from_records=_calendar_from_records,
        describe={"row": "every dated corporate event of the issuer the release reports (meetings, results dates, calls, "
                         "dividends, NCIBs, presentations, consolidations, name / symbol changes, arrangements, "
                         "spin-outs, listings, take-over bids, rights offerings)",
                  "kind": "which of those it is",
                  "date": "the event's date (a dividend's payment date); none when the release gives no day",
                  "status": "scheduled, proposed, completed, cancelled or postponed, as of the release",
                  "record_date": "a dividend's record date (reported)",
                  "role": "presenting or attending, for conferences (reported)",
                  "show": "OTC / Frankfurt symbol changes and quotations are stored, not shown (reported)"}))

if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test() else 0)
