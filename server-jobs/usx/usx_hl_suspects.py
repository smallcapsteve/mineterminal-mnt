#!/usr/bin/env python3
"""usx_hl_suspects.py - READ-ONLY (2026-11-13, Justin: headline corrections "After the close today", "Fix in one pass,
send the list"). Lists suspect headlines among the US history releases posted overnight (HMY, GFI, SQM, BVN, AU) and a
proposed headline taken from the release text by rules. Opens MNT's database read-only; writes the list to
/var/tmp/usx-sens/hist/hl_suspects.tsv. usage: usx_hl_suspects.py [--since 2026-11-12T23:00] [--all]"""
import sys, re, json, sqlite3, html
sys.dont_write_bytecode = True
DB = '/opt/mnt/app/portal/portal.db'
OUT = '/var/tmp/usx-sens/hist/hl_suspects.tsv'
TK = ['HMY.US', 'GFI.US', 'SQM.US', 'BVN.US', 'AU.US']
NAMES = {'HMY.US': r'harmony', 'GFI.US': r'gold fields', 'SQM.US': r'sqm|sociedad qu[ií]mica', 'BVN.US': r'buenaventura', 'AU.US': r'anglogold'}
BOIL = re.compile(r'(?i)(incorporated in|registration (?:number|no)|reg\.? no|share code|isin\b|jse\b|nyse\b|a2x|lei\b|bond code|issuer code|\("?(?:the )?company"?\)|^\(|\(\s*["“][^"”]+["”]\s*(?:or|and)|'
                  r'commission file|form 6-k|form 20-f|report of foreign|pursuant to rule|securities exchange act|exhibit\s*\d|signatures?\b|^page \d|'
                  r'www\.|https?://|tel\b|telephone|\+\d{2}|p\.?o\.? box|registered office|johannesburg, |santiago, |lima, |^for immediate release|^press release$|^news release$|'
                  r'^media release$|^stock exchange news|^sens\b|^announcement$|^\d{1,2} \w+ \d{4}$|^\w+ \d{1,2}, \d{4}$|^date:|^dated)')


def why(h, tk):
    h = (h or '').strip(); w = []
    if len(h) < 18: w.append('too short')
    if len(h) > 220: w.append('too long')
    if BOIL.search(h): w.append('boilerplate')
    if re.fullmatch(r'[\W\d_]+', h or 'x'): w.append('no words')
    if re.fullmatch(r'(?i)(%s)[\w .,()&-]{0,40}(limited|ltd|s\.?a\.?a?|inc\.?|plc|corporation)?\.?' % NAMES[tk], h): w.append('company name only')
    if re.search(r'(?i)^(re:|subject:|to:)', h): w.append('letter header')
    return w


def lines(body):
    b = html.unescape(re.sub(r'<[^>]+>', '\n', body or ''))
    for ln in re.split(r'\n|\r|(?<=[a-z\)])\s{3,}(?=[A-Z])', b):
        ln = re.sub(r'\s+', ' ', ln).strip(' -*|')
        if ln: yield ln


def propose(body, tk):
    for i, ln in enumerate(lines(body)):
        if i > 60: break
        if 18 <= len(ln) <= 200 and not why(ln, tk) and not re.search(r'(?i)^(harmony|gold fields|anglogold|buenaventura|sqm)\b.{0,6}(is|has|today|announced|reports?|\(|,)', ln) \
           and len(re.findall(r'[A-Za-z]{3,}', ln)) >= 3 and not re.search(r'[.;:]$', ln) and not re.search(r'(?i)\b(dear|shareholders are|notice is hereby)\b', ln):
            return ln
    return ''


def main():
    since = sys.argv[sys.argv.index('--since') + 1] if '--since' in sys.argv else '2026-11-12T23:00'
    c = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
    q = 'select event_id, ticker, published_at, raw_headline, raw_body, slug, review_status, source_url from events where ticker in (%s) and ingested_at >= ? and review_status in ("auto_approved","approved")' % ','.join('?' * len(TK))
    rows = c.execute(q, TK + [since]).fetchall()
    seen = {}
    for r in rows:
        seen.setdefault((r[1], (r[3] or '').strip().lower()), []).append(r[0])
    out = []
    for eid, tk, pub, h, body, slug, st, url in rows:
        w = why(h, tk)
        if len(seen[(tk, (h or '').strip().lower())]) > 1: w.append('same headline as %d other releases' % (len(seen[(tk, (h or '').strip().lower())]) - 1))
        if w or '--all' in sys.argv:
            out.append((tk, pub[:10], eid, '; '.join(w), (h or '').replace('\t', ' ')[:200], propose(body, tk).replace('\t', ' '), slug, url))
    out.sort()
    with open(OUT, 'w') as fh:
        fh.write('ticker\tdate\tevent_id\twhy\theadline\tproposed\tslug\turl\n')
        for o in out: fh.write('\t'.join(o) + '\n')
    per = {}
    for o in out: per[o[0]] = per.get(o[0], 0) + 1
    tot = {}
    for r in rows: tot[r[1]] = tot.get(r[1], 0) + 1
    print('posted since %s: %s' % (since, json.dumps(tot)))
    print('suspect: %d %s | with a proposed headline: %d' % (len(out), json.dumps(per), sum(1 for o in out if o[5])))
    for o in out:
        print('%s|%s|%s|%s || %s' % (o[0], o[1], o[3][:40], o[4][:110], o[5][:110]))


if __name__ == '__main__':
    main()
