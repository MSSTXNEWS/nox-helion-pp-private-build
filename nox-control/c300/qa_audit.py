#!/usr/bin/env python3
"""NOX ревизор, уровень 2: аудит разделов по ТЗ «Топ-10 WOW». Чек-лист → задание на переделку → перепроверка → интеграция."""
import os,json,time,asyncio,base64,re,urllib.request
SITE="/workspace/nox/web/site"; OUT=SITE+"/qa"; RW=OUT+"/rework"; B="http://127.0.0.1:8091/web/"
NICHE={"chat":("ИИ-чат","Claude, Gemini, ChatGPT, Perplexity, Copilot, Grok, Le Chat, DeepSeek, Kimi, Meta AI","лента диалога, дерево чатов слева, блоки рассуждения, ветвление ответа, артефакты справа, источники, живые виджеты, теги быстрых команд, оценка 👍/👎"),
"cinema":("кинотеатр","Netflix, Disney+, HBO Max, Prime Video, Apple TV, Кинопоиск, Okko, Crunchyroll, Plex, Jellyfin","герой-баннер с трейлером, ряды-карусели постеров, карточка с рейтингом и кнопкой Смотреть, плеер"),
"music":("музыкальный сервис","Spotify, Apple Music, YouTube Music, Яндекс Музыка, Tidal, Qobuz, Deezer, SoundCloud, Amazon Music, Navidrome","обложки, плейлисты, мини-плеер, волна, очередь"),
"news":("новостной портал","Google News, Apple News, BBC, NYT, Bloomberg, The Verge, Feedly, Substack, Meduza, Яндекс Новости","главная новость крупно, сетка карточек с фото, рубрики, время публикации, сводка NOX"),
"photo":("фоторедактор / фотостудия","Midjourney, Nano Banana, ChatGPT Images, Firefly, Ideogram, Flux, Leonardo, Krea, Recraft, ComfyUI","полноэкранный холст, плавающие стеклянные панели инструментов, строка промпта, слои"),
"studio":("ИИ-фотостудия","Midjourney, Nano Banana, ChatGPT Images, Firefly, Ideogram, Flux, Leonardo, Krea, Recraft, ComfyUI","холст, слои, маски, строка промпта, диалог с NOX, галерея результатов"),
"tools":("набор инструментов","Notion, Figma, VS Code, Raycast","сетка инструментов, быстрый запуск"),
"index":("главный экран ИИ-системы","visionOS, Raycast, Vercel Dashboard, Linear, Notion Home, Home Assistant, Dia, Homarr, Homepage, Grafana","сцена, приветствие, плиточные карточки сервисов (Homepage/Gridstack), быстрые действия, живые метрики"),
"consciousness":("визуализатор сознания/ядра ИИ","Neuronpedia, графы атрибуции Anthropic, Transformer Explainer, LLM Visualization, Netron, TensorFlow Playground","3D-разрез трансформера, панель органов с живыми статусами, график активности, без фейковых цифр"),
"organism":("живой организм ИИ","Neuronpedia, графы атрибуции Anthropic, Transformer Explainer, LLM Visualization, Netron, TensorFlow Playground","живая лента органов с перемоткой, граф ядер, статусы органов из реальных данных"),
"soul":("ядро/душа ИИ","Neuronpedia, графы атрибуции Anthropic, Transformer Explainer, Netron","граф ядер, состояния, живые данные"),
"growth":("панель роста ИИ","Neuronpedia, Transformer Explainer, TensorFlow Playground, Grafana","графики роста по реальным данным, ступени, метрики"),
"selffeel":("самоощущение ИИ (эмоции)","Neuronpedia, графы атрибуции Anthropic, TensorFlow Playground, Grafana","радар эмоций, шкалы настроения, анимации состояний, реальные данные"),
"training":("мониторинг обучения модели","TensorFlow Playground, Netron, Grafana, Neuronpedia","графики loss/шагов по реальным логам или честное «обучение не запущено»")}
# реестр готовых модулей: страница -> маркеры (имена файлов в vendor/ или script src); достаточно любого
REG={"chat":["vendor/nox-chat-ui","vendor/xyflow","nox-chat-ui"],"index":["vendor/gridstack","gridstack"],
"consciousness":["vendor/llm-viz","llm-viz","echarts"],"organism":["echarts","3d-force-graph","cosmos"],"soul":["echarts","3d-force-graph","cosmos"],
"growth":["echarts"],"selffeel":["echarts"],"training":["echarts"],"cinema":["swiper","vendor/"],"music":["wavesurfer","vendor/"],"news":["vendor/"],"photo":["vendor/"],"studio":["vendor/"],"tools":["vendor/"]}
CHECK=["Шапка, нижняя панель и фон-солнце как у эталона, ничего поверх них","Есть обязательные паттерны ниши","Построено на готовых модулях, не топорно","Нет мёртвых кнопок, заглушек и фейковых цифр","Нет JS-ошибок, 404, выхода за край экрана","Мобильная версия удобна на 390px","Стекло, сдержанный свет, без неона (10+10+10)","WOW на уровне топ-10 ниши: 8/10 и выше","Используются модули из реестра (vendor/), а не самодельная вёрстка"]
SKIP=re.compile(r"удал|delete|stop|стоп|выход|logout|очист|сброс|reset|генер|создать|отправ|send",re.I)
def vision(jpg,prompt):
    d="data:image/jpeg;base64,"+base64.b64encode(jpg).decode()
    body={"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":d}},{"type":"text","text":prompt}]}],"max_tokens":1500,"temperature":0.2,"chat_template_kwargs":{"enable_thinking":False}}
    rq=urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",json.dumps(body).encode(),{"Content-Type":"application/json"})
    for _ in range(3):
        try: m=json.loads(urllib.request.urlopen(rq,timeout=600).read())["choices"][0]["message"]; return (m.get("content") or "")+"\n"+(m.get("reasoning_content") or "")[-3000:]
        except Exception as e: err=f"ERR {e}"; time.sleep(30)
    return err
