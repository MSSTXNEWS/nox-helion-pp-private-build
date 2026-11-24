import os, re, json, urllib.request, glob, time
ROOT="/workspace/nox/web/site"; B="http://127.0.0.1:8091"
def get(u, data=None, t=10):
    try:
        r=urllib.request.urlopen(urllib.request.Request(B+u, data, {"Content-Type":"application/json"} if data else {}), timeout=t); return r.status, r.read()[:400]
    except urllib.error.HTTPError as e: return e.code, e.read()[:200]
    except Exception as e: return 0, str(e)[:100].encode()
print("health", get("/api/chat/health"))
# 1) недостающие ресурсы: ссылки из html/js на локальные файлы
miss={}; pages=sorted(glob.glob(ROOT+"/*.html"))
for f in pages+glob.glob(ROOT+"/*.js"):
    s=open(f,encoding="utf-8",errors="ignore").read()
    for m in re.findall(r'''(?:src|href)=["'](\.?/?(?:vendor|wow|planets|fonts)[^"'?#]+)''', s)+re.findall(r'''["'](\./vendor/[^"'?#]+)["']''', s):
        p=os.path.normpath(os.path.join(ROOT, m.lstrip("./") if not m.startswith("/web/") else m[5:]))
        if not os.path.exists(p): miss.setdefault(m,set()).add(os.path.basename(f))
print("pages", len(pages), "missing assets", len(miss))
libs={}
for m,fs in miss.items():
    k=m.split("vendor/")[1].split("/")[0] if "vendor/" in m else m
    libs.setdefault(k,set()).update(fs)
for k,fs in sorted(libs.items()): print("  MISS", k, "<-", ",".join(sorted(fs))[:120])
print("vendor present:", " ".join(sorted(os.listdir(ROOT+"/vendor"))) if os.path.isdir(ROOT+"/vendor") else "NO vendor dir")
# 2) страницы
bad=[os.path.basename(p) for p in pages if get("/web/"+os.path.basename(p))[0]!=200]; print("pages not 200:", bad[:20])
# 3) API, которые зовёт веб
for u in ("/brain/organism","/brain/wellbeing","/brain/growth","/brain/soul","/api/pc-metrics","/memory/health","/tts/health","/stt/health","/api/push/vapid","/drive/health","/api/drive/status"):
    c,b=get(u); print("api", u, c, b[:90].decode("utf-8","ignore").replace("\n"," "))
