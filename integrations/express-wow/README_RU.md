# NOX HELION V16 — EXPRESS WOW / Creative source integration

**Область только этого блока:** подключить существующую Creative Studio, WOW 001–200, базовую кинематографическую сцену HELION+8 CoreID, настоящее меню/RouteID и готовые локальные генерационные адаптеры к единственному WPF/WebView2 хосту. Не переделывать Ollama/SQLite/LoRA/датчики/NSIS чужих владельцев.

## Физические исправления

- Устранён выбор устаревшего WOW HOME-рендерера. Архив PR30/PR44 остаётся побайтово в `integrations/wow200/proposals/NOX-CINEMA-FX`, но **не является активным импортом**.
- Активный рендерер E01 из точных Git blobs `a0bc34add0990b3f70bdbfd94fe52615193a4c08` (JS) и `77417160147607f2d7350209b865d86bfe49abd0` (CSS) сохранён в `integrations/wow200/canonical`. `home-scene.mjs` импортирует только его. Таким образом реальные девять сфер используют одно определение состояний `noxFxState` / `noxFxMode`, а не старый `noxState`.
- `stage_wow200.py` проверяет весь старый 56-файловый пакет **и отдельно** оба Git blob SHA-1 активного владельца *до записи*. Изменения применяются на копии; при ошибке запись откатывается. Проверяются оригинальные четыре D02 SHA-256.
- `integrations/express-wow/apply_express.py`: один вход для последовательной передачи Creative+WOW в отдельную disposable R13 копию с JSON-отчётом. Не меняет исходный установленный EXE или `main`.
- Репозиторий уже содержит адаптеры ComfyUI/FFmpeg/Ollama/P03, original WOW secondary 51–200 и безопасное `nox.creative.navigate.v1` для первых 50 маршрутов. В этом блоке они **переиспользуются**, не пишутся повторно.

## Как применять

```powershell
python integrations/express-wow/apply_express.py --r13 C:\NOX\R13\R11 --repo C:\NOX\UNIFIED-SOURCE --out C:\NOX\WORK\NOX-WOW-EXPRESS
```

Запустить оригинальный E06 WPF/NSIS builder *после* прохождения source SHA gates и Windows P01 owner admission. `NOX-WOW-EXPRESS/R11` — подготовленное дерево, НЕ уже собранный EXE.

## Испытания и честная граница готовности

- Компонентные проверки Python с негативными данными/откатом и проверка JS-модуля проверяют **логику SourceLock/маршрутизации**, но не FPS, микрофон, GPU или installed EXE.
- Реальная Windows native `dotnet publish + NSIS clean install/update/rollback`, WebView2/E01 UI comparison, ComfyUI модель+видео, 5 Persona autoplay, физический проектор, full 10+10+10 и independent E07 same-SHA приёмка остаются HOLD.
- Никаких процентов «100%» без живой Windows и пользователей. 200 идентификаторов и 56 исходных файлов — **не** 200 подтверждённых runtime эффектов.

## Технический урок

**Ошибка:** исходники E01 и архивный PR30 оба сохранялись, но `home-scene.mjs` импортировал архив. **Исправление:** frozen native import-closure E01. **Экономия:** сохранён существующий рендерер, без третьего движка, без изменения D02 или rewrite host. **Защита:** exact-owner Git blobs + no-loss staging + negative regression tests.