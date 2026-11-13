#!/usr/bin/env python3
"""usx_hl_manual.py - USX_HLFIX_V2 (2026-11-13, Justin: remaining headlines "Read them one by one"). Applies headlines
written by reading each release (usx_hl_manual.tsv: row number in the sorted 'leave' rows of hl_fix_plan3.tsv, the start
of the current headline as a guard, the new headline). Headline only; a row is changed only if its stored headline still
starts with the guard. Run as mnt. Backup /var/tmp/usx-sens/hist/hl_fix_backup_<UTC>.json; undo with usx_hl_apply.py --undo.
usage: usx_hl_manual.py TSV [--dry]"""
import sys, csv, json, time, sqlite3
DB = '/opt/mnt/app/portal/portal.db'
PLAN = '/var/tmp/usx-sens/hist/hl_fix_plan3.tsv'


def norm(s):
    return ' '.join((s or '').split()).lower()


def main():
    man = [l.rstrip('\n').split('\t') for l in open(sys.argv[1], encoding='utf-8') if l.strip()]
    rows = [r for r in csv.DictReader(open(PLAN), delimiter='\t', quoting=csv.QUOTE_NONE) if r['action'] == 'leave']
    rows.sort(key=lambda r: (r['ticker'], r['date']))
    c = sqlite3.connect(DB, timeout=60); c.execute('pragma busy_timeout=60000')
    done, skipped = [], []
    for idx, guard, new in man:
        r = rows[int(idx) - 1]
        cur = c.execute('select raw_headline from events where event_id=?', (r['event_id'],)).fetchone()
        if not cur or not norm(cur[0]).startswith(norm(guard)):
            skipped.append(idx); continue
        if '--dry' not in sys.argv:
            c.execute('update events set raw_headline=? where event_id=?', (new.strip(), r['event_id']))
        done.append({'event_id': r['event_id'], 'ticker': r['ticker'], 'old': cur[0], 'new': new.strip(), 'row': idx})
    if '--dry' not in sys.argv:
        c.commit()
        bk = '/var/tmp/usx-sens/hist/hl_fix_backup_%s.json' % time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
        json.dump(done, open(bk, 'w'), indent=0)
        print('backup', bk)
    per = {}
    for d in done: per[d['ticker']] = per.get(d['ticker'], 0) + 1
    print('%s %d %s | skipped (guard did not match) %d: %s' % ('would change' if '--dry' in sys.argv else 'changed', len(done), json.dumps(per), len(skipped), ','.join(skipped)))


if __name__ == '__main__':
    main()
