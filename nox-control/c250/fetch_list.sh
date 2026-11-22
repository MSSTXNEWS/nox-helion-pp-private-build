#!/bin/bash
# B: скачать/проверить пакет v7 exec, показать состав
D=/root/nox/dl/v7; mkdir -p $D /root/nox/receipts /root/nox/logs
SHA=c67003e1a0c5a319f47bdca6059f09eedbfc3b9344a3ace9a04112cb8efe2bbf
if [ -d $D/exec ] && [ -n "$(ls -A $D/exec 2>/dev/null)" ]; then echo "exec уже распакован"; else
  if [ ! -f $D/exec.zip ] || [ "$(sha256sum $D/exec.zip|cut -d' ' -f1)" != $SHA ]; then
    command -v gdown >/dev/null || pip install -q gdown 2>&1|tail -1
    gdown -q "https://drive.google.com/uc?id=1eBFplMsS8HrQTTWqrw8-2yrT47IZLJmu" -O $D/exec.zip
  fi
  echo "sha: $(sha256sum $D/exec.zip|cut -d' ' -f1)"; [ "$(sha256sum $D/exec.zip|cut -d' ' -f1)" = $SHA ] || { echo SHA_MISMATCH; exit 1; }
  mkdir -p $D/exec && (cd $D/exec && unzip -qo ../exec.zip)
fi
cd $D/exec; find . -type f | head -80
