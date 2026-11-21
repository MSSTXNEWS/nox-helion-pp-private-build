#!/bin/bash
# c55: безопасная очистка диска (только одноразовое: старые сборки веба, кэши, tmp, ротированные логи). Веса, адаптеры, память, состояние НЕ трогаются.
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-200; }
echo "== BEFORE"; df -h / | tail -1
echo "== top dirs"; du -xsh /root/nox/* /opt/* /root/.cache /root/.npm /tmp /var/log /var/cache 2>/dev/null | sort -rh | head -14 | a
echo "== old web builds"; ls -d /opt/nox-web.prev.* 2>/dev/null | sort | head -20
KEEP=$(ls -d /opt/nox-web.prev.* 2>/dev/null | sort | tail -1)
for d in /opt/nox-web.prev.*; do [ -e "$d" ] && [ "$d" != "$KEEP" ] && rm -rf "$d" && echo "removed $d"; done
rm -rf /opt/nox-web.new /opt/.nox-web-dl /tmp/nox-web-deploy.lock 2>/dev/null
echo "== caches"; rm -rf /root/.cache/pip /root/.npm/_cacache /var/cache/apt/archives/*.deb 2>/dev/null; apt-get clean 2>/dev/null
echo "== tmp >2d"; find /tmp -xdev -mindepth 1 -mtime +2 -not -path '/tmp/nox-web*' -not -name 'deploy_web.sh' -delete 2>/dev/null
echo "== rotated logs >3d"; find /root/nox/logs /var/log -xdev -type f \( -name '*.gz' -o -name '*.log.[0-9]*' -o -name '*.bak_*' \) -mtime +3 -delete 2>/dev/null
echo "== AFTER"; df -h / | tail -1
echo "== largest remaining (review, not deleted)"; du -xsh /root/nox/lora/* /root/nox/models/* 2>/dev/null | sort -rh | head -8 | a
echo "== core files"; find /root /workspace -xdev -type f -size +200M \( -name 'core.*' -o -name '*.tmp' -o -name '*.part' \) 2>/dev/null | head -8 | a
