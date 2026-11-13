#!/usr/bin/env python3
"""usx_hl_exclude.py - (2026-11-13) marks plan rows I checked and judged wrong as 'leave' before usx_hl_apply.py runs:
every SQM 'not a title' pick (its picks are sentences from the release body) and seven other 'not a title' picks.
Then, after the apply, --list prints the changed headlines from the newest backup."""
import sys, csv, json, glob, os
PLAN = '/var/tmp/usx-sens/hist/hl_fix_plan3.tsv'
BAD = {('AU.US', '2011-02-17'), ('AU.US', '2016-02-16'), ('AU.US', '2020-09-28'), ('AU.US', '2021-10-19'), ('BVN.US', '2020-03-17'), ('GFI.US', '2010-09-27'), ('GFI.US', '2018-08-28')}
if '--list' in sys.argv:
    bk = sorted(glob.glob('/var/tmp/usx-sens/hist/hl_fix_backup_*.json'))[-1]
    rows = json.load(open(bk))
    with open('/var/tmp/usx-sens/hist/hl_fixed_list.tsv', 'w') as fh:
        fh.write('ticker\tevent_id\told\tnew\n')
        for r in rows:
            fh.write('%s\t%s\t%s\t%s\n' % (r['ticker'], r['event_id'], r['old'].replace('\t', ' '), r['new']))
    print('backup', bk, len(rows))
    for r in rows:
        print('FIXED|%s|%s|%s' % (r['ticker'], ' '.join(r['old'].split())[:150], r['new'][:150]))
    sys.exit()
rows = list(csv.DictReader(open(PLAN), delimiter='\t', quoting=csv.QUOTE_NONE))
n = 0
for r in rows:
    if r['action'] == 'apply' and 'not a title' in r['kind'] and (r['ticker'] == 'SQM.US' or (r['ticker'], r['date']) in BAD):
        r['action'] = 'leave'; n += 1
with open(PLAN, 'w') as fh:
    keys = list(rows[0].keys())
    fh.write('\t'.join(keys) + '\n')
    for r in rows:
        fh.write('\t'.join(r[k] for k in keys) + '\n')
print('marked leave: %d | apply now %d' % (n, sum(1 for r in rows if r['action'] == 'apply')))
