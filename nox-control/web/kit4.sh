#!/bin/bash
# kit4: постоянная копия комплекта в /root/nox/soul_kit, удаление временных загрузок, карта
set -u
S=/root/nox/soul_kit; ls -d /root/nox_kit_* 2>/dev/null
src=$(ls -d /root/nox_kit_1795311721 2>/dev/null)
if [ -n "$src" ] && [ ! -d $S ]; then
  (cd $src/zip && sha256sum kit_*.zip > /tmp/zipsha.txt); mkdir -p /root/nox && mv $src/out $S && cp /tmp/zipsha.txt $S/ZIP_SHA256_DOWNLOADED.txt
fi
(cd $S && sha256sum -c SHA256SUMS 2>&1 | grep -vc ': OK$' | sed 's/^/sha_nonOK=/'; sha256sum -c SHA256SUMS 2>&1 | grep -c ': OK$' | sed 's/^/sha_OK=/')
rm -rf /root/nox_kit_*; df -h / | tail -1; ls /root/nox_kit_* 2>&1 | head -2
cd $S/12_Living_NOX && ls -l | awk '{print $5,$9}'
