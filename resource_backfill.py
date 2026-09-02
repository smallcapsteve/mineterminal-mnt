"""resource_backfill.py — re-extract MREs from events and populate resource_estimates."""
from __future__ import annotations
import json as _json, re, sqlite3, sys
from datetime import datetime

sys.path.insert(0, "/opt/mnt/app")
sys.path.insert(0, "/opt/mnt/app/portal")

from resource_extract import extract_resources, find_project, fmt_category_line  # type: ignore

DB = "/opt/mnt/app/portal/portal.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS resource_estimates (
    res_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT NOT NULL UNIQUE,
    ticker          TEXT,
    project         TEXT,
    summary         TEXT,
    headline_oz_au  REAL,
    headline_t_metal REAL,
    metal_focus     TEXT,
    raw_headline    TEXT,
    published_at    TEXT,
    n_categories    INTEGER,
    mre_type        TEXT,
    categories_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_res_ticker    ON resource_estimates(ticker);
CREATE INDEX IF NOT EXISTS ix_res_published ON resource_estimates(published_at);
"""

NOISE = re.compile(
    r"^(?:CORRECTION(?:\s+FROM\s+SOURCE)?:?\s*|RETRANSMISSION:?\s*|REPLACEMENT:?\s*|"
    r"UPDATE:?\s*|REPEAT:?\s*|AMENDED\s+AND\s+RESTATED:?\s*)",
    re.I,
)

def _norm(s):
    s = NOISE.sub("", (s or "").strip())
    return re.sub(r"[^a-z0-9]+", "", s.lower())[:120]


def main() -> int:
    con = sqlite3.connect(DB)
    con.execute("PRAGMA busy_timeout = 30000")
    con.executescript(SCHEMA)
    # Ensure mre_type + categories_json exist (idempotent migrate)
    cols = [r[1] for r in con.execute("PRAGMA table_info(resource_estimates)")]
    if "mre_type" not in cols:
        con.execute("ALTER TABLE resource_estimates ADD COLUMN mre_type TEXT")
    if "categories_json" not in cols:
        con.execute("ALTER TABLE resource_estimates ADD COLUMN categories_json TEXT")
    con.commit()
    con.execute("DELETE FROM resource_estimates")
    con.commit()

    rows = list(con.execute(
        "SELECT event_id, ticker, raw_headline, raw_body, published_at "
        "FROM events WHERE categories LIKE ? AND review_status='auto_approved'",
        ("%Resource Estimates%",),
    ))
    print(f"events to scan: {len(rows)}")

    candidates = []
    for eid, ticker, hl, body, pub in rows:
        x = extract_resources(hl or "", body or "")
        if not x.get("categories"):
            continue
        try:
            d = datetime.fromisoformat((pub or "").replace("Z", "+00:00"))
        except Exception:
            d = None
        cats = list(x["categories"].values())
        order = {"Measured": 0, "Indicated": 1, "M&I": 2, "Inferred": 3, "Total": 4}
        cats.sort(key=lambda c: order.get(c.get("category"), 5))
        summary = "  ·  ".join(fmt_category_line(c) for c in cats)
        cats_json = _json.dumps([
            {
                "category": c["category"],
                "stat": fmt_category_line(c).replace(c["category"], "", 1).lstrip(),
            }
            for c in cats
        ])
        prefer = ["Indicated", "M&I", "Measured", "Inferred", "Total"]
        chosen = None
        for tag in prefer:
            for c in cats:
                if c.get("category") == tag:
                    chosen = c
                    break
            if chosen:
                break
        chosen = chosen or cats[0]
        candidates.append({
            "event_id":         eid,
            "ticker":           ticker,
            "project":          find_project(hl or "", body or ""),
            "summary":          summary,
            "categories_json":  cats_json,
            "mre_type":         x.get("mre_type"),
            "headline_oz_au":   chosen.get("contained_oz") or 0,
            "headline_t_metal": chosen.get("contained_t") or 0,
            "metal_focus":      chosen.get("metal") or "",
            "raw_headline":     (hl or "")[:500],
            "published_at":     pub,
            "n_categories":     len(cats),
            "_dt":              d,
            "_norm":            _norm(hl),
        })

    # Dedup by (ticker, normalized_headline_prefix) within ±30 days
    candidates.sort(key=lambda c: (c["ticker"] or "", -(c["_dt"].timestamp() if c["_dt"] else 0)))
    kept = []
    seen = {}
    for c in candidates:
        bucket = seen.setdefault(c["ticker"], [])
        is_dup = False
        for prev_norm, prev_dt in bucket:
            if (
                prev_norm[:60] == c["_norm"][:60]
                or c["_norm"].startswith(prev_norm[:50])
                or prev_norm.startswith(c["_norm"][:50])
            ):
                if c["_dt"] and prev_dt and abs((c["_dt"] - prev_dt).days) <= 180:
                    is_dup = True
                    break
                elif c["_dt"] is None or prev_dt is None:
                    is_dup = True
                    break
        if not is_dup:
            kept.append(c)
            bucket.append((c["_norm"], c["_dt"]))

    print(f"with MRE data: {len(candidates)}")
    print(f"after dedup:   {len(kept)}")


    # Secondary dedup: same (ticker, top resource signature) = same MRE,
    # regardless of date-window. This catches "Maiden MRE" + "Filing of Technical Report"
    # for the same MRE published months apart.
    sig_signatures = {}
    final_kept = []
    for c in kept:
        sig = (c["ticker"],
               round(c.get("headline_oz_au") or 0, 0),
               round(c.get("headline_t_metal") or 0, 0),
               c.get("metal_focus") or "")
        if sig in sig_signatures:
            continue
        sig_signatures[sig] = True
        final_kept.append(c)
    kept = final_kept
    print(f"after signature dedup: {len(kept)}")

    for c in kept:
        con.execute(
            "INSERT INTO resource_estimates("
            "event_id, ticker, project, summary, headline_oz_au, headline_t_metal, metal_focus,"
            "raw_headline, published_at, n_categories, mre_type, categories_json"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (c["event_id"], c["ticker"], c["project"], c["summary"],
             c["headline_oz_au"], c["headline_t_metal"], c["metal_focus"],
             c["raw_headline"], c["published_at"], c["n_categories"],
             c["mre_type"], c["categories_json"]),
        )
    con.commit()
    print(f"inserted: {len(kept)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
