"""SWEEP1112_RESMARK (Justin, 2026-11-12: "Mark at the source"). Marks on MNT's resource rows, worked out from what MNT
already holds, so Mine Terminal Pro's $/oz screener and Leaderboards can skip or merge rows with one check each:

  third_party          the release says another listed company prepared the estimate (Bullfrog Gold quoting AngloGold
                       Ashanti's deposits): that company's name, else None. A row with the same category, tonnes and
                       grades as a marked row of the same company takes the mark too (the figures quoted again without
                       the footnote).
  project_hint         the company's project this estimate belongs to when the row itself does not say so, else None:
                       a row with no project and no deposit whose headline names one of the company's projects ("Aris Mining Expands
                       High-Grade Segovia Reserve and Resource Estimates" -> Segovia), or "<deposit> Deposit at
                       <project>" in the headline (Goldstorm -> Treaty Creek)
  project_hint_source  'headline' or 'parent'

The row's own `project` is never changed: a hint is a reason to check for a double count, not a fact.
portal/resources_api.py calls get(conn, names) -> {(event_id, ordinal): (third_party, project_hint, project_hint_source)}.
"""
import json
import os
import re
import threading
import time

QP_PATH = '/var/lib/mnt-c19/qp.json'
_SUFFIX = {'inc', 'incorporated', 'corp', 'corporation', 'ltd', 'limited', 'plc', 'co', 'company', 'sa', 'nv', 'ag', 'llc',
           'the', 'pty', 'sab', 'de', 'cv', 'nl', 'asa', 'ab'}
# words a company's name may carry or drop ("Agnico Eagle" / "Agnico Eagle Mines"); "G Mining" is not "G Mining Ventures"
_DESCRIPTOR = {'mines', 'mining', 'gold', 'silver', 'copper', 'resources', 'minerals', 'metals', 'royalties', 'royalty',
               'group', 'international', 'holdings', 'exploration', 'energy', 'uranium', 'lithium', 'nickel'}
_GENERIC = {'project', 'property', 'deposit', 'mine', 'gold', 'silver', 'copper', 'zinc', 'lithium', 'uranium', 'nickel',
            'mineral', 'resource', 'resources', 'reserve', 'reserves', 'north', 'south', 'east', 'west', 'main', 'central',
            'total', 'open', 'underground', 'pit', 'zone', 'area', 'company', 'canada', 'mining', 'mines', 'metals',
            'update', 'updated', 'estimate', 'technical', 'report', 'global', 'combined', 'other', 'certain'}
# Checked by hand: the release quotes another company's estimate and c19_qp holds no firm for the row.
HAND_THIRD = {
    # GGR 2025-12-08: "(1) Measured and indicated resource of 11.1 million tonnes grading 11.4 g/t gold. Gold Fields
    # January 18, 2024 news release" (the Windfall deposit next door; Golden Goose showed 4.07 Moz)
    '88958e89471c694d947c30d6baf4a5c9f74b487a': 'Gold Fields',
}
_PARENT = r' %s (?:deposits?|zones?|areas?|targets?|discovery) (?:at|on|of|within|in) (?:its )?%s '


def norm(s):
    return ' '.join(x for x in re.sub(r'[^a-z0-9 ]+', ' ', (s or '').lower()).split() if x not in _SUFFIX)


def bare(t):
    return (t or '').strip().upper().split('.')[0]


def _same(a, b):
    """Two normalised names are one company: equal, or the longer is the shorter (2+ words) plus descriptor words."""
    if not a or not b:
        return False
    if a == b:
        return True
    s, l = (a, b) if len(a) <= len(b) else (b, a)
    return len(s.split()) >= 2 and l.startswith(s + ' ') and all(w in _DESCRIPTOR for w in l[len(s):].split())


