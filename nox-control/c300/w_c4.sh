echo "C300: w_c4"
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_bridge/api_bridge.py?cb=$t" -o /tmp/api_bridge.py; grep -q 'up_d' /tmp/api_bridge.py && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp $N/ops/api_bridge/api_bridge.py $N/ops/api_bridge/api_bridge.py.bak_c4; cp /tmp/api_bridge.py $N/ops/api_bridge/api_bridge.py
supervisorctl restart nox_api_bridge | tail -1; sleep 4
for u in training/status nox/activity notifications settings nox/status; do echo "== $u"; curl -s -m8 http://127.0.0.1:18091/api/$u | python3 -c "import sys,json;d=json.load(sys.stdin);print({k:(v if not isinstance(v,(dict,list)) else type(v).__name__) for k,v in d.items()})" 2>&1 | cut -c1-600; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/home.py <<'P'
import base64,json,urllib.request,re
from playwright.sync_api import sync_playwright
Q="Это скриншот главной страницы панели ИИ. Перечисли коротко: какие виджеты показывают реальные числа/данные, какие пустые или с «Н/Д», «нет данных», «—». Оцени 0-10 аккуратность вёрстки и читаемость. Ответ на русском, до 80 слов."
def vision(path):
    b=base64.b64encode(open(path,'rb').read()).decode()
    body={"model":"x","max_tokens":220,"temperature":0,"chat_template_kwargs":{"enable_thinking":False},"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+b}},{"type":"text","text":Q}]}]}
    rq=urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
    try: return json.load(urllib.request.urlopen(rq,timeout=90))["choices"][0]["message"]["content"].strip()[:500]
    except Exception as e: return 'ERR '+repr(e)[:100]
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    for w,h in ((1440,900),(390,844)):
        pg=b.new_page(viewport={'width':w,'height':h});pg.goto('http://127.0.0.1:18091/web/index.html',wait_until='load',timeout=60000);pg.wait_for_timeout(7000)
        t=pg.evaluate("document.body.innerText")
        print(w,'ND',len(re.findall(r'Н/Д|нет данных|Нет данных|HOLD',t)),'textlen',len(t))
        print(w,'EMPTYHINTS',sorted(set(re.findall(r'[^\n]{0,30}(?:Н/Д|нет данных|Нет данных|HOLD)[^\n]{0,30}',t)))[:8])
        pg.screenshot(path='/tmp/h%d.jpg'%w,type='jpeg',quality=70);pg.close()
    b.close()
for w in (1440,390): print(w,'VISION',vision('/tmp/h%d.jpg'%w),flush=True)
P
timeout 200 $N/venv/bin/python -W ignore /tmp/home.py 2>&1 | cut -c1-900
