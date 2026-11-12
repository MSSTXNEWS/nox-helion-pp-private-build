# NOX HELION — WEB WOW V25: единая сборка без потерь

**Статус: подготовлен воспроизводимый сборщик исходников; реальный объединённый WEB ещё требует запуска на архивных файлах и OneHost/Windows QA.** Это не второе приложение, не установка моделей и не демонстрация вместо NOX.

## Источники

1. Основной WEB V25.1: архив `NOX_HELION_WEB_V25_1_CANDIDATE_20261112.zip` из ChatGPT Library. Сохраняет оригинальные D02/HOME, 14 миров, cinematic presets, страницы и дизайнерские токены. PR241 — [оригинальные WOW кандидаты](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/241).
2. CHAT V25 из живой системы в `C:\NOX`: [NOX_CHAT_V25_SOURCES_PC_20261112.zip](https://drive.google.com/file/d/1bORWgKORNkeFkWIEIsWhSKq6sQJ8f_M6/view).
3. CHAT V24 для отсутствующих зависимостей: [NOX_CHAT_V24_SOURCES_20261112.zip](https://drive.google.com/file/d/1XfWLP4wrFzvKioxdbZH-adAgwJZ9n3Nu/view).
4. ONEPASS V2: [готовый проверенный ZIP](https://drive.google.com/file/d/1TWXd7YSufzRjNF2MCydVEqGYzVHw2Q6x/view), источник независимой приёмки. Вход в merge как кодовый overlay не подменяет тестирование.

## Запуск на Windows (проверка + staging, не production)

Сохранить три исходных ZIP в `C:\NOX\incoming`; оба скрипта из этой папки GitHub — в одну папку на ПК. Затем в CMD выполнить:

```cmd
CALL MERGE_NOX_WEB_WOW_STAGING.cmd
```

Сборщик: (1) проверяет CRC/безопасность ZIP и находит корни сайтов, (2) не изменяет `C:\NOX\helion`, `C:\NOX\lora`, `C:\NOX\agents`, Ollama, порт :8766 или рабочие процессы, (3) берёт оригинальный WEB V25.1, (4) заменяет только `chat.html` / `memory.html` канонической версией V25 и добавляет реально используемые локальные зависимости, (5) V24 используется только как резерв отсутствующего, (6) при конфликте общего JS/CSS выдаёт `HOLD_CONFLICTS`, не выбирает случайный файл, (7) сохраняет манифест SHA в `C:\NOX\builds\NOX_WEB_WOW_V25_STAGING\NOX_MERGE_RECEIPT.json`.

При исходном `SOURCE_MERGED_PHYSICAL_QA_HOLD` следующим шагом необходимы настоящие Windows/OneHost/S03/STOP/Orbit14/WOW30/voice/cinema тесты и владелец релизного SourceLock. Этот инструмент **не называет локальное совмещение HTML нейронным обучением или production-релизом**. Копирование staging поверх действующего сайта запрещено без no-loss check и резервной копии.

## Новая каноническая файловая схема

`C:\NOX\helion` — действующий NOX, `C:\NOX\incoming` — исходные архивы и патчи, `C:\NOX\builds` — изолированная сборка, `C:\NOX\archive` — исторические резервные копии, `C:\NOX\lora` — обученные активы, `C:\NOX\agents` — сервисные исполнители. Совместимые старые пути через junctions не удалять до проверки. `ROLLBACK_20261112.ps1` не восстанавливает удалённый мусор и дубль Qwen.

**Незакрытые ворота:** проверить исходные архивы на конкретном Windows, убедиться в наличии работы :8766, OneHost/voice/S03/STOP, физическая Windows приёмка. PR и тесты не являются этим доказательством.
