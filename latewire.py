"""LATEWIRE_V1 (2026-11-03, Justin: "Late wire copy replaces exchange").
Before this, every wire collector skipped a release when ANY stored copy matched it, including the TMX/CSE exchange
copy (a PDF). So a wire copy that arrived after the exchange copy was dropped, and MNT kept the PDF. The duplicate
guard (portal/dupguard.py, DATEDUP) already replaces an exchange copy with a wire copy inside upsert_event; the
collectors just never got that far. takes_over() says when to let the wire copy through to upsert_event:
  * the matched copy is a visible TMX/CSE copy;
  * the wire copy has real text (>= 800 chars and >= 40% of the exchange copy's length), so a placeholder never
    replaces a full PDF text;
  * the guard itself would replace exactly that copy (find_visible_twin + new_copy_replaces: same release, the wire
    copy dated no more than a day later), and has not already turned this wire copy away.
Anything else, or any error: False, and the collector skips the release as before.
Undo: restore the collectors from the backup (undo.sh); this file is then unused."""
MIN_BODY = 800
MIN_SHARE = 0.4


def takes_over(conn, row, dupe_id, source_name):
    try:
        from portal import dupguard as G
        r = conn.execute("SELECT source_name, review_status, length(COALESCE(raw_body,'')) FROM events WHERE event_id = ?",
                         (dupe_id,)).fetchone()
        if not r or not G.is_exchange(r[0]) or r[1] not in G.VISIBLE:
            return False
        body = row.get("raw_body") or ""
        if len(body) < MIN_BODY or len(body) < MIN_SHARE * (r[2] or 0):
            return False
        new = {"event_id": row.get("event_id") or "", "ticker": row.get("ticker"), "published_at": row.get("published_at"),
               "raw_headline": row.get("raw_headline"), "raw_body": body, "source_name": source_name}
        if new["event_id"] and G.was_removed(conn, new["event_id"]):
            return False
        twin = G.find_visible_twin(conn, new)
        if not twin or twin["event_id"] != dupe_id or not G.new_copy_replaces(new, twin):
            return False
        print("  ^ LATEWIRE_V1 %s %s copy replaces the exchange copy %s: %s"
              % (new["ticker"], source_name, dupe_id[:12], (new["raw_headline"] or "")[:60]), flush=True)
        return True
    except Exception as e:  # noqa: BLE001 - never let this check stop collection
        print("  ! LATEWIRE_V1 check failed (%s: %s); kept as a duplicate" % (type(e).__name__, e), flush=True)
        return False
