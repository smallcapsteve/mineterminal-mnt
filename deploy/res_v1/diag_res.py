#!/usr/bin/env python3
"""Show what the table reader sees for one release (RES_V1, 2026-09-18).

Fireweed's tonnage comes back as 94 and RUA Gold's as its contained ounces, and neither is
explained by the column-reuse rule that was supposed to cause it. This prints, for each category
row, the header run in force, the values, and the mapping that was chosen -- so the next fix is
aimed rather than guessed.

Usage: diag_res.py <id-prefix> [<id-prefix> ...]
"""
import gzip
import importlib.util
import json
import sys

sys.path.insert(0, "/opt/mnt/app")
SRC = "/var/tmp/mnt-res/corpus.json.gz"
MOD = "/var/tmp/mnt-res/resources.py"

spec = importlib.util.spec_from_file_location("res_v1", MOD)
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def trace(ls):
    header, deposit, last_cols, last_n = [], None, [], 0
    dirty = False
    i = 0
    while i < len(ls):
        ln = ls[i]
        if not ln:
            i += 1
            continue
        wide = R.rowline_of(ln)
        if wide and not R.category_of(ln):
            canon, tail, vals = wide
            wc = R.wide_columns([x for x in ls[max(0, i - 8):i] if x], len(vals))
            bc = R.build_columns(header, len(vals))
            print("  ROWLINE %-22s vals=%d  wide=%d build=%d last=%d  strength=%d"
                  % (canon, len(vals), len(wc), len(bc), len(last_cols), R.header_strength(header)))
            print("    header:", header[-12:])
            cols = R._best_columns([wc, bc, last_cols if (not R.header_strength(header)
                                                          and len(vals) == last_n) else []])
            print("    chosen:", [(c["kind"], c["metal"], c["unit"], c["mult"]) for c in cols])
            print("    values:", [v[0] for v in vals])
            if cols:
                last_cols, last_n = cols, len(vals)
            dirty = True
            i += 1
            continue
        cat = R.category_of(ln)
        if cat:
            vals, j = [], i + 1
            while j < len(ls):
                if not ls[j]:
                    j += 1
                    continue
                nn = R.number_of(ls[j])
                if nn is None:
                    break
                vals.append(nn)
                j += 1
            if len([v for v in vals if v[0]]) >= 2:
                bc = R.build_columns(header, len(vals))
                print("  TABLE   %-22s vals=%d  build=%d last=%d strength=%d dep=%r"
                      % (cat[0], len(vals), len(bc), len(last_cols), R.header_strength(header),
                         deposit))
                print("    header:", header[-14:])
                cols = R._best_columns([bc, last_cols if (not R.header_strength(header)
                                                          and len(vals) == last_n) else []])
                print("    chosen:", [(c["kind"], c["metal"], c["unit"], c["mult"]) for c in cols])
                print("    values:", [v[0] for v in vals])
                if cols:
                    last_cols, last_n = cols, len(vals)
                dirty = True
                i = j
                continue
            i += 1
            continue
        if R.number_of(ln) is not None:
            i += 1
            continue
        if R._RE_STOP.match(ln) or (len(ln) > 90 and not R._is_header_material(ln)):
            header, deposit, dirty = [], None, False
            last_cols, last_n = [], 0
            i += 1
            continue
        if R._is_header_material(ln):
            if dirty:
                header, dirty = [], False
            header.append(ln)
            del header[:-40]
            i += 1
            continue
        d = R.deposit_name(ln)
        if d:
            deposit = d
        i += 1


def main(argv):
    d = json.loads(gzip.open(SRC, "rb").read().decode())
    by_id = {r["event_id"]: r for r in d["tagged"]}
    for p in argv:
        hit = [e for e in by_id if e.startswith(p)]
        if len(hit) != 1:
            print("!!", p, "matches", len(hit))
            continue
        r = by_id[hit[0]]
        print("#" * 70)
        print(r["event_id"][:12], r["ticker"], r["headline"][:90])
        trace(R.lines_of(r["body"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
