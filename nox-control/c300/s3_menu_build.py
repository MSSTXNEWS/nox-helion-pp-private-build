import json, os, re, shutil, time
S = '/workspace/nox/web/site'
nav = json.load(open(S + '/nav.json'))
old_items = {i['file']: i for g in nav['groups'] for i in g['items']}
N = {  # file: (категория, название, иконка tabler, описание)
 'constructor.html': ('КОНСТРУКТОР','Конструктор','hierarchy-2','Собрать страницу из блоков'),
 'tools.html': ('КОНСТРУКТОР','Инструменты','tool','Набор утилит NOX'),
 'editor.html': ('КОНСТРУКТОР','Редактор','edit','Текст и код с помощью ИИ'),
 'forge.html': ('КОНСТРУКТОР','Кузница','hammer','Сборка и запуск проектов'),
 'cinema.html': ('КИНОТЕАТР','Кинозал','movie','Фильмы, сериалы и трейлеры'),
 'tv.html': ('КИНОТЕАТР','Проектор','device-tv','Большой экран для просмотра'),
 'games.html': ('КИНОТЕАТР','Игры','device-gamepad-2','Игры с персонажами NOX'),
 'studio.html': ('АТЕЛЬЕ','Ателье','brush','Создание изображений'),
 'photo.html': ('АТЕЛЬЕ','Фотостудия','photo','Редактор и обработка фото'),
 'assistant.html': ('ПОМОЩНИК','Помощник','checklist','Задачи и поручения NOX'),
 'calendar.html': ('ПОМОЩНИК','Календарь','calendar','Дела, события и напоминания'),
 'contacts.html': ('ПОМОЩНИК','Контакты','address-book','Люди и связи'),
 'mail.html': ('ПОМОЩНИК','Почта','mail','Письма и черновики'),
 'messenger.html': ('ПОМОЩНИК','Мессенджеры','messages','Чаты в одном месте'),
 'notifications.html': ('ПОМОЩНИК','Уведомления','bell','Оповещения и команды'),
 'browser.html': ('ПОМОЩНИК','Браузер','world-www','Веб-поиск через NOX'),
 'knowledge.html': ('ПОМОЩНИК','Знания','books','База знаний и поиск по ней'),
 'board.html': ('ДОСКА','Доска','layout-board','Идеи, схемы и заметки'),
 'ops.html': ('ДОСКА','Канбан','layout-kanban','Задачи по колонкам'),
 'intents.html': ('ДОСКА','Замыслы','bulb','Планы и намерения NOX'),
 'nexus.html': ('ДОСКА','Связи','topology-star-3','Карта связей проектов'),
 'chat.html': ('РЕЗОНАНС','Резонанс','message-circle','Разговор с NOX'),
 'consciousness.html': ('РЕЗОНАНС','Сознание','brain','Как NOX думает сейчас'),
 'selffeel.html': ('РЕЗОНАНС','Самочувствие','heartbeat','Состояние и настроение NOX'),
 'soul.html': ('РЕЗОНАНС','Душа','flame','Характер и ценности'),
 'organism.html': ('РЕЗОНАНС','Организм','dna-2','Органы и их нагрузка'),
 'growth.html': ('РЕЗОНАНС','Рост','trending-up','Чему NOX научился'),
 'models.html': ('РЕЗОНАНС','Ядро','cpu','Модели и их состояние'),
 'advisors.html': ('РЕЗОНАНС','Советники','users-group','Судьи и консультанты'),
 'music.html': ('МУЗЫКА','Музыка','music','Плеер и библиотека'),
 'voice.html': ('ГОЛОС','Голос','microphone','Разговор голосом'),
 'calls.html': ('ГОЛОС','Звонки','phone-call','Звонки и перевод речи'),
 'scene.html': ('ЦВЕТ СЦЕНЫ','Цвет сцены','palette','Мир, палитра и фон'),
 'effects.html': ('ЭФФЕКТЫ','Эффекты','sparkles','Анимации и качество'),
 'widgets.html': ('ВИДЖЕТЫ','Виджеты','layout-dashboard','Живые карточки на экране'),
 'news.html': ('ВИДЖЕТЫ','Новости','news','Лента новостей'),
 'atlas.html': ('ВИДЖЕТЫ','Атлас','map-2','Небо, карта и мир'),
 'map.html': ('ВИДЖЕТЫ','Карта','map','Карта мира'),
 'about.html': ('ВИДЖЕТЫ','О сборке','code','Библиотеки и лицензии'),
 'integrations.html': ('ВИДЖЕТЫ','Интеграции','plug-connected','Диск и внешние сервисы'),
 # шапка
 'dispatcher.html': ('СИСТЕМА','Диспетчер','activity','Процессы и задачи сервера'),
 'downloads.html': ('СИСТЕМА','Загрузки','download','Файлы и загрузки'),
 'training.html': ('СИСТЕМА','Обучение','school','Дообучение и журналы'),
 'memory.html': ('СИСТЕМА','Память','database','Что NOX помнит'),
 'system.html': ('СИСТЕМА','Система','server','Железо и датчики'),
 'projects.html': ('СИСТЕМА','Проекты','folders','Проекты и их статус'),
 'install.html': ('СИСТЕМА','Установка','device-desktop-down','Приложение и офлайн'),
 'settings.html': ('СИСТЕМА','Настройки','settings','Личность, голос, интерфейс'),
}
HEAD_ORDER = ['dispatcher.html','downloads.html','training.html','memory.html','system.html','projects.html','install.html','settings.html']
REDIR = {  # дубль -> куда ведёт
 'resonance.html':'chat.html','planets.html':'scene.html','creative.html':'studio.html','ai-learning.html':'training.html',
 'weights.html':'training.html','g01-status.html':'dispatcher.html','g07-hardware.html':'system.html','events.html':'calendar.html'}
