python3 - <<'P'
import json,os,time
R="/workspace/nox/web/site/qa/rework/"
N={
"music":["Ручной просмотр S5, 03:55 (после .fixed). Прогресс: появились настоящие обложки (Свободная музыка), плеер в стекле. Остаётся: шапка сдвинута влево и обрезана («ТЧЕР»), иконки по центру смещены относительно чёрного солнца — общий дефект шапки на music/news/studio (на cinema нормально): проверить ширину шапки/overflow-x у страниц; плавающий чип «МУЗЫКА / МУЗЫКА» дублирует название; волна wavesurfer не видна."],
"news":["Ручной просмотр S5, 03:55. Правая лента с миниатюрами стала лучше, но: шапка сдвинута и обрезана («ТЧЕР»), два блока нижнего ряда по-прежнему пустые прямоугольники без картинки и заголовка (пункт 8/честные статусы); карточка со скриншотом кода вместо новости выглядит как баг. Исправить обе вещи."],
"studio":["Ручной просмотр S5, 03:55. Прогресс: строка промпта поднята, кнопка «Создать» видна. Остаётся: шапка сдвинута и обрезана («ТЧЕР»), центральная мозаика пустых тёмных плиток с чёрным солнцем — как у Midjourney нужна masonry-лента реальных работ (из /img/ или примеров) или одна пустая карточка-подсказка; заголовок «Фотостудия» слит с шапкой."],
"cinema":["Ручной просмотр S5, 03:55. Страница визуально не изменилась после .fixed: по-прежнему нет рядов постеров под героем (Netflix: «Продолжить просмотр», «Популярное», «Новое», Swiper, постеры 2:3), плашки «Jellyfin: не настроен» и «Метаданные TMDB» остаются поверх. Вернуть до внесения рядов."]}
for k,v in N.items():
    f=R+k+".json"
    j=json.load(open(f)) if os.path.exists(f) else {"page":k+".html","cycle":0,"fails":[]}
    j["s5_review"]={"ts":time.strftime("%F %T"),"notes":v}
    j["fails"]=[x for x in j.get("fails",[]) if not str(x.get("item","")).startswith("РУЧНОЙ")]+[{"item":"РУЧНОЙ ПРОСМОТР S5 (приоритетнее авто-замечаний)","detail":v}]
    json.dump(j,open(f,"w"),ensure_ascii=False,indent=1)
print("ok")
P
cat > /tmp/s5v.py <<'P'
import sys,json,base64,urllib.request
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader']); pg=b.new_page(viewport={'width':1440,'height':900}); pg.goto('http://localhost:8091/web/index.html',wait_until='load'); pg.wait_for_timeout(4000); jpg=pg.screenshot(type='jpeg',quality=55); b.close()
d="data:image/jpeg;base64,"+base64.b64encode(jpg).decode()
body={"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":d}},{"type":"text","text":'Оцени экран. Ответь строго JSON {"wow":0-10,"A":0-10,"R":0-10,"U":0-10,"handmade":false}'}]}],"max_tokens":1500,"temperature":0.2,"chat_template_kwargs":{"enable_thinking":False}}
rq=urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",json.dumps(body).encode(),{"Content-Type":"application/json"})
try:
    r=json.loads(urllib.request.urlopen(rq,timeout=300).read()); print("OUT: VISION",json.dumps(r["choices"][0]["message"],ensure_ascii=False)[:500])
except Exception as e: print("OUT: VISIONERR",str(e)[:300])
P
/workspace/nox/venv/bin/python /tmp/s5v.py 2>&1 | tail -3 | cut -c1-600
