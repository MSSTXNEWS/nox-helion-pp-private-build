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


## ФИЗИЧЕСКОЕ ОБЪЕДИНЕНИЕ, 12.11.2026 — SOURCE QA PASS, WINDOWS E07 HOLD

Четыре **реальных** приватных ZIP скачаны и прочитаны в изолированном Vercel Sandbox проекта `nox-helion-real-home-preview` (без доступа в рабочий C:\\NOX):

| Файл | Размер | SHA-256 |
|---|---:|---|
| WEB V25.1 | 12 899 679 | `a0db5a04287fff5ba677a247fbbe8c7937aeeae842aca5a8e3c40ab4fd086df4` |
| CHAT V25 PC | 66 740 477 | `1f9301d5555135e343143742e4274ec89f2333b17ad53a46fa3d29737c9ffdbc` |
| CHAT V24 | 85 291 723 | `c9229f7a4cfbfc2a342310039c9958028e50e33a2b045b57b8473fbe264043bf` |
| ONEPASS V2 | 12 957 582 | `ef1cf8262483879e47eee75d1cd81fab22f1be4e3109a1ea7966f1cc04a6f127` |

**Физически собран ZIP:** `NOX_WEB_WOW_V25_PC_UNIFIED_SOURCE_CANDIDATE.zip`, **76 185 778 байт**, SHA256 **`9556b5be3e8e9ce24eee7c6ae77a62ab8c8d58fe145568a35981565e14240145`**.

Внутри: 1 045 файлов `site/`, 10 оригинальных QA-скриптов ONEPASS V2, машинный `NOX_PHYSICAL_MERGE_RECEIPT.json`. Все 292 исходных WEB V25.1 сохранены: 290 рабочих файлов побайтово неизменны, первоначальные две страницы `chat.html` и `memory.html` неизменённо сохранены под `site/original_web_v25_1/`; входы теперь ведут в `site/pc/resonance.html` и `site/pc/memory.html`. Добавлены 743 файла **полного PC V25 web** и 7 отсутствовавших зависимостей V24; **32** различающихся исходных пути не перезаписывались, а безопасно развёрнуты под `site/pc/`. Проверенный в стороннем Excalidraw Firebase ключ обнулён для отсутствия скрытой облачной синхронизации.

**Реальный QA:** все 290 неизменяемых WEB-файлов прошли побайтовую сверку, 10 основных маршрутов на месте; 38 рабочих HTML-страниц дали **0 битых статических ссылок** (исторические шаблоны и резервные исходные HTML исключены как нерабочие маршруты); 18/18 HTTP-запросов на временном локальном сервере HTTP 200; 19 реальных HTML-кнопок в `pc/resonance.html`, 23 в `pc/memory.html` (их **нативная функция не проверена**). Тестируемый исходный PC сервер `nox_chat_server.py` содержит `WEB = os.path.join(ROOT, "web")` и `Handler._static`, принимающий вложенные пути, так что источники допускают один текущий сервер :8766, а не второй backend. Полная Windows/OneHost/S03/STOP/Ollama/GPU/E07 приёмка **не выполнена**.

**Где лежит физический архив** (приватный Vercel Sandbox, команда скачивания для владельца с аутентификацией Vercel):

```powershell
vercel --scope msttx sandbox cp "nox-web-wow-merge-20261112:/vercel/nox-merge/output_v3/NOX_WEB_WOW_V25_PC_UNIFIED_SOURCE_CANDIDATE.zip" "C:\NOX\incoming\NOX_WEB_WOW_V25_PC_UNIFIED_SOURCE_CANDIDATE.zip"
```

После скачивания подготовлен `APPLY_NOX_WEB_WOW_V25.ps1`: без аргументов проверяет SHA, оригинальный D02, текущий сервер 8766, S03 endpoints и распаковывает только в `C:\NOX\builds`; **лишь явное `-Apply`** осуществляет резервируемое переключение существующей WEB-папки на том же сервере, HTTP-readback и rollback при ошибке. Без этого локального запуска нельзя писать «установлено» или «готов EXE». Production/GPU/модели/память в ходе сборки не изменялись.

Исходный код физического слияния: `merge_physical_web_v25.py`, независимая проверка: `qa_physical_web_v25.py`, временный шаблон команд: `APPLY_NOX_WEB_WOW_V25.ps1`. Код и тесты — в [PR #251](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/251); итоговый ZIP в приватном Vercel Sandbox, а не в открытом GitHub.
