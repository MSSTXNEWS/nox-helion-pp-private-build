# NOX HELION — единый WEB WOW V25.1 + CHAT V25/V24 + ONEPASS V2

**Состояние: проверен исходный сборщик и целостность оригинальных архивов; физическая интеграция на ПК и релиз остаются HOLD.** Это развитие оригинального NOX, не второе приложение и не отдельная демонстрация. Единственная действующая установка — `C:\NOX\helion`.

## Реальные источники (Google Диск)

| Источник | Физический файл | Статус |
|---|---|---|
| Оригинальный WEB V25.1 | [NOX_HELION_WEB_V25_1_CANDIDATE_20261112.zip](https://drive.google.com/file/d/1cNt9FYth9K9dNihLi-ixIxdRgJy05mzV/view) | 292 ZIP-файла, структура проверена |
| Чат из ПК V25 | [NOX_CHAT_V25_SOURCES_PC_20261112.zip](https://drive.google.com/file/d/1bORWgKORNkeFkWIEIsWhSKq6sQJ8f_M6/view) | 66 740 477 байт; приватный архив, его внутреннее дерево здесь пока не проверено |
| Чат V24 (только резерв зависимостей) | [NOX_CHAT_V24_SOURCES_20261112.zip](https://drive.google.com/file/d/1XfWLP4wrFzvKioxdbZH-adAgwJZ9n3Nu/view) | 85 291 723 байта; приватный архив, внутреннее дерево не проверено |
| Приёмка и восстановление | [NOX_HELION_ONEPASS_V2_HARDENED_20261112.zip](https://drive.google.com/file/d/1TWXd7YSufzRjNF2MCydVEqGYzVHw2Q6x/view) | 302 ZIP-файла (292 site + 10 QA файлов), структура проверена |

**Установлено без распаковки:** все 292 записи исходного WEB совпадают с `site/` в ONEPASS V2 по имени, CRC32, распакованному размеру и ZIP-методу. Поэтому в кандидатном пакете **только одна копия WEB**, а из ONEPASS берутся только 10 оригинальных QA-файлов в `qa/onepass_v2_original/`, без вложенного второго WEB-архива. Оригинальный `SOURCE_MANIFEST.json` относится к WEB до замены чата и не считается доказательством приёмки объединения.

Репозитории и source-ветки: [WEB PR #241](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/241), [OneHost/Windows PR #162](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/162), [NOX PRIME / WEB merge PR #251](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/251).

## Один безопасный запуск на Windows

Поместить **четыре** оригинальных ZIP в `C:\NOX\incoming`, скачать `MERGE_NOX_WEB_WOW_STAGING.cmd` и `merge_nox_web_wow.py` из этой папки GitHub рядом друг с другом и вызвать в CMD:

```cmd
CALL MERGE_NOX_WEB_WOW_STAGING.cmd
```

Команда **не останавливает** `127.0.0.1:8766`, Ollama, тренировочный процесс, S03 или старый OneHost, не трогает `C:\NOX\helion` и не изменяет production.

**При успешном объединении:** `C:\NOX\builds\NOX_WEB_WOW_V25_STAGING\NOX_WEB_WOW_V25_UNIFIED_CANDIDATE.zip`, `site/`, `qa/onepass_v2_original/`, `NOX_MERGE_RECEIPT.json` со SHA всех файлов и `READ_ME.txt`. Если найден конфликт или недостающая зависимость, создаётся только манифест с `HOLD_CONFLICTS`; ZIP релиза не формируется. Существующую папку staging инструмент не перезаписывает.

**Ни один тест не называет `SOURCE_MERGED_PHYSICAL_QA_HOLD` полноценным релизом**. Обязательны OneHost/WebView2 live, голос, чат и история после рестарта, S03, STOP, 14 миров и проверка 10+10+10, Windows BuildID+SHA, GPU SAFE и независимая E07. Кодовый CI проверяет полную ZIP→ZIP процедуру на синтетических архивах, включая подмены, traversal и коллизии; архивы чата из закрытого Google Drive в GitHub Actions автоматически не передаются. Для физической проверки нужны реальные ZIP в доступной Windows-среде.

## Правило NO-LOSS

Канонический порядок: оригинальный WEB V25.1 → только проверенные отсутствующие зависимости V24 → CHAT V25 страницы и их зависимости → 10 оригинальных QA файлов ONEPASS в изолированной поддиректории. **V24 не может заменить страницы V25**, D02/index/орбиты защищены, конфликт одинаковых путей разных SHA не решается случайным выбором, новый backend и новая память не создаются. Использовать только актуальные пути `C:\NOX`; старые junctions сохраняются до независимой приёмки. Скрипт отката переезда `C:\NOX\archive\ROLLBACK_20261112.ps1` исторический, текущая сборка не вызывает его.

Последний проверенный статус всегда смотреть в GitHub Actions, не полагаться на слово «готово» в старых отчётах.
