#!/bin/bash
# реальный импорт на КОПИИ (живая БД не трогается), фон
cp /root/nox/memory/backups/s03_pre_c400_20261122_131919.sqlite /root/nox/state/c400_s03_copy.db
cat > /root/nox/state/c400_imp.sh <<'IN'
cd /root/nox/repo/nox-control
python3 -m qs6.import_cli --db /root/nox/state/c400_s03_copy.db --root /root/nox/backup_s2/unpacked --json > /root/nox/state/c400_imp.json 2>&1; echo rc=$? > /root/nox/state/c400_imp.rc
IN
rm -f /root/nox/state/c400_imp.rc; nohup setsid bash /root/nox/state/c400_imp.sh >/dev/null 2>&1 &
sleep 2; echo started
