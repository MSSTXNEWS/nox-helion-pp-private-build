# NOX MASTER CATALOG — физическое дополнение №1–100 (12 ноября 2026)

## Состояние
Проверенные ZIP-источники каталога из предыдущей загрузки №1–100 сохранены в папке
Google Drive `NOX HELION EXPRESS INTEGRATOR / NOX MASTER CATALOG`.
Первоначальный отчёт 200 DOWNLOAD_REPORT.json фиксировал 182/200, это история, не финальный статус.

**Дополнительные реальные загрузки:**
- №32 — Qwen/Qwen3-Embedding-0.6B: полный HF снимок с весами, 15 ZIP-частей + манифест.
- №33 — Qwen/Qwen3-Reranker-0.6B: полный HF снимок с весами, 15 ZIP-частей + манифест.
- №70 — vectorize-io/hindsight: полный зафиксированный SHA снимок GitHub, 3 ZIP-части + манифест.
- №74 — joonspk-research/generative_agents: полный зафиксированный SHA снимок GitHub, 4 ZIP-части + манифест.
- №77 — cointegrated/rubert-tiny2-cedr-emotion-detection: полный HF снимок, 3 ZIP-части + манифест.
- №78 — UMUTeam/MarIA-emotion-es: полный HF снимок, 6 ZIP-частей + манифест.
- №6 OpenRouter Free — публичная выгрузка списка моделей в ZIP: **облачный API-сервис, не исходный код и не локальная модель**.

Исходные файлы были скачаны в GitHub Actions run 43234180775,
проверены на runner, затем разбиты в run 43236424633 на части по 80 МиБ.
Google Drive подтвердил хранение **52/52** частей и манифестов.
В каждом `..._MANIFEST.zip` лежит `PARTS_INDEX.json` c SHA256 отдельных
частей и полного исходного TAR.

## Как восстановить реальные архивы

1. Скачать **все** `NOX_CATALOG_032_*.zip`, `033`, `070`, `074`, `077`, `078` из одной папки.
2. Скачать `reassemble_catalog_completion.py` из этого репозитория / комплекта TOOLS.
3. Положить скачанные файлы и скрипт в одну локальную папку.
4. Проверить без сохранения: `python reassemble_catalog_completion.py .`
5. Восстановить TAR файлы: `python reassemble_catalog_completion.py . --assemble`
6. Распаковывать только после независимого аудита происхождения, лицензий и безопасности.

GitHub Actions артефакты по каждой части — реальные ZIP-файлы с байтами `pieceNN`.
Скрипт проверяет внутренние SHA256, длины, общую SHA256 после соединения.
Прежний `STAGING.zip` содержал только загрузчик и **не является исходниками**.

## Граница применения
Скачано / проверено / размещено на Drive ≠ установлено или интегрировано в NOX.
Не выполнялось изменение production NOX, обучения, S03, собственных весов,
checkpoints, процессов GPU. Распаковка и запуск внешнего кода не производится
автоматически. Pickle/torch `.bin` не следует безусловно загружать до аудита.

Каталог источников: https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/251
Папка Drive: https://drive.google.com/drive/folders/180zabWv3mn0tPI3k7BLgA2frf4zSRRjF
