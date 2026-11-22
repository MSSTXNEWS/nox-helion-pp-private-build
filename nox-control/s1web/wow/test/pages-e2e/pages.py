# ---------------- Главная ----------------
page('index.html','home','ГЛАВНАЯ','nox-p-home.js','''
<div class="ph"><div><span class="kick mono">Палуба · состояние систем</span><h1>Главная</h1></div>
  <div class="acts"><span class="tag" id="auto">ОПРОС КАЖДЫЕ 15 С</span><span class="seg"><button type="button" id="refresh"><sl-icon library="tabler" name="refresh"></sl-icon>Опросить сейчас</button></span></div></div>
<section class="card" aria-label="Сводка"><div class="sum"><i class="led" id="sumLed"></i><b id="sumText" style="font:500 14px var(--head);letter-spacing:.12em">ПРОВЕРКА…</b><span class="muted mono" id="sumTime"></span></div></section>
<div class="grid" id="svc" aria-live="polite"></div>
<div class="grid">
  <section class="card c4"><h2>Скорость и кэш <span class="r mono" id="spMs"></span></h2><div id="speed" class="muted">Загрузка…</div></section>
  <section class="card c4"><h2>Память NOX <a class="tag" href="memory.html">Открыть</a></h2><div id="memBox" class="muted">Загрузка…</div></section>
  <section class="card c4"><h2>Резюме прошлой сессии</h2><div id="resume" class="muted">Загрузка…</div></section>
</div>
<nav class="seg quick" aria-label="Быстрый переход"><a href="chat.html">Резонанс</a><a href="projects.html">Проекты</a><a href="memory.html">Память</a><a href="training.html">Обучение</a><a href="models.html">Ядро</a><a href="system.html">Система</a><a href="settings.html">Настройки</a></nav>
''')

# ---------------- Проекты и задачи ----------------
page('projects.html','proj','ПРОЕКТЫ','nox-p-projects.js','''
<div class="ph"><div><span class="kick mono">Задачи · сроки · календарь</span><h1>Проекты</h1></div>
  <div class="acts"><span class="seg" role="group" aria-label="Вид"><button type="button" id="vBoard" aria-pressed="true"><sl-icon library="tabler" name="layout-kanban"></sl-icon>Доска</button><button type="button" id="vCal" aria-pressed="false"><sl-icon library="tabler" name="calendar"></sl-icon>Календарь</button></span>
  <span class="seg" role="group" aria-label="Данные"><button type="button" id="exp"><sl-icon library="tabler" name="download"></sl-icon>JSON</button><button type="button" id="expIcs"><sl-icon library="tabler" name="calendar-down"></sl-icon>ICS</button><button type="button" id="imp"><sl-icon library="tabler" name="upload"></sl-icon>Импорт</button></span></div></div>
<input type="file" id="impFile" accept=".json,application/json" hidden>
<form class="card" id="addForm" autocomplete="off"><div class="frow">
  <label class="fld grow" style="flex:3 1 220px"><span>Новая задача</span><input type="text" id="aTitle" maxlength="200" placeholder="Что нужно сделать" required></label>
  <label class="fld grow"><span>Проект</span><input type="text" id="aProj" maxlength="40" list="projList" placeholder="Общий"></label>
  <label class="fld grow"><span>Владелец</span><input type="text" id="aOwner" maxlength="40" list="ownList" placeholder="Кто отвечает"></label>
  <label class="fld"><span>Срок</span><input type="date" id="aDue"></label>
  <label class="fld"><span>Колонка</span><select id="aCol"></select></label>
  <span class="seg" style="align-self:flex-end"><button type="submit"><sl-icon library="tabler" name="plus"></sl-icon>Добавить</button></span></div>
  <datalist id="projList"></datalist><datalist id="ownList"></datalist></form>
<div class="card flat"><div class="frow"><span class="mono muted">Проект:</span><span id="chips" class="frow"></span><span style="flex:1"></span><button type="button" class="tag" id="ntag">УВЕДОМЛЕНИЯ</button><span class="tag" id="apiTag">API ЗАДАЧ: ПРОВЕРКА</span><span class="seg" id="apiAct" hidden><button type="button" id="apiImp">Импорт из NOX</button></span></div></div>
<div class="board" id="vBoardBox"></div>
<section class="card" id="vCalBox" hidden><div id="cal"></div><p class="muted" style="margin:8px 0 0;font-size:12px">Клик по дню создаёт событие или задачу; события и сроки карточек можно перетаскивать на другой день.</p></section>
<sl-dialog id="dlg" class="nox-dl" label="Задача"><form class="dlg" id="dForm" autocomplete="off">
  <div class="frow"><label class="fld"><span>Тип</span><select id="dKind"><option value="task">Задача</option><option value="event">Событие</option></select></label><label class="fld grow"><span>Название</span><input type="text" id="dTitle" maxlength="200" required></label></div>
  <div class="frow"><label class="fld grow"><span>Проект</span><input type="text" id="dProj" maxlength="40" list="projList"></label><label class="fld grow"><span>Владелец</span><input type="text" id="dOwner" maxlength="40" list="ownList"></label></div>
  <div class="frow"><label class="fld"><span>Срок / дата</span><input type="date" id="dDue"></label><label class="fld" id="dTimeW"><span>Время</span><input type="time" id="dTime"></label><label class="fld" id="dColW"><span>Колонка</span><select id="dCol"></select></label></div>
  <label class="fld"><span>Заметка</span><textarea id="dNote" maxlength="2000"></textarea></label>
  <button type="submit" hidden></button></form>
  <div class="seg" slot="footer"><button type="button" id="dSave">Сохранить</button><button type="button" id="dDel" style="color:rgb(var(--mg))">Удалить</button><button type="button" id="dCancel">Отмена</button></div></sl-dialog>
''',CSS='<script src="./vendor/nox-wow/sortablejs/Sortable.min.js"></script>\n<script src="./vendor/nox-extra/fullcalendar.global.min.js"></script>\n<script src="./vendor/dexie/dexie.min.js"></script>\n')

