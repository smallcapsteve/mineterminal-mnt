"""financing_backfill.py — create schema + extract + match across all events.

Pass 1: extract per-event fields, write financing_events rows.
Pass 2: group events into financing lifecycles (announcement -> closes).
Pass 3: aggregate into financings table.

Match heuristic for grouping:
  - Announcements seed new financing rows (ticker, announcement_date,
    extracted fields).
  - For each non-announcement event with a ref_date, find an announcement
    on the same ticker within ±5 days of any ref_date — attach to that.
  - For non-announcement events without ref_dates, attach to the most
    recent prior announcement on same ticker within 180 days, IF roles
    are compatible AND gross/unit_price are similar (or missing).
  - Orphans (no announcement match) become standalone financing rows.
"""
import os, sys, sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, "/opt/mnt/app")
sys.path.insert(0, "/opt/mnt/app/portal")

from financing_extract import extract  # type: ignore

DB = "/opt/mnt/app/portal/portal.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS financings (
    financing_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker            TEXT NOT NULL,
    announced_at      TEXT,
    last_update_at    TEXT,
    kind              TEXT,
    status            TEXT,             -- announced|upsized|tranche_closed|closed|terminated|amended
    gross_announced   REAL,
    gross_closed      REAL,
    unit_price        REAL,
    unit_comp         TEXT,
    warrant_strike    REAL,
    warrant_term_months INTEGER,
    n_tranches        INTEGER DEFAULT 0,
    n_events          INTEGER DEFAULT 0,
    seed_event_id     TEXT
);
CREATE INDEX IF NOT EXISTS ix_financings_ticker ON financings(ticker);
CREATE INDEX IF NOT EXISTS ix_financings_status ON financings(status);
CREATE INDEX IF NOT EXISTS ix_financings_announced_at ON financings(announced_at);

