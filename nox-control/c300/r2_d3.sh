cd /workspace/nox
cp -n web/site/qa/registry.json web/site/qa/registry.json.bak_r2_1
python3 - <<'P'
import json
f='/workspace/nox/web/site/qa/registry.json'; r=json.load(open(f))
N={
'constructor':('конструктор страниц','Framer, Webflow, Figma, Builder.io, Wix Studio','холст с блоками, панель свойств, drag-and-drop, адаптив-превью'),
'pdf':('PDF и документы','Acrobat, Preview, Foxit, PDF Expert, Notion','рендер страниц, миниатюры, панель аннотаций, поиск, масштаб'),
'assistant':('помощник/задачи и код','VS Code web, Cursor, GitHub Codespaces, Linear, Todoist','боковая панель, командная палитра, вкладки, терминал, дерево файлов'),
'intents':('намерения и команды','Raycast, Alfred, Spotlight, Linear, Superhuman','командная палитра, быстрые действия, горячие клавиши, группы команд'),
'models':('модели ИИ','LM Studio, Ollama, Hugging Face, Replicate, Civitai','карточки моделей, размер/квантование, загрузка, статусы, бенчмарки'),
'scene':('сцены и обои','Apple Wallpapers, Wallpaper Engine, Unsplash, Lively','крупные превью, живые сцены, переключатель, предпросмотр'),
'effects':('эффекты','Apple Wallpapers, Wallpaper Engine, Shadertoy, CodePen','живые превью эффектов, ползунки параметров, пресеты'),
'widgets':('виджеты','Glance, Apple Widgets, Notion widgets, Home Assistant','сетка карточек-виджетов, перетаскивание, размеры, настройки'),
'about':('о системе','Apple About This Mac, macOS System Settings, Linear','сводка системы, версия, ресурсы, лицензии, чистая иерархия'),
'integrations':('интеграции','Zapier, Make, n8n, Notion, Slack apps','каталог коннекторов, статус подключения, поиск, категории'),
'glance':('сводка Glance','Glance, Home Assistant, Apple Home, Grafana','панель сводки, карточки метрик, обновление в реальном времени'),
'install':('установка','Ollama, Docker Desktop, Vercel, Homebrew','шаги установки, копирование команд, статус, платформы'),
}
for k,(n,refs,pat) in N.items():
    r['sections'].setdefault(k,{"name":n,"top10_refs":[x.strip() for x in refs.split(',')],"markers":["vendor/"],"patterns":pat,"commands":["health","svc.status"]})
json.dump(r,open(f,'w'),ensure_ascii=False,indent=1)
print(len(r['sections']))
P
# колонка связи с ИИ
cp -n r2_reg.py r2_reg.py.bak_r2_1
python3 - <<'P'
f='/workspace/nox/r2_reg.py'; s=open(f).read()
if 'def aiLink' not in s:
    s=s.replace("def rw(p):","""def aiLink(p):
    try: t=open(f"{S}/{p}.html",encoding='utf-8',errors='replace').read()
    except Exception: return 'нет файла'
    for m in re.findall(r'<script[^>]+src=[\\"\\']([^\\"\\'?#]+)',t):
        if m.startswith(('http','//')): continue
        try: t+=' '+open(os.path.join(S,m.lstrip('/').replace('web/','',1)) if m.startswith('/') else os.path.join(S,m),encoding='utf-8',errors='replace').read()
        except Exception: pass
    h=[k for k in ('/api/chat','NOXcmd','/api/cmd','/glm') if k in t]
    return ('да: '+' '.join(h)) if h else 'нет'
def rw(p):""",1)
    s=s.replace('"| Страница | Статус | A/R/U (медиана) | vendor | handmade | Мёртвые кнопки | п.23 | Проверено |", "|---|---|---|---|---|---|---|---|"','"| Страница | Статус | A/R/U (медиана) | vendor | handmade | Мёртвые кнопки | п.23 | Связь с ИИ | Проверено |", "|---|---|---|---|---|---|---|---|---|"')
    s=s.replace('нет аудита | - | - | - | - | - | - |"','нет аудита | - | - | - | - | - | " + aiLink(p) + " | - |"')
    s=s.replace("{it.get('23',{}).get('status')} | {r.get('ts')} |","{it.get('23',{}).get('status')} | {aiLink(p)} | {r.get('ts')} |")
    open(f,'w').write(s)
P
python3 r2_reg.py && grep -c "" web/site/qa/registry.md; sed -n 7,50p web/site/qa/registry.md | cut -c1-160
# очередь аудитов под flock
cat > /workspace/nox/r2_queue.sh <<'Q'
#!/bin/bash
for p in "$@"; do
 flock /tmp/qaa.lock nice -n 15 /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py $p.html >> /tmp/r2_audit.log 2>&1
 echo "DONE_$p $(date +%T)" >> /tmp/r2_audit.log
done
Q
chmod +x /workspace/nox/r2_queue.sh
setsid nohup /workspace/nox/r2_queue.sh cinema photo atlas index news chat constructor pdf assistant intents models scene effects widgets about integrations glance install >/dev/null 2>&1 < /dev/null &
sleep 1; pgrep -fa r2_queue | head -2
