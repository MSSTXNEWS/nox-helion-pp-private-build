import json, time
P = '/workspace/nox/web/pkg/server/nox_cmd.py'; R = '/workspace/nox/web/site/qa/registry.json'
t = open(P, encoding='utf-8').read()
if '_b_meili' not in t:
    code = '''

# ---- S3: поиск Meilisearch (ключ читается на сервере и в браузер не отдаётся) и перезапуск сервисов по рецептам start_all.sh ----
KEYF = "/workspace/nox/secrets/meili_key.txt"
def _b_meili(p):
    q = str(p.get("q", "")).strip()
    if len(q) < 2: return 400, {"ok": False, "error": "q: минимум 2 символа"}
    try:
        with open(KEYF, encoding="utf-8") as f: key = f.read().strip()
    except Exception: return 503, {"ok": False, "error": "ключ Meilisearch не найден на сервере"}
    def call(path, body=None):
        rq = urllib.request.Request("http://127.0.0.1:7700" + path, data=(json.dumps(body).encode() if body is not None else None), method=("POST" if body is not None else "GET"), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        with urllib.request.urlopen(rq, timeout=8) as r: return json.loads(r.read().decode())
    try:
        idx = [i["uid"] for i in call("/indexes?limit=20").get("results", [])]
        if not idx: return 200, {"ok": True, "result": json.dumps({"hits": []})}
        res = call("/multi-search", {"queries": [{"indexUid": u, "q": q, "limit": 4} for u in idx]})
        hits = []
        for r in res.get("results", []):
            for h in r.get("hits", []):
                h2 = {k: str(v)[:160] for k, v in h.items() if isinstance(v, (str, int, float)) and not k.startswith("_")}
                h2["_index"] = r.get("indexUid"); hits.append(h2)
        return 200, {"ok": True, "result": json.dumps({"hits": hits[:12]}, ensure_ascii=False)}
    except Exception as e:
        return 502, {"ok": False, "error": ("Meilisearch: " + str(e)[:100]).replace(key, "***")}
SVC_PORTS = {"filebrowser": 8187, "navidrome": 4533, "ntfy": 2586, "jellyfin": 8096, "freshrss": 8098, "meili": 7700}
def _port_up(port):
    import socket
    s = socket.socket(); s.settimeout(1)
    try: s.connect(("127.0.0.1", port)); return True
    except Exception: return False
    finally: s.close()
def _pids_on(port):
    out = subprocess.run(["bash", "-c", "ss -ltnpH 'sport = :%d' | grep -o 'pid=[0-9]*' | cut -d= -f2" % port], capture_output=True, text=True).stdout.split()
    return [int(x) for x in out if x.isdigit()]
def _b_restart2(p):
    name = p.get("service")
    if name == "web": return _b_restart_web(p)
    port = SVC_PORTS.get(name)
    if not port: return 400, {"ok": False, "error": "сервис не из белого списка: " + str(name)}
    import signal
    for pid in _pids_on(port):
        try: os.kill(pid, signal.SIGTERM)
        except Exception: pass
    for _ in range(20):
        if not _port_up(port): break
        time.sleep(0.5)
    # рецепты запуска — start_all.sh (идемпотентен: поднимает только то, что не слушает порт); meili поднимает start_extra.sh изнутри
    subprocess.Popen(["bash", "/workspace/nox/svc/start_all.sh"], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if _port_up(port): return 200, {"ok": True, "result": "%s перезапущен (порт %d отвечает)" % (name, port)}
        time.sleep(0.5)
    return 504, {"ok": False, "error": "%s не поднялся за 25 с, смотрите /workspace/nox/svc/logs/" % name}
_b_restart_web = BUILTIN["svc.restart"]
BUILTIN["svc.restart"] = _b_restart2
BUILTIN["search.meili"] = _b_meili
'''
    t = t.replace('\ndef handle(h, path, raw):', code + '\ndef handle(h, path, raw):', 1)
    open(P, 'w', encoding='utf-8').write(t)
r = json.load(open(R, encoding='utf-8'))
r['commands']['search.meili'] = {'desc': 'Поиск по файлам, памяти и каталогам (Meilisearch)', 'method': 'POST', 'endpoint': None, 'builtin': 'search.meili', 'params': {'type': 'object', 'properties': {'q': {'type': 'string', 'minLength': 2}}, 'required': ['q']}, 'confirm': False}
r['commands']['svc.restart']['desc'] = 'Перезапуск сервиса: web, filebrowser, navidrome, ntfy, jellyfin, freshrss, meili (с подтверждением)'
r['commands']['svc.restart']['params']['properties']['service'] = {'enum': ['web'] + sorted(['filebrowser', 'navidrome', 'ntfy', 'jellyfin', 'freshrss', 'meili'])}
json.dump(r, open(R, 'w', encoding='utf-8'), ensure_ascii=False, indent=1); print('patched2', len(r['commands']))
