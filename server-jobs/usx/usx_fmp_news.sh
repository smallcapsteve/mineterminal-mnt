#!/bin/bash
# USX_FMP_NEWS_V2: US company news, short versions from the FMP press-release feed, every 30 minutes.
# Step 1 (root, read-only on MNT): build the rows. Step 2 (mnt user): post them through upsert_event.
set -u
H=/var/tmp/usx-sens/hist
cd /opt/mnt/app || exit 1
PYTHONDONTWRITEBYTECODE=1 timeout 240 .venv/bin/python /root/usx/usx_fmp_news.py --build 2>&1 | grep -v -i -E 'apikey|api_key|token|secret|passw' | tail -40
[ "${PIPESTATUS[0]}" = 0 ] || { echo "build failed"; exit 2; }
grep -q '"event_id"' $H/fmp_news_rows.json || { echo "nothing new"; exit 0; }
runuser -u mnt -- env PYTHONPATH=/opt/mnt/app PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=ignore timeout 240 /opt/mnt/app/.venv/bin/python $H/usx_fmp_news.py --apply 2>&1 | tail -40