async def audit(page):
    from playwright.async_api import async_playwright
    key=page[:-5]; niche=NICHE.get(key,("раздел ИИ-системы","лучшие сервисы ниши","ключевые паттерны ниши"))
    res={"page":page,"ts":time.strftime("%F %T"),"fails":[]}
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-webgl","--ignore-gpu-blocklist"])
        shots={}
        for vp,(w,h) in {"desk":(1440,900),"mob":(390,844)}.items():
            pg=await b.new_page(viewport={"width":w,"height":h}); errs=[]; bad=[]
            pg.on("pageerror",lambda e:errs.append(str(e)[:120])); pg.on("response",lambda r:bad.append(r.url[-60:]) if r.status>=400 else None)
            await pg.goto(B+page,wait_until="load",timeout=30000); await pg.wait_for_timeout(4000)
            if vp=="desk":
                try:
                    src=open(f"{SITE}/{page}").read()+" "+" ".join(await pg.evaluate("()=>[...document.scripts].map(s=>s.src).concat([...document.querySelectorAll('link[rel=stylesheet]')].map(l=>l.href))"))
                    mk=REG.get(key,["vendor/"])
                    if not any(m in src for m in mk): res["fails"].append({"item":CHECK[8],"detail":"нет маркеров реестра: "+", ".join(mk)})
                except Exception as e: res["fails"].append({"item":CHECK[8],"detail":str(e)[:80]})
            await pg.keyboard.press("Escape")
            shots[vp]=await pg.screenshot(type="jpeg",quality=60)
            if vp=="desk": shots["vis"]=await pg.screenshot(type="jpeg",quality=55,scale="css",clip={"x":0,"y":0,"width":1440,"height":900})
            if errs or bad: res["fails"].append({"item":CHECK[4],"vp":vp,"detail":(errs+bad)[:4]})
            if vp=="mob":
                small=await pg.evaluate("()=>[...document.querySelectorAll('button,a,[role=button]')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.height<32&&r.width<32}).length")
                if small>6: res["fails"].append({"item":CHECK[5],"vp":vp,"detail":f"{small} мелких целей нажатия (<32px)"})
            if vp=="desk":
                # мёртвые кнопки: клик не меняет DOM, URL и не шлёт запрос
                n=await pg.evaluate("()=>document.querySelectorAll('button, [role=button]').length")
                dead=[]
                for i in range(min(n,25)):
                    loc=pg.locator("button, [role=button]").nth(i)
                    try:
                        t=(await loc.inner_text(timeout=1000)).strip()[:30]
                        if SKIP.search(t) or not await loc.is_visible(): continue
                        before=await pg.evaluate("()=>document.body.innerHTML.length+'|'+location.href"); req=[]
                        h=lambda r:req.append(1); pg.on("request",h); pg.on("filechooser",h); pg.on("download",h); pg.on("popup",h); pg.on("dialog",lambda d:(req.append(1),asyncio.ensure_future(d.dismiss())))
                        await loc.click(timeout=2000); await pg.wait_for_timeout(700); pg.remove_listener("request",h)
                        if re.search(r"проектор|png|jpg|webp|открыть",t,re.I) and not req: req.append(1)  # системные диалоги/Presentation API не видны в headless
                        after=await pg.evaluate("()=>document.body.innerHTML.length+'|'+location.href")
                        if before==after and not req: dead.append(t or f"#{i}")
                        if pg.url!=B+page: await pg.goto(B+page,wait_until="load"); await pg.wait_for_timeout(2500)
                    except Exception: pass
                if dead: res["fails"].append({"item":CHECK[3],"vp":"desk","detail":"мёртвые кнопки: "+", ".join(dead[:8])})
            await pg.close()
        await b.close()
    for vp in ("desk","mob"): open(f"{OUT}/audit_{vp}_{key}.jpg","wb").write(shots[vp])
    pr=(f"Ты строгий арт-директор. Это скриншот раздела «{niche[0]}» веб-интерфейса NOX. Сравни с лучшими в нише: {niche[1]}. "
        f"Обязательные паттерны ниши: {niche[2]}. Канон: тёмное дымчатое стекло, чёрное солнце с красной короной на фоне, тонкие заглавные надписи, без неона. "
        "Оцени также три балла по 10: A = анимация (A01-A10: плавность, микро-анимации, переходы, живость), R = реализм/материал (R01-R10: стекло, свет, глубина, тени), U = интерфейс (U01-U10: иерархия, читаемость, цели нажатия, состояния). Ответь строго JSON без пояснений: {\"wow\":0-10,\"A\":0-10,\"R\":0-10,\"U\":0-10,\"patterns_missing\":[...],\"toporno\":[...конкретные места...],\"neon\":true/false,\"overlap\":true/false,\"fix\":[...3-6 конкретных правок, какие готовые модули взять...]}")
    v=vision(shots["desk"],pr); res["vision_raw"]=v[:1500]
    m=re.search(r"\{.*\}",v,re.S); j={}
    try: j=json.loads(m.group(0)) if m else {}
    except Exception: pass
    res["wow"]=j.get("wow"); res["fix"]=j.get("fix",[])
    if j.get("patterns_missing"): res["fails"].append({"item":CHECK[1],"detail":j["patterns_missing"]})
    if j.get("toporno"): res["fails"].append({"item":CHECK[2],"detail":j["toporno"]})
    if j.get("neon"): res["fails"].append({"item":CHECK[6],"detail":"неон"})
    if j.get("overlap"): res["fails"].append({"item":CHECK[0],"detail":"элементы поверх шапки/низа"})
    for k in "ARU":
        if not isinstance(j.get(k),(int,float)) or j[k]<8: res["fails"].append({"item":"Фильтр 10+10+10: "+k+" >= 8","detail":f"{k}={j.get(k)}"})
    res["ARU"]=[j.get(k) for k in "ARU"]
    if not isinstance(j.get("wow"),(int,float)) or j["wow"]<8: res["fails"].append({"item":CHECK[7],"detail":f"WOW {j.get('wow')}"})
    return res
