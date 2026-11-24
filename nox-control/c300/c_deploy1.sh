#!/bin/bash
# c_deploy1: командная шина (/api/cmd), реестр, клиент nox-cmd.js, Ctrl+K-команды, новый ревизор.
# Бэкапы *.bak_c_1, компиляция, рестарт через run_web.sh, при провале health — откат.
set -u
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/cfiles
N=/workspace/nox; S=$N/web/pkg/server; W=$N/web/site; Q=$W/qa
mkdir -p $Q $N/state; TS=$(date +%s)
rollback(){ echo "ROLLBACK: $1"; cp $S/web_server.py.bak_c_1 $S/web_server.py; cp $W/nox-ninja.js.bak_c_1 $W/nox-ninja.js; rm -f $S/nox_cmd.py; $S/run_web.sh restart; exit 1; }
# 1. бэкапы
for f in $S/web_server.py $W/nox-ninja.js $N/qa_audit.py; do [ -f "$f" ] && { [ -f "$f.bak_c_1" ] || cp -p "$f" "$f.bak_c_1"; echo "bak $f"; }; done
[ -f $Q/audit.json ] && cp -p $Q/audit.json $Q/audit.json.bak_c_1
# 2. загрузка файлов
curl -fsSL $RAW/registry.json -o $Q/registry.json || rollback "registry"
curl -fsSL $RAW/nox_cmd.py -o $S/nox_cmd.py || rollback "nox_cmd"
curl -fsSL $RAW/nox-cmd.js -o $W/nox-cmd.js || rollback "nox-cmd"
curl -fsSL $RAW/qa_audit.py -o $N/qa_audit.py.new || rollback "qa_audit"
curl -fsSL $RAW/ninja_append.js -o /tmp/ninja_append_c1.js || rollback "ninja"
# 3. правка web_server.py: одна строка маршрута перед /api/chat
python3 -I - "$S/web_server.py" <<'PY' || rollback "patch web_server"
import sys
p=sys.argv[1]; s=open(p,encoding="utf-8").read()
anchor='        if p == "/api/chat": return self._chat(raw)\n'
if s.count(anchor)!=1: raise SystemExit("anchor count %d" % s.count(anchor))
if "nox_cmd" not in s:
    s=s.replace(anchor,'        if p in ("/api/cmd", "/api/cmd/confirm"): return __import__("nox_cmd").handle(self, p, raw)  # C-1 шина\n'+anchor)
open(p,"w",encoding="utf-8").write(s); print("patched")
PY
# 4. ninja: добавляем блок команд пульта (после бэкапа)
cat /tmp/ninja_append_c1.js >> $W/nox-ninja.js
# 5. компиляция
python3 -I -m py_compile $S/web_server.py $S/nox_cmd.py $N/qa_audit.py.new && echo compiled || rollback "py_compile"
mv $N/qa_audit.py.new $N/qa_audit.py
NODE=$N/tools/node/bin/node; [ -x $NODE ] && { $NODE --check $W/nox-ninja.js && echo "node ok" || rollback "node check nox-ninja"; }
# 6. рестарт и проверка здоровья
$S/run_web.sh restart; sleep 6
H=$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/api/chat/health); echo "health $H"
[ "$H" = 200 ] || rollback "health $H"
# 7. тесты шины: неизвестная 404, health 200, svc 200, без endpoint 501, подтверждение без клика 400
t(){ curl -s -m 20 -o /tmp/c1_body -w '%{http_code}' -X POST http://127.0.0.1:8091/api/cmd -H 'Content-Type: application/json' -d "$1"; echo " $(head -c 160 /tmp/c1_body)"; }
echo "T1 unknown: $(t '{"name":"__nope__"}')"
echo "T2 health: $(t '{"name":"health"}')"
echo "T3 svc.status: $(t '{"name":"svc.status"}')"
echo "T4 sleep (no endpoint): $(t '{"name":"sleep"}')"
echo "T5 confirm without click: $(curl -s -m 10 -o /tmp/c1_c -w '%{http_code}' -X POST http://127.0.0.1:8091/api/cmd/confirm -H 'Content-Type: application/json' -d '{"name":"health"}') $(head -c 120 /tmp/c1_c)"
echo "LOG:"; tail -n 4 $N/state/cmd_log.jsonl 2>/dev/null
echo "DONE $TS"
