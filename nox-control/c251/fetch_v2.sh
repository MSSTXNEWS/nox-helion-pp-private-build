#!/bin/bash
# B: скачать/проверить v2 (идемпотентно, не дублирует А)
D=/root/nox/dl/v7; mkdir -p $D /root/nox/receipts /root/nox/logs
SHA=24d65c67ff5fbe6f8d76a00aa11c58e4123482b5080392ebc5f409f7f99ac152
if [ -d $D/exec2 ] && [ -n "$(ls -A $D/exec2 2>/dev/null)" ] && [ -f $D/exec2.zip ] && [ "$(sha256sum $D/exec2.zip|cut -d' ' -f1)" = $SHA ]; then echo "exec2 уже есть, sha ок"; else
  command -v gdown >/dev/null || pip install -q gdown 2>&1|tail -1
  gdown -q "https://drive.google.com/uc?id=1BokgkdisSTgnah1pwwhBX95b_hjzjH6f" -O $D/exec2.zip
  [ "$(sha256sum $D/exec2.zip|cut -d' ' -f1)" = $SHA ] || { echo SHA_MISMATCH; exit 1; }
  mkdir -p $D/exec2 && (cd $D/exec2 && unzip -qo ../exec2.zip)
fi
mkdir -p /tmp/nox_v7 && cp -rn $D/exec2/. /tmp/nox_v7/ 2>/dev/null
echo ok; cd $D/exec2; ls nox_wow/DEPLOY nox_wow/SPD nox_wow/OPT 2>&1 | head -60
