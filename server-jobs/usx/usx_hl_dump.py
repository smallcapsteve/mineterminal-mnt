#!/usr/bin/env python3
"""usx_hl_dump.py - READ-ONLY (2026-11-13, Justin: remaining headlines "Read them one by one"). Prints, for the US history
releases the rules left alone (plan rows marked 'leave' in hl_fix_plan3.tsv), the current headline and the first lines of
the release, in parts, so each headline can be written by reading the release. usage: usx_hl_dump.py PART [PER_PART]"""
import sys, csv, re, sqlite3, html
sys.dont_write_bytecode = True
DB = '/opt/mnt/app/portal/portal.db'
PLAN = '/var/tmp/usx-sens/hist/hl_fix_plan3.tsv'
part = int(sys.argv[1]); per = int(sys.argv[2]) if len(sys.argv) > 2 else 40
rows = [r for r in csv.DictReader(open(PLAN), delimiter='\t', quoting=csv.QUOTE_NONE) if r['action'] == 'leave']
rows.sort(key=lambda r: (r['ticker'], r['date']))
c = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
print('leave rows %d | part %d of %d' % (len(rows), part, (len(rows) + per - 1) // per))
for i, r in enumerate(rows[(part - 1) * per:part * per], (part - 1) * per + 1):
    got = c.execute('select raw_headline, raw_body from events where event_id=?', (r['event_id'],)).fetchone()
    if not got:
        continue
    h, body = got
    b = html.unescape(re.sub(r'(?i)<br\s*/?>|</(?:p|div|tr|h\d|li|td)>', '\n', body or ''))
    b = re.sub(r'<[^>]+>', ' ', b)
    ls = [re.sub(r'\s+', ' ', x).strip() for x in re.split(r'[\n\r]+', b)]
    ls = [x for x in ls if len(x) > 2][:22]
    print('#%d %s %s %s\n  H: %s' % (i, r['ticker'], r['date'], r['event_id'], ' '.join((h or '').split())[:200]))
    print('  B: ' + ' | '.join(x[:110] for x in ls)[:1500])
