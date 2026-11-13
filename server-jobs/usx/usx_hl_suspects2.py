#!/usr/bin/env python3
"""usx_hl_suspects2.py - READ-ONLY (2026-11-13). Narrower suspect-headline rules for the US history releases posted
overnight (HMY, GFI, SQM, BVN, AU), with a rule-made fix for each kind:
  cut short   - headline stops on a dangling word; fix joins the next line of the release
  prefix      - "Press release" / "News Release -" in front; fix removes it
  tail        - place and date (or the company name, or a stray character) stuck on the end; fix removes it
  not a title - an address, directors list, signature, exhibit note or sentence; fix takes the first title-like line
                of the release, or leaves it if none is found
Opens MNT's database read-only. Writes /var/tmp/usx-sens/hist/hl_fix_plan.tsv. usage: usx_hl_suspects2.py [--body]"""
import sys, re, json, sqlite3, html
sys.dont_write_bytecode = True
DB = '/opt/mnt/app/portal/portal.db'
OUT = '/var/tmp/usx-sens/hist/hl_fix_plan.tsv'
TK = ['HMY.US', 'GFI.US', 'SQM.US', 'BVN.US', 'AU.US']
CO = r'(?:harmony(?: gold mining company limited| gold)?|gold fields(?: limited)?|anglogold ashanti(?: limited| holdings plc)?|anglogold|(?:compa[nñ]ia de minas )?buenaventura(?: s\.?a\.?a\.?)?|sqm|sociedad qu[ií]mica y minera de chile(?: s\.?a\.?)?)'
DANGLE = re.compile(r'(?i)(?:\b(?:the|of|for|and|to|on|in|at|with|by|from|ended|six|nine|its|says|announces|annual|african|update on|changes to|issues its|'
                    r'contractor|resolutions|completion|initiate|various|earn|six-month|nine-month|full year|full|a|an|or|regarding|about|its\s+\d{4}|resource and ore)|\bfor\s+\d|&)\s*$')
PREFIX = re.compile(r'(?i)^\s*(?:press release\s*)?(?:news release\s*[-:]\s*|media release\s*[-:]\s*)?')
TAIL = re.compile(r'(?i)\s+(?:(?:johannesburg|lima|santiago|denver|perth|london|accra)\s*[,:]?\s*(?:\w+day,?\s*)?(?:\d{1,2}\s+\w+|\w+\s+\d{1,2},?)\s+\d{4}\s*:?.*'
                  r'|' + CO + r'\.?\s*$|[a-z]$|(?<=appointment\s)1$)')
NOT_TITLE = re.compile(r'(?i)(^corporate affairs|,\s*\d{4}\s*$|^\w(?: \w)+ \w+,|\(chair\)|^directors?\b|sandown|sandton|street|floor|private bag|p\.?o\.? box|'
                       r'^\(|^by:\s*/s/|^/s/|^each of |^in accordance with|^with reference to|^in compliance with|^note on|^lima,|^santiago,|^johannesburg,|^subject:|'
                       r'is pleased to|\bwill be based\b|^the presentation|^mr |^ms |^dr |filing the following exhibits|registration nos|\(\*\)|^announcement$|'
                       r'^press release\s*(?:news release\s*-?)?\s*$|^' + CO + r'\.?\s*$|operations and assets in south africa|from operating activities$|\|\s*$|advises that)')
BAD_LINE = re.compile(r'(?i)(incorporated in|registration|share code|isin|jse|nyse|a2x|\blei\b|bond code|issuer code|company"?\)|"the company"|commission file|form 6-k|'
                      r'form 20-f|report of foreign|pursuant to|exchange act|exhibit|signature|^page \d|www\.|https?://|\btel\b|telephone|\+\d{2}|box|registered office|'
                      r'^directors?\b|directors?\s*:|\(chair\)|chief executive|chief financial|sandton|sandown|street|floor|^issued by|^\(|/s/|^note on|^lima|^santiago|^johannesburg|'
                      r'^for immediate release|^press release|^news release|^media release|^date|^dated|^\d{1,2} \w+ \d{4}$|^\w+ \d{1,2}, \d{4}$|^' + CO + r'\.?$|'
                      r'^(?:dear|notice is hereby|shareholders are)|^contact|^investor|^media|^enquiries|^sponsor|^jse sponsor|nyx code|swx code)')


