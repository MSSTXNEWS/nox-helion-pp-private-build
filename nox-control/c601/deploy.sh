#!/bin/bash
# c601: деплой чат-фикса (вступление выкл, max_tokens>=1500, метка уровня, настройка длины, душа). Бэкапы *.bak_chatfix, ничего не удаляется.
export PYTHONDONTWRITEBYTECODE=1
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main; C=/root/nox/repo/nox-control; T=/tmp/c601; mkdir -p $T
FILES="wow7/brain/executors.py wow7/brain/nox_core.py wow7/brain/organs.py wow7/brain/chatset.py wow7/rte/rte_server.py wow7/prime/soul_prime_v3.txt glm53/soul_prime_v3.txt c600/soul_patch.py"
for f in $FILES; do curl -fsS -m 30 "$R/nox-control/$f?cb=$RANDOM$RANDOM" -o $T/$(echo $f|tr / _) || { echo "FAIL curl $f"; exit 1; }; done
for f in wow7/brain/executors.py wow7/brain/nox_core.py wow7/brain/organs.py wow7/brain/chatset.py wow7/rte/rte_server.py; do python3 -c "import ast,sys;ast.parse(open(sys.argv[1]).read())" $T/$(echo $f|tr / _) || { echo "FAIL syntax $f"; exit 1; }; done
grep -q "NOX_INTRO" $T/wow7_brain_executors.py && grep -q "tier_info" $T/wow7_brain_nox_core.py || { echo "FAIL: не те файлы в main"; exit 1; }
for f in wow7/brain/executors.py wow7/brain/nox_core.py wow7/brain/organs.py wow7/rte/rte_server.py wow7/prime/soul_prime_v3.txt glm53/soul_prime_v3.txt; do
  [ -f $C/$f ] && [ ! -e $C/$f.bak_chatfix ] && cp -p $C/$f $C/$f.bak_chatfix
  cp $T/$(echo $f|tr / _) $C/$f
done
cp $T/wow7_brain_chatset.py $C/wow7/brain/chatset.py
# другие копии души, если есть как обычные файлы
for p in /root/nox/PRIME/soul_prime_v3.txt $C/wow7/PRIME/soul_prime_v3.txt; do [ -f "$p" ] && [ ! -L "$p" ] && python3 $T/c600_soul_patch.py $p; done
ls -la $C/wow7/PRIME 2>&1 | head -2
cd $C/wow7/brain && NOX_INTRO=1 timeout 100 python3 -m unittest test_core test_intent 2>&1 | tail -3
# рестарт ядра и RTE (флаги и окружение сохраняются: gw_env без ARGV)
if pgrep -f 'nox_dispatcher\.py run' >/dev/null; then echo DSP; DSP_HOME=/root/nox python3 /root/nox/dsp/current/nox_dispatcher.py restart core; DSP_HOME=/root/nox python3 /root/nox/dsp/current/nox_dispatcher.py restart rte; sleep 4
else
  python3 $C/wow7/deploy/gw_env.py restart --match 'wow7/brain/nox_core\.py' --cwd $C/wow7/brain --log /root/nox/logs/core.log --health http://127.0.0.1:8090/health 2>&1 | tail -3
  python3 $C/wow7/deploy/gw_env.py restart --match 'rte_server\.py' --cwd $C/wow7/rte --log /root/nox/logs/rte.log --health http://127.0.0.1:8084/v1/rte/health 2>&1 | tail -3
fi
sleep 3; curl -s -m 5 http://127.0.0.1:8090/health | cut -c1-200; echo; curl -s -m 5 http://127.0.0.1:8084/v1/rte/health | cut -c1-120; echo
ps -eo pid,lstart,args | grep -E "nox_core|rte_server" | grep -v grep | cut -c1-120
