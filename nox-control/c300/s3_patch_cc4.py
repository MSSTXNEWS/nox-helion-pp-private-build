import re,json
F='/workspace/nox/web/pkg/server/chat_core.py'; s=open(F,encoding='utf-8').read()
if '_persona_prefix' not in s:
    helper='''
# ---- S3: личность NOX (ползунки из настроек): persona.json -> system_hint в системный промпт; отключается enabled=false или NOX_PERSONA=0 ----
def _persona_prefix():
    try:
        if os.environ.get("NOX_PERSONA", "1") == "0": return []
        with open("/workspace/nox/state/persona.json", encoding="utf-8") as f: d = json.load(f)
        if d.get("enabled", True) is False: return []
        h = str(d.get("system_hint") or "").strip()
        return [{"role": "system", "content": h[:600]}] if h else []
    except Exception:
        return []

'''
    s=s.replace('def run_turn(body, emit):',helper+'def run_turn(body, emit):',1)
    old='        history = [{"role": m["role"], "content": m.get("ctx") or m["content"]} for m in conv["messages"][:-1]][-HIST_MAX:]\n'
    assert old in s
    s=s.replace(old,old+'        history = _persona_prefix() + history\n',1)
    open(F,'w',encoding='utf-8').write(s); print('chat_core patched')
P='/workspace/nox/web/pkg/server/nox_cmd.py'; t=open(P,encoding='utf-8').read()
a=t.index('def _persona_core_reads'); b=t.index('def _persona_hint')
t=t[:a]+'''def _persona_core_reads():
    try:
        with open("/workspace/nox/web/pkg/server/chat_core.py", encoding="utf-8") as f: src = f.read()
        if "_persona_prefix" not in src: return False
        with open(PERSONA_F, encoding="utf-8") as f: d = json.load(f)
        return d.get("enabled", True) is not False
    except FileNotFoundError: return "_persona_prefix" in src
    except Exception: return False
'''+t[b:]
t=t.replace('out = dict(v); out["system_hint"]','out = dict(v); out["enabled"] = bool(p["enabled"]) if "enabled" in p else _persona_enabled(); out["system_hint"]')
t=t.replace('def _persona_hint(v):','''def _persona_enabled():
    try:
        with open(PERSONA_F, encoding="utf-8") as f: return json.load(f).get("enabled", True) is not False
    except Exception: return True
def _persona_hint(v):''',1)
open(P,'w',encoding='utf-8').write(t); print('nox_cmd patched')
S='/workspace/nox/web/site/'
f=S+'nox-persona.js'; j=open(f,encoding='utf-8').read()
j=j.replace("(core ? 'Ядро читает этот файл.' : 'Ядро этот файл пока не читает: будет применено после подключения ядра.')","(core ? 'Применяется: подсказка добавляется в системный промпт каждого сообщения чата.' : 'Не применяется: будет применено после подключения ядра.')")
open(f,'w',encoding='utf-8').write(j); print('js patched', 'Применяется' in j)
R=S+'qa/registry.json'; r=json.load(open(R,encoding='utf-8'))
r['commands']['persona.set']['params']['properties']['enabled']={'type':'boolean','description':'применять в чате'}
json.dump(r,open(R,'w',encoding='utf-8'),ensure_ascii=False,indent=1)