CREATE TABLE IF NOT EXISTS financing_events (
    event_id          TEXT PRIMARY KEY,
    financing_id      INTEGER,
    ticker            TEXT NOT NULL,
    role              TEXT,             -- announcement|upsize|tranche_close|final_close|amendment|terminated|mention
    tranche_label     TEXT,
    kind              TEXT,
    gross_total       REAL,
    unit_count        INTEGER,
    unit_price        REAL,
    unit_comp         TEXT,
    warrant_strike    REAL,
    warrant_term_months INTEGER,
    ref_dates         TEXT,             -- pipe-delimited
    event_date        TEXT,             -- copied from events.published_at for fast joins
    raw_headline      TEXT,
    FOREIGN KEY (financing_id) REFERENCES financings(financing_id)
);
CREATE INDEX IF NOT EXISTS ix_finev_ticker ON financing_events(ticker);
CREATE INDEX IF NOT EXISTS ix_finev_event_date ON financing_events(event_date);
CREATE INDEX IF NOT EXISTS ix_finev_role ON financing_events(role);
"""


def init_schema(con):
    con.executescript(SCHEMA)
    con.commit()


def run_pass1(con):
    """Extract per-event into financing_events. Idempotent: re-runs replace existing rows."""
    con.execute("DELETE FROM financing_events")
    con.commit()
    rows = list(con.execute(
        "SELECT event_id, ticker, raw_headline, raw_body, published_at "
        "FROM events WHERE categories LIKE ? AND review_status='auto_approved'",
        ("%Financings%",),
    ))
    print(f"[pass1] processing {len(rows)} financing events")
    inserted = 0
    cur = con.cursor()
    for r in rows:
        ev = dict(r)
        try:
            x = extract(ev)
        except Exception as e:
            print(f"  extract error {ev['event_id']}: {e}", file=sys.stderr)
            continue
        ref_str = "|".join(x.get("ref_dates") or [])
        cur.execute(
            "INSERT INTO financing_events("
            " event_id, financing_id, ticker, role, tranche_label, kind,"
            " gross_total, unit_count, unit_price, unit_comp,"
            " warrant_strike, warrant_term_months, ref_dates,"
            " event_date, raw_headline"
            ") VALUES (?,NULL,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                ev["event_id"], ev["ticker"], x.get("role"),
                x.get("tranche_label"), x.get("kind"),
                x.get("gross_total"), x.get("unit_count"),
                x.get("unit_price"), x.get("unit_comp"),
                x.get("warrant_strike"), x.get("warrant_term_months"),
                ref_str, (ev.get("published_at") or "")[:10],
                (ev.get("raw_headline") or "")[:500],
            ),
        )
        inserted += 1
    con.commit()
    print(f"[pass1] inserted {inserted} financing_events")


def run_pass2_group(con):
    """Group financing_events into financings lifecycles."""
    con.execute("DELETE FROM financings")
    con.execute("UPDATE financing_events SET financing_id=NULL")
    con.commit()

    # Pull announcements first, then attach others
    rows_a = list(con.execute(
        "SELECT * FROM financing_events WHERE role='announcement' ORDER BY ticker, event_date"
    ))
    rows_o = list(con.execute(
        "SELECT * FROM financing_events WHERE role!='announcement' ORDER BY ticker, event_date"
    ))
    print(f"[pass2] {len(rows_a)} announcements, {len(rows_o)} non-announcement events")

    cur = con.cursor()
    # Seed financings from announcements
    ann_ids: dict[str, list[int]] = {}  # ticker -> list of (financing_id, event_date, gross)
    for a in rows_a:
        cur.execute(
            "INSERT INTO financings("
            " ticker, announced_at, last_update_at, kind, status,"
            " gross_announced, unit_price, unit_comp, warrant_strike,"
            " warrant_term_months, n_events, seed_event_id"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                a["ticker"], a["event_date"], a["event_date"], a["kind"],
                "announced",
                a["gross_total"], a["unit_price"], a["unit_comp"],
                a["warrant_strike"], a["warrant_term_months"], 1,
                a["event_id"],
            ),
        )
        fid = cur.lastrowid
        cur.execute("UPDATE financing_events SET financing_id=? WHERE event_id=?",
                    (fid, a["event_id"]))
        ann_ids.setdefault(a["ticker"], []).append({
            "financing_id": fid,
            "event_date": a["event_date"],
            "gross": a["gross_total"],
            "unit_price": a["unit_price"],
        })

    # Attach non-announcement events
    matched = orphan = 0
    for o in rows_o:
        candidates = ann_ids.get(o["ticker"], [])
        chosen = None
        # 1) ref-date match
        ref_dates = (o["ref_dates"] or "").split("|") if o["ref_dates"] else []
        if ref_dates and candidates:
            for ref in ref_dates:
                for c in candidates:
                    if not c["event_date"] or not ref:
                        continue
                    try:
                        d_ref = datetime.strptime(ref, "%Y-%m-%d")
                        d_ann = datetime.strptime(c["event_date"], "%Y-%m-%d")
                        if abs((d_ref - d_ann).days) <= 5:
                            chosen = c
                            break
                    except ValueError:
                        continue
                if chosen:
                    break
        # 2) Recency + amount match
        if not chosen and candidates:
            try:
                d_ev = datetime.strptime(o["event_date"], "%Y-%m-%d")
            except (ValueError, TypeError):
                d_ev = None
            if d_ev:
                best = None
                for c in candidates:
                    try:
                        d_a = datetime.strptime(c["event_date"], "%Y-%m-%d")
                    except (ValueError, TypeError):
                        continue
                    delta = (d_ev - d_a).days
                    if delta < 0 or delta > 180:
                        continue
                    # gross / unit_price compat
                    score = 0
                    if o["gross_total"] and c["gross"]:
                        ratio = abs(o["gross_total"] - c["gross"]) / max(c["gross"], 1)
                        if ratio < 0.5:
                            score += 2
                    if o["unit_price"] and c["unit_price"]:
                        if abs(o["unit_price"] - c["unit_price"]) < 0.01:
                            score += 2
                    # Always prefer most recent
                    score += max(0, 10 - delta // 30)
                    if best is None or score > best[1]:
                        best = (c, score)
                if best:
                    chosen = best[0]

        if chosen:
            fid = chosen["financing_id"]
            cur.execute("UPDATE financing_events SET financing_id=? WHERE event_id=?",
                        (fid, o["event_id"]))
            # update lifecycle row
            new_status = {
                "upsize": "upsized",
                "tranche_close": "tranche_closed",
                "final_close": "closed",
                "amendment": "amended",
                "terminated": "terminated",
            }.get(o["role"], None)
            patch = ["last_update_at=?", "n_events = n_events + 1"]
            args = [o["event_date"]]
            if new_status:
                patch.append("status=?")
                args.append(new_status)
            if o["role"] in ("tranche_close", "final_close"):
                patch.append("n_tranches = n_tranches + 1")
                if o["gross_total"]:
                    patch.append("gross_closed = COALESCE(gross_closed, 0) + ?")
                    args.append(o["gross_total"])
            if o["role"] == "upsize" and o["gross_total"]:
                patch.append("gross_announced = ?")
                args.append(o["gross_total"])
            if o["role"] == "upsize" and o["kind"]:
                patch.append("kind = ?")
                args.append(o["kind"])
            args.append(fid)
            cur.execute(
                f"UPDATE financings SET {', '.join(patch)} WHERE financing_id=?",
                args,
            )
            matched += 1
        else:
            # Orphan: create standalone financing row
            new_status = {
                "upsize": "upsized",
                "tranche_close": "tranche_closed",
                "final_close": "closed",
                "amendment": "amended",
                "terminated": "terminated",
            }.get(o["role"], "mention")
            cur.execute(
                "INSERT INTO financings("
                " ticker, announced_at, last_update_at, kind, status,"
                " gross_announced, gross_closed, unit_price, unit_comp, warrant_strike,"
                " warrant_term_months, n_tranches, n_events, seed_event_id"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    o["ticker"], o["event_date"], o["event_date"], o["kind"],
                    new_status,
                    o["gross_total"] if o["role"] == "upsize" else None,
                    o["gross_total"] if o["role"] in ("final_close", "tranche_close") else None,
                    o["unit_price"], o["unit_comp"],
                    o["warrant_strike"], o["warrant_term_months"],
                    1 if o["role"] in ("final_close", "tranche_close") else 0,
                    1, o["event_id"],
                ),
            )
            fid = cur.lastrowid
            cur.execute("UPDATE financing_events SET financing_id=? WHERE event_id=?",
                        (fid, o["event_id"]))
            orphan += 1
    con.commit()
    print(f"[pass2] matched={matched} orphan={orphan}")


def report(con):
    print()
    print("=== FINANCINGS SUMMARY ===")
    n = con.execute("SELECT COUNT(*) FROM financings").fetchone()[0]
    print(f"financings rows: {n}")
    print("by status:")
    for r in con.execute(
        "SELECT status, COUNT(*) FROM financings GROUP BY status ORDER BY 2 DESC"
    ):
        print(f"  {r[0]:<20s} {r[1]}")
    print("\nby kind:")
    for r in con.execute(
        "SELECT kind, COUNT(*) FROM financings GROUP BY kind ORDER BY 2 DESC LIMIT 10"
    ):
        print(f"  {r[0]:<25s} {r[1]}")
    print("\ntop 5 most-recently-updated:")
    for r in con.execute(
        "SELECT ticker, status, gross_announced, gross_closed, unit_price, "
        " unit_comp, warrant_strike, warrant_term_months, last_update_at "
        "FROM financings ORDER BY last_update_at DESC LIMIT 5"
    ):
        print(" ", dict(r) if hasattr(r, "keys") else r)


def main():
    con = sqlite3.connect(DB); con.execute("PRAGMA busy_timeout = 30000")
    con.row_factory = sqlite3.Row
    init_schema(con)
    run_pass1(con)
    run_pass2_group(con)
    report(con)
    con.close()


if __name__ == "__main__":
    main()
