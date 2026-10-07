#!/usr/bin/env python3
"""MNT per-issuer headline memory (TAGFIX_V3). Correct one release's tags and remember the correction for every
release from the same issuer with the same headline template (dates and numbers blanked).

  tag_memory.py show   <event_id>                  the release, its template and any remembered tags
  tag_memory.py set    <event_id> <code,code,...>  correct this release, remember it, retag the issuer's same-template
                                                   releases (all statuses); prints what changed
  tag_memory.py forget <event_id>                  drop the remembered entry for this release's template (tags stay)
  tag_memory.py list                               every remembered entry

Codes are the site's tag codes (exp, drl, fin, ...; see CODE_TO_CAT in categorize.py). Every change is logged to
portal/tag_memory_log.tsv (event_id, before, after, time) so it can be undone."""
import os, sys, json, time, sqlite3

PORTAL = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(PORTAL), PORTAL]
from portal import categorize as C  # noqa: E402

DB = os.path.join(PORTAL, "portal.db")
MEM = os.path.join(PORTAL, "tag_memory.json")
LOG = os.path.join(PORTAL, "tag_memory_log.tsv")


def load():
    try:
        return json.load(open(MEM, encoding="utf-8"))
    except (OSError, ValueError):
        return {"marker": "TAGFIX_V3", "entries": []}


def save(d):
    tmp = MEM + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if os.path.exists(MEM):
        st = os.stat(MEM)
        os.chown(tmp, st.st_uid, st.st_gid)
    os.replace(tmp, MEM)


def row(con, eid):
    r = con.execute("select event_id, ticker, raw_headline, categories, raw_body from events where event_id=?", (eid,)).fetchone()
    if not r:
        sys.exit("no such event_id")
    return r


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    d = load()
    if cmd == "list":
        for e in d["entries"]:
            print(f"{e['symbol']:8s} {','.join(C.CAT_TO_CODE.get(t, t) for t in e['tags']):20s} {e['template']}  ({e.get('date', '')})")
        print(len(d["entries"]), "entries")
        return
    con = sqlite3.connect(DB, timeout=60)
    eid, tk, h, cats, body = row(con, sys.argv[2])
    sym, tpl = C.issuer_symbol(tk, body), C.headline_template(h)
    if cmd == "show":
        hit = [e for e in d["entries"] if e["symbol"] == sym and e["template"] == tpl]
        print("ticker", tk, "| symbol", sym, "\nheadline", h, "\ntemplate", tpl, "\ntags", cats,
              "\nremembered", hit[0]["tags"] if hit else None)
        return
    if cmd == "forget":
        n = len(d["entries"])
        d["entries"] = [e for e in d["entries"] if not (e["symbol"] == sym and e["template"] == tpl)]
        save(d)
        print("forgot", n - len(d["entries"]), "entry")
        return
    if cmd != "set" or len(sys.argv) < 4:
        sys.exit(__doc__)
    codes = [c.strip() for c in sys.argv[3].split(",") if c.strip()]
    unknown = [c for c in codes if c not in C.CODE_TO_CAT]
    if unknown or not codes:
        sys.exit(f"unknown tag codes {unknown}; valid: {', '.join(sorted(C.CODE_TO_CAT))}")
    tags = [C.CODE_TO_CAT[c] for c in codes]
    if not sym or not tpl or C.is_hollow(C.norm_head(h)):
        # generic headline: correct this one release only, remember nothing
        new = "|".join(c for c in C.CATEGORIES if c in tags)
        con.execute("update events set categories=? where event_id=?", (new, eid))
        con.commit()
        with open(LOG, "a", encoding="utf-8") as lg:
            lg.write(f"{eid}\t{cats}\t{new}\t{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
        print("generic headline or no issuer symbol: corrected this release only, nothing remembered |", cats, "->", new)
        return
    d["entries"] = [e for e in d["entries"] if not (e["symbol"] == sym and e["template"] == tpl)]
    d["entries"].append({"symbol": sym, "template": tpl, "tags": [c for c in C.CATEGORIES if c in tags],
                         "from": eid, "date": time.strftime("%Y-%m-%d")})
    save(d)
    new = "|".join(c for c in C.CATEGORIES if c in tags)
    changed = 0
    with open(LOG, "a", encoding="utf-8") as lg:
        for e2, t2, h2, c2 in con.execute("select event_id, ticker, raw_headline, categories from events").fetchall():
            if (c2 or "") == new or C.headline_template(h2) != tpl:
                continue
            s2 = C.issuer_symbol(t2) if t2 else C.issuer_symbol(None, con.execute(
                "select raw_body from events where event_id=?", (e2,)).fetchone()[0])
            if s2 == sym:
                con.execute("update events set categories=? where event_id=? and coalesce(categories,'')=?", (new, e2, c2 or ""))
                lg.write(f"{e2}\t{c2}\t{new}\t{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
                changed += 1
                print("  retagged", e2, c2, "->", new, "|", (h2 or "")[:90])
    con.commit()
    print("remembered", sym, repr(tpl), "->", new, "|", changed, "releases retagged")


if __name__ == "__main__":
    main()
