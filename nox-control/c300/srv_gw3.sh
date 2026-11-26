#!/bin/bash
cat > /tmp/srv_gw_patch.py <<'PYEOF'
import re,sys,shutil,time,os
G="/workspace/nox/advisors/gateway.py"
s=open(G,encoding="utf-8").read()
if "JRN_P3" in s: print("already patched"); sys.exit(0)
shutil.copy(G,G+".bak_jrn_%d"%int(time.time()))
helper='''
# JRN_P3: журнал запросов шлюза без содержимого (время, провайдер, prio, категория), ротация 7 дней
JRN_DIR = '/workspace/nox/state/gw_journal'
_JRN_CAT = [('code', r'(?i)\\b(python|код|функци|скрипт|bug|ошибк\\w* в коде|sql|html|css|javascript|def )\\b|```'),
            ('math', r'(?i)(сколько будет|\\d+\\s*[*/+x×-]\\s*\\d+|уравнени|интеграл|производн)'),
            ('translate', r'(?i)(переведи|перевод|translate)'),
            ('image', r'(?i)(нарису|картинк|изображени|рисун|draw|image)'),
            ('news', r'(?i)(новост|погод|курс\\b|сегодня|сейчас в)'),
            ('smalltalk', r'(?i)^\\W*(привет|здравствуй|как дела|hi\\b|hello|спасибо)')]
def _jrn_cat(body):
    try:
        t = ' '.join(str(x.get('content', '')) for x in (body.get('messages') or body.get('prompt') and [{'content': body.get('prompt')}] or []) if isinstance(x, dict))
        if PRIVATE_TOPICS.search(t): return 'private'
        for n, rx in _JRN_CAT:
            if re.search(rx, t): return n
        return 'other'
    except Exception: return 'unknown'
def _jrn(path, body, code, out):
    try:
        os.makedirs(JRN_DIR, exist_ok=True)
        nx = (out.get('nox') or {}) if isinstance(out, dict) else {}
        rec = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'route': path.split('?')[0][-24:], 'code': code, 'provider': nx.get('provider') or ('none' if code != 200 else ''),
               'local': bool(nx.get('local')), 'cached': bool(nx.get('cached')), 'prio': int(body.get('x_nox_prio', 5)), 'cat': _jrn_cat(body), 'ms': nx.get('ms')}
        fn = os.path.join(JRN_DIR, time.strftime('%Y-%m-%d') + '.jsonl')
        first = not os.path.exists(fn)
        with open(fn, 'a', encoding='utf-8') as f: f.write(json.dumps(rec, ensure_ascii=False) + '\\n')
        if first:
            for o in os.listdir(JRN_DIR):
                p = os.path.join(JRN_DIR, o)
                if o.endswith('.jsonl') and time.time() - os.path.getmtime(p) > 7 * 86400:
                    try: os.remove(p)
                    except Exception: pass
    except Exception: pass
'''
anchor="class H(BaseHTTPRequestHandler):"
assert anchor in s
s=s.replace(anchor,helper+"\n"+anchor,1)
old="        code, out = (route or chat)(body); self.send(code, out)"
assert old in s
s=s.replace(old,"        code, out = (route or chat)(body); _jrn(self.path, body, code, out); self.send(code, out)",1)
open(G,"w",encoding="utf-8").write(s)
import py_compile; py_compile.compile(G,doraise=True); print("patched ok")
PYEOF
G=/workspace/nox/advisors/gateway.py
OLD=$(pgrep -f 'advisors/gateway.py' | head -1)
python3 -I /tmp/srv_gw_patch.py || exit 1
grep -c JRN_P3 $G
tr '\0' '\n' </proc/$OLD/environ > /tmp/gw_env.txt
kill $OLD; sleep 1
python3 -I - <<'PY'
import subprocess,os
env=dict(l.split("=",1) for l in open("/tmp/gw_env.txt").read().splitlines() if "=" in l)
subprocess.Popen(["python3","/workspace/nox/advisors/gateway.py"],env=env,cwd="/workspace/nox/advisors",stdout=open("/workspace/nox/state/gw_restart.log","a"),stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
PY
rm -f /tmp/gw_env.txt; sleep 3
curl -s -m5 127.0.0.1:8793/health | head -c 120; echo
# rollback if dead
if ! curl -s -m5 127.0.0.1:8793/health >/dev/null; then cp $(ls -t $G.bak_jrn_* | head -1) $G; setsid -f python3 $G >> /workspace/nox/state/gw_restart.log 2>&1 < /dev/null; echo ROLLED_BACK; fi
curl -s -m20 -X POST 127.0.0.1:8793/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"auto","messages":[{"role":"user","content":"Сколько будет 2+2?"}],"max_tokens":20,"x_nox_prio":3}' | head -c 200; echo
curl -s -m20 -X POST 127.0.0.1:8793/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"auto","messages":[{"role":"user","content":"расскажи про иск о сносе дома"}],"max_tokens":20}' | head -c 200; echo
cat /workspace/nox/state/gw_journal/*.jsonl | tail -3
