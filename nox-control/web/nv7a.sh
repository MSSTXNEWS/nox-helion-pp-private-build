#!/bin/bash
# NOX v7 step A: download zip from Drive, verify sha, unpack, list. No secrets printed.
set -u
ID=1lCPmdClzvjNtxsKobdwu3Hnio4d986pn; SHA=87261ebe60da6096aa9c7ee4150cee0c7fe4905974f2a7f4cb70857adaa3885d
echo "== disk"; df -h / | tail -1
mkdir -p /tmp/nox_v7_dl && cd /tmp/nox_v7_dl
which gdown >/dev/null 2>&1 || pip install -q gdown 2>&1 | tail -1
gdown "https://drive.google.com/uc?id=$ID" -O v4.zip 2>&1 | tail -3
ls -l v4.zip 2>&1
got=$(sha256sum v4.zip 2>/dev/null | cut -d' ' -f1); echo "sha=$got"
if [ "$got" != "$SHA" ]; then echo "SHA MISMATCH/NO FILE"; head -c 300 v4.zip 2>/dev/null | tr -c '[:print:]\n' '.'; exit 3; fi
rm -rf /tmp/nox_v7; mkdir -p /tmp/nox_v7 && python3 -c "import zipfile;zipfile.ZipFile('v4.zip').extractall('/tmp/nox_v7')" && rm -f v4.zip && echo unpacked
cd /tmp/nox_v7; find . -type f | head -120; du -sh .
