import json, os, glob, hashlib, urllib.request, time
SEC = "/workspace/nox/secrets"; KEY = open(SEC + "/meili_key.txt").read().strip()
def mreq(path, body=None, method=None):
    rq = urllib.request.Request("http://127.0.0.1:7700" + path, data=json.dumps(body).encode() if body is not None else None, method=method or ("POST" if body is not None else "GET"), headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(rq, timeout=20))
docs = []
def add(kind, title, url, text=""):
    docs.append({"id": hashlib.sha1((kind + url + title).encode()).hexdigest()[:20], "kind": kind, "title": str(title)[:200], "url": url, "text": str(text)[:4000]})
try:
    nav = json.load(open("/workspace/nox/web/site/nav.json"))
    for g in nav["groups"]:
        for i in g["items"]: add("страница", i["title"].replace("NOX HELION · ", ""), i["file"], g["group"])
except Exception: pass
try:
    for f in os.listdir("/workspace/nox/dl_files"): add("файл", f, "/svc/filebrowser/files/" + f)
except Exception: pass
try:
    for e in json.load(open("/workspace/nox/state/cal_events.json")): add("событие", e.get("title"), "events.html", (e.get("start") or "") + " " + (e.get("notes") or ""))
except Exception: pass
n = 0
for f in glob.glob("/workspace/nox/state/web/**/*.json", recursive=True)[:3000]:
    if n > 3000: break
    try:
        c = json.load(open(f, encoding="utf-8"))
        ms = c.get("messages") if isinstance(c, dict) else None
        if not ms: continue
        txt = " ".join(str(m.get("content", "")) for m in ms if isinstance(m, dict))[:4000]
        add("чат", (c.get("title") or os.path.basename(f))[:80], "chat.html", txt); n += 1
    except Exception: pass
try:
    mreq("/indexes", {"uid": "nox", "primaryKey": "id"})
except Exception: pass
mreq("/indexes/nox/settings", {"searchableAttributes": ["title", "text"], "displayedAttributes": ["kind", "title", "url", "text"]}, "PATCH")
mreq("/indexes/nox/documents", docs, "PUT")
print("indexed", len(docs))
