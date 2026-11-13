#!/usr/bin/env python3
"""usx_hl_apply.py - USX_HLFIX_V1 (2026-11-13, Justin: "After the close today", "Fix in one pass, send the list").
Applies the 'apply' rows of /var/tmp/usx-sens/hist/hl_fix_plan3.tsv (or --plan TSV) to MNT: changes raw_headline only (slug, dates,
body untouched), and only where the stored headline still equals the planned old headline. Run as the mnt user.
Backup of every changed row's old headline: /var/tmp/usx-sens/hist/hl_fix_backup_<UTC>.json. Undo: usx_hl_apply.py --undo <backup>.
usage: usx_hl_apply.py [--dry] [--plan TSV] | --undo FILE"""
import sys, json, time, sqlite3, csv
DB = '/opt/mnt/app/portal/portal.db'
PLAN = sys.argv[sys.argv.index('--plan') + 1] if '--plan' in sys.argv else '/var/tmp/usx-sens/hist/hl_fix_plan3.tsv'
H = '/var/tmp/usx-sens/hist/'


def connect():
    c = sqlite3.connect(DB, timeout=60)
    c.execute('pragma busy_timeout=60000')
    return c


def main():
    c = connect()
    if '--undo' in sys.argv:
        bk = json.load(open(sys.argv[sys.argv.index('--undo') + 1]))
        n = 0
        for r in bk:
            n += c.execute('update events set raw_headline=? where event_id=? and raw_headline=?', (r['old'], r['event_id'], r['new'])).rowcount
        c.commit(); print('undone %d of %d' % (n, len(bk))); return
    rows = list(csv.DictReader(open(PLAN), delimiter='\t', quoting=csv.QUOTE_NONE))
    todo = [r for r in rows if r['action'] == 'apply' and r['new_headline'].strip() and r['new_headline'] != r['headline']]
    done, skipped = [], []
    for r in todo:
        cur = c.execute('select raw_headline from events where event_id=?', (r['event_id'],)).fetchone()
        if not cur or ' '.join((cur[0] or '').split()) != ' '.join(r['headline'].split()):
            skipped.append(r['event_id']); continue
        if '--dry' not in sys.argv:
            for k in range(5):
                try:
                    c.execute('update events set raw_headline=? where event_id=?', (r['new_headline'].strip(), r['event_id'])); break
                except sqlite3.OperationalError as e:
                    if 'locked' not in str(e): raise
                    time.sleep(5)
        done.append({'event_id': r['event_id'], 'ticker': r['ticker'], 'old': cur[0], 'new': r['new_headline'].strip()})
    if '--dry' not in sys.argv:
        c.commit()
        bk = H + 'hl_fix_backup_%s.json' % time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
        json.dump(done, open(bk, 'w'), indent=0)
        print('backup', bk)
    per = {}
    for d in done: per[d['ticker']] = per.get(d['ticker'], 0) + 1
    print('%s %d headlines %s | skipped (headline changed since the plan) %d | left as is %d' % ('would change' if '--dry' in sys.argv else 'changed', len(done), json.dumps(per), len(skipped), sum(1 for r in rows if r['action'] == 'leave')))


if __name__ == '__main__':
    main()