def lines(body):
    b = html.unescape(re.sub(r'(?i)<br\s*/?>|</(?:p|div|tr|h\d|li|td)>', '\n', body or ''))
    b = re.sub(r'<[^>]+>', ' ', b)
    out = []
    for ln in re.split(r'[\n\r]+', b):
        ln = re.sub(r'\s+', ' ', ln).strip(' -*|\\')
        if ln: out.append(ln)
    return out


def title_like(ln):
    if not (12 <= len(ln) <= 160) or BAD_LINE.search(ln) or NOT_TITLE.search(ln) or re.search(r'[.,;:]$', ln):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'&\-]*", ln)
    if len(words) < 3:
        return False
    caps = sum(1 for w in words if w[0].isupper() or w.lower() in ('of', 'and', 'the', 'for', 'to', 'in', 'on', 'at', 'a', 'an', 'with', 'by', 's'))
    return caps / len(words) >= 0.7


def plan(h, body):
    h0 = (h or '').strip(); L = lines(body)
    h1 = PREFIX.sub('', h0).strip()
    kinds = []
    if h1 != h0 and len(h1) >= 12:
        kinds.append('prefix')
    h2 = TAIL.sub('', h1).strip(' -:,')
    if h2 != h1 and len(h2) >= 12:
        kinds.append('tail')
    else:
        h2 = h1
    if NOT_TITLE.search(h0) or len(h2) < 12 or NOT_TITLE.search(h2):
        for ln in L[:60]:
            if title_like(ln) and ln.lower() != h0.lower():
                return 'not a title', ln
        return 'not a title', ''
    if DANGLE.search(h2) or re.search(r'(?i)\bfor\s+\d$', h2):
        key = re.sub(r'\W+', ' ', h2.lower()).split()[-3:]
        for i, ln in enumerate(L[:80]):
            if re.sub(r'\W+', ' ', ln.lower()).split()[-3:] == key and i + 1 < len(L):
                nxt = L[i + 1]
                if 2 <= len(nxt) <= 120 and not BAD_LINE.search(nxt) and not re.match(r'[a-z]', nxt) and len(nxt.split()) <= 14:
                    j = (h2 + ' ' + nxt).strip()
                    j = re.sub(r'(?i)\s+prepared in accordance.*$', '', j)
                    if not DANGLE.search(j):
                        kinds.append('cut short'); return ', '.join(kinds), j
                break
        kinds.append('cut short')
        return ', '.join(kinds), ''
    return ', '.join(kinds), (h2 if kinds else None)


def main():
    c = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
    cols = [r[1] for r in c.execute('pragma table_info(events)')]
    print('events columns:', ', '.join(cols))
    print('tables:', ', '.join(r[0] for r in c.execute("select name from sqlite_master where type in ('table','trigger') and (name like '%fts%' or name like '%event%' or type='trigger')")))
    q = 'select event_id, ticker, published_at, raw_headline, raw_body, slug from events where ticker in (%s) and ingested_at >= ? and review_status in ("auto_approved","approved")' % ','.join('?' * len(TK))
    rows = c.execute(q, TK + ['2026-11-12T23:00']).fetchall()
    out = []
    for eid, tk, pub, h, body, slug in rows:
        k, fix = plan(h, body)
        if fix is None:
            continue
        out.append((tk, pub[:10], eid, k, (h or '').replace('\t', ' ')[:200], fix.replace('\t', ' '), 'apply' if fix else 'leave', slug))
        if '--body' in sys.argv and not fix:
            out[-1] = out[-1] + (' // '.join(x[:70] for x in lines(body)[:9]),)
    out.sort()
    with open(OUT, 'w') as fh:
        fh.write('ticker\tdate\tevent_id\tkind\theadline\tnew_headline\taction\tslug\n')
        for o in out: fh.write('\t'.join(o[:8]) + '\n')
    st = {}
    for o in out:
        for kk in o[3].split(', '):
            st[kk] = st.get(kk, 0) + 1
    print('releases checked %d | to fix %d | to leave %d | by kind %s' % (len(rows), sum(o[6] == 'apply' for o in out), sum(o[6] == 'leave' for o in out), json.dumps(st)))
    for o in out:
        print('%s|%s|%s|%s|%s => %s%s' % (o[6], o[0], o[1], o[3], o[4][:95], o[5][:95], ('\n      body: ' + o[8][:520]) if len(o) > 8 else ''))


if __name__ == '__main__':
    main()