# ---------------- Память ----------------
page('memory.html','mem','ПАМЯТЬ','nox-p-memory.js','''
<div class="ph"><div><span class="kick mono">Что NOX вспомнил</span><h1>Память</h1></div>
  <div class="acts"><span class="tag" id="mStats">СТАТИСТИКА…</span><span class="seg"><button type="button" id="mRefresh"><sl-icon library="tabler" name="refresh"></sl-icon>Обновить</button></span></div></div>
<form class="card" id="qForm" role="search"><div class="frow"><label class="fld grow" style="flex:1 1 260px"><span>Поиск по памяти NOX</span><input type="search" id="q" maxlength="300" placeholder="Например: проект, язык, сервер" autocomplete="off"></label>
  <span class="seg" style="align-self:flex-end"><button type="submit"><sl-icon library="tabler" name="search"></sl-icon>Найти</button></span></div></form>
<div class="splitwrap" id="split">
  <section class="card" id="paneL"><h2>Найденное <span class="r mono" id="rInfo"></span></h2><div id="results"><div class="empty">Введите запрос: NOX покажет факты, эпизоды и записи профиля, которые он помнит. Каждую запись можно подтвердить, исправить или удалить; удаление мягкое, его можно откатить.</div></div></section>
  <section class="card" id="paneR"><h2>Ядро памяти <span class="r mono" id="coreInfo"></span></h2><div id="core" class="muted">Загрузка…</div></section>
</div>
<div class="grid">
  <section class="card c12"><h2>Журнал правок владельца <span class="r mono" id="jInfo"></span></h2><div id="journal" class="scroll-x muted">Загрузка…</div></section>
  <section class="card c12"><h2>Вложения: PDF и фото <span class="r mono" id="vInfo"></span></h2>
    <div class="frow"><span class="seg"><button type="button" id="vPick"><sl-icon library="tabler" name="paperclip"></sl-icon>Открыть файлы</button></span><input type="file" id="vFile" multiple accept="application/pdf,image/*" hidden><span class="muted" style="font-size:12.5px">PDF листаются здесь (PDF.js), фото открываются во весь экран (PhotoSwipe). Файлы остаются в браузере.</span></div>
    <div id="gallery" class="gallery"></div>
    <div id="pdfBox" hidden><div class="frow" style="margin:8px 0"><span class="seg"><button type="button" id="pPrev" aria-label="Предыдущая страница"><sl-icon library="tabler" name="chevron-left"></sl-icon></button><button type="button" id="pNext" aria-label="Следующая страница"><sl-icon library="tabler" name="chevron-right"></sl-icon></button></span><span class="mono" id="pInfo"></span><span style="flex:1"></span><button type="button" class="tag" id="pClose">Закрыть PDF</button></div><div class="scroll-x"><canvas id="pdfCv" style="max-width:100%;background:#fff"></canvas></div></div></section>
</div>
<sl-dialog id="dlgC" class="nox-dl" label="Исправить запись"><div class="dlg"><div class="mono muted" id="cRef"></div><label class="fld"><span>Новый текст</span><textarea id="cText" maxlength="2000"></textarea></label></div>
  <div class="seg" slot="footer"><button type="button" id="cSave">Сохранить</button><button type="button" id="cCancel">Отмена</button></div></sl-dialog>
<sl-dialog id="dlgD" class="nox-dl" label="Удалить запись"><div class="dlg"><div class="mono muted" id="dRef"></div><p id="dText"></p><p class="muted">Удаление мягкое: запись исчезнет из ответов, но её можно вернуть из журнала правок.</p></div>
  <div class="seg" slot="footer"><button type="button" id="dOk" style="color:rgb(var(--mg))">Удалить</button><button type="button" id="dNo">Отмена</button></div></sl-dialog>
''',CSS='<link rel="stylesheet" href="./vendor/nox-extra/photoswipe.css">\n<script src="./vendor/nox-extra/fuse.min.js"></script>\n<script src="./vendor/split.js/split.min.js"></script>\n')