DOCKPAGES = {'constructor.html','cinema.html','studio.html','assistant.html','board.html','chat.html','music.html','voice.html','scene.html','effects.html','widgets.html','settings.html','dispatcher.html','downloads.html','training.html','memory.html','system.html','projects.html','install.html'}
DOCK = ['КОНСТРУКТОР','КИНОТЕАТР','АТЕЛЬЕ','ПОМОЩНИК','ДОСКА','РЕЗОНАНС','МУЗЫКА','ГОЛОС','ЦВЕТ СЦЕНЫ','ЭФФЕКТЫ','ВИДЖЕТЫ']
def empty(f):
    p = S + '/' + f
    if not os.path.exists(p): return 'нет файла'
    t = open(p, encoding='utf-8', errors='ignore').read()
    if re.search(r'http-equiv=["\']refresh', t, re.I): return 'перенаправление'
    if re.search(r'СТРАНИЦА ПЕРЕНЕСЕНА', t): return 'перенесена'
    if len(t) < 3500: return 'пустая заглушка (<3.5 КБ)'
    if old_items.get(f, {}).get('soon') and t.count('\n') in (89, 90, 91, 92) and len(t) < 9000: return 'шаблон-заглушка «Скоро»'
    return ''
groups = {k: [] for k in DOCK + ['СИСТЕМА']}
hidden = []
for f, (cat, name, ic, desc) in N.items():
    why = empty(f)
    if why and f not in DOCKPAGES:
        hidden.append({'file': f, 'reason': why}); continue
    groups[cat].append({'file': f, 'name': name, 'title': 'NOX HELION · ' + name.upper(), 'icon': ic, 'desc': desc, 'soon': False})
groups['СИСТЕМА'].sort(key=lambda i: HEAD_ORDER.index(i['file']))
for f, to in REDIR.items(): hidden.append({'file': f, 'reason': 'дубль, ведёт на ' + to})
mapped = set(N) | set(REDIR) | {'index.html'}
for f in sorted(old_items):
    if f not in mapped: hidden.append({'file': f, 'reason': 'не в меню: ' + (empty(f) or 'без категории')})
shutil.copy(S + '/nav.json', S + '/nav.json.bak_s3_1') if not os.path.exists(S + '/nav.json.bak_s3_1') else None
out = {'groups': [{'group': k, 'items': groups[k]} for k in DOCK + ['СИСТЕМА'] if groups[k]], 'hidden': hidden}
out['pages'] = sum(len(g['items']) for g in out['groups']); out['soon'] = 0
json.dump(out, open(S + '/nav.json', 'w'), ensure_ascii=False, indent=1)
# перенаправления для дублей (бэкап .bak_s3_1)
nr = 0
for f, to in REDIR.items():
    p = S + '/' + f
    if not os.path.exists(p): continue
    t = open(p, encoding='utf-8', errors='ignore').read()
    if 'nox-s3-redirect' in t: continue
    shutil.copy(p, p + '.bak_s3_1')
    tag = '<meta name="nox-s3-redirect" content="%s"><meta http-equiv="refresh" content="0;url=%s"><script>location.replace("%s"+location.hash)</script>' % (to, to, to)
    t = re.sub(r'(<head[^>]*>)', r'\1' + tag, t, count=1, flags=re.I) if re.search(r'<head', t, re.I) else tag + t
    open(p, 'w', encoding='utf-8').write(t); nr += 1
# план
old_n = sum(len(g['items']) for g in nav['groups'])
lines = ['# План меню (S3, %s)' % time.strftime('%F'), '', 'Было пунктов в nav.json: %d (из них «Скоро»: %d). Стало: %d в 11 категориях нижней панели + шапке.' % (old_n, nav.get('soon', 0), out['pages']), '']
for g in out['groups']:
    lines.append('## ' + g['group'] + (' (шапка)' if g['group'] == 'СИСТЕМА' else ''))
    lines += ['- %s — %s · %s (%s)' % (i['file'], i['name'], i['desc'], i['icon']) for i in g['items']]
    lines.append('')
lines.append('## Скрыто из меню (файлы не удалены)')
lines += ['- %s — %s' % (h['file'], h['reason']) for h in hidden]
os.makedirs(S + '/qa', exist_ok=True)
open(S + '/qa/menu_plan.md', 'w', encoding='utf-8').write('\n'.join(lines))
print('MENU old=%d new=%d hidden=%d redirects=%d' % (old_n, out['pages'], len(hidden), nr))
for g in out['groups']: print(g['group'], [i['file'] for i in g['items']])
print('HIDDEN', [(h['file'], h['reason'][:20]) for h in hidden])
