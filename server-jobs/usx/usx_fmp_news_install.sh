#!/bin/bash
# USX_FMP_NEWS install (2026-11-12, Justin: "ongoing, lets do every 30 minutes", "After the first post checks out").
# Installs the script, the wrapper and a 30-minute timer. Undo is printed at the end.
set -eu
[ "${CONFIRM:-}" = "APPLY-USX-FMPNEWS" ] || { echo "dry: would install /root/usx/usx_fmp_news.{py,sh}, mnt-usx-fmpnews.{service,timer}"; exit 0; }
S=/opt/mnt/relay/repo/payloads/usx; H=/var/tmp/usx-sens/hist
mkdir -p /root/usx
install -m 755 $S/usx_fmp_news.py /root/usx/usx_fmp_news.py
install -m 755 $S/usx_fmp_news.sh /root/usx/usx_fmp_news.sh
install -o mnt -m 644 $S/usx_fmp_news.py $H/usx_fmp_news.py
cat > /etc/systemd/system/mnt-usx-fmpnews.service <<'U'
# USX_FMP_NEWS 2026-11-12 (Justin approved by popup). Undo: systemctl disable --now mnt-usx-fmpnews.timer;
# rm /etc/systemd/system/mnt-usx-fmpnews.service /etc/systemd/system/mnt-usx-fmpnews.timer; systemctl daemon-reload
[Unit]
Description=MNT US company news, short versions from the FMP press-release feed
After=network.target

[Service]
Type=oneshot
ExecStart=/root/usx/usx_fmp_news.sh
Slice=mnt-batch.slice
Nice=10
TimeoutStartSec=10min
StandardOutput=journal
StandardError=journal
U
cat > /etc/systemd/system/mnt-usx-fmpnews.timer <<'U'
# USX_FMP_NEWS 2026-11-12: every 30 minutes at :14 and :44
[Unit]
Description=MNT US company news from FMP, every 30 minutes

[Timer]
OnCalendar=*:14,44:00
Persistent=false

[Install]
WantedBy=timers.target
U
systemd-analyze verify /etc/systemd/system/mnt-usx-fmpnews.service 2>&1 | head -5 || true
systemctl daemon-reload
systemctl enable --now mnt-usx-fmpnews.timer
systemctl list-timers --all --no-legend | grep usx-fmpnews || true
echo "installed. undo: systemctl disable --now mnt-usx-fmpnews.timer; rm /etc/systemd/system/mnt-usx-fmpnews.service /etc/systemd/system/mnt-usx-fmpnews.timer; systemctl daemon-reload"