# ---------------- Обучение ----------------
page('training.html','train','ОБУЧЕНИЕ','nox-p-training.js','''
<div class="ph"><div><span class="kick mono">Прогресс · данные владельца</span><h1>Обучение</h1></div>
  <div class="acts"><span class="seg"><button type="button" id="tRefresh"><sl-icon library="tabler" name="refresh"></sl-icon>Проверить снова</button><button type="button" id="tJsonl"><sl-icon library="tabler" name="download"></sl-icon>Правки как JSONL</button></span></div></div>
<section class="card"><h2>Прогресс обучения модели <span class="r mono" id="pState"></span></h2><div id="prog" class="muted">Проверка…</div></section>
<div class="grid">
  <section class="card c6"><h2>Состав памяти</h2><div id="chMem" class="chart" style="min-height:220px"></div><div id="chMemNote" class="muted"></div></section>
  <section class="card c6"><h2>Действия владельца <span class="r mono" id="actInfo"></span></h2><div id="chAct" class="chart" style="min-height:220px"></div><div id="chActNote" class="muted"></div></section>
  <section class="card c12"><h2>Исправления как обучающие пары <span class="r mono" id="pairInfo"></span></h2><div id="pairs" class="scroll-x muted">Загрузка…</div></section>
</div>
''',TAIL='<script src="./vendor/nox-extra/echarts.min.js"></script>\n')

# ---------------- Ядро ----------------
page('models.html','core','ЯДРО','nox-p-models.js','''
<div class="ph"><div><span class="kick mono">Модели · тиры · серверы</span><h1>Ядро</h1></div>
  <div class="acts"><span class="tag" id="cTime"></span><span class="seg"><button type="button" id="cRefresh"><sl-icon library="tabler" name="refresh"></sl-icon>Обновить</button></span></div></div>
<div class="grid" id="tiers"></div>
<div class="grid">
  <section class="card c6"><h2>Модели шлюза <span class="r mono" id="mInfo"></span></h2><div id="models" class="scroll-x muted">Загрузка…</div></section>
  <section class="card c6"><h2>Параметры llama-server <span class="r mono">/glm/props</span></h2><div id="props" class="muted">Загрузка…</div></section>
  <section class="card c6"><h2>Проверка генерации</h2><p class="muted">Короткий запрос к модели через шлюз: покажет, что цепочка шлюз → llama отвечает, и сколько это занимает.</p><div class="frow"><span class="seg"><button type="button" id="gen"><sl-icon library="tabler" name="bolt"></sl-icon>Запустить проверку</button></span></div><div id="genOut" style="margin-top:8px"></div></section>
  <section class="card c6"><h2>Активные запросы <span class="r mono" id="actN"></span></h2><div id="active" class="muted">Загрузка…</div></section>
  <section class="card c12"><h2>Серверы и службы</h2><div id="srv" class="scroll-x muted">Загрузка…</div></section>
</div>
''')

# ---------------- Система ----------------
page('system.html','sys','СИСТЕМА','nox-p-system.js','''
<div class="ph"><div><span class="kick mono">Метрики · живые графики</span><h1>Система</h1></div>
  <div class="acts"><span class="tag" id="sState">ОПРОС КАЖДЫЕ 5 С</span><span class="seg"><button type="button" id="sPause" aria-pressed="false"><sl-icon library="tabler" name="player-pause"></sl-icon><span>Пауза</span></button><button type="button" id="sClear"><sl-icon library="tabler" name="eraser"></sl-icon>Очистить</button><button type="button" id="sCsv"><sl-icon library="tabler" name="download"></sl-icon>CSV</button></span></div></div>
<div class="grid" id="tiles"></div>
<div class="grid">
  <section class="card c6"><h2>Отклик служб, мс <span class="r mono" id="lat1"></span></h2><div id="ch1" class="chart"></div></section>
  <section class="card c6"><h2>Браузер: кадры/с и память JS <span class="r mono" id="lat2"></span></h2><div id="ch2" class="chart"></div></section>
  <section class="card c6"><h2>Сервер: ресурсы <span class="r mono">/api/pc-metrics</span></h2><div id="pc" class="muted">Проверка…</div></section>
  <section class="card c6"><h2>Это устройство</h2><div id="dev" class="muted"></div></section>
  <section class="card c12"><h2>Журнал событий</h2><ul class="mono-log" id="log"><li class="muted">Событий пока нет</li></ul></section>
</div>
''',CSS='<link rel="stylesheet" href="./vendor/fx/uPlot.min.css">\n',TAIL='<script src="./vendor/fx/uPlot.iife.min.js"></script>\n')

