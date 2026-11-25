import json, re, shutil, time
P = '/workspace/nox/web/pkg/server/nox_cmd.py'
R = '/workspace/nox/web/site/qa/registry.json'
t = open(P, encoding='utf-8').read()
if 'BUILTIN' not in t:
    code = '''

# ---- S3: встроенные команды пульта (состояние интерфейса, тест уведомления, перезапуск веба) ----
import subprocess
STATE_F = "/workspace/nox/state/ui_state.json"
SVC_REG = "/workspace/nox/web/pkg/server/svc_registry.json"
def _ui_load():
    try:
        with open(STATE_F, encoding="utf-8") as f: return json.load(f)
    except Exception: return {"volume": 1.0, "projector": False, "focus": False}
def _ui_save(st):
    os.makedirs(os.path.dirname(STATE_F), exist_ok=True)
    st["ts"] = time.strftime("%FT%T")
    with open(STATE_F, "w", encoding="utf-8") as f: json.dump(st, f, ensure_ascii=False)
    return st
def _b_state(p): return 200, {"ok": True, "result": json.dumps(_ui_load(), ensure_ascii=False)}
def _b_volume(p):
    try: v = float(p.get("level"))
    except Exception: return 400, {"ok": False, "error": "level: число 0..1"}
    st = _ui_load(); st["volume"] = max(0.0, min(1.0, v)); _ui_save(st); return 200, {"ok": True, "result": json.dumps(st)}
def _b_flag(key):
    def f(p):
        st = _ui_load(); st[key] = bool(p.get("on")); _ui_save(st); return 200, {"ok": True, "result": json.dumps(st)}
    return f
def _b_notify(p):
    rq = urllib.request.Request("http://127.0.0.1:2586/nox-helion", data="Проверка канала уведомлений NOX HELION".encode(), method="POST", headers={"Title": "NOX HELION"})
    try:
        with urllib.request.urlopen(rq, timeout=8) as r: return 200, {"ok": True, "result": "ntfy: отправлено (%d)" % r.status}
    except Exception as e: return 502, {"ok": False, "error": "ntfy недоступен: " + str(e)[:120]}
def _b_restart(p):
    name = p.get("service")
    try:
        with open(SVC_REG, encoding="utf-8") as f: known = set(json.load(f).keys())
    except Exception: known = set()
    if name not in known | {"web"}: return 400, {"ok": False, "error": "сервис не из белого списка"}
    if name != "web": return 501, {"ok": False, "error": "рецепт перезапуска для «%s» не задан (есть только web)" % name}
    subprocess.Popen(["bash", "-c", "sleep 2; /workspace/nox/web/pkg/server/run_web.sh restart"], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return 200, {"ok": True, "result": "перезапуск веба запущен, связь вернётся через несколько секунд"}
BUILTIN = {"ui.state": _b_state, "volume": _b_volume, "projector": _b_flag("projector"), "focus": _b_flag("focus"), "notify.test": _b_notify, "svc.restart": _b_restart}
'''
    t = t.replace('\ndef handle(h, path, raw):', code + '\ndef handle(h, path, raw):', 1)
    t = t.replace('def _exec(cmd, params):\n', 'def _exec(cmd, params):\n    if cmd.get("builtin"):\n        fn = BUILTIN.get(cmd["builtin"])\n        return fn(params or {}) if fn else (501, {"ok": False, "error": "встроенная команда не найдена"})\n', 1)
    open(P, 'w', encoding='utf-8').write(t)
r = json.load(open(R, encoding='utf-8'))
obj = lambda props=None, req=None: {'type': 'object', 'properties': props or {}, **({'required': req} if req else {})}
new = {
 'ui.state': ('Состояние интерфейса (громкость, проектор, концентрация)', 'GET', obj(), False),
 'volume': ('Громкость интерфейса', 'POST', obj({'level': {'type': 'number', 'minimum': 0, 'maximum': 1}}, ['level']), False),
 'projector': ('Режим проектора (атмосфера)', 'POST', obj({'on': {'type': 'boolean'}}, ['on']), False),
 'focus': ('Режим концентрации', 'POST', obj({'on': {'type': 'boolean'}}, ['on']), False),
 'notify.test': ('Тест уведомления (ntfy)', 'POST', obj(), False),
 'svc.restart': ('Перезапуск сервиса (с подтверждением)', 'POST', obj({'service': {'type': 'string'}}, ['service']), True),
}
for k, (d, m, pr, cf) in new.items():
    r['commands'][k] = {'desc': d, 'method': m, 'endpoint': None, 'builtin': k, 'params': pr, 'confirm': cf}
r['updated'] = time.strftime('%F')
json.dump(r, open(R, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('patched; commands:', len(r['commands']))
