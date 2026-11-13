#!/usr/bin/env python3
"""usx_hl_deep.py - READ-ONLY (2026-11-13, Justin: "Dig deeper on the 50"). For the given row numbers of the sorted 'leave'
rows of hl_fix_plan3.tsv, prints the current headline, the source address, the stored text sizes, and the release's text
past the letterhead (from raw_body, or from raw_html when the body is short), so a headline can be written by reading it.
usage: usx_hl_deep.py IDX[,IDX...] [CHARS]"""
import sys, csv, re, sqlite3, html
sys.dont_write_bytecode = True
DB = '/opt/mnt/app/portal/portal.db'
PLAN = '/var/tmp/usx-sens/hist/hl_fix_plan3.tsv'
want = [int(x) for x in sys.argv[1].split(',')]
cap = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
rows = [r for r in csv.DictReader(open(PLAN), delimiter='\t', quoting=csv.QUOTE_NONE) if r['action'] == 'leave']
rows.sort(key=lambda r: (r['ticker'], r['date']))
c = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
SKIP = re.compile(r'(?i)^(sandown|sandton|2196|150 helen road|registration number|reg\. no|incorporated in|isin|jse share code|nyse share code|share code|\(?incorporated|website|tel\b|fax\b|telephone|johannesburg,? south africa$|page \d|form 6-k|commission file|indicate by check|yes\s*no|\[?x\]?$)')
def lines(t):
    t = html.unescape(re.sub(r'(?i)<br\s*/?>|</(?:p|div|tr|h\d|li|td)>', '\n', t or ''))
    t = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', t)
    t = re.sub(r'<[^>]+>', ' ', t)
    out = [re.sub(r'\s+', ' ', x).strip() for x in re.split(r'[\n\r]+', t)]
    return [x for x in out if len(x) > 2 and not SKIP.match(x)]
for i in want:
    r = rows[i - 1]
    got = c.execute('select raw_headline, raw_body, raw_html, source_url, raw_excerpt from events where event_id=?', (r['event_id'],)).fetchone()
    if not got:
        print('#%d missing' % i); continue
    h, body, rh, url, ex = got
    ls = lines(body)
    src = 'body'
    if sum(len(x) for x in ls) < 400 and rh:
        ls2 = lines(rh)
        if sum(len(x) for x in ls2) > sum(len(x) for x in ls):
            ls, src = ls2, 'html'
    print('#%d %s %s | body %d html %d | %s' % (i, r['ticker'], r['date'], len(body or ''), len(rh or ''), url or ''))
    print('  H: ' + ' '.join((h or '').split())[:200])
    if ex: print('  X: ' + ' '.join(ex.split())[:300])
    print('  %s: ' % src[0].upper() + ' | '.join(x[:180] for x in ls)[:cap])
