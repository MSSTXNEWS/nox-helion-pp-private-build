import sys,os,json,base64,time,urllib.request
from playwright.sync_api import sync_playwright
AXE=open('/workspace/nox/tools/uiscore/node_modules/axe-core/axe.min.js').read()
U='http://127.0.0.1:8091/web/chat-dc.html'
def vision(path):
    b=base64.b64encode(open(path,'rb').read()).decode()
    q="Это скриншот окна чата с ИИ. Оцени по шкале 0-10: A) удобство и ясность, R) аккуратность вёрстки (выравнивание, отступы, пустое место), WOW) визуальное впечатление. Ответь строго одной строкой JSON: {\"A\":n,\"R\":n,\"WOW\":n,\"issues\":\"до 25 слов, что кривое\"}"
    body={"model":"x","max_tokens":160,"temperature":0,"chat_template_kwargs":{"enable_thinking":False},"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+b}},{"type":"text","text":q}]}]}
    rq=urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
    try: return json.load(urllib.request.urlopen(rq,timeout=150))["choices"][0]["message"]["content"].strip()[:300]
    except Exception as e: return 'ERR '+repr(e)[:100]
with sync_playwright() as p:
    b=p.chromium.launch()
    for w,h,m in [(1920,1080,0),(390,844,1)]:
        pg=b.new_page(viewport={'width':w,'height':h},has_touch=bool(m),is_mobile=bool(m))
        pg.route('**/api/nox/outbox*',lambda r:r.fulfill(status=200,content_type='application/json',body='{"messages":[]}'))
        pg.goto(U,wait_until='load');pg.evaluate("localStorage.setItem('nox.wow.cur','qa-dcq%d')"%w);pg.reload();pg.wait_for_timeout(2500)
        pg.evaluate("document.querySelector('deep-chat').submitUserMessage({text:'Объясни в двух предложениях, что такое энтропия'})")
        for i in range(80):
            if pg.evaluate("!!document.querySelector('deep-chat').shadowRoot.querySelector('.dc-acts-live')"):break
            pg.wait_for_timeout(1000)
        pg.wait_for_timeout(800)
        pg.add_script_tag(content=AXE)
        r=pg.evaluate("axe.run(document,{resultTypes:['violations']}).then(r=>r.violations.map(v=>[v.id,v.impact,v.nodes.length]))")
        print(w,'AXE',json.dumps(r))
        path='/tmp/dcq%d.jpg'%w;pg.screenshot(path=path,type='jpeg',quality=70)
        print(w,'VISION',vision(path),flush=True);pg.close()
    b.close()