# ---------------- Настройки ----------------
page('settings.html','set','НАСТРОЙКИ','nox-p-settings.js','''
<div class="ph"><div><span class="kick mono">Внешний вид · режимы</span><h1>Настройки</h1></div>
  <div class="acts"><span class="seg"><button type="button" id="sExp"><sl-icon library="tabler" name="download"></sl-icon>Экспорт</button><button type="button" id="sImp"><sl-icon library="tabler" name="upload"></sl-icon>Импорт</button><button type="button" id="sReset" style="color:rgb(var(--mg))"><sl-icon library="tabler" name="restore"></sl-icon>Сбросить</button></span></div></div>
<input type="file" id="sFile" accept=".json,application/json" hidden>
<div class="grid">
  <section class="card c6 setg"><h3 class="mono">Планета фона</h3><div class="planets big" id="planets" role="radiogroup" aria-label="Планета"></div><p class="note mono" id="planetNote"></p></section>
  <section class="card c6 setg"><h3 class="mono">Цвет неона</h3><div class="seg swatches" id="accent" role="radiogroup" aria-label="Цвет неона"></div>
    <h3 class="mono">Космос</h3><div class="seg opt" data-opt="space" role="radiogroup" aria-label="Яркость космоса"><button role="radio" data-v="on">Мягко</button><button role="radio" data-v="high">Ярко</button></div>
    <h3 class="mono">Плотность интерфейса</h3><div class="seg opt" data-opt="dens" role="radiogroup" aria-label="Плотность"><button role="radio" data-v="cozy">Просторно</button><button role="radio" data-v="tight">Компактно</button></div></section>
  <section class="card c6 setg"><h3 class="mono">Резонанс (чат)</h3>
    <div class="seg opt" data-opt="proto" role="radiogroup" aria-label="Протокол чата"><button role="radio" data-v="classic">Классический /api/chat</button><button role="radio" data-v="glm">Шлюз GLM</button></div>
    <div class="seg opt" data-opt="enter" role="radiogroup" aria-label="Отправка"><button role="radio" data-v="enter">Enter</button><button role="radio" data-v="ctrl">Ctrl+Enter</button></div></section>
  <section class="card c6 setg"><h3 class="mono">Голос</h3>
    <div class="seg opt" data-opt="speak" role="radiogroup" aria-label="Озвучка ответов"><button role="radio" data-v="off">Озвучка выкл</button><button role="radio" data-v="on">Озвучка вкл</button></div>
    <div class="seg opt" data-opt="lang" role="radiogroup" aria-label="Язык распознавания"><button role="radio" data-v="auto">Авто</button><button role="radio" data-v="ru">RU</button><button role="radio" data-v="es">ES</button></div>
    <div class="seg opt" data-opt="auto" role="radiogroup" aria-label="Автоотправка"><button role="radio" data-v="off">Текст в поле</button><button role="radio" data-v="on">Сразу отправлять</button></div>
    <p class="note mono" id="voiceStat">STT — · TTS —</p></section>
  <section class="card c12 setg"><h3 class="mono">Уведомления и напоминания</h3>
    <div class="frow"><span class="tag" id="nState">ПРОВЕРКА</span><span class="seg"><button type="button" id="nAsk"><sl-icon library="tabler" name="bell"></sl-icon>Разрешить уведомления</button><button type="button" id="nTest"><sl-icon library="tabler" name="bell-ringing"></sl-icon>Тестовое уведомление</button><button type="button" id="nToggle" aria-pressed="true"><sl-icon library="tabler" name="alarm"></sl-icon><span>Напоминания по срокам: вкл</span></button></span></div>
    <p class="note" id="nNote"></p></section>
  <section class="card c12 setg"><h3 class="mono">О сборке</h3><p class="note">Текстуры планет — Solar System Scope, CC BY 4.0 (данные NASA). Шрифты Inter, Manrope, JetBrains Mono (OFL). Библиотеки: three, postprocessing, motion, tsparticles, Sortable, FullCalendar, uPlot, ECharts, Shoelace, Swiper, Tabler Icons (MIT/BSD/Zlib). Настройки хранятся только в этом браузере.</p></section>
</div>
''')
