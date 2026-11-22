#!/bin/bash
# stage5: скачать временный пакет с Диска, проверить sha256, развернуть в /root/nox/src/wow7, прогнать тесты на копии. Содержимое пакета в лог не печатается.
ID=1FC-MaTaaBmRXm6u3mmBIKdJwmIfhFg34; SHA=8705fed21bb8fa34abf7d0ccb54f54b394a9b58053e66bb37b923276b1bc634f
P=/root/nox/hotfix_pkg; mkdir -p $P; cd $P; rm -f pkg.zip
curl -fsSL "https://drive.usercontent.google.com/download?id=$ID&export=download&confirm=t" -o pkg.zip 2>/dev/null
got=$(sha256sum pkg.zip 2>/dev/null | cut -d' ' -f1)
if [ "$got" != "$SHA" ]; then pip install -q gdown 2>/dev/null; python3 -m gdown "https://drive.google.com/uc?id=$ID" -O pkg.zip -q 2>/dev/null; got=$(sha256sum pkg.zip | cut -d' ' -f1); fi
echo "zip sha ok: $([ "$got" = "$SHA" ] && echo yes || echo NO) size=$(stat -c %s pkg.zip)"
[ "$got" = "$SHA" ] || exit 1
rm -rf x; mkdir x; python3 -c "import zipfile;zipfile.ZipFile('pkg.zip').extractall('x')" && rm -f pkg.zip && echo "zip removed from S1"
W=$P/x/nox_wow; S=/root/nox/src/wow7; mkdir -p $S/brain $S/common $S/prime
[ -f $S/.bak_hotfix2.tgz ] || tar czf $S/.bak_hotfix2.tgz -C $S brain common prime 2>/dev/null
cp -a $W/BRAIN/. $S/brain/; cp -a $W/COMMON/. $S/common/; cp -a $W/PRIME/. $S/prime/; cp $W/HOTFIX_NOW.md $S/
for d in BRAIN:brain COMMON:common PRIME:prime; do [ -e $S/${d%%:*} ] || ln -s ${d##*:} $S/${d%%:*}; done
chmod -R go-rwx $S/prime $P
ls $S $S/brain | tr '\n' ' '; echo
echo "== tests on copy"; rm -rf /tmp/wow_t; cp -a $W /tmp/wow_t; export PYTHONDONTWRITEBYTECODE=1 NOX_WOW_SRC=/tmp/wow_t
for t in COMMON/test_common BRAIN/test_core PRIME/test_prime; do d=$(dirname $t); m=$(basename $t)
  out=$(cd /tmp/wow_t/$d && timeout 280 nice -n 15 python3 -W ignore -m unittest $m 2>&1); rc=$?
  echo "$t rc=$rc :: $(echo "$out" | grep -E '^(Ran |OK|FAILED)' | tr '\n' ' ')"
  [ $rc -ne 0 ] && echo "$out" | grep -E "^(FAIL|ERROR):" | head -8
done
rm -rf /tmp/wow_t
df -h /root | tail -1
