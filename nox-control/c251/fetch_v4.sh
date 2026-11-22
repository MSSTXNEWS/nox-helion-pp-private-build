#!/bin/bash
D=/root/nox/dl/v7; SHA=87261ebe60da6096aa9c7ee4150cee0c7fe4905974f2a7f4cb70857adaa3885d
if [ -d $D/v4 ] && [ -n "$(ls -A $D/v4 2>/dev/null)" ] && [ -f $D/v4.zip ] && [ "$(sha256sum $D/v4.zip|cut -d' ' -f1)" = $SHA ]; then echo "v4 уже есть, sha ок"; else
  command -v gdown >/dev/null || pip install -q gdown 2>&1|tail -1
  gdown -q "https://drive.google.com/uc?id=1lCPmdClzvjNtxsKobdwu3Hnio4d986pn" -O $D/v4.zip
  [ "$(sha256sum $D/v4.zip|cut -d' ' -f1)" = $SHA ] || { echo SHA_MISMATCH; exit 1; }
  mkdir -p $D/v4 && (cd $D/v4 && unzip -qo ../v4.zip)
fi
mkdir -p /tmp/nox_v7 && cp -rn $D/v4/. /tmp/nox_v7/ 2>/dev/null
cd $D/v4/nox_wow 2>/dev/null || cd $D/v4; echo ok; ls; ls OPT SPD | head -50
