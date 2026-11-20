#!/bin/bash
# деплой WOW-слоя B: файлы моста + nox_wow + regress50, рестарт только nox-bridge (модель не трогаем)
B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/bridge
cd /opt/nox-bridge || exit 1
mkdir -p /opt/nox-bridge.bak && cp -a nox_bridge.py nox_soul.py nox_webapi.py nox_wow.py /opt/nox-bridge.bak/ 2>/dev/null
for f in nox_bridge.py nox_soul.py nox_webapi.py nox_wow.py; do curl -fsSL $B/$f -o /tmp/$f.new && python3 -m py_compile /tmp/$f.new && mv /tmp/$f.new /opt/nox-bridge/$f || { echo FAIL $f; exit 1; }; done
curl -fsSL $B/regress50.py -o /opt/regress50.py
supervisorctl restart nox-bridge >/dev/null 2>&1; sleep 10
supervisorctl status nox-bridge; curl -s -m5 127.0.0.1:8091/api/health; echo
for e in unknown decisions changes personality reminders kto/export lora/candidates notes; do echo "== $e"; curl -s -m8 127.0.0.1:8091/api/nox/$e | head -c 260; echo; done
tail -3 /root/nox/logs/nox_bridge.log | cut -c1-200
# проверка в фоне: демо (3 живых ответа), затем регрессия 12 из 50, затем полные 50
nohup sh -c '/root/nox/venv/bin/python /opt/regress50.py --demo > /opt/wow_demo.out 2>&1; /root/nox/venv/bin/python /opt/regress50.py --n 12 --out /root/nox/state/regress_sub.json > /opt/regress_sub.out 2>&1' </dev/null >/dev/null 2>&1 &
echo started
