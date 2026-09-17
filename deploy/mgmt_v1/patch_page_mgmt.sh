#!/bin/bash
# MGMT_V1 page: swap the /management-changes handler in portal/app.py and install the new template.
# app.py is 91 KB and only this one section changes, so the block between the two markers is replaced
# in place and the whole file's sha256 is checked afterwards. (2026-09-17)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
REF="${MGMT_REF:?set MGMT_REF}"
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
RAW="https://raw.githubusercontent.com/smallcapsteve/mineterminal-mnt/$REF"
B=/var/tmp/mnt-mgmt-page-backup-$(date -u +%Y%m%d-%H%M%S)
TMPL=5a7f01d8eb145e0b6019550130d82a91e870fbc1f21061360530b331f40d025f

install -d -o mnt -g mnt $B
cp -p $LIVE/portal/app.py $B/app.py
cp -p $LIVE/portal/templates/management.html $B/management.html
echo "backup: $B"

curl -fsSL "$RAW/deploy/mgmt_v1/management_page_block.py" -o /var/tmp/mgmt_block.py || exit 3
curl -fsSL "$RAW/portal/templates/management.html" -o /var/tmp/mgmt_template.html || exit 3
echo "$TMPL  /var/tmp/mgmt_template.html" | sha256sum -c - || { echo "REFUSED: template arrived wrong"; exit 3; }

$PY - <<'PY' || exit 3
import hashlib
BEFORE = "73ac320e1aca3e17e6961dc2e2617a92de1509598f465a2175fcc986bec71de9"
AFTER = "ebe067d879d89a22698981fbc8d41ce42ad0a2d7ccccb8932ae95badfa6c110f"
START = "# ====== /management-changes tab (appended 2026-09-14) ======"
END = "# ====== generic category pages (appended 2026-09-15) ======"
p = "/opt/mnt/app/portal/app.py"
s = open(p, encoding="utf-8").read()
got = hashlib.sha256(s.encode()).hexdigest()
if got == AFTER:
    raise SystemExit(0)
if got != BEFORE:
    raise SystemExit("REFUSED: app.py is %s, expected %s" % (got[:16], BEFORE[:16]))
block = open("/var/tmp/mgmt_block.py", encoding="utf-8").read().rstrip("\n") + "\n" * 4
i, j = s.index(START), s.index(END)
out = s[:i] + block + s[j:]
end = hashlib.sha256(out.encode()).hexdigest()
if end != AFTER:
    raise SystemExit("REFUSED: the patched file would be %s, expected %s" % (end[:16], AFTER[:16]))
open(p, "w", encoding="utf-8").write(out)
print("app.py patched, now", end[:16])
PY

install -o mnt -g mnt -m 644 /var/tmp/mgmt_template.html $LIVE/portal/templates/management.html
find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
echo "app.py     $(sha256sum $LIVE/portal/app.py)"
echo "template   $(sha256sum $LIVE/portal/templates/management.html)"
runuser -u mnt -- $PY -c "import ast; ast.parse(open('$LIVE/portal/app.py').read()); print('app.py parses')" || exit 3

systemctl restart mnt-portal
for i in $(seq 1 20); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz)
  [ "$code" = "200" ] && break
  sleep 3
done
echo "healthz $code"
for u in "/management-changes" "/management-changes?scope=board" "/management-changes?role=Director" \
         "/management-changes?action=departed" "/management-changes?ticker=NGEX.TO"; do
  echo "  $u -> $(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8001$u")"
done
if [ "$code" != "200" ]; then
  echo "ROLLING BACK"
  install -o mnt -g mnt -m 644 $B/app.py $LIVE/portal/app.py
  install -o mnt -g mnt -m 644 $B/management.html $LIVE/portal/templates/management.html
  find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
  systemctl restart mnt-portal
  sleep 5
  echo "healthz after rollback $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz)"
  exit 3
fi
curl -s http://127.0.0.1:8001/management-changes | grep -o 'option value="[^"]*"' | head -12
curl -s http://127.0.0.1:8001/management-changes | grep -o '<td class="mgmt-role"[^>]*>[^<]*' | head -6
echo "PATCH_PAGE_DONE $(date -u +%FT%TZ)"
