echo "K1: l1_stop1"
S=/workspace/nox/state
cat > $S/WINDOWS.md <<'W'
# Правила окон (L1, 27.11)
1. Playwright/Chromium на K1 запрещён. Приёмка UI только локально на зеркале k1-snap, внешний timeout на страницу 60 с, на весь прогон 15 мин.
2. На K1 проверки чата только через API (curl /api/turn, диалоги с префиксом qa-).
3. Окна (STOP, QA, DPO-сборка): перед тяжёлым запуском создать state/windows/<имя>.lock (в файле время начала и срок); не стартовать, если есть живой lock другого окна.
4. Замеры скорости чата только при пустом фоне (нет build_dpo/тренера/судей по ps) или с пометкой нагрузки load1.
5. Ход владельца: owner_active ставит на SIGSTOP тренер/DPO/ворота/:8105, на nice 19 судей и build_dpo.
W
mkdir -p $S/windows; echo "windows_md=ok load1=$(cut -d' ' -f1 /proc/loadavg)"
grep -n "api/stop\|/stop" /workspace/nox/web/pkg/server/web_server.py | cut -c1-140 | head -5
python3 - <<'P'
import json,time,threading,urllib.request
cid="qa-l1stop-%d"%time.time()
def go():
    rq=urllib.request.Request("http://127.0.0.1:8091/api/turn",data=json.dumps({"conversation_id":cid,"message":"Напиши длинный рассказ на 600 слов про море."}).encode(),headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(rq,timeout=60) as r:
            for l in r:
                if b'"done"' in l or b'"error"' in l: break
    except Exception: pass
th=threading.Thread(target=go); th.start(); time.sleep(4)
t0=time.time()
for path in ("/api/stop","/api/turn/stop"):
    try:
        rq=urllib.request.Request("http://127.0.0.1:8091"+path,data=json.dumps({"conversation_id":cid}).encode(),headers={"Content-Type":"application/json"})
        r=urllib.request.urlopen(rq,timeout=10); print(path,r.status,r.read()[:80]); break
    except Exception as e: print(path,type(e).__name__,getattr(e,"code",""))
th.join(15); print("stop_to_stream_end_s",round(time.time()-t0,1),"alive",th.is_alive())
P
