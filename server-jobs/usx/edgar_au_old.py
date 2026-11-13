# One-time history read of AngloGold's former SEC number (1067428, AngloGold Ashanti (Pty) Ltd, formerly AngloGold Ashanti Ltd).
# Same reader, same flags; only the company-number map is replaced for this run.   edgar_au_old.py --dry-run|--apply ...
import sys
sys.path.insert(0, '/opt/mnt/app')
import edgar_news as E
_orig = E.build_map
def _bm(con, apply):
    m = _orig(con, False)
    v = dict(next(x for x in m.values() if x['ticker'] == 'AU-US'))
    v['cik'] = 1067428
    return {1067428: v}
E.build_map = _bm
sys.exit(E.main())
