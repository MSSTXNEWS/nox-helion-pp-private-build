"""NOX · события -> ntfy: смена состояния шлюза, завершение генераций InvokeAI, новые файлы в dl_files."""
import json, os, time, urllib.request
def pub(msg, title="NOX HELION", tags=""):
    try:
        urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:2586/nox-helion", data=msg.encode(), headers={"Title": title.encode("utf-8").decode("latin-1", "ignore") if False else title, "Tags": tags}), timeout=5)
    except Exception: pass
def jget(u):
    try: return json.load(urllib.request.urlopen(u, timeout=4))
    except Exception: return None
st = {"gw": None, "done": None, "files": None}
while True:
    h = jget("http://127.0.0.1:8091/api/chat/health"); gw = bool(h and h.get("ok", True) and not h.get("error")) if h is not None else False
    if st["gw"] is not None and gw != st["gw"]: pub("Шлюз ответов NOX " + ("снова доступен" if gw else "недоступен"), "NOX: ядро")
    st["gw"] = gw
    q = jget("http://127.0.0.1:9090/api/v1/queue/default/status")
    if q:
        done = (q.get("queue") or {}).get("completed", 0)
        if st["done"] is not None and done > st["done"]: pub("Генерация изображения завершена (%d)" % (done - st["done"]), "NOX: Фотостудия")
        st["done"] = done
    try:
        fl = set(os.listdir("/workspace/nox/dl_files"))
        if st["files"] is not None:
            for f in sorted(fl - st["files"]): pub("Новый файл в загрузках: " + f, "NOX: Загрузки")
        st["files"] = fl
    except Exception: pass
    time.sleep(12)
