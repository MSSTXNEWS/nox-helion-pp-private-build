# NOX V16 · Реальная проверка WOW / NO-LOSS FIX

**Дата:** 2026-10-28. **Состояние:** source-integrated candidate; **Windows EXE и E07 НЕ ПРИНЯТЫ**.

Этот пакет — адресный патч к PR60 (base commit `7089da979cc35a148688d5c77f3ebbf2577506db`), НЕ замена успешного R13 NSIS и НЕ релиз. Обновлённые исходники публикуются отдельным GitHub PR. Поставщики исходников WOW PR44/38/14/15 сохранены, оригинальный D02 нетронут.

## Фактически исправлено

1. `integrations/creative/stage_creative.py`: **проверяет четыре SHA D02 до любой записи** и обеспечивает откат исходных WPF/HTML при ошибке. Проверяет отсутствие конфликтов маршрутов, комплект UI-файлов, допустимый жизненный цикл окна. Никакой перепаковки исходного Python EXE.
2. `integrations/wow200/stage_wow200.py`: **пинует неизменённый Git SHA-1 самого реестра доноров**, ровно 56 Git blobs, обязательное наличие ключевых реальных скриптов; неполные/фальшивые записи не проходят. Все пути и blob SHA проверяются до копирования. Применение HTML и копирование FX обратимы при ошибке. Всё содержимое донорских файлов сохраняется без правок.
3. `runtime/home-scene.mjs`: подключает существующий PR30 `installNoxCinemaFX` к **реальным HELION + 8 CoreID элементам оригинальной R13 HOME**. Ровно девять, в каноническом порядке; другой DOM → HOLD. Не добавляет новый renderer/bus/процесс/модель; источник статусов пока idle, без фальшивого GPU/обучения. Offscreen pause/Reduced Motion/ECO/MAX используют прежний renderer.
4. `runtime/home-guard.css`: PR30 никогда не сдвигает координаты/кликабельность оригинальных ядер; декоративные слои не принимают нажатия.
5. Автоматические отрицательные тесты для повреждённой графики, неполного manifest, изменённого blob, конфликтов маршрутизатора, rollback и недопустимого CoreID. JS source fixture проверяет подключение, отключение и восемь имён; native EXE отдельно не проверен.

## Что реально в установленном EXE НЕ доказано

- GitHub Actions последних веток завершались в первые секунды **без единого шага**; первопричина не установлена. Нельзя считать это тестом компилятора, исходников или GPU. GitHub Actions billing/usage and runner restrictions — гипотезы, не установленный диагноз.
- R13 успешный диагностический NSIS SHA-256 `44c72980f8999772fbef27eb47ca34f4329f02b1be999c06a0a56cd633058aa3`; источник патча в новом PR **не является новым проверенным EXE**.
- Финальное E06 WPF↔Python↔Ollama streaming + остановка, P03 реальная загрузка 15–20+ pinned моделей, P04 GPU training/checkpoints, P05 live events/SPACE, real Persona video, real 3D/video generation, FHD/4K/мобильный HTTPS + проектор и E07 Windows same-SHA acceptance: HOLD.
- Каталог 200 ID и 56 файлов — **не 200 визуально принятых эффектов**. Первые 50 — пресеты рабочих маршрутов, 51–200 вторичные cinematic cues/compositions; новая девятисферная сцена R13 пока только JS source/staging acceptance.

## Инструкция интегратору №6 / QA №7

1. Взять **точный** неизменённый R13 исходный staging checkout, не менять оригинальный R13 EXE, основную ветку, D02/Persona.
2. В том же disposable source tree выполнить `integrations/creative/stage_creative.py`, затем `integrations/wow200/stage_wow200.py`, только с owner-approved manifest/бинарным payload и подтверждённым SourceLock.
3. Провести Python и Node unit tests; сборка Windows: WPF/WebView2 + original Python diagnostic + Creative worker + штатный NSIS. Сначала исправить *причину* zero-step GitHub Actions, не переписывать рабочий код без logs.
4. На чистом Windows провести install→start→uninstall/update/rollback, сценарии D02 девяти объектов и WOW вторичных экранов, CPU/GPU/RAM/VRAM/temperature, реальное локальное inference/ComfyUI FFmpeg, keyboard/touch 320/390/800×480 и многомониторный проектор. Записать один конечный EXE SHA и независимый E07 acceptance.
5. При несовпадении SourceLock, SHA любой графики/manifest или недоступности native provider — HOLD, без подделки процентов.

## Семь доказательных индикаторов

P01/D02 **Н/Д**, P02/live AI **Н/Д**, P03/model downloads **Н/Д**, P04/GPU **Н/Д**, P05/events **Н/Д**, E06/combined Windows **HOLD**, E07/same-SHA acceptance **NOT_RUN**; общий взвешенный **Н/Д**. Эти значения не являются оценкой инженерной работы, только статусом доказанной приёмки.