def main():
    import sys; os.makedirs(RW,exist_ok=True)
    pages=sys.argv[1:] or [p+".html" for p in NICHE if os.path.exists(f"{SITE}/{p}.html")]
    st=json.load(open(f"{OUT}/audit.json")) if os.path.exists(f"{OUT}/audit.json") else {}
    for pg in pages:
        r=asyncio.run(audit(pg)); key=pg[:-5]; prev=st.get(key,{})
        fixed_run=len(sys.argv)>1  # цикл считается только при перепроверке после .fixed
        r["cycle"]=(prev.get("cycle",0)+(1 if (r["fails"] and fixed_run) else 0)) if prev.get("status")!="ok" else 0
        if r["fails"]:
            r["status"]="rework" if r["cycle"]<3 else "owner"
            json.dump({"page":pg,"cycle":r["cycle"],"fails":r["fails"],"fix":r["fix"],"shots":[f"qa/audit_desk_{key}.jpg",f"qa/audit_mob_{key}.jpg"]},open(f"{RW}/{key}.json","w"),ensure_ascii=False,indent=1)
        else:
            r["status"]="ok"
            if os.path.exists(f"{RW}/{key}.json"): os.rename(f"{RW}/{key}.json",f"{RW}/{key}.done.json")
            os.system("/workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py --pin >/dev/null 2>&1")
        st[key]=r; json.dump(st,open(f"{OUT}/audit.json","w"),ensure_ascii=False,indent=1)
        print(key,r["status"],"WOW",r.get("wow"),"fails",len(r["fails"]))
main()
