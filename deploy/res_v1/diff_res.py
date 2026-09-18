#!/usr/bin/env python3
"""Diff two RES_V1 readers over the whole tagged corpus (2026-09-18).

A set of 50 labelled releases cannot see a defect it does not contain: 1.0.16 fixes a tonnage the
set never happened to phrase that way ("Mineral Resources TOTAL 6.3 million tonnes"). Scoring the
set again proves only that nothing regressed there. This runs both readers over all 642 tagged
releases and reports what actually changed everywhere, so a fix is never shipped on the strength of
a synthetic example.

Usage: diff_res.py <old.py> <new.py> [max_examples]
"""
import collections
import gzip
import importlib.util
import json
import sys

sys.path.insert(0, "/opt/mnt/app")   # the reader imports portal.facts at module level
SRC = "/var/tmp/mnt-res/corpus.json.gz"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def rkey(r):
    """A row's identity across the two readers: what it is about, not what it says."""
    return (r["category"] or "", (r["deposit"] or "").strip().lower())


def figs(r):
    return (r["tonnes"],
            tuple(sorted((g["metal"] or "", round(float(g["value"]), 6), g["unit"] or "")
                         for g in r["grades"])),
            tuple(sorted((c["metal"] or "", round(float(c["value"]), 6), c["unit"] or "")
                         for c in r["contained"])),
            r["context"])


def show_t(t):
    if t is None:
        return "-"
    return ("%.2f Mt" % (t / 1e6)) if t >= 1e6 else ("%.0f kt" % (t / 1e3)) if t >= 1e3 else ("%.0f t" % t)


def show_c(cs):
    return ",".join("%s %g %s" % (c["metal"] or "?", c["value"], c["unit"] or "") for c in cs) or "-"


def main(argv):
    old = load(argv[0], "res_old")
    new = load(argv[1], "res_new")
    cap = int(argv[2]) if len(argv) > 2 else 25
    print("old %s   new %s" % (old.VERSION, new.VERSION))

    d = json.loads(gzip.open(SRC, "rb").read().decode())
    tagged = d["tagged"]
    st = collections.Counter()
    ex = collections.defaultdict(list)

    for rel in tagged:
        a = old.analyse(rel["headline"], rel["body"])
        b = new.analyse(rel["headline"], rel["body"])
        ao, bo = a["rows"], b["rows"]
        st["releases"] += 1
        st["rows_old"] += len(ao)
        st["rows_new"] += len(bo)
        if len(ao) != len(bo):
            st["row_count_changed"] += 1
        amap, bmap = {}, {}
        for r in ao:
            amap.setdefault(rkey(r), []).append(r)
        for r in bo:
            bmap.setdefault(rkey(r), []).append(r)
        changed = False
        for k in set(amap) | set(bmap):
            av, bv = amap.get(k, []), bmap.get(k, [])
            if not bv:
                st["row_dropped"] += len(av)
                changed = True
                ex["row_dropped"].append("%s %s | %s / %s  %s" % (
                    rel["event_id"][:8], rel["ticker"], k[1] or "-", k[0], show_t(av[0]["tonnes"])))
                continue
            if not av:
                st["row_added"] += len(bv)
                changed = True
                ex["row_added"].append("%s %s | %s / %s  %s" % (
                    rel["event_id"][:8], rel["ticker"], k[1] or "-", k[0], show_t(bv[0]["tonnes"])))
                continue
            for x, y in zip(av, bv):
                if figs(x) == figs(y):
                    continue
                changed = True
                if x["tonnes"] is None and y["tonnes"] is not None:
                    st["tonnage_gained"] += 1
                    ex["tonnage_gained"].append("%s %s | %s / %s  - -> %s" % (
                        rel["event_id"][:8], rel["ticker"], k[1] or "-", k[0], show_t(y["tonnes"])))
                elif x["tonnes"] is not None and y["tonnes"] is None:
                    st["tonnage_lost"] += 1
                    ex["tonnage_lost"].append("%s %s | %s / %s  %s -> -" % (
                        rel["event_id"][:8], rel["ticker"], k[1] or "-", k[0], show_t(x["tonnes"])))
                elif x["tonnes"] != y["tonnes"]:
                    st["tonnage_changed"] += 1
                    ex["tonnage_changed"].append("%s %s | %s / %s  %s -> %s" % (
                        rel["event_id"][:8], rel["ticker"], k[1] or "-", k[0],
                        show_t(x["tonnes"]), show_t(y["tonnes"])))
                if len(x["contained"]) != len(y["contained"]):
                    st["contained_dropped" if len(y["contained"]) < len(x["contained"])
                       else "contained_added"] += 1
                    ex["contained"].append("%s %s | %s / %s  [%s] -> [%s]" % (
                        rel["event_id"][:8], rel["ticker"], k[1] or "-", k[0],
                        show_c(x["contained"]), show_c(y["contained"])))
                if x["context"] != y["context"]:
                    st["context_changed"] += 1
                    ex["context"].append("%s %s | %s / %s  %s -> %s" % (
                        rel["event_id"][:8], rel["ticker"], k[1] or "-", k[0], x["context"], y["context"]))
        st["releases_changed"] += changed

    print("\n--- totals ---")
    for k in ("releases", "releases_changed", "rows_old", "rows_new", "row_count_changed",
              "row_added", "row_dropped", "tonnage_gained", "tonnage_lost", "tonnage_changed",
              "contained_added", "contained_dropped", "context_changed"):
        print("  %-20s %d" % (k, st[k]))
    for name in ("tonnage_gained", "tonnage_lost", "tonnage_changed", "row_added", "row_dropped",
                 "contained", "context"):
        v = ex[name]
        if not v:
            continue
        print("\n--- %s (%d) ---" % (name, len(v)))
        for line in v[:cap]:
            print("  " + line)
        if len(v) > cap:
            print("  ... %d more" % (len(v) - cap))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
