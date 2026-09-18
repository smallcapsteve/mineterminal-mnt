#!/usr/bin/env python3
"""Run RES_V1 over the corpus and print its output compactly (2026-09-17).

Two modes. `set` prints every row the reader finds for the 50 accuracy-set releases, small enough
to carry back and score against the labels off the droplet -- the corpus stays here, only the
reader's answers travel. `counts` prints aggregates over all 642 tagged releases and the 400
untagged lookalikes.

Usage: run_res.py set|counts|both
"""
import gzip
import importlib.util
import json
import sys

sys.path.insert(0, "/opt/mnt/app")
SRC = "/var/tmp/mnt-res/corpus.json.gz"
SET = "/var/tmp/mnt-res/sample.json"
MOD = "/var/tmp/mnt-res/resources.py"


def load():
    spec = importlib.util.spec_from_file_location("res_v1", MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def compact(r):
    g = [[x["metal"], x["value"], x["unit"]] for x in r["grades"]]
    c = [[x["metal"], x["value"], x["unit"]] for x in r["contained"]]
    return [r["deposit"], r["category"], r["tonnes"], g, c, r["cut_off"], r["basis"],
            r["context"], r["source"]]


def main(argv):
    mode = argv[0] if argv else "both"
    R = load()
    d = json.loads(gzip.open(SRC, "rb").read().decode())
    tagged = d["tagged"]
    tagged.sort(key=lambda r: ((r["published_at"] or ""), r["event_id"]), reverse=True)
    by_id = {r["event_id"]: r for r in tagged}

    if mode in ("set", "both"):
        want = json.load(open(SET))["event_ids"]
        out = []
        for eid in want:
            r = by_id.get(eid)
            if r is None:
                continue
            a = R.analyse(r["headline"], r["body"])
            out.append({"e": eid[:12], "t": r["ticker"], "m": a["mre_type"],
                        "a": a["announces"], "p": a["project"],
                        "r": [compact(x) for x in a["rows"]]})
        print("###SET###")
        print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))

    if mode in ("counts", "both"):
        import collections
        print("###COUNTS###")
        for name, rows in (("tagged", tagged), ("control", d["control"])):
            n_rel = n_rows = 0
            src = collections.Counter()
            ctx = collections.Counter()
            cat = collections.Counter()
            with_t = with_g = with_d = 0
            mt = collections.Counter()
            for r in rows:
                a = R.analyse(r["headline"], r["body"])
                if not a["rows"]:
                    continue
                n_rel += 1
                mt[a["mre_type"]] += 1
                for x in a["rows"]:
                    n_rows += 1
                    src[x["source"]] += 1
                    ctx[x["context"]] += 1
                    cat[x["category"]] += 1
                    with_t += x["tonnes"] is not None
                    with_g += bool(x["grades"])
                    with_d += bool(x["deposit"])
            print(name, "of", len(rows), "-> releases with rows:", n_rel, " rows:", n_rows)
            print("  source:", dict(src), " context:", dict(ctx))
            print("  category:", dict(cat.most_common()))
            print("  with tonnes:", with_t, " with a grade:", with_g, " with a deposit:", with_d)
            print("  mre_type:", dict(mt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
