N=/workspace/nox; F=$N/advisors/gateway.py; T=$(date +%Y%m%d_%H%M%S); cp -p $F $F.bak_p3_$T
python3 - "$F" <<'PY'
import sys,re
p=sys.argv[1]; s=open(p).read()
if "P3_PRIVATE" in s: print("already"); sys.exit()
m=re.search(r"^def chat\(body\):\n",s,re.M)
if not m: print("no def chat(body)"); sys.exit(1)
rx='''PRIVATE_TOPICS = re.compile(r"(?i)(исков\\w*|судебн\\w+|в суд\\w*|судья|суде\\b|ответчик\\w*|истец|снос\\w*\\s+дом\\w*|самовольн\\w+\\s+постройк\\w*|алуштинск\\w*|\\bиск\\b|финанс\\w*|банковск\\w+|кредит\\w*|ипотек\\w*|долг\\w*|зарплат\\w*|налог\\w*|диагноз\\w*|болезн\\w*|лечени\\w*|здоровь\\w*|врач\\w*|лекарств\\w*|анализ\\w*\\s+крови)")  # P3_PRIVATE: иск, суд, финансы, здоровье не уходят наружу
'''
s=s[:m.start()]+rx+s[m.start():m.end()]+'''    if not cfg().get('allow_personal'):  # P3_PRIVATE
        _txt = ' '.join(str(x.get('content', '')) if isinstance(x.get('content', ''), str) else json.dumps(x.get('content', ''), ensure_ascii=False) for x in (body.get('messages') or []) if isinstance(x, dict))
        if PRIVATE_TOPICS.search(_txt):
            return 403, {'error': 'private_topic: запрос про иск/суд/финансы/здоровье не отправляется наружу'}
'''+s[m.end():]
open(p,"w").write(s); print("patched")
PY
$N/venv/bin/python -m py_compile $F 2>&1 || python3 -m py_compile $F && echo syntax ok
python3 - <<'PY'
import re,importlib.util
src=open("/workspace/nox/advisors/gateway.py").read(); m=re.search(r'PRIVATE_TOPICS = re.compile\((.*?)\)  # P3',src,re.S); rx=eval("re.compile("+m.group(1)+")")
for t in ["расскажи про иск о сносе дома","как работает кэш","что с моими финансами","у меня болит голова, какое лечение","привет как дела","риск высокий"]: print(bool(rx.search(t)),t)
PY
