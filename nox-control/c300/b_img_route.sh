#!/bin/bash
# b_img_route.sh: /img/generate -> sun_adapter :8097 /generate с откатом на :8500 при 503/обрыве. Флаг state/flags.json (img_sun_adapter). Бэкап, py_compile, перезапуск web_server, тест 1 картинки только если чат свободен.
set -u
W=/workspace/nox
WS=$W/web/pkg/server/web_server.py
TS=$(date -u +%Y%m%d_%H%M%S)
mkdir -p $W/state
[ -f $W/state/flags.json ] || echo '{"img_sun_adapter": true}' > $W/state/flags.json
cp $WS $WS.bak_b_img_$TS
echo "backup: $WS.bak_b_img_$TS"
python3 - "$WS" <<'PY'
import sys
f=sys.argv[1]; s=open(f,encoding='utf-8').read()
old='        if p == "/img/generate": return self._proxy("POST", "/generate", raw, os.environ.get("NOX_IMGSVC", "127.0.0.1:8500"), "генерация (:8500)", "application/json")'
new='        if p == "/img/generate": return self._img_generate(raw)'
helper='''    def _img_generate(self, raw):
        # sun_adapter :8097 первым (флаг state/flags.json img_sun_adapter), откат на imgsvc :8500 при 503 или обрыве
        import json as _j
        try:
            on = bool(_j.load(open("/workspace/nox/state/flags.json", encoding="utf-8")).get("img_sun_adapter", True))
        except Exception:
            on = True
        hosts = [("127.0.0.1:8097", "sun_adapter (:8097)"), ("127.0.0.1:8500", "imgsvc (:8500)")] if on else [("127.0.0.1:8500", "imgsvc (:8500)")]
        last = None
        for host, name in hosts:
            try:
                c = http.client.HTTPConnection(host, timeout=900)
                c.request("POST", "/generate", body=raw, headers={"Content-Type": "application/json"})
                r = c.getresponse(); data = r.read(); c.close()
            except Exception as e:
                last = (502, {"ok": False, "error": "%s недоступен: %s" % (name, str(e)[:120])}); continue
            if r.status == 503 and host != hosts[-1][0]:
                last = (r.status, data); continue
            return self._send(r.status, data, r.getheader("Content-Type", "application/json"))
        if isinstance(last, tuple) and isinstance(last[1], dict):
            return self._j(last[0], last[1])
        return self._j(503, {"ok": False, "error": "генерация недоступна"})

    def _proxy(self, method, path, raw, host=None, name="шлюз GLM", ctype=None):'''
assert s.count(old)==1, "route line not unique"
s=s.replace(old,new)
assert s.count('    def _proxy(self, method, path, raw, host=None, name="шлюз GLM", ctype=None):')==1
s=s.replace('    def _proxy(self, method, path, raw, host=None, name="шлюз GLM", ctype=None):', helper, 1)
open(f,'w',encoding='utf-8').write(s); print("patched")
PY
if ! python3 -m py_compile "$WS"; then echo "COMPILE FAIL -> rollback"; cp $WS.bak_b_img_$TS $WS; exit 1; fi
echo "compile ok"
echo "== restart web_server"
ps -eo pid,args | grep "[w]eb_server.py" | head -3
PID=$(pgrep -f "web_server.py" | head -1); CMD=$(ps -o args= -p "$PID" 2>/dev/null)
echo "pid=$PID cmd=$CMD"
