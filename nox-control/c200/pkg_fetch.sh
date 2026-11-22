#!/bin/bash
# c200: скачать/проверить/распаковать пакет exec
D=/root/nox/dl/v7; mkdir -p $D /root/nox/receipts /root/nox/logs
H=c67003e1a0c5a319f47bdca6059f09eedbfc3b9344a3ace9a04112cb8efe2bbf
if [ "$(sha256sum $D/exec.zip 2>/dev/null|cut -d' ' -f1)" != "$H" ]; then
 command -v gdown >/dev/null || pip install -q gdown --break-system-packages 2>&1|tail -1
 gdown -q "https://drive.google.com/uc?id=1eBFplMsS8HrQTTWqrw8-2yrT47IZLJmu" -O $D/exec.zip
fi
echo "sha: $(sha256sum $D/exec.zip|cut -d' ' -f1)"
[ "$(sha256sum $D/exec.zip|cut -d' ' -f1)" = "$H" ] || { echo SHA_MISMATCH; exit 1; }
mkdir -p $D/exec; cd $D/exec; unzip -oq ../exec.zip; find . -type f | sort | head -80