def marks(rows, names, qp):
    """rows: mappings with event_id, ordinal, ticker, project, deposit, category, tonnes, grades_json, raw_headline.
    names: {ticker: company name}. qp: {"event|ordinal": {"fs": [firms]}} (c19_qp's file)."""
    co, own = {}, {}
    for t, nm in names.items():
        n = norm(nm)
        if n and n != norm(bare(t)):
            co.setdefault(n, set()).add(bare(t))
            own.setdefault(bare(t), set()).add(n)
    by_first = {}
    for n in co:
        by_first.setdefault(n.split()[0], []).append(n)
    projects = {}
    for r in rows:
        p = (r['project'] or '').strip()
        pn = norm(p)
        t = bare(r['ticker'])
        if p and len(pn) >= 4 and pn not in _GENERIC and not pn.isdigit() \
                and not any(o == pn or o.startswith(pn + ' ') for o in own.get(t, ())):   # a "project" that is the company's name
            projects.setdefault(t, {})[pn] = p
    third, sigs = {}, {}
    sig = lambda r: (bare(r['ticker']), r['category'], round(r['tonnes'] or 0), r['grades_json'] or '')
    for r in rows:
        t = bare(r['ticker'])
        if r['event_id'] in HAND_THIRD:
            third[(r['event_id'], r['ordinal'])] = HAND_THIRD[r['event_id']]
            if r['tonnes']:
                sigs[sig(r)] = HAND_THIRD[r['event_id']]
            continue
        for f in (qp.get('%s|%s' % (r['event_id'], r['ordinal'])) or {}).get('fs') or []:
            fn = norm(f)
            if not fn or any(_same(fn, o) for o in own.get(t, ())):
                continue
            if any(_same(fn, n) and co[n] != {t} for n in by_first.get(fn.split()[0], [])):
                third[(r['event_id'], r['ordinal'])] = f
                if r['tonnes']:
                    sigs[sig(r)] = f
                break
    out = {}
    for r in rows:
        k = (r['event_id'], r['ordinal'])
        t = bare(r['ticker'])
        tp = third.get(k) or (sigs.get(sig(r)) if r['tonnes'] else None)
        p = (r['project'] or '').strip()
        hint = src = None
        known = projects.get(t)
        if known:
            h = ' ' + norm(r['raw_headline']) + ' '
            if not p and not (r['deposit'] or '').strip():   # a named deposit is its own thing, whatever the headline mentions (Silverco: Cusi)
                found = sorted((pn for pn in known if ' ' + pn + ' ' in h), key=len, reverse=True)
                if found:
                    hint, src = known[found[0]], 'headline'
            elif p:
                pn = norm(p)
                if pn and ' ' + pn + ' ' in h:
                    for qn, qname in known.items():
                        if qn != pn and pn not in qn and qn not in pn and ' ' + qn + ' ' in h \
                                and re.search(_PARENT % (re.escape(pn), re.escape(qn)), h):
                            hint, src = qname, 'parent'
                            break
        out[k] = (tp, hint, src)
    return out


_C = {}   # database file -> {'key', 'at', 'marks'}
_LOCK = threading.Lock()


def _build(conn, names):
    try:
        with open(QP_PATH) as fh:
            qp = json.load(fh).get('rows') or {}
    except Exception:
        qp = {}
    rows = conn.execute('SELECT event_id, ordinal, ticker, project, deposit, category, tonnes, grades_json, raw_headline '
                        'FROM resource_estimates WHERE category IS NOT NULL').fetchall()
    return marks(rows, names, qp)


def get(conn, names, ttl=600.0):
    """Marks for the whole table, worked out again when the table or c19_qp's file changes (checked at most every `ttl` s).
    A database with no file (a test) is never cached."""
    path = conn.execute('PRAGMA database_list').fetchone()[2]
    if not path:
        return _build(conn, names)
    now = time.monotonic()
    with _LOCK:
        c = _C.setdefault(path, {'key': None, 'at': 0.0, 'marks': {}})
        if c['key'] is not None and now - c['at'] < ttl:
            return c['marks']
        n, mx = conn.execute('SELECT COUNT(*), MAX(res_id) FROM resource_estimates').fetchone()
        try:
            qm = os.stat(QP_PATH).st_mtime
        except OSError:
            qm = None
        key = (n, mx, qm, len(names))
        if key != c['key']:
            c['marks'] = _build(conn, names)
            c['key'] = key
        c['at'] = now
        return c['marks']